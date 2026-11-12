"""Reputation — thank members for helpful contributions."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import GOLD, ACCENT, embed_error, embed_info, embed_premium, embed_success


class Reputation(commands.Cog):
    """Lightweight reputation system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldowns: dict[tuple[int, int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        content = message.content.lower().strip()
        if not (content.startswith("thanks ") or content.startswith("thank ") or content.startswith("thx ")):
            return
        if not message.mentions:
            return
        import time
        for mentioned in message.mentions:
            if mentioned.id == message.author.id or mentioned.bot:
                continue
            key = (message.guild.id, message.author.id, mentioned.id)
            now = time.monotonic()
            if now - self.cooldowns.get(key, 0) < 3600:  # 1h cooldown per pair
                continue
            self.cooldowns[key] = now
            await get_db().execute(
                """
                INSERT INTO user_reputation (guild_id, user_id, reputation, last_thanked)
                VALUES ($1,$2,1,NOW())
                ON CONFLICT (guild_id, user_id) DO UPDATE
                SET reputation = user_reputation.reputation + 1, last_thanked = NOW()
                """,
                message.guild.id, mentioned.id,
            )

    group = app_commands.Group(name="rep", description="Reputation commands.", default_permissions=None)

    @group.command(name="view", description="View a member's reputation.")
    async def view(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        rep = await get_db().fetchval("SELECT reputation FROM user_reputation WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        rep = rep or 0
        embed = embed_premium(f"Reputation — {member}", f"★ **{rep}** reputation points")
        await interaction.response.send_message(embed=embed)

    @group.command(name="leaderboard", description="Show the top reputed members.")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT user_id, reputation FROM user_reputation WHERE guild_id=$1 ORDER BY reputation DESC LIMIT 10", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("Empty", "No reputation given yet."))
            return
        embed = embed_premium("Reputation Leaderboard")
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows[:10]):
            medal = medals[i] if i < 3 else f"`#{i+1}`"
            member = interaction.guild.get_member(int(r["user_id"]))
            name = member.mention if member else f"`{r['user_id']}`"
            embed.add_field(name=f"{medal}  {name}", value=f"★ **{r['reputation']}**", inline=False)
        await interaction.response.send_message(embed=embed)

    @group.command(name="give", description="Manually give reputation to a member (admin).")
    @app_commands.default_permissions(manage_guild=True)
    async def give(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, -100, 100] = 1):
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
        rep = await get_db().fetchval("SELECT reputation FROM user_reputation WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed_success("Reputation Updated", f"{member.mention} now has **{rep}** rep (Δ {amount:+d})."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reputation(bot))
