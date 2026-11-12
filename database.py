"""Database layer for BypassX Management.

Uses asyncpg to connect to a Neon Postgres free-tier database. The schema is
initialised automatically on startup so the bot is self-bootstrapping.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable

import asyncpg

log = logging.getLogger("bypassx.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id BIGINT PRIMARY KEY,
    prefix TEXT DEFAULT 'bx!',
    log_channel_id BIGINT,
    mod_log_channel_id BIGINT,
    welcome_channel_id BIGINT,
    welcome_message TEXT,
    leave_message TEXT,
    auto_role_id BIGINT,
    mute_role_id BIGINT,
    verification_role_id BIGINT,
    ticket_category_id BIGINT,
    ticket_staff_role_id BIGINT,
    anti_raid_enabled BOOLEAN DEFAULT FALSE,
    anti_spam_enabled BOOLEAN DEFAULT TRUE,
    word_filter_enabled BOOLEAN DEFAULT TRUE,
    link_filter_enabled BOOLEAN DEFAULT FALSE,
    mention_spam_threshold INTEGER DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS warnings (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings(guild_id, user_id);

CREATE TABLE IF NOT EXISTS mutes (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    reason TEXT,
    expires_at TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mutes_active ON mutes(guild_id, user_id) WHERE active = TRUE;

CREATE TABLE IF NOT EXISTS reaction_roles (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    emoji TEXT NOT NULL,
    role_id BIGINT NOT NULL,
    UNIQUE(message_id, emoji)
);
CREATE INDEX IF NOT EXISTS idx_rr_guild ON reaction_roles(guild_id);

CREATE TABLE IF NOT EXISTS filtered_words (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    word TEXT NOT NULL,
    UNIQUE(guild_id, word)
);

CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    claimed_by BIGINT,
    closed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tickets_channel ON tickets(channel_id);

CREATE TABLE IF NOT EXISTS ticket_panels (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    title TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS reminders (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT,
    user_id BIGINT NOT NULL,
    channel_id BIGINT,
    message TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders(expires_at) WHERE completed = FALSE;

CREATE TABLE IF NOT EXISTS afk_users (
    user_id BIGINT,
    guild_id BIGINT,
    reason TEXT,
    since TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    owner_id BIGINT NOT NULL,
    uses INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS mod_logs (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_id BIGINT,
    moderator_id BIGINT,
    reason TEXT,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_modlogs_guild ON mod_logs(guild_id, created_at DESC);

CREATE TABLE IF NOT EXISTS verification_config (
    guild_id BIGINT PRIMARY KEY,
    role_id BIGINT NOT NULL,
    channel_id BIGINT,
    message_id BIGINT,
    verification_type TEXT DEFAULT 'button'
);

CREATE TABLE IF NOT EXISTS anti_raid_config (
    guild_id BIGINT PRIMARY KEY,
    threshold INTEGER DEFAULT 5,
    timeframe_seconds INTEGER DEFAULT 10,
    action TEXT DEFAULT 'kick',
    new_account_days INTEGER DEFAULT 7
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    user_id BIGINT,
    target_id BIGINT,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_guild ON audit_log(guild_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sticky_messages (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    content TEXT NOT NULL
);

-- ===== v2 expansion tables =====

CREATE TABLE IF NOT EXISTS starboard_config (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    threshold INTEGER DEFAULT 3,
    emoji TEXT DEFAULT 'star',
    enabled BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS starred_messages (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    source_channel_id BIGINT NOT NULL,
    starboard_message_id BIGINT,
    stars INTEGER DEFAULT 0,
    UNIQUE(guild_id, source_message_id)
);

CREATE TABLE IF NOT EXISTS giveaways (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    host_id BIGINT NOT NULL,
    prize TEXT NOT NULL,
    winners_count INTEGER DEFAULT 1,
    ends_at TIMESTAMPTZ NOT NULL,
    ended BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_giveaways_pending ON giveaways(ends_at) WHERE ended = FALSE;

CREATE TABLE IF NOT EXISTS giveaway_participants (
    giveaway_id BIGINT REFERENCES giveaways(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    PRIMARY KEY (giveaway_id, user_id)
);

CREATE TABLE IF NOT EXISTS user_xp (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    xp BIGINT DEFAULT 0,
    messages BIGINT DEFAULT 0,
    last_xp TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_xp_guild_rank ON user_xp(guild_id, xp DESC);

CREATE TABLE IF NOT EXISTS level_rewards (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    level INTEGER NOT NULL,
    role_id BIGINT NOT NULL,
    UNIQUE(guild_id, level)
);

CREATE TABLE IF NOT EXISTS level_config (
    guild_id BIGINT PRIMARY KEY,
    enabled BOOLEAN DEFAULT TRUE,
    announce_channel_id BIGINT,
    xp_per_message INTEGER DEFAULT 15,
    xp_cooldown_seconds INTEGER DEFAULT 60,
    stack_roles BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id BIGINT,
    guild_id BIGINT,
    bio TEXT,
    title TEXT,
    color INTEGER DEFAULT 5793266,
    badges TEXT[],
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS captcha_config (
    guild_id BIGINT PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE,
    role_id BIGINT,
    channel_id BIGINT,
    log_channel_id BIGINT,
    difficulty TEXT DEFAULT 'medium',
    kick_unverified_minutes INTEGER DEFAULT 0,
    verified_role_id BIGINT
);

CREATE TABLE IF NOT EXISTS captcha_pending (
    user_id BIGINT,
    guild_id BIGINT,
    answer TEXT NOT NULL,
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS auto_responses (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    trigger TEXT NOT NULL,
    response TEXT NOT NULL,
    match_type TEXT DEFAULT 'contains',
    created_by BIGINT,
    uses INTEGER DEFAULT 0,
    UNIQUE(guild_id, trigger)
);

CREATE TABLE IF NOT EXISTS server_stats (
    guild_id BIGINT PRIMARY KEY,
    members_channel_id BIGINT,
    humans_channel_id BIGINT,
    bots_channel_id BIGINT,
    channels_count_id BIGINT,
    roles_count_id BIGINT,
    boost_count_id BIGINT,
    online_count_id BIGINT
);

CREATE TABLE IF NOT EXISTS temp_voice_config (
    guild_id BIGINT PRIMARY KEY,
    category_id BIGINT,
    creator_channel_id BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS temp_voice_sessions (
    channel_id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    quoter_id BIGINT NOT NULL,
    author_id BIGINT,
    author_name TEXT,
    content TEXT NOT NULL,
    channel_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS role_persistence (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    role_ids BIGINT[],
    saved_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS birthdays (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL,
    announced_year INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS custom_commands (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    embed_color INTEGER DEFAULT 5793266,
    created_by BIGINT,
    uses INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS saved_embeds (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    title TEXT,
    description TEXT,
    color INTEGER DEFAULT 5793266,
    footer TEXT,
    image_url TEXT,
    thumbnail_url TEXT,
    author_name TEXT,
    created_by BIGINT,
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS guild_lockdown_state (
    guild_id BIGINT PRIMARY KEY,
    locked BOOLEAN DEFAULT FALSE,
    locked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS reaction_polls (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    question TEXT,
    options JSONB,
    ends_at TIMESTAMPTZ,
    ended BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS anti_nuke_whitelist (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    added_by BIGINT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS guild_join_leave_log (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    event TEXT NOT NULL,
    user_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nickname_history (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    old_nick TEXT,
    new_nick TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_nickhistory_user ON nickname_history(guild_id, user_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS scheduled_announcements (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    content TEXT,
    cron_expr TEXT,
    next_run TIMESTAMPTZ,
    last_run TIMESTAMPTZ,
    active BOOLEAN DEFAULT TRUE,
    created_by BIGINT
);

-- ===== v3 expansion tables =====

CREATE TABLE IF NOT EXISTS ticket_categories (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    panel_id BIGINT NOT NULL,
    label TEXT NOT NULL,
    description TEXT,
    emoji TEXT,
    category_id BIGINT,
    staff_role_id BIGINT,
    button_style TEXT DEFAULT 'secondary'
);

CREATE TABLE IF NOT EXISTS ticket_panels_v3 (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    title TEXT,
    description TEXT,
    color INTEGER DEFAULT 5793266,
    selection_type TEXT DEFAULT 'dropdown'
);

CREATE TABLE IF NOT EXISTS dropdown_role_panels (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    title TEXT,
    description TEXT,
    placeholder TEXT,
    min_values INTEGER DEFAULT 0,
    max_values INTEGER DEFAULT 25
);

CREATE TABLE IF NOT EXISTS dropdown_role_options (
    id SERIAL PRIMARY KEY,
    panel_id BIGINT REFERENCES dropdown_role_panels(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL,
    label TEXT NOT NULL,
    description TEXT,
    emoji TEXT
);

CREATE TABLE IF NOT EXISTS user_reputation (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    reputation INTEGER DEFAULT 0,
    last_thanked TIMESTAMPTZ,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS color_role_assignments (
    guild_id BIGINT PRIMARY KEY,
    template_role_id BIGINT NOT NULL,
    category_id BIGINT
);

CREATE TABLE IF NOT EXISTS user_color_roles (
    user_id BIGINT,
    guild_id BIGINT,
    role_id BIGINT NOT NULL,
    color INTEGER NOT NULL,
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS mod_notes (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_modnotes_user ON mod_notes(guild_id, user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS member_history (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    moderator_id BIGINT,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_member_history ON member_history(guild_id, user_id, created_at DESC);
"""

