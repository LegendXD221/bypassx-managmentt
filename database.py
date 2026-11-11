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
"""


class Database:
    """Thin async wrapper around an asyncpg connection pool."""

    def __init__(self, dsn: str):
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
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
        log.info("Database schema verified.")

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
