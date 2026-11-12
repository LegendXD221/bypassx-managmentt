"""Voice channel tools — move, mute, deafen, disconnect, mass-move."""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import embed_error, embed_premium, embed_success, is_mod, send_modlog


class VcTools(commands.Cog):
    """Voice channel management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="voice", description="Voice channel tools.", default_permissions=discord.Permissions(move_members=True))

    @group.command(name="move", description="Move a member to another voice channel.")
    @is_mod()
    async def move(self, interaction: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
        if member.voice is None or member.voice.channel is None:
            await interaction.response.send_message(embed=embed_error("That member isn't in a voice channel."), ephemeral=True)
            return
        try:
            await member.move_to(channel, reason=f"Moved by {interaction.user}")
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Moved", f"{member.mention} moved to **{channel.name}**."))
        await send_modlog(interaction.guild, action="voice move", target=member, moderator=interaction.user, details={"To": channel.mention})

    @group.command(name="massmove", description="Move all members from one voice channel to another.")
    @is_mod()
    async def massmove(self, interaction: discord.Interaction, source: discord.VoiceChannel, target: discord.VoiceChannel):
        await interaction.response.defer(ephemeral=True, thinking=True)
        moved = 0
        for m in list(source.members):
            try:
                await m.move_to(target, reason=f"Mass move by {interaction.user}")
                moved += 1
            except discord.HTTPException:
                pass
        await interaction.followup.send(embed=embed_success("Mass Move Done", f"Moved **{moved}** members from {source.mention} to {target.mention}."), ephemeral=True)
        await send_modlog(interaction.guild, action="voice mass-move", moderator=interaction.user, details={"From": source.mention, "To": target.mention, "Count": moved})

    @group.command(name="mute", description="Server-mute a member in voice.")
    @is_mod()
    async def mute(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        try:
            await member.edit(mute=True, reason=f"Voice mute by {interaction.user}: {reason or ''}")
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Voice Muted", f"{member.mention} is now server-muted."))
        await send_modlog(interaction.guild, action="voice mute", target=member, moderator=interaction.user, reason=reason)

    @group.command(name="unmute", description="Remove server-mute from a member.")
    @is_mod()
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await member.edit(mute=False, reason=f"Voice unmute by {interaction.user}")
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Voice Unmuted", f"{member.mention} can speak again."))

    @group.command(name="deafen", description="Server-deafen a member.")
    @is_mod()
    async def deafen(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        try:
            await member.edit(deafen=True, reason=f"Voice deafen by {interaction.user}: {reason or ''}")
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Deafened", f"{member.mention} is now server-deafened."))
        await send_modlog(interaction.guild, action="voice deafen", target=member, moderator=interaction.user, reason=reason)

    @group.command(name="undeafen", description="Remove server-deafen.")
    @is_mod()
    async def undeafen(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await member.edit(deafen=False, reason=f"Voice undeafen by {interaction.user}")
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Undeafened", f"{member.mention} can hear again."))

    @group.command(name="disconnect", description="Disconnect a member from voice.")
    @is_mod()
    async def disconnect(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        if member.voice is None:
            await interaction.response.send_message(embed=embed_error("That member isn't in voice."), ephemeral=True)
            return
        try:
            await member.move_to(None, reason=f"Disconnected by {interaction.user}: {reason or ''}")
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Disconnected", f"{member.mention} was disconnected from voice."))
        await send_modlog(interaction.guild, action="voice disconnect", target=member, moderator=interaction.user, reason=reason)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VcTools(bot))
