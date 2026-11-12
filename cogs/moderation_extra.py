"""Moderation extras — mod notes, member history lookup, modnotes management."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_premium, embed_success, is_mod


class ModerationExtra(commands.Cog):
    """Moderator notes and member history."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="note", description="Private moderator notes on members.", default_permissions=discord.Permissions(manage_messages=True))

    @group.command(name="add", description="Add a private mod note about a member.")
    @is_mod()
    async def add_note(self, interaction: discord.Interaction, member: discord.Member, note: str):
        await get_db().execute(
            "INSERT INTO mod_notes (guild_id, user_id, moderator_id, note) VALUES ($1,$2,$3,$4)",
            interaction.guild.id, member.id, interaction.user.id, note,
        )
        await interaction.response.send_message(embed=embed_success("Note Added", f"Private note saved for {member.mention}."), ephemeral=True)

    @group.command(name="view", description="View private mod notes for a member.")
    @is_mod()
    async def view_notes(self, interaction: discord.Interaction, member: discord.Member):
        rows = await get_db().fetch(
            "SELECT note, moderator_id, created_at FROM mod_notes WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 25",
            interaction.guild.id, member.id,
        )
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Notes", f"No private notes for {member.mention}."), ephemeral=True)
            return
        embed = embed_premium(f"Mod Notes — {member}", f"**{len(rows)}** note(s) (showing last 25):")
        for r in rows[:15]:
            mod = self.bot.get_user(int(r["moderator_id"])) or await self.bot.fetch_user(int(r["moderator_id"]))
            embed.add_field(name=f"<t:{int(r['created_at'].timestamp())}:R>", value=f"{r['note']}\n— {mod.mention if mod else r['moderator_id']}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="clear", description="Clear all mod notes for a member.")
    @is_mod()
    async def clear_notes(self, interaction: discord.Interaction, member: discord.Member):
        await get_db().execute("DELETE FROM mod_notes WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed_success("Notes Cleared", f"All notes for {member.mention} removed."), ephemeral=True)

    @app_commands.command(name="history", description="Show a member's full moderation history.")
    @is_mod()
    @app_commands.default_permissions(manage_messages=True)
    async def history(self, interaction: discord.Interaction, member: discord.Member):
        # warnings
        warnings = await get_db().fetch("SELECT reason, moderator_id, created_at FROM warnings WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 10", interaction.guild.id, member.id)
        # mutes
        mutes = await get_db().fetch("SELECT reason, moderator_id, created_at FROM mutes WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 10", interaction.guild.id, member.id)
        # mod_logs
        logs = await get_db().fetch("SELECT action, reason, moderator_id, created_at FROM mod_logs WHERE guild_id=$1 AND target_id=$2 ORDER BY created_at DESC LIMIT 10", interaction.guild.id, member.id)
        # notes count
        notes_count = await get_db().fetchval("SELECT COUNT(*) FROM mod_notes WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)

        embed = embed_premium(f"History — {member}", f"Warnings: **{len(warnings)}** · Mutes: **{len(mutes)}** · Log entries: **{len(logs)}** · Notes: **{notes_count}**")

        if warnings:
            embed.add_field(name="⚠ Recent Warnings", value="\n".join(f"• {r['reason']} — <t:{int(r['created_at'].timestamp())}:R>" for r in warnings[:5]) or "—", inline=False)
        if mutes:
            embed.add_field(name="🔇 Recent Mutes", value="\n".join(f"• {r['reason'] or 'No reason'} — <t:{int(r['created_at'].timestamp())}:R>" for r in mutes[:5]) or "—", inline=False)
        if logs:
            embed.add_field(name="📋 Recent Log Entries", value="\n".join(f"• {r['action']} — <t:{int(r['created_at'].timestamp())}:R>" for r in logs[:5]) or "—", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="memberinfo", description="Show detailed mod-facing info about a member.")
    @is_mod()
    @app_commands.default_permissions(manage_messages=True)
    async def memberinfo(self, interaction: discord.Interaction, member: discord.Member):
        warnings = await get_db().fetchval("SELECT COUNT(*) FROM warnings WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        notes = await get_db().fetchval("SELECT COUNT(*) FROM mod_notes WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        embed = embed_premium(f"Member Info — {member}")
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "—", inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
        embed.add_field(name="Roles", value=str(len(member.roles) - 1), inline=True)
        embed.add_field(name="Warnings", value=str(warnings), inline=True)
        embed.add_field(name="Mod Notes", value=str(notes), inline=True)
        embed.add_field(name="Pending Timeout", value=f"<t:{int(member.timed_out_until.timestamp())}:R>" if member.timed_out_until else "None", inline=True)
        embed.add_field(name="Voice", value=member.voice.channel.mention if member.voice and member.voice.channel else "Not connected", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationExtra(bot))
