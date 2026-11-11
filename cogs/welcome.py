"""Welcome/leave messages and auto-role assignment on join."""
from __future__ import annotations

import datetime as dt
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_success, is_admin, send_modlog

PLACEHOLDERS = {
    "{user}": "user mention",
    "{username}": "user's name",
    "{discriminator}": "user's #discrim",
    "{server}": "server name",
    "{member_count}": "current member count",
    "{user_id}": "user id",
}


def render(text: str, member: discord.Member) -> str:
    return (
        text.replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{discriminator}", member.discriminator if member.discriminator != "0" else "0")
        .replace("{server}", member.guild.name)
        .replace("{member_count}", str(member.guild.member_count))
        .replace("{user_id}", str(member.id))
    )


class Welcome(commands.Cog):
    """Welcomes new members and handles auto-role."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await get_db().get_guild_config(member.guild.id)
        if not cfg:
            return
        # auto-role
        if cfg["auto_role_id"]:
            role = member.guild.get_role(int(cfg["auto_role_id"]))
            if role and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Auto-role on join")
                except discord.HTTPException:
                    pass
        # welcome message
        if cfg["welcome_channel_id"] and cfg["welcome_message"]:
            ch = member.guild.get_channel(int(cfg["welcome_channel_id"]))
            if ch and isinstance(ch, discord.TextChannel):
                try:
                    await ch.send(render(cfg["welcome_message"], member))
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = await get_db().get_guild_config(member.guild.id)
        if not cfg or not cfg["leave_message"] or not cfg["welcome_channel_id"]:
            return
        ch = member.guild.get_channel(int(cfg["welcome_channel_id"]))
        if ch and isinstance(ch, discord.TextChannel):
            try:
                await ch.send(render(cfg["leave_message"], member))
            except discord.HTTPException:
                pass

    # ---------------- config commands --------------------------------------

    group = app_commands.Group(name="welcome", description="Configure welcome/leave messages.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="setchannel", description="Set the welcome/leave channel.")
    @is_admin()
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await get_db().set_guild_field(interaction.guild.id, "welcome_channel_id", channel.id)
        await interaction.response.send_message(embed=embed_success("Welcome Channel Set", f"Welcome/leave messages will be sent to {channel.mention}."))

    @group.command(name="message", description="Set the welcome message. Placeholders: {user}, {username}, {server}, {member_count}")
    @is_admin()
    async def set_message(self, interaction: discord.Interaction, message: str):
        if len(message) > 1800:
            await interaction.response.send_message(embed=embed_error("Message too long (max 1800 chars)."), ephemeral=True)
            return
        await get_db().set_guild_field(interaction.guild.id, "welcome_message", message)
        await interaction.response.send_message(embed=embed_success("Welcome Message Set", f"Preview:\n{render(message, interaction.user)}"))

    @group.command(name="leavemessage", description="Set the leave message.")
    @is_admin()
    async def set_leave(self, interaction: discord.Interaction, message: str):
        await get_db().set_guild_field(interaction.guild.id, "leave_message", message)
        await interaction.response.send_message(embed=embed_success("Leave Message Set", f"Preview:\n{render(message, interaction.user)}"))

    @group.command(name="test", description="Test the welcome message against yourself.")
    @is_admin()
    async def test(self, interaction: discord.Interaction):
        cfg = await get_db().get_guild_config(interaction.guild.id)
        if not cfg or not cfg["welcome_message"]:
            await interaction.response.send_message(embed=embed_error("No welcome message set."), ephemeral=True)
            return
        member = interaction.user
        assert isinstance(member, discord.Member)
        await interaction.response.send_message(embed=embed_info("Welcome Preview", render(cfg["welcome_message"], member)))

    @group.command(name="autorole", description="Set the role given automatically to new members.")
    @is_admin()
    async def set_autorole(self, interaction: discord.Interaction, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("That role is above me — I can't assign it."), ephemeral=True)
            return
        await get_db().set_guild_field(interaction.guild.id, "auto_role_id", role.id)
        await interaction.response.send_message(embed=embed_success("Auto-Role Set", f"New members will receive {role.mention}."))

    @group.command(name="placeholders", description="Show all available placeholders.")
    async def placeholders(self, interaction: discord.Interaction):
        embed = embed_info("Welcome Placeholders", "Use these in your welcome/leave messages:")
        for k, v in PLACEHOLDERS.items():
            embed.add_field(name=k, value=v, inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
