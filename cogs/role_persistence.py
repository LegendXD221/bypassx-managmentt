"""Role persistence — restore member roles when they rejoin the server."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_success, is_admin


class RolePersistence(commands.Cog):
    """Save member roles on leave and restore them on rejoin."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = await get_db().get_guild_config(member.guild.id)
        if not cfg or not cfg.get("role_persistence_enabled"):
            return
        role_ids = [
            r.id for r in member.roles
            if not r.is_default() and not r.is_integration() and not r.is_bot_managed() and r < member.guild.me.top_role
        ]
        if not role_ids:
            return
        await get_db().execute(
            """
            INSERT INTO role_persistence (guild_id, user_id, role_ids) VALUES ($1,$2,$3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET role_ids=$3, saved_at=NOW()
            """,
            member.guild.id, member.id, role_ids,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await get_db().get_guild_config(member.guild.id)
        if not cfg or not cfg.get("role_persistence_enabled"):
            return
        row = await get_db().fetchrow("SELECT role_ids FROM role_persistence WHERE guild_id=$1 AND user_id=$2", member.guild.id, member.id)
        if not row or not row["role_ids"]:
            return
        restored = 0
        for rid in row["role_ids"]:
            role = member.guild.get_role(int(rid))
            if role and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Role persistence restore")
                    restored += 1
                except discord.HTTPException:
                    pass
        if restored:
            try:
                await member.send(embed=embed_info("Roles Restored", f"Welcome back to **{member.guild.name}**! I restored **{restored}** of your previous roles."))
            except discord.Forbidden:
                pass

    group = app_commands.Group(name="rolepersistence", description="Configure role persistence.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="toggle", description="Enable or disable role persistence.")
    @is_admin()
    async def toggle(self, interaction: discord.Interaction, enabled: bool):
        await get_db().set_guild_field(interaction.guild.id, "role_persistence_enabled", enabled)
        await interaction.response.send_message(embed=embed_success("Role Persistence Updated", f"Now **{'enabled' if enabled else 'disabled'}**."))

    @group.command(name="status", description="Show role persistence status.")
    async def status(self, interaction: discord.Interaction):
        cfg = await get_db().get_guild_config(interaction.guild.id)
        enabled = cfg.get("role_persistence_enabled") if cfg else False
        embed = embed_info("Role Persistence", f"Status: **{'✓ enabled' if enabled else '✕ disabled'}**")
        await interaction.response.send_message(embed=embed)

    @group.command(name="clear", description="Clear saved roles for a user (or all).")
    @is_admin()
    async def clear(self, interaction: discord.Interaction, user: discord.User = None):
        if user:
            await get_db().execute("DELETE FROM role_persistence WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, user.id)
            await interaction.response.send_message(embed=embed_success("Cleared", f"Saved roles for {user.mention} have been removed."))
        else:
            await get_db().execute("DELETE FROM role_persistence WHERE guild_id=$1", interaction.guild.id)
            await interaction.response.send_message(embed=embed_success("Cleared", "All saved roles for this server have been removed."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RolePersistence(bot))
