"""Reminders — schedule personal or channel reminders."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_success, human_timedelta, parse_duration


async def fire_due_reminders(bot: commands.Bot) -> None:
    rows = await get_db().fetch(
        "SELECT id, user_id, channel_id, message, guild_id FROM reminders WHERE completed=FALSE AND expires_at <= NOW() LIMIT 50"
    )
    for row in rows:
        user = bot.get_user(int(row["user_id"])) or await bot.fetch_user(int(row["user_id"]))
        message_text = row["message"]
        try:
            if row["channel_id"]:
                channel = bot.get_channel(int(row["channel_id"]))
                if channel:
                    await channel.send(content=f"<@{row['user_id']}>", embed=discord.Embed(title="⏰ Reminder", description=message_text, color=0x5865F2))
                else:
                    await user.send(embed=discord.Embed(title="⏰ Reminder", description=message_text, color=0x5865F2))
            else:
                await user.send(embed=discord.Embed(title="⏰ Reminder", description=message_text, color=0x5865F2))
        except discord.HTTPException:
            pass
        await get_db().execute("UPDATE reminders SET completed=TRUE WHERE id=$1", row["id"])


class Reminders(commands.Cog):
    """Reminder commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="remind", description="Set a reminder. The bot will ping you when it's time.")
    @app_commands.describe(duration="How long from now (e.g. 1h30m, 2d, 15m)", message="What to remind you about")
    async def remind(self, interaction: discord.Interaction, duration: str, message: str):
        seconds = parse_duration(duration)
        if seconds is None or seconds < 30:
            await interaction.response.send_message(embed=embed_error("Invalid duration. Use formats like `15m`, `1h30m`, `2d`. Minimum 30s."), ephemeral=True)
            return
        expires_at = discord.utils.utcnow() + dt.timedelta(seconds=seconds)
        await get_db().execute(
            "INSERT INTO reminders (guild_id, user_id, channel_id, message, expires_at) VALUES ($1,$2,$3,$4,$5)",
            interaction.guild.id if interaction.guild else None, interaction.user.id, interaction.channel.id if interaction.channel else None, message, expires_at,
        )
        await interaction.response.send_message(
            embed=embed_success("Reminder Set", f"I'll remind you in **{human_timedelta(seconds)}** (<t:{int(expires_at.timestamp())}:R>).\n**Message:** {message}")
        )

    @app_commands.command(name="reminders", description="List your pending reminders.")
    async def list_reminders(self, interaction: discord.Interaction):
        rows = await get_db().fetch(
            "SELECT id, message, expires_at FROM reminders WHERE user_id=$1 AND completed=FALSE ORDER BY expires_at LIMIT 20",
            interaction.user.id,
        )
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Reminders", "You have no pending reminders."))
            return
        embed = embed_info("Your Reminders", f"You have **{len(rows)}** pending reminder(s).")
        for i, r in enumerate(rows, 1):
            embed.add_field(
                name=f"#{i} • <t:{int(r['expires_at'].timestamp())}:R>",
                value=r["message"][:200],
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="cancelreminder", description="Cancel all your pending reminders.")
    async def cancel_reminders(self, interaction: discord.Interaction):
        n = await get_db().fetchval("SELECT COUNT(*) FROM reminders WHERE user_id=$1 AND completed=FALSE", interaction.user.id)
        await get_db().execute("UPDATE reminders SET completed=TRUE WHERE user_id=$1 AND completed=FALSE", interaction.user.id)
        await interaction.response.send_message(embed=embed_success("Reminders Cleared", f"Cleared **{n}** pending reminder(s)."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reminders(bot))
