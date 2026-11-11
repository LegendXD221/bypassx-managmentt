"""Automod — spam protection, word filter, link filter, mention spam, anti-raid."""
from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_info, embed_success, embed_warn, embed_error, is_admin, send_modlog

URL_REGEX = re.compile(r"https?://[^\s<>\"]+|www\.[^\s<>\"]+", re.IGNORECASE)
INVITE_REGEX = re.compile(r"(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+", re.IGNORECASE)


class SpamTracker:
    """Per-guild, per-user sliding window message tracker."""

    def __init__(self, *, max_messages: int = 6, window_seconds: int = 5):
        self.max_messages = max_messages
        self.window = window_seconds
        self.history: Dict[Tuple[int, int], Deque[float]] = defaultdict(lambda: deque(maxlen=max_messages))

    def hit(self, guild_id: int, user_id: int) -> tuple[bool, int]:
        """Record a message; return (is_spamming, count_in_window)."""
        now = asyncio.get_event_loop().time()
        key = (guild_id, user_id)
        dq = self.history[key]
        # purge old
        cutoff = now - self.window
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(now)
        return (len(dq) >= self.max_messages, len(dq))


class RaidShield:
    """Tracks member joins in a sliding window to detect raid patterns."""

    def __init__(self):
        self.recent_joins: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=200))

    def register_join(self, guild_id: int) -> tuple[bool, int]:
        now = asyncio.get_event_loop().time()
        dq = self.recent_joins[guild_id]
        cutoff = now - 30  # 30s window
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(now)
        return (len(dq) >= 10, len(dq))