# tables that already existed in v1 but might need additional columns;
# these ALTERs are idempotent (DO NOTHING if column exists).
SCHEMA_ALTERS = """
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS anti_nuke_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS starboard_channel_id BIGINT;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS starboard_threshold INTEGER DEFAULT 3;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS levels_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS levels_announce_channel_id BIGINT;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS captcha_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS sticky_role_id BIGINT;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS role_persistence_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS birthday_channel_id BIGINT;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS birthday_role_id BIGINT;
"""


class Database:
    """Thin async wrapper around an asyncpg connection pool."""

    def __init__(self, dsn: str):
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
        # Strip parameters asyncpg doesn't natively understand (Neon's
        # channel_binding=require is enforced server-side regardless).
        try:
            from urllib.parse import urlparse, parse_qsl, urlencode
            parsed = urlparse(dsn)
            params = dict(parse_qsl(parsed.query))
            params.pop("channel_binding", None)
            cleaned_query = urlencode(params)
            dsn = parsed._replace(query=cleaned_query).geturl()
        except Exception:  # noqa: BLE001
            pass
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self, *, retries: int = 5, delay: float = 2.0) -> None:
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=self.dsn,
                    min_size=1,
                    max_size=10,
                    command_timeout=30,
                    ssl="require" if "sslmode=require" in self.dsn or "neon" in self.dsn else None,
                )
                if self.pool is None:
                    raise RuntimeError("asyncpg returned a None pool")
                log.info("Database connection pool established (attempt %d).", attempt)
                await self._init_schema()
                return
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                log.warning("DB connect attempt %d/%d failed: %s", attempt, retries, exc)
                await asyncio.sleep(delay)
        raise RuntimeError(f"Could not connect to database after {retries} attempts: {last_err}")

    async def _init_schema(self) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(SCHEMA)
            await conn.execute(SCHEMA_ALTERS)
        log.info("Database schema verified (v3 expansion applied).")

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            log.info("Database pool closed.")

    # ----- generic helpers -------------------------------------------------

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def executemany(self, query: str, args: Iterable[tuple]) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.executemany(query, list(args))

    # ----- guild config helpers -------------------------------------------

    async def ensure_guild(self, guild_id: int) -> None:
        await self.execute(
            "INSERT INTO guild_config (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING",
            guild_id,
        )

    async def get_guild_config(self, guild_id: int) -> asyncpg.Record | None:
        await self.ensure_guild(guild_id)
        return await self.fetchrow("SELECT * FROM guild_config WHERE guild_id = $1", guild_id)

    async def set_guild_field(self, guild_id: int, field: str, value: Any) -> None:
        await self.ensure_guild(guild_id)
        # field is only ever set from internal callers — never user input — but
        # we still validate against an allowlist to be safe.
        allowed = {
            "prefix", "log_channel_id", "mod_log_channel_id", "welcome_channel_id",
            "welcome_message", "leave_message", "auto_role_id", "mute_role_id",
            "verification_role_id", "ticket_category_id", "ticket_staff_role_id",
            "anti_raid_enabled", "anti_spam_enabled", "word_filter_enabled",
            "link_filter_enabled", "mention_spam_threshold",
        }
        if field not in allowed:
            raise ValueError(f"Refusing to set unknown guild config field: {field}")
        await self.execute(
            f"UPDATE guild_config SET {field} = $1 WHERE guild_id = $2", value, guild_id
        )


# Module-level singleton, populated by main.py on startup.
db: Database | None = None


def get_db() -> Database:
    if db is None:
        raise RuntimeError("Database has not been initialised. Call Database.connect first.")
    return db
