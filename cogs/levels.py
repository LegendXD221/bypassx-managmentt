"""Leveling system — XP per message, level-up announcements, role rewards, leaderboard."""
from __future__ import annotations

import datetime as dt
import math
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import get_db
from utils import ACCENT, GOLD, embed_error, embed_info, embed_premium, embed_success, is_admin


def xp_for_level(level: int) -> int:
    """XP required to reach `level`."""
    return 5 * (level ** 2) + 50 * level + 100


def level_from_xp(xp: int) -> tuple[int, int]:
    """Return (level, xp_into_next_level)."""
    level = 0
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level, xp - xp_for_level(level)


def progress_bar(current: int, needed: int, width: int = 10) -> str:
    pct = min(1.0, current / needed if needed else 0)
    filled = int(pct * width)
    return "█" * filled + "░" * (width - filled)


class Levels(commands.Cog):
    """Premium leveling system — Sapphire/MEE6 inspired."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.xp_cooldown: dict[tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or message.content is None:
            return
        guild_id = message.guild.id
        user_id = message.author.id
        cfg = await get_db().fetchrow("SELECT * FROM level_config WHERE guild_id=$1", guild_id)
        if cfg is None:
            cfg_dict = {"enabled": True, "announce_channel_id": None, "xp_per_message": 15, "xp_cooldown_seconds": 60}
        elif not cfg["enabled"]:
            return
        else:
            cfg_dict = cfg
        # cooldown
        import time
        now = time.monotonic()
        last = self.xp_cooldown.get((guild_id, user_id), 0)
        if now - last < int(cfg_dict.get("xp_cooldown_seconds", 60) or 60):
            return
        self.xp_cooldown[(guild_id, user_id)] = now
        xp_gain = int(cfg_dict.get("xp_per_message", 15) or 15) + random.randint(0, 5)
        await get_db().execute(
            """
            INSERT INTO user_xp (guild_id, user_id, xp, messages, last_xp)
            VALUES ($1,$2,$3,1,NOW())
            ON CONFLICT (guild_id, user_id) DO UPDATE
            SET xp = user_xp.xp + EXCLUDED.xp,
                messages = user_xp.messages + 1,
                last_xp = NOW()
            """,
            guild_id, user_id, xp_gain,
        )
        # check for level-up
        row = await get_db().fetchrow("SELECT xp FROM user_xp WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)
        if not row:
            return
        level, _ = level_from_xp(int(row["xp"]))
        prev_level, _ = level_from_xp(int(row["xp"]) - xp_gain)
        if level > prev_level:
            await self._on_levelup(message.guild, message.author, level, cfg_dict)

    async def _on_levelup(self, guild: discord.Guild, member: discord.Member, level: int, cfg) -> None:
        # role rewards
        rewards = await get_db().fetch(
            "SELECT role_id FROM level_rewards WHERE guild_id=$1 AND level<=$2 ORDER BY level DESC",
            guild.id, level,
        )
        if rewards:
            stack = bool(cfg.get("stack_roles")) if cfg else False
            member_obj = member
            top_role = int(rewards[0]["role_id"])
            role = guild.get_role(top_role)
            if role and role < guild.me.top_role:
                try:
                    if not stack:
                        # remove lower rewards
                        for r in rewards[1:]:
                            lower = guild.get_role(int(r["role_id"]))
                            if lower and lower in member_obj.roles:
                                await member_obj.remove_roles(lower, reason="Level reward upgrade")
                    if role not in member_obj.roles:
                        await member_obj.add_roles(role, reason=f"Reached level {level}")
                except discord.HTTPException:
                    pass
        # announce
        announce_channel_id = cfg.get("announce_channel_id") if cfg else None
        if announce_channel_id:
            ch = guild.get_channel(int(announce_channel_id))
            if ch:
                try:
                    embed = embed_premium("Level Up", f"{member.mention} reached **level {level}** ✦")
                    await ch.send(content=member.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
                except discord.HTTPException:
                    pass

    # ---------------- commands ----------------------------------------------

    group = app_commands.Group(name="rank", description="View your XP and level.", default_permissions=None)

    @group.command(name="view", description="Show your rank card.")
    @app_commands.describe(member="Member (defaults to you)")
    async def rank_view(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(embed=embed_error("Invalid member."), ephemeral=True)
            return
        row = await get_db().fetchrow("SELECT xp, messages FROM user_xp WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        xp = int(row["xp"]) if row else 0
        messages = int(row["messages"]) if row else 0
        level, into_next = level_from_xp(xp)
        next_total = xp_for_level(level + 1)
        needed = next_total - xp_for_level(level)
        # rank
        rank = await get_db().fetchval(
            "SELECT COUNT(*)+1 FROM user_xp WHERE guild_id=$1 AND xp > $2",
            interaction.guild.id, xp,
        )
        embed = discord.Embed(title=f"✦  {member}", color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="Rank", value=f"**#{rank}**", inline=True)
        embed.add_field(name="Messages", value=str(messages), inline=True)
        embed.add_field(name="XP", value=f"{into_next} / {needed}", inline=True)
        embed.add_field(name="Progress", value=f"`{progress_bar(into_next, needed)}`", inline=False)
        embed.add_field(name="Total XP", value=str(xp), inline=True)
        embed.set_footer(text="BypassX · Levels")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Show the top-ranked members in this server.")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = await get_db().fetch(
            "SELECT user_id, xp, messages FROM user_xp WHERE guild_id=$1 ORDER BY xp DESC LIMIT 10",
            interaction.guild.id,
        )
        if not rows:
            await interaction.followup.send(embed=embed_info("Empty Leaderboard", "No one has earned XP yet."))
            return
        embed = embed_premium(f"Leaderboard — {interaction.guild.name}", "Top members by XP:")
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows):
            medal = medals[i] if i < 3 else f"`#{i+1}`"
            member = interaction.guild.get_member(int(r["user_id"]))
            name = member.mention if member else f"`{r['user_id']}`"
            level, _ = level_from_xp(int(r["xp"]))
            embed.add_field(name=f"{medal}  {name}", value=f"Level **{level}** · {int(r['xp']):,} XP · {int(r['messages']):,} msgs", inline=False)
        await interaction.followup.send(embed=embed)

    config = app_commands.Group(name="levels", description="Configure the leveling system.", default_permissions=discord.Permissions(manage_guild=True))

    @config.command(name="toggle", description="Enable or disable XP gain in this server.")
    @is_admin()
    async def toggle(self, interaction: discord.Interaction, enabled: bool):
        await get_db().execute(
            """
            INSERT INTO level_config (guild_id, enabled) VALUES ($1,$2)
            ON CONFLICT (guild_id) DO UPDATE SET enabled=$2
            """,
            interaction.guild.id, enabled,
        )
        await interaction.response.send_message(embed=embed_success("Levels Updated", f"Leveling is now **{'enabled' if enabled else 'disabled'}**."))

    @config.command(name="channel", description="Set the channel where level-up messages are sent.")
    @is_admin()
    async def channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await get_db().execute(
            """
            INSERT INTO level_config (guild_id, announce_channel_id) VALUES ($1,$2)
            ON CONFLICT (guild_id) DO UPDATE SET announce_channel_id=$2
            """,
            interaction.guild.id, channel.id,
        )
        await interaction.response.send_message(embed=embed_success("Announce Channel Set", f"Level-up messages will go to {channel.mention}."))

    @config.command(name="reward", description="Add a role reward for reaching a level.")
    @is_admin()
    async def reward(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 500], role: discord.Role):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("That role is above me."), ephemeral=True)
            return
        await get_db().execute(
            "INSERT INTO level_rewards (guild_id, level, role_id) VALUES ($1,$2,$3) ON CONFLICT (guild_id, level) DO UPDATE SET role_id=$3",
            interaction.guild.id, level, role.id,
        )
        await interaction.response.send_message(embed=embed_success("Reward Added", f"Reaching level **{level}** now grants {role.mention}."))

    @config.command(name="rewards", description="List all level rewards.")
    async def list_rewards(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT level, role_id FROM level_rewards WHERE guild_id=$1 ORDER BY level", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Rewards", "No level rewards configured."))
            return
        embed = embed_premium("Level Rewards")
        for r in rows:
            role = interaction.guild.get_role(int(r["role_id"]))
            embed.add_field(name=f"Level {r['level']}", value=role.mention if role else "missing", inline=True)
        await interaction.response.send_message(embed=embed)

    @config.command(name="reset", description="Reset a member's XP (or everyone's).")
    @is_admin()
    async def reset(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if member:
            await get_db().execute("DELETE FROM user_xp WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
            await interaction.response.send_message(embed=embed_success("Reset", f"Cleared XP for {member.mention}."))
        else:
            await get_db().execute("DELETE FROM user_xp WHERE guild_id=$1", interaction.guild.id)
            await interaction.response.send_message(embed=embed_success("Reset", "Cleared XP for **everyone** in this server."))

    # ---------- reputation (folded in v4) ----------

    rep = app_commands.Group(name="rep", description="Reputation commands.", default_permissions=None)

    @rep.command(name="view", description="View a member's reputation.")
    async def rep_view(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        rep_val = await get_db().fetchval("SELECT reputation FROM user_reputation WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        rep_val = rep_val or 0
        embed = embed_premium(f"Reputation — {member}", f"★ **{rep_val}** reputation points")
        await interaction.response.send_message(embed=embed)

    @rep.command(name="leaderboard", description="Show the top reputed members.")
    async def rep_leaderboard(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT user_id, reputation FROM user_reputation WHERE guild_id=$1 ORDER BY reputation DESC LIMIT 10", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("Empty", "No reputation given yet."))
            return
        embed = embed_premium("Reputation Leaderboard")
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows[:10]):
            medal = medals[i] if i < 3 else f"`#{i+1}`"
            m = interaction.guild.get_member(int(r["user_id"]))
            name = m.mention if m else f"`{r['user_id']}`"
            embed.add_field(name=f"{medal}  {name}", value=f"★ **{r['reputation']}**", inline=False)
        await interaction.response.send_message(embed=embed)

    @rep.command(name="give", description="Manually give reputation (admin).")
    @app_commands.default_permissions(manage_guild=True)
    async def rep_give(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, -100, 100] = 1):
        if member.bot:
            await interaction.response.send_message(embed=embed_error("Can't give rep to a bot."), ephemeral=True)
            return
        await get_db().execute(
            """
            INSERT INTO user_reputation (guild_id, user_id, reputation)
            VALUES ($1,$2,$3)
            ON CONFLICT (guild_id, user_id) DO UPDATE
            SET reputation = GREATEST(0, user_reputation.reputation + $3)
            """,
            interaction.guild.id, member.id, amount,
        )
        rep_val = await get_db().fetchval("SELECT reputation FROM user_reputation WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed_success("Reputation Updated", f"{member.mention} now has **{rep_val}** rep (Δ {amount:+d})."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Levels(bot))
