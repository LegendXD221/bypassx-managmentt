"""Server stats — voice channels that display member/role/boost counts, auto-updating."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import get_db
from utils import embed_error, embed_info, embed_premium, embed_success, is_admin


class ServerStats(commands.Cog):
    """Premium server stats — Wick-style counters."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_loop.start()

    @tasks.loop(minutes=5)
    async def update_loop(self) -> None:
        rows = await get_db().fetch("SELECT * FROM server_stats")
        for row in rows:
            guild = self.bot.get_guild(int(row["guild_id"]))
            if guild is None:
                continue
            for col_name in ["members_channel_id", "humans_channel_id", "bots_channel_id", "channels_count_id", "roles_count_id", "boost_count_id", "online_count_id"]:
                cid = row[col_name]
                if not cid:
                    continue
                channel = guild.get_channel(int(cid))
                if channel is None or not isinstance(channel, discord.VoiceChannel):
                    continue
                if col_name == "members_channel_id":
                    name = f"Members: {guild.member_count}"
                elif col_name == "humans_channel_id":
                    name = f"Humans: {sum(1 for m in guild.members if not m.bot) if guild.member_count else '?'}"
                elif col_name == "bots_channel_id":
                    name = f"Bots: {sum(1 for m in guild.members if m.bot) if guild.member_count else '?'}"
                elif col_name == "channels_count_id":
                    name = f"Channels: {len(guild.text_channels) + len(guild.voice_channels)}"
                elif col_name == "roles_count_id":
                    name = f"Roles: {len(guild.roles)}"
                elif col_name == "boost_count_id":
                    name = f"Boosts: {guild.premium_subscription_count}"
                elif col_name == "online_count_id":
                    online = sum(1 for m in guild.members if m.status != discord.Status.offline) if guild.member_count else 0
                    name = f"Online: {online}"
                else:
                    continue
                try:
                    if channel.name != name:
                        await channel.edit(name=name, reason="Server stats update")
                except discord.HTTPException:
                    pass

    @update_loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    group = app_commands.Group(name="serverstats", description="Configure live server stats counters.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="setup", description="Create all stat counters in a new category.")
    @is_admin()
    async def setup(self, interaction: discord.Interaction, category_name: str = "Server Stats"):
        await interaction.response.defer(ephemeral=True)
        category = await interaction.guild.create_category(category_name)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
            interaction.guild.me: discord.PermissionOverwrite(connect=False, view_channel=True, manage_channels=True),
        }
        members_ch = await category.create_voice_channel(name=f"Members: {interaction.guild.member_count}", overwrites=overwrites)
        humans_ch = await category.create_voice_channel(name=f"Humans: {sum(1 for m in interaction.guild.members if not m.bot) if interaction.guild.member_count else 0}", overwrites=overwrites)
        bots_ch = await category.create_voice_channel(name=f"Bots: {sum(1 for m in interaction.guild.members if m.bot) if interaction.guild.member_count else 0}", overwrites=overwrites)
        channels_ch = await category.create_voice_channel(name=f"Channels: {len(interaction.guild.text_channels) + len(interaction.guild.voice_channels)}", overwrites=overwrites)
        roles_ch = await category.create_voice_channel(name=f"Roles: {len(interaction.guild.roles)}", overwrites=overwrites)
        boost_ch = await category.create_voice_channel(name=f"Boosts: {interaction.guild.premium_subscription_count}", overwrites=overwrites)
        online_ch = await category.create_voice_channel(name=f"Online: {sum(1 for m in interaction.guild.members if m.status != discord.Status.offline) if interaction.guild.member_count else 0}", overwrites=overwrites)
        await get_db().execute(
            """
            INSERT INTO server_stats (guild_id, members_channel_id, humans_channel_id, bots_channel_id, channels_count_id, roles_count_id, boost_count_id, online_count_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (guild_id) DO UPDATE SET members_channel_id=$2, humans_channel_id=$3, bots_channel_id=$4, channels_count_id=$5, roles_count_id=$6, boost_count_id=$7, online_count_id=$8
            """,
            interaction.guild.id, members_ch.id, humans_ch.id, bots_ch.id, channels_ch.id, roles_ch.id, boost_ch.id, online_ch.id,
        )
        await interaction.followup.send(embed=embed_success("Server Stats Created", f"Created 7 counters under {category.mention}. They will refresh every 5 minutes."), ephemeral=True)

    @group.command(name="disable", description="Remove all stat counters.")
    @is_admin()
    async def disable(self, interaction: discord.Interaction):
        row = await get_db().fetchrow("SELECT * FROM server_stats WHERE guild_id=$1", interaction.guild.id)
        if not row:
            await interaction.response.send_message(embed=embed_error("No stats configured."), ephemeral=True)
            return
        for col in ["members_channel_id", "humans_channel_id", "bots_channel_id", "channels_count_id", "roles_count_id", "boost_count_id", "online_count_id"]:
            cid = row[col]
            if cid:
                ch = interaction.guild.get_channel(int(cid))
                if ch:
                    try:
                        await ch.delete(reason="Server stats disabled")
                    except discord.HTTPException:
                        pass
        await get_db().execute("DELETE FROM server_stats WHERE guild_id=$1", interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Stats Disabled", "All counters removed."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerStats(bot))
