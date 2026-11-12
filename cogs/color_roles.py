"""Color roles — members set a custom hex color for their own role."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import ACCENT, embed_error, embed_info, embed_premium, embed_success, is_admin


class ColorRoles(commands.Cog):
    """Premium custom color roles for members."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="color", description="Custom color roles.", default_permissions=None)

    @group.command(name="set", description="Set your name color with a hex code. Creates a personal role.")
    async def set_color(self, interaction: discord.Interaction, hex_color: str):
        try:
            hex_str = hex_color.lstrip("#").strip()
            if len(hex_str) == 3:
                hex_str = "".join(c * 2 for c in hex_str)
            color_int = int(hex_str, 16)
        except (ValueError, TypeError):
            await interaction.response.send_message(embed=embed_error("Invalid hex. Use `#6366F1` or `6366F1`."), ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member):
            return
        # find or create user's color role
        row = await get_db().fetchrow("SELECT role_id FROM user_color_roles WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
        role = None
        if row:
            role = interaction.guild.get_role(int(row["role_id"]))
        if role is None:
            # create new role
            try:
                role = await interaction.guild.create_role(name=interaction.user.name, color=color_int, reason=f"Color role for {interaction.user}")
                # position: above the member's top role but below bot
                target_pos = min(interaction.user.top_role.position + 1, interaction.guild.me.top_role.position - 1)
                if target_pos > 0:
                    try:
                        await role.edit(position=target_pos)
                    except discord.HTTPException:
                        pass
                await interaction.user.add_roles(role, reason="Color role")
                await get_db().execute(
                    "INSERT INTO user_color_roles (user_id, guild_id, role_id, color) VALUES ($1,$2,$3,$4) ON CONFLICT (user_id, guild_id) DO UPDATE SET role_id=$3, color=$4",
                    interaction.user.id, interaction.guild.id, role.id, color_int,
                )
            except discord.Forbidden:
                await interaction.response.send_message(embed=embed_error("I need Manage Roles permission."), ephemeral=True)
                return
            except discord.HTTPException as exc:
                await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
                return
        else:
            try:
                await role.edit(color=color_int, reason=f"Color update by {interaction.user}")
                await get_db().execute("UPDATE user_color_roles SET color=$1 WHERE user_id=$2 AND guild_id=$3", color_int, interaction.user.id, interaction.guild.id)
            except discord.HTTPException as exc:
                await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
                return
        embed = discord.Embed(title="✦ Color Set", description=f"Your name color is now `#{hex_str.upper()}`.", color=color_int, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Premium")
        await interaction.response.send_message(embed=embed)

    @group.command(name="clear", description="Remove your custom color role.")
    async def clear(self, interaction: discord.Interaction):
        row = await get_db().fetchrow("SELECT role_id FROM user_color_roles WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
        if not row:
            await interaction.response.send_message(embed=embed_error("You don't have a custom color."), ephemeral=True)
            return
        role = interaction.guild.get_role(int(row["role_id"]))
        if role:
            try:
                await role.delete(reason=f"Color cleared by {interaction.user}")
            except discord.HTTPException:
                pass
        await get_db().execute("DELETE FROM user_color_roles WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Color Cleared", "Your custom color role has been removed."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ColorRoles(bot))
