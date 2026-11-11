"""AFK system — set yourself away and the bot replies to mentions."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_info, embed_success, human_timedelta


class AFK(commands.Cog):
    """AFK / away system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="afk", description="Mark yourself as AFK. The bot replies to your mentions.")
    @app_commands.describe(reason="Why you're AFK (optional)")
    @app_commands.guild_only()
    async def afk(self, interaction: discord.Interaction, reason: Optional[str] = None):
        await get_db().execute(
            "INSERT INTO afk_users (user_id, guild_id, reason) VALUES ($1,$2,$3) ON CONFLICT (user_id, guild_id) DO UPDATE SET reason=$3, since=NOW()",
            interaction.user.id, interaction.guild.id, reason or "AFK",
        )
        try:
            await interaction.user.edit(nick=f"[AFK] {interaction.user.display_name}"[:32])
        except (discord.Forbidden, discord.HTTPException):
            pass
        await interaction.response.send_message(embed=embed_success("You're AFK", f"I'll let people know you're away.\n**Reason:** {reason or 'AFK'}"))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        # clear AFK when the user types
        row = await get_db().fetchrow("SELECT since FROM afk_users WHERE user_id=$1 AND guild_id=$2", message.author.id, message.guild.id)
        if row:
            await get_db().execute("DELETE FROM afk_users WHERE user_id=$1 AND guild_id=$2", message.author.id, message.guild.id)
            try:
                nick = message.author.nick
                if nick and nick.startswith("[AFK] "):
                    await message.author.edit(nick=nick[6:])
            except (discord.Forbidden, discord.HTTPException):
                pass
            try:
                await message.reply(embed=embed_info("Welcome Back", f"You've been AFK for **{human_timedelta((dt.datetime.now(dt.UTC) - row['since'].replace(tzinfo=dt.UTC)).total_seconds())}**."), delete_after=10)
            except discord.HTTPException:
                pass
        # alert mentions
        for mentioned in message.mentions:
            if mentioned.id == message.author.id:
                continue
            afk = await get_db().fetchrow("SELECT reason, since FROM afk_users WHERE user_id=$1 AND guild_id=$2", mentioned.id, message.guild.id)
            if afk:
                try:
                    await message.reply(embed=embed_info("User is AFK", f"{mentioned.mention} is currently AFK.\n**Reason:** {afk['reason']}\n**Since:** <t:{int(afk['since'].timestamp())}:R>"), delete_after=15)
                except discord.HTTPException:
                    pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AFK(bot))
