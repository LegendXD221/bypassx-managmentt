"""Birthdays — track member birthdays and announce them."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import get_db
from utils import GOLD, embed_error, embed_info, embed_premium, embed_success, is_admin


class Birthdays(commands.Cog):
    """Birthday tracking and announcements."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.birthday_loop.start()

    @tasks.loop(minutes=30)
    async def birthday_loop(self) -> None:
        today = discord.utils.utcnow()
        rows = await get_db().fetch(
            "SELECT b.guild_id, b.user_id, b.month, b.day FROM birthdays b WHERE b.month=$1 AND b.day=$2 AND (b.announced_year IS NULL OR b.announced_year <> $3)",
            today.month, today.day, today.year,
        )
        for row in rows:
            guild = self.bot.get_guild(int(row["guild_id"]))
            if guild is None:
                continue
            cfg = await get_db().get_guild_config(guild.id)
            channel_id = cfg.get("birthday_channel_id") if cfg else None
            role_id = cfg.get("birthday_role_id") if cfg else None
            member = guild.get_member(int(row["user_id"]))
            if member:
                if channel_id:
                    ch = guild.get_channel(int(channel_id))
                    if ch and isinstance(ch, discord.TextChannel):
                        embed = embed_premium("🎂 Happy Birthday!", f"Today is {member.mention}'s birthday! Wish them well.")
                        try:
                            await ch.send(content=member.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
                        except discord.HTTPException:
                            pass
                if role_id:
                    role = guild.get_role(int(role_id))
                    if role and role < guild.me.top_role:
                        try:
                            await member.add_roles(role, reason="Birthday role")
                        except discord.HTTPException:
                            pass
            await get_db().execute("UPDATE birthdays SET announced_year=$1 WHERE guild_id=$2 AND user_id=$3", today.year, row["guild_id"], row["user_id"])

    @birthday_loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    group = app_commands.Group(name="birthday", description="Birthday commands.", default_permissions=None)

    @group.command(name="set", description="Set your birthday (month and day).")
    @app_commands.describe(month="Month (1-12)", day="Day (1-31)")
    async def set_birthday(self, interaction: discord.Interaction, month: app_commands.Range[int, 1, 12], day: app_commands.Range[int, 1, 31]):
        try:
            dt.date(2024, month, day)  # validate
        except ValueError:
            await interaction.response.send_message(embed=embed_error("Invalid date."), ephemeral=True)
            return
        await get_db().execute(
            "INSERT INTO birthdays (guild_id, user_id, month, day) VALUES ($1,$2,$3,$4) ON CONFLICT (guild_id, user_id) DO UPDATE SET month=$3, day=$4, announced_year=NULL",
            interaction.guild.id, interaction.user.id, month, day,
        )
        await interaction.response.send_message(embed=embed_success("Birthday Saved", f"Your birthday is **{month}/{day}**. I'll announce it!"))

    @group.command(name="view", description="View a member's birthday.")
    async def view(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        row = await get_db().fetchrow("SELECT month, day FROM birthdays WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        if not row:
            await interaction.response.send_message(embed=embed_info("No Birthday", f"{member.mention} hasn't set a birthday."))
            return
        embed = embed_premium("🎂 Birthday", f"{member.mention}'s birthday is **{row['month']}/{row['day']}**")
        await interaction.response.send_message(embed=embed)

    @group.command(name="upcoming", description="Show upcoming birthdays.")
    async def upcoming(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT user_id, month, day FROM birthdays WHERE guild_id=$1 ORDER BY month, day", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Birthdays", "No one has set a birthday yet."))
            return
        embed = embed_premium("Upcoming Birthdays")
        for r in rows[:15]:
            member = interaction.guild.get_member(int(r["user_id"]))
            name = member.mention if member else f"`{r['user_id']}`"
            embed.add_field(name=f"{r['month']}/{r['day']}", value=name, inline=True)
        await interaction.response.send_message(embed=embed)

    @group.command(name="remove", description="Remove your birthday.")
    async def remove(self, interaction: discord.Interaction):
        await get_db().execute("DELETE FROM birthdays WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(embed=embed_success("Removed", "Your birthday has been deleted."))

    config = app_commands.Group(name="birthdays", description="Configure birthday announcements.", default_permissions=discord.Permissions(manage_guild=True))

    @config.command(name="channel", description="Set the birthday announcement channel.")
    @is_admin()
    async def channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await get_db().set_guild_field(interaction.guild.id, "birthday_channel_id", channel.id)
        await interaction.response.send_message(embed=embed_success("Birthday Channel Set", f"Announcements go to {channel.mention}."))

    @config.command(name="role", description="Set the temporary birthday role.")
    @is_admin()
    async def role(self, interaction: discord.Interaction, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("That role is above me."), ephemeral=True)
            return
        await get_db().set_guild_field(interaction.guild.id, "birthday_role_id", role.id)
        await interaction.response.send_message(embed=embed_success("Birthday Role Set", f"On their birthday, members will get {role.mention}."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Birthdays(bot))