class AutoMod(commands.Cog):
    """Real-time chat protection."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spam = SpamTracker(max_messages=6, window_seconds=5)
        self.raid = RaidShield()
        self._recently_punished: set[Tuple[int, int]] = set()
        self._lock = asyncio.Lock()

    # ---------------- listeners --------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        member = message.author
        if isinstance(member, discord.Member) and (member.guild_permissions.manage_messages or member.guild_permissions.administrator):
            return

        cfg = await get_db().get_guild_config(message.guild.id)
        if not cfg:
            return

        # ---- word filter
        if cfg["word_filter_enabled"]:
            await self._check_word_filter(message)

        # ---- link filter
        if cfg["link_filter_enabled"]:
            await self._check_link_filter(message)

        # ---- mention spam
        if message.mentions:
            await self._check_mention_spam(message, cfg)

        # ---- spam detection
        if cfg["anti_spam_enabled"]:
            await self._check_spam(message)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild is None:
            return
        cfg = await get_db().get_guild_config(member.guild.id)
        if not cfg or not cfg["anti_raid_enabled"]:
            return
        await self._check_raid(member)

    # ---------------- individual checks ------------------------------------

    async def _check_word_filter(self, message: discord.Message) -> None:
        rows = await get_db().fetch("SELECT word FROM filtered_words WHERE guild_id = $1", message.guild.id)
        if not rows:
            return
        banned = {r["word"].lower() for r in rows}
        content = message.content.lower()
        for word in banned:
            if word and word in content:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
                await self._punish(message, reason=f"Filtered word: `{word}`")
                await send_modlog(
                    message.guild,
                    action="automod • word-filter",
                    target=message.author,
                    details={"Channel": message.channel.mention, "Word": word},
                )
                return

    async def _check_link_filter(self, message: discord.Message) -> None:
        urls = URL_REGEX.findall(message.content)
        invites = INVITE_REGEX.findall(message.content)
        if not urls and not invites:
            return
        # Allow if member has manage_messages
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await self._punish(message, reason="Link/invite filter")
        await send_modlog(
            message.guild,
            action="automod • link-filter",
            target=message.author,
            details={"Channel": message.channel.mention, "Content": (message.content[:200] + "…") if len(message.content) > 200 else message.content},
        )

    async def _check_mention_spam(self, message: discord.Message, cfg) -> None:
        threshold = cfg["mention_spam_threshold"] or 5
        if len(message.mentions) < threshold:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await self._punish(message, reason=f"Mention spam ({len(message.mentions)} mentions)")
        await send_modlog(message.guild, action="automod • mention-spam", target=message.author, details={"Mentions": len(message.mentions)})

    async def _check_spam(self, message: discord.Message) -> None:
        is_spam, count = self.spam.hit(message.guild.id, message.author.id)
        if not is_spam:
            return
        async with self._lock:
            key = (message.guild.id, message.author.id)
            if key in self._recently_punished:
                return
            self._recently_punished.add(key)
            # auto-remove the cooldown lock after a short window
            asyncio.get_event_loop().call_later(8, lambda: self._recently_punished.discard(key))
        # delete recent messages by the user
        try:
            async for m in message.channel.history(limit=30):
                if m.author.id == message.author.id:
                    try:
                        await m.delete()
                    except discord.HTTPException:
                        pass
        except discord.HTTPException:
            pass
        await self._punish(message, reason=f"Spam ({count} messages in 5s)")
        await send_modlog(message.guild, action="automod • anti-spam", target=message.author, details={"Channel": message.channel.mention, "Messages": count})

    async def _punish(self, message: discord.Message, reason: str) -> None:
        """Apply progressive punishment: timeout first; if recurring, escalate."""
        member = message.author
        if not isinstance(member, discord.Member):
            return
        try:
            await member.timeout(discord.utils.utcnow() + dt.timedelta(minutes=10), reason=f"AutoMod: {reason}")
        except discord.Forbidden:
            # fall back to kick if we can't timeout
            try:
                await member.kick(reason=f"AutoMod: {reason}")
            except discord.HTTPException:
                pass
        try:
            await member.send(embed=embed_warn("AutoMod Action", f"Your message in **{message.guild.name}** was removed: {reason}"))
        except discord.HTTPException:
            pass

    async def _check_raid(self, member: discord.Member) -> None:
        is_raid, joins = self.raid.register_join(member.guild.id)
        # check new-account age protection too
        cfg_row = await get_db().fetchrow("SELECT * FROM anti_raid_config WHERE guild_id = $1", member.guild.id)
        new_acc_days = (cfg_row["new_account_days"] if cfg_row else 7) or 7
        action = (cfg_row["action"] if cfg_row else "kick") or "kick"
        threshold = (cfg_row["threshold"] if cfg_row else 5) or 5
        timeframe = (cfg_row["timeframe_seconds"] if cfg_row else 10) or 10

        # new account check
        if member.created_at > (discord.utils.utcnow() - dt.timedelta(days=new_acc_days)):
            await self._raid_action(member, action, reason=f"New account (<{new_acc_days}d)")
            await send_modlog(member.guild, action=f"anti-raid • new-account ({action})", target=member, details={"Account Age": member.created_at.isoformat()})
            return

        if is_raid or joins >= threshold:
            # mass join — flag every recent joiner? For safety we just kick this one.
            await self._raid_action(member, action, reason="Mass join raid shield")
            await send_modlog(member.guild, action=f"anti-raid • mass-join ({action})", target=member, details={"Joins": joins})

    async def _raid_action(self, member: discord.Member, action: str, reason: str) -> None:
        action = (action or "kick").lower()
        try:
            if action == "ban":
                await member.ban(reason=f"Anti-raid: {reason}", delete_message_days=1)
            elif action == "kick":
                await member.kick(reason=f"Anti-raid: {reason}")
            else:
                await member.timeout(discord.utils.utcnow() + dt.timedelta(minutes=30), reason=f"Anti-raid: {reason}")
        except discord.HTTPException:
            pass

    # ---------------- configuration commands --------------------------------

    group = app_commands.Group(name="automod", description="Configure AutoMod features.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="toggle", description="Enable/disable an AutoMod module.")
    @app_commands.describe(module="Module to toggle", enabled="True to enable, False to disable")
    @is_admin()
    async def toggle(self, interaction: discord.Interaction, module: str, enabled: bool):
        module = module.lower()
        mapping = {
            "spam": "anti_spam_enabled",
            "words": "word_filter_enabled",
            "links": "link_filter_enabled",
            "antiraid": "anti_raid_enabled",
        }
        if module not in mapping:
            await interaction.response.send_message(embed=embed_error("Invalid module.", f"Available: {', '.join(mapping)}"), ephemeral=True)
            return
        await get_db().set_guild_field(interaction.guild.id, mapping[module], enabled)
        await interaction.response.send_message(embed=embed_success("AutoMod Updated", f"`{module}` is now **{'enabled' if enabled else 'disabled'}**."))

    @group.command(name="status", description="Show current AutoMod status.")
    async def status(self, interaction: discord.Interaction):
        cfg = await get_db().get_guild_config(interaction.guild.id)
        embed = embed_info("AutoMod Status", "Current state of all modules.")
        embed.add_field(name="Spam Protection", value="✅ on" if cfg["anti_spam_enabled"] else "❌ off")
        embed.add_field(name="Word Filter", value="✅ on" if cfg["word_filter_enabled"] else "❌ off")
        embed.add_field(name="Link Filter", value="✅ on" if cfg["link_filter_enabled"] else "❌ off")
        embed.add_field(name="Anti-Raid", value="✅ on" if cfg["anti_raid_enabled"] else "❌ off")
        embed.add_field(name="Mention Threshold", value=str(cfg["mention_spam_threshold"] or 5))
        await interaction.response.send_message(embed=embed)

    @group.command(name="addword", description="Add a word to the filter list.")
    @app_commands.describe(word="Word or phrase to block")
    @is_admin()
    async def add_word(self, interaction: discord.Interaction, word: str):
        word = word.strip().lower()
        if not word:
            await interaction.response.send_message(embed=embed_error("Word cannot be empty."), ephemeral=True)
            return
        try:
            await get_db().execute("INSERT INTO filtered_words (guild_id, word) VALUES ($1,$2) ON CONFLICT DO NOTHING", interaction.guild.id, word)
        except Exception:
            pass
        await interaction.response.send_message(embed=embed_success("Word Added", f"`{word}` is now filtered."))

    @group.command(name="removeword", description="Remove a word from the filter list.")
    @is_admin()
    async def remove_word(self, interaction: discord.Interaction, word: str):
        await get_db().execute("DELETE FROM filtered_words WHERE guild_id = $1 AND word = $2", interaction.guild.id, word.strip().lower())
        await interaction.response.send_message(embed=embed_success("Word Removed", f"`{word}` is no longer filtered."))

    @group.command(name="listwords", description="List all filtered words.")
    async def list_words(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT word FROM filtered_words WHERE guild_id = $1 ORDER BY word", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Filtered Words", "Use `/automod addword` to add some."))
            return
        words = ", ".join(f"`{r['word']}`" for r in rows)
        await interaction.response.send_message(embed=embed_info("Filtered Words", words[:4000]))

    @group.command(name="mentionthreshold", description="Set how many mentions trigger AutoMod (default 5).")
    @app_commands.describe(threshold="Number of mentions (1-50)")
    @is_admin()
    async def mention_threshold(self, interaction: discord.Interaction, threshold: app_commands.Range[int, 1, 50]):
        await get_db().set_guild_field(interaction.guild.id, "mention_spam_threshold", threshold)
        await interaction.response.send_message(embed=embed_success("Updated", f"Mention threshold set to **{threshold}**."))

    @group.command(name="antiraidconfig", description="Configure anti-raid thresholds.")
    @app_commands.describe(threshold="Joins within timeframe to trigger", timeframe="Window in seconds", action="kick/ban/timeout", new_account_days="Reject accounts newer than N days")
    @is_admin()
    async def antiraid_config(self, interaction: discord.Interaction, threshold: app_commands.Range[int, 1, 100] = 5, timeframe: app_commands.Range[int, 5, 600] = 10, action: str = "kick", new_account_days: app_commands.Range[int, 0, 365] = 7):
        action = action.lower()
        if action not in {"kick", "ban", "timeout"}:
            await interaction.response.send_message(embed=embed_error("Action must be kick, ban, or timeout."), ephemeral=True)
            return
        await get_db().execute(
            """
            INSERT INTO anti_raid_config (guild_id, threshold, timeframe_seconds, action, new_account_days)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (guild_id) DO UPDATE SET threshold=$2, timeframe_seconds=$3, action=$4, new_account_days=$5
            """,
            interaction.guild.id, threshold, timeframe, action, new_account_days,
        )
        await get_db().set_guild_field(interaction.guild.id, "anti_raid_enabled", True)
        await interaction.response.send_message(
            embed=embed_success("Anti-Raid Configured", f"Threshold: **{threshold}** joins / **{timeframe}s**\nAction: **{action}**\nNew account cutoff: **{new_account_days} days**")
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
