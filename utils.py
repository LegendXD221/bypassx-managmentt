"""Shared helpers used across all cogs: embeds, permission checks, formatting."""
from __future__ import annotations

import datetime as dt
import time
from typing import Any, Iterable

import discord
from discord import app_commands

ACCENT = 0x5865F2      # Discord blurple
SUCCESS = 0x57F287     # green
WARN = 0xFEE75C       # yellow
DANGER = 0xED4245      # red
INFO = 0x5865F2       # blurple


def embed_success(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=SUCCESS, timestamp=dt.datetime.now(dt.UTC))


def embed_info(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=INFO, timestamp=dt.datetime.now(dt.UTC))


def embed_warn(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=WARN, timestamp=dt.datetime.now(dt.UTC))


def embed_error(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=DANGER, timestamp=dt.datetime.now(dt.UTC))


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
        # plain seconds if all digits
        if text.isdigit():
            return int(text)
        return None
    if current:
        return None
    return total if total > 0 else None


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
    """Send a formatted moderation log embed to the guild's mod-log channel.

    Safe to call even if no mod-log channel is configured; it will silently skip.
    """
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

    embed = discord.Embed(title=f"Moderation • {action.title()}", color=color, timestamp=dt.datetime.now(dt.UTC))
    if target:
        embed.add_field(name="Target", value=f"{target.mention}\n{target} (`{target.id}`)", inline=False)
    if moderator:
        embed.add_field(name="Moderator", value=f"{moderator.mention}\n{moderator}", inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=True)
    if details:
        for k, v in details.items():
            embed.add_field(name=k.title(), value=str(v), inline=True)
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


def is_mod() -> app_commands.Command:
    """Decorator factory — usage: @is_mod() on a slash command.

    Checks that the invoker has manage_messages, kick_members, ban_members, or
    is the guild owner. Add as the first check.
    """
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
