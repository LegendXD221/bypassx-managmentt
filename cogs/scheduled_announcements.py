"""Scheduled announcements — fire messages on a fixed interval (every N hours/days)."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import get_db
from utils import embed_error, embed_info, embed_premium, embed_success, human_timedelta, is_admin, parse_duration


class ScheduledAnnouncements(commands.Cog):
    """Schedule messages to fire at regular intervals."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop.start()

    @tasks.loop(minutes=1)
    async def loop(self) -> None:
        rows = await get_db().fetch(
            "SELECT id, guild_id, channel_id, content FROM scheduled_announcements WHERE active=TRUE AND next_run IS NOT NULL AND next_run <= NOW() LIMIT 25"
        )
        for row in rows:
            guild = self.bot.get_guild(int(row["guild_id"]))
            if guild is None:
                continue
            channel = guild.get_channel(int(row["channel_id"]))
            if channel is None:
                continue
            try:
                await channel.send(embed=embed_premium("Scheduled Announcement", row["content"]))
            except discord.HTTPException:
                pass
            # parse cron_expr like every-Nh to compute next run
            next_run = self._compute_next(row["cron_expr"])
            await get_db().execute(
                "UPDATE scheduled_announcements SET last_run=NOW(), next_run=$1 WHERE id=$2",
                next_run, row["id"],
            )

    @loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    def _compute_next(self, expr: Optional[str]) -> dt.datetime:
        """Parse simple interval expressions like 'every-6h' or 'every-1d'."""
        if not expr:
            return discord.utils.utcnow() + dt.timedelta(hours=24)
        seconds = parse_duration(expr.replace("every-", "")) if expr.startswith("every-") else None
        if seconds is None:
            seconds = 24 * 3600  # default daily
        return discord.utils.utcnow() + dt.timedelta(seconds=seconds)

    group = app_commands.Group(name="schedule", description="Schedule recurring announcements.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="add", description="Schedule a recurring message (e.g. every-6h, every-1d).")
    @is_admin()
    async def add(self, interaction: discord.Interaction, channel: discord.TextChannel, interval: str, content: str):
        if not interval.startswith("every-"):
            await interaction.response.send_message(embed=embed_error("Interval must start with `every-`, e.g. `every-6h`, `every-1d`."), ephemeral=True)
            return
        seconds = parse_duration(interval.replace("every-", ""))
        if seconds is None or seconds < 300:
            await interaction.response.send_message(embed=embed_error("Invalid interval. Use formats like `every-6h`, `every-30m`. Min 5m."), ephemeral=True)
            return
        next_run = self._compute_next(interval)
        await get_db().execute(
            "INSERT INTO scheduled_announcements (guild_id, channel_id, content, cron_expr, next_run, created_by) VALUES ($1,$2,$3,$4,$5,$6)",
            interaction.guild.id, channel.id, content, interval, next_run, interaction.user.id,
        )
        await interaction.response.send_message(embed=embed_success("Scheduled", f"Message will post every **{human_timedelta(seconds)}** in {channel.mention}.\nFirst run: <t:{int(next_run.timestamp())}:R>"))

    @group.command(name="list", description="List all scheduled announcements.")
    async def list(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT id, channel_id, content, cron_expr, next_run, active FROM scheduled_announcements WHERE guild_id=$1 ORDER BY id", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Scheduled Messages", "None yet."))
            return
        embed = embed_premium("Scheduled Announcements", f"**{len(rows)}** scheduled:")
        for r in rows[:15]:
            status = "✓" if r["active"] else "✕"
            embed.add_field(name=f"{status} #{r['id']} — {r['cron_expr']}", value=f"Channel: <#{r['channel_id']}>\nNext: <t:{int(r['next_run'].timestamp())}:R>\nContent: {r['content'][:100]}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="remove", description="Remove a scheduled announcement by ID.")
    @is_admin()
    async def remove(self, interaction: discord.Interaction, announcement_id: int):
        await get_db().execute("DELETE FROM scheduled_announcements WHERE id=$1 AND guild_id=$2", announcement_id, interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Removed", f"Scheduled message #{announcement_id} deleted."))

    @group.command(name="pause", description="Pause a scheduled announcement.")
    @is_admin()
    async def pause(self, interaction: discord.Interaction, announcement_id: int):
        await get_db().execute("UPDATE scheduled_announcements SET active=FALSE WHERE id=$1 AND guild_id=$2", announcement_id, interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Paused", f"Scheduled message #{announcement_id} paused."))

    @group.command(name="resume", description="Resume a paused scheduled announcement.")
    @is_admin()
    async def resume(self, interaction: discord.Interaction, announcement_id: int):
        await get_db().execute("UPDATE scheduled_announcements SET active=TRUE WHERE id=$1 AND guild_id=$2", announcement_id, interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Resumed", f"Scheduled message #{announcement_id} resumed."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ScheduledAnnouncements(bot))
