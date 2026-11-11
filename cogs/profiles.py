"""User profiles — bio, title, color, badges. View with /profile."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import ACCENT, GOLD, embed_error, embed_info, embed_premium, embed_success

PRESET_BADGES = {
    "developer": ("⚙", "Bot Developer"),
    "staff": ("🛡", "Server Staff"),
    "booster": ("💎", "Server Booster"),
    "vip": ("★", "VIP Member"),
    "early": ("✦", "Early Supporter"),
    "verified": ("✓", "Verified"),
}


class Profiles(commands.Cog):
    """Premium user profiles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="profile", description="Customisable user profiles.", default_permissions=None)

    @group.command(name="view", description="View a member's profile.")
    async def view(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        row = await get_db().fetchrow("SELECT * FROM user_profiles WHERE user_id=$1 AND guild_id=$2", member.id, interaction.guild.id)
        embed = discord.Embed(color=(row["color"] if row and row["color"] else ACCENT), timestamp=dt.datetime.now(dt.UTC))
        embed.set_author(name=str(member), icon_url=member.display_avatar.url if member.display_avatar else None)
        title = row["title"] if row and row["title"] else "Member"
        embed.title = f"✦  {title}"
        bio = row["bio"] if row and row["bio"] else "No bio set."
        embed.description = f"*{bio}*"
        embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "—")
        embed.add_field(name="Account", value=f"<t:{int(member.created_at.timestamp())}:R>")
        embed.add_field(name="Roles", value=str(len(member.roles) - 1))
        if row and row["badges"]:
            badge_text = " ".join(PRESET_BADGES[b][0] for b in row["badges"] if b in PRESET_BADGES)
            if badge_text:
                embed.add_field(name="Badges", value=badge_text, inline=False)
        embed.set_footer(text="BypassX · Profiles")
        await interaction.response.send_message(embed=embed)

    @group.command(name="bio", description="Set your profile bio.")
    async def set_bio(self, interaction: discord.Interaction, bio: str):
        if len(bio) > 500:
            await interaction.response.send_message(embed=embed_error("Bio too long (max 500 chars)."), ephemeral=True)
            return
        await get_db().execute(
            """
            INSERT INTO user_profiles (user_id, guild_id, bio) VALUES ($1,$2,$3)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET bio=$3
            """,
            interaction.user.id, interaction.guild.id, bio,
        )
        await interaction.response.send_message(embed=embed_success("Bio Updated", "Your profile bio has been updated."))

    @group.command(name="title", description="Set your profile title.")
    async def set_title(self, interaction: discord.Interaction, title: str):
        if len(title) > 80:
            await interaction.response.send_message(embed=embed_error("Title too long (max 80 chars)."), ephemeral=True)
            return
        await get_db().execute(
            """
            INSERT INTO user_profiles (user_id, guild_id, title) VALUES ($1,$2,$3)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET title=$3
            """,
            interaction.user.id, interaction.guild.id, title,
        )
        await interaction.response.send_message(embed=embed_success("Title Updated", "Your profile title has been updated."))

    @group.command(name="color", description="Set your profile accent color (hex, e.g. #6366F1).")
    async def set_color(self, interaction: discord.Interaction, hex_color: str):
        try:
            hex_color = hex_color.lstrip("#")
            color = int(hex_color, 16)
            if color < 0 or color > 0xFFFFFF:
                raise ValueError
        except (ValueError, TypeError):
            await interaction.response.send_message(embed=embed_error("Invalid color. Use hex like `#6366F1`."), ephemeral=True)
            return
        await get_db().execute(
            """
            INSERT INTO user_profiles (user_id, guild_id, color) VALUES ($1,$2,$3)
            ON CONFLICT (user_id, guild_id) DO UPDATE SET color=$3
            """,
            interaction.user.id, interaction.guild.id, color,
        )
        await interaction.response.send_message(embed=embed_success("Color Updated", f"Your profile color is now `#{hex_color.upper()}`."))

    @group.command(name="clear", description="Reset your profile.")
    async def clear(self, interaction: discord.Interaction):
        await get_db().execute("DELETE FROM user_profiles WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Profile Cleared", "Your profile has been reset."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profiles(bot))
