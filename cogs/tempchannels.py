"""Temporary voice channels — join a creator channel to spawn your own."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_premium, embed_success, is_admin


class TempVoice(commands.Cog):
    """Premium temp voice — join to claim, leave to delete."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        # joining the creator channel?
        if after.channel is not None:
            cfg = await get_db().fetchrow("SELECT category_id, creator_channel_id FROM temp_voice_config WHERE guild_id=$1", member.guild.id)
            if cfg and int(cfg["creator_channel_id"]) == after.channel.id:
                category = member.guild.get_channel(int(cfg["category_id"])) if cfg["category_id"] else after.channel.category
                try:
                    new_ch = await member.guild.create_voice_channel(
                        name=f"{member.name}'s Room",
                        category=category if isinstance(category, discord.CategoryChannel) else None,
                        reason=f"Temp voice by {member}",
                    )
                    await member.move_to(new_ch, reason="Move to new temp channel")
                    await get_db().execute(
                        "INSERT INTO temp_voice_sessions (channel_id, owner_id, guild_id) VALUES ($1,$2,$3)",
                        new_ch.id, member.id, member.guild.id,
                    )
                except discord.HTTPException:
                    pass
        # leaving a temp channel?
        if before.channel is not None and after.channel is None:
            row = await get_db().fetchrow("SELECT * FROM temp_voice_sessions WHERE channel_id=$1", before.channel.id)
            if row:
                # delete if empty
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete(reason="Temp voice empty")
                    except discord.HTTPException:
                        pass
                    await get_db().execute("DELETE FROM temp_voice_sessions WHERE channel_id=$1", before.channel.id)

    group = app_commands.Group(name="tempvoice", description="Configure temporary voice channels.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="setup", description="Set the creator channel that members join to spawn a temp voice.")
    @is_admin()
    async def setup(self, interaction: discord.Interaction, creator_channel: discord.VoiceChannel, category: discord.CategoryChannel = None):
        await get_db().execute(
            """
            INSERT INTO temp_voice_config (guild_id, category_id, creator_channel_id) VALUES ($1,$2,$3)
            ON CONFLICT (guild_id) DO UPDATE SET category_id=$2, creator_channel_id=$3
            """,
            interaction.guild.id, category.id if category else None, creator_channel.id,
        )
        await interaction.response.send_message(embed=embed_success("Temp Voice Configured", f"Members can now join {creator_channel.mention} to create their own temporary voice channel."))

    @group.command(name="status", description="Show temp voice configuration.")
    async def status(self, interaction: discord.Interaction):
        cfg = await get_db().fetchrow("SELECT * FROM temp_voice_config WHERE guild_id=$1", interaction.guild.id)
        if not cfg:
            await interaction.response.send_message(embed=embed_error("Not configured. Use `/tempvoice setup`."), ephemeral=True)
            return
        ch = interaction.guild.get_channel(int(cfg["creator_channel_id"]))
        embed = embed_premium("Temp Voice Status")
        embed.add_field(name="Creator Channel", value=ch.mention if ch else "missing", inline=False)
        embed.add_field(name="Category", value=f"<#{cfg['category_id']}>" if cfg["category_id"] else "—", inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TempVoice(bot))
