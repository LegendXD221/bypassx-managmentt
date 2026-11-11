"""Comprehensive logging — message edits/deletes, member events, role/channel changes, voice."""
from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_info, embed_success, embed_warn, is_admin

LOG_COLOURS = {
    "message_delete": 0xED4245,
    "message_edit": 0xFEE75C,
    "member_join": 0x57F287,
    "member_remove": 0xED4245,
    "member_update": 0x5865F2,
    "role_create": 0x57F287,
    "role_delete": 0xED4245,
    "role_update": 0xFEE75C,
    "channel_create": 0x57F287,
    "channel_delete": 0xED4245,
    "channel_update": 0xFEE75C,
    "voice_update": 0x5865F2,
    "guild_update": 0xFEE75C,
}


class Logging(commands.Cog):
    """Audit logging for everything that happens in a server."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, guild: discord.Guild, event: str, embed: discord.Embed) -> None:
        cfg = await get_db().get_guild_config(guild.id)
        if not cfg or not cfg["log_channel_id"]:
            return
        ch = guild.get_channel(int(cfg["log_channel_id"]))
        if ch is None or not isinstance(ch, discord.TextChannel):
            return
        embed.timestamp = dt.datetime.now(dt.UTC)
        embed.set_footer(text=f"BypassX Logs • {event}")
        embed.color = LOG_COLOURS.get(event, 0x5865F2)
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        embed = discord.Embed(title="🗑️ Message Deleted", description=f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}", color=0xED4245)
        embed.add_field(name="Content", value=(message.content[:1024] or "*(no text)*"), inline=False)
        await self._send_log(message.guild, "message_delete", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild is None or before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(title="📝 Message Edited", description=f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}\n[Jump]({after.jump_url})", color=0xFEE75C)
        embed.add_field(name="Before", value=(before.content[:1024] or "*(empty)*"), inline=False)
        embed.add_field(name="After", value=(after.content[:1024] or "*(empty)*"), inline=False)
        await self._send_log(before.guild, "message_edit", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        embed = discord.Embed(title="👋 Member Joined", description=f"{member.mention} ({member})\nAccount created <t:{int(member.created_at.timestamp())}:R>", color=0x57F287)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, "member_join", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        embed = discord.Embed(title="🚪 Member Left", description=f"{member.mention} ({member})", color=0xED4245)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, "member_remove", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        # role changes
        before_roles = set(before.roles)
        after_roles = set(after.roles)
        added = after_roles - before_roles
        removed = before_roles - after_roles
        if added or removed:
            parts = []
            if added:
                parts.append("+ " + ", ".join(r.mention for r in added))
            if removed:
                parts.append("- " + ", ".join(r.mention for r in removed))
            embed = discord.Embed(title="🎭 Roles Updated", description=f"**Member:** {after.mention}\n" + "\n".join(parts), color=0x5865F2)
            await self._send_log(after.guild, "member_update", embed)
        # nickname changes
        if before.nick != after.nick:
            embed = discord.Embed(title="✏️ Nickname Changed", description=f"**Member:** {after.mention}\n**Before:** {before.nick or '(none)'}\n**After:** {after.nick or '(none)'}", color=0x5865F2)
            await self._send_log(after.guild, "member_update", embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        embed = discord.Embed(title="➕ Role Created", description=f"**Role:** {role.mention}\n**ID:** `{role.id}`", color=0x57F287)
        await self._send_log(role.guild, "role_create", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        embed = discord.Embed(title="➖ Role Deleted", description=f"**Role:** {role.name}\n**ID:** `{role.id}`", color=0xED4245)
        await self._send_log(role.guild, "role_delete", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        embed = discord.Embed(title="➕ Channel Created", description=f"**Channel:** {channel.mention}\n**Type:** {channel.type}", color=0x57F287)
        await self._send_log(channel.guild, "channel_create", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        embed = discord.Embed(title="➖ Channel Deleted", description=f"**Channel:** #{channel.name}\n**Type:** {channel.type}", color=0xED4245)
        await self._send_log(channel.guild, "channel_delete", embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel == after.channel:
            return
        if before.channel and not after.channel:
            desc = f"**{member.mention}** left **{before.channel.mention}**"
        elif not before.channel and after.channel:
            desc = f"**{member.mention}** joined **{after.channel.mention}**"
        else:
            desc = f"**{member.mention}** moved from **{before.channel.mention}** to **{after.channel.mention}**"
        embed = discord.Embed(title="🔊 Voice Activity", description=desc, color=0x5865F2)
        await self._send_log(member.guild, "voice_update", embed)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} → {after.name}")
        if before.owner_id != after.owner_id:
            changes.append(f"**Owner:** <@{before.owner_id}> → <@{after.owner_id}>")
        if before.premium_tier != after.premium_tier:
            changes.append(f"**Boost Tier:** {before.premium_tier} → {after.premium_tier}")
        if not changes:
            return
        embed = discord.Embed(title="⚙️ Server Updated", description="\n".join(changes), color=0xFEE75C)
        await self._send_log(after, "guild_update", embed)

    # ---------------- config -----------------------------------------------

    group = app_commands.Group(name="logging", description="Configure logging.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="setchannel", description="Set the channel where all logs are sent.")
    @is_admin()
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await get_db().set_guild_field(interaction.guild.id, "log_channel_id", channel.id)
        await interaction.response.send_message(embed=embed_success("Logging Channel Set", f"All logs will go to {channel.mention}."))

    @group.command(name="setmodlog", description="Set a separate channel just for moderation logs (optional).")
    @is_admin()
    async def set_modlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await get_db().set_guild_field(interaction.guild.id, "mod_log_channel_id", channel.id)
        await interaction.response.send_message(embed=embed_success("Mod-Log Channel Set", f"Moderation logs will go to {channel.mention}."))

    @group.command(name="disable", description="Disable logging in this server.")
    @is_admin()
    async def disable(self, interaction: discord.Interaction):
        await get_db().set_guild_field(interaction.guild.id, "log_channel_id", None)
        await get_db().set_guild_field(interaction.guild.id, "mod_log_channel_id", None)
        await interaction.response.send_message(embed=embed_success("Logging Disabled", "All logging has been turned off."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Logging(bot))
