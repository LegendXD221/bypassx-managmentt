"""Mass actions — mass role add/remove, mass ban, mass kick, mass nickname."""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_premium, embed_success, is_admin, send_modlog


class MassActions(commands.Cog):
    """Bulk administrative actions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="mass", description="Bulk admin actions.", default_permissions=discord.Permissions(administrator=True))

    @group.command(name="roleadd", description="Add a role to many members at once.")
    @is_admin()
    async def role_add(self, interaction: discord.Interaction, role: discord.Role, members: str):
        # members can be a comma-separated list of mentions/IDs
        ids = []
        for part in members.split(","):
            part = part.strip()
            if part.startswith("<@") and part.endswith(">"):
                part = part.strip("<@&!>")
            try:
                ids.append(int(part))
            except ValueError:
                continue
        if not ids:
            await interaction.response.send_message(embed=embed_error("No valid member IDs found."), ephemeral=True)
            return
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("That role is above me."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        added = 0
        for uid in ids[:50]:
            member = interaction.guild.get_member(uid)
            if member and role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Mass role add by {interaction.user}")
                    added += 1
                except discord.HTTPException:
                    pass
        await interaction.followup.send(embed=embed_success("Mass Role Added", f"Added {role.mention} to **{added}** members."), ephemeral=True)
        await send_modlog(interaction.guild, action="mass role add", moderator=interaction.user, details={"Role": role.mention, "Count": added})

    @group.command(name="roleremove", description="Remove a role from many members at once.")
    @is_admin()
    async def role_remove(self, interaction: discord.Interaction, role: discord.Role, members: str):
        ids = []
        for part in members.split(","):
            part = part.strip()
            if part.startswith("<@") and part.endswith(">"):
                part = part.strip("<@&!>")
            try:
                ids.append(int(part))
            except ValueError:
                continue
        if not ids:
            await interaction.response.send_message(embed=embed_error("No valid member IDs found."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        removed = 0
        for uid in ids[:50]:
            member = interaction.guild.get_member(uid)
            if member and role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Mass role remove by {interaction.user}")
                    removed += 1
                except discord.HTTPException:
                    pass
        await interaction.followup.send(embed=embed_success("Mass Role Removed", f"Removed {role.mention} from **{removed}** members."), ephemeral=True)
        await send_modlog(interaction.guild, action="mass role remove", moderator=interaction.user, details={"Role": role.mention, "Count": removed})

    @group.command(name="ban", description="Mass ban members by ID list.")
    @is_admin()
    async def mass_ban(self, interaction: discord.Interaction, user_ids: str, reason: Optional[str] = None):
        ids = []
        for part in user_ids.split(","):
            part = part.strip()
            try:
                ids.append(int(part))
            except ValueError:
                continue
        if not ids:
            await interaction.response.send_message(embed=embed_error("No valid IDs."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        banned = 0
        for uid in ids[:30]:
            try:
                user = await self.bot.fetch_user(uid)
                await interaction.guild.ban(user, reason=f"Mass ban by {interaction.user}: {reason or ''}", delete_message_days=1)
                banned += 1
            except discord.HTTPException:
                pass
        await interaction.followup.send(embed=embed_success("Mass Ban Complete", f"Banned **{banned}** users."), ephemeral=True)
        await send_modlog(interaction.guild, action="mass ban", moderator=interaction.user, reason=reason, details={"Count": banned})

    @group.command(name="kick", description="Mass kick members.")
    @is_admin()
    async def mass_kick(self, interaction: discord.Interaction, members: str, reason: Optional[str] = None):
        ids = []
        for part in members.split(","):
            part = part.strip()
            if part.startswith("<@") and part.endswith(">"):
                part = part.strip("<@&!>")
            try:
                ids.append(int(part))
            except ValueError:
                continue
        if not ids:
            await interaction.response.send_message(embed=embed_error("No valid IDs."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        kicked = 0
        for uid in ids[:30]:
            member = interaction.guild.get_member(uid)
            if member:
                try:
                    await member.kick(reason=f"Mass kick by {interaction.user}: {reason or ''}")
                    kicked += 1
                except discord.HTTPException:
                    pass
        await interaction.followup.send(embed=embed_success("Mass Kick Complete", f"Kicked **{kicked}** members."), ephemeral=True)
        await send_modlog(interaction.guild, action="mass kick", moderator=interaction.user, reason=reason, details={"Count": kicked})

    @group.command(name="nickname", description="Mass set nicknames for members with a specific pattern.")
    @is_admin()
    async def mass_nick(self, interaction: discord.Interaction, role: discord.Role, prefix: str = "", suffix: str = "", strip_current: bool = False):
        await interaction.response.defer(ephemeral=True, thinking=True)
        updated = 0
        for member in role.members[:50]:
            base = member.name if strip_current or not member.nick else member.nick
            new_nick = f"{prefix}{base}{suffix}"[:32]
            try:
                if member.top_role < interaction.guild.me.top_role:
                    await member.edit(nick=new_nick, reason=f"Mass nickname by {interaction.user}")
                    updated += 1
            except discord.HTTPException:
                pass
        await interaction.followup.send(embed=embed_success("Mass Nickname Done", f"Updated **{updated}** members."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MassActions(bot))
