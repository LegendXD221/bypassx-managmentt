"""Shared helpers used across all cogs.

Premium, minimal, aesthetic design system:
  • Refined palette (deep indigo primary, gold accent, soft success/danger)
  • Consistent footer on every embed
  • Tasteful glyphs (no emoji soup)
  • Clean inline fields
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Any, Iterable

import discord
from discord import app_commands

# ---------- Premium palette --------------------------------------------------
ACCENT   = 0x6366F1   # indigo-500 — primary
GOLD     = 0xF5B544   # muted gold — premium accent
SUCCESS  = 0x10B981   # emerald
WARN     = 0xF59E0B   # amber
DANGER   = 0xE11D48   # rose
INFO     = 0x6366F1   # indigo
NEUTRAL  = 0x94A3B8   # slate
INK      = 0x0B0F19   # near-black for embed sidebars (Discord auto-dims)

FOOTER_TEXT = "BypassX Management"
FOOTER_ICON = ""  # optional: set to a CDN URL for a branded mark

# ---------- Embed factory ----------------------------------------------------

def _stamp() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _apply_footer(embed: discord.Embed) -> discord.Embed:
    embed.set_footer(text=FOOTER_TEXT, icon_url=FOOTER_ICON or None)
    return embed


def embed_success(title: str, description: str = "") -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=SUCCESS, timestamp=_stamp())
    return _apply_footer(e)


def embed_info(title: str, description: str = "") -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=INFO, timestamp=_stamp())
    return _apply_footer(e)


def embed_warn(title: str, description: str = "") -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=WARN, timestamp=_stamp())
    return _apply_footer(e)


def embed_error(title: str, description: str = "") -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=DANGER, timestamp=_stamp())
    return _apply_footer(e)


def embed_premium(title: str, description: str = "") -> discord.Embed:
    """Premium-styled embed — indigo with gold accent in the footer."""
    e = discord.Embed(title=title, description=description, color=ACCENT, timestamp=_stamp())
    e.set_footer(text=f"{FOOTER_TEXT}  •  Premium", icon_url=FOOTER_ICON or None)
    return e


def embed_field(embed: discord.Embed, name: str, value: Any, inline: bool = True) -> discord.Embed:
    """Add a clean field; blank values are replaced with an em dash."""
    embed.add_field(name=name, value=(str(value) if value not in (None, "") else "—"), inline=inline)
    return embed


def divider(embed: discord.Embed) -> discord.Embed:
    """Add an invisible divider field to break up content."""
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    return embed


# ---------- Time helpers -----------------------------------------------------

def human_timedelta(seconds: float) -> str:
    """Return a short human readable duration like '2h 5m'."""
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if sec and not days and not hours:
        parts.append(f"{sec}s")
    return " ".join(parts) or "0s"


def parse_duration(text: str) -> int | None:
    """Parse strings like '1h30m', '2d', '15m', '600s' into seconds."""
    if not text:
        return None
    text = text.strip().lower()
    total = 0
    current = ""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    matched_any = False
    for ch in text:
        if ch.isdigit():
            current += ch
        elif ch in units and current:
            total += int(current) * units[ch]
            current = ""
            matched_any = True
        else:
            return None
    if not matched_any:
        if text.isdigit():
            return int(text)
        return None
    if current:
        return None
    return total if total > 0 else None


def format_number(n: int | float) -> str:
    """Format a number with thousands separators."""
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


# ---------- Modlog -----------------------------------------------------------

async def send_modlog(
    guild: discord.Guild,
    *,
    action: str,
    target: discord.abc.User | None = None,
    moderator: discord.abc.User | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
    color: int = ACCENT,
) -> None:
    """Send a formatted moderation log embed to the guild's mod-log channel."""
    from database import get_db

    try:
        cfg = await get_db().get_guild_config(guild.id)
    except Exception:  # noqa: BLE001
        return
    channel_id = (cfg or {}).get("mod_log_channel_id") if cfg else None
    if not channel_id:
        channel_id = (cfg or {}).get("log_channel_id") if cfg else None
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if channel is None or not isinstance(channel, discord.TextChannel):
        return

    embed = discord.Embed(title=f"Moderation · {action.title()}", color=color, timestamp=_stamp())
    embed.set_footer(text=f"{FOOTER_TEXT} · mod-log")
    if target:
        embed.add_field(name="Target", value=f"{target.mention}\n{target} · `{target.id}`", inline=False)
    if moderator:
        embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=True)
    if details:
        for k, v in details.items():
            embed.add_field(name=k.title(), value=str(v), inline=True)
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


# ---------- Permission checks ------------------------------------------------

def is_mod():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.NoPrivateMessage("This command can only be used in a server.")
        member = interaction.user
        if not isinstance(member, discord.Member):
            return False
        if member.guild.owner_id == member.id:
            return True
        perms = member.guild_permissions
        return perms.manage_guild or perms.kick_members or perms.ban_members or perms.manage_messages
    return app_commands.check(predicate)


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.NoPrivateMessage("This command can only be used in a server.")
        member = interaction.user
        if not isinstance(member, discord.Member):
            return False
        if member.guild.owner_id == member.id:
            return True
        return member.guild_permissions.manage_guild
    return app_commands.check(predicate)


def is_owner():
    """Use on app_commands that only the bot owner may run."""
    from config import config
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == config.owner_id
    return app_commands.check(predicate)


# ---------- Misc helpers -----------------------------------------------------

def chunk(seq: Iterable[Any], size: int) -> list[list[Any]]:
    out: list[list[Any]] = []
    cur: list[Any] = []
    for item in seq:
        cur.append(item)
        if len(cur) >= size:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def start_timer() -> float:
    return time.monotonic()


def elapsed_since(t0: float) -> float:
    return time.monotonic() - t0


# ---------- Premium UI strings ----------------------------------------------

GLYPHS = {
    "success": "✓",
    "error":   "✕",
    "warn":    "!",
    "info":    "i",
    "star":    "★",
    "diamond": "◆",
    "arrow":   "→",
    "bullet":  "•",
    "dot":     "·",
    "shield":  "🛡",
    "crown":   "♔",
    "spark":   "✦",
}
