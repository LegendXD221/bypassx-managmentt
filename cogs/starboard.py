"""Starboard — members star a message to feature it in a dedicated channel."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import ACCENT, GOLD, embed_error, embed_info, embed_premium, embed_success, is_admin


class Starboard(commands.Cog):
    """Premium starboard with configurable threshold & emoji."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.member is None or payload.member.bot:
            return
        cfg = await get_db().fetchrow("SELECT * FROM starboard_config WHERE guild_id=$1", payload.guild_id)
        if not cfg or not cfg["enabled"]:
            return
        emoji_str = str(payload.emoji)
        # accept either ⭐ or the configured emoji name
        is_star = emoji_str == "⭐" or emoji_str == cfg["emoji"] or emoji_str.startswith("⭐")
        if not is_star:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(payload.channel_id)
        if channel is None:
            return
        try:
            msg = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden):
            return
        if msg.author.id == payload.user_id:
            # don't allow self-starring
            try:
                await msg.remove_reaction(payload.emoji, payload.member)
            except discord.HTTPException:
                pass
            return
        # count stars
        star_count = 0
        for r in msg.reactions:
            if str(r.emoji) == "⭐" or str(r.emoji) == cfg["emoji"]:
                star_count = r.count
                break
        await self._upsert_star(msg, star_count, guild, cfg)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        cfg = await get_db().fetchrow("SELECT * FROM starboard_config WHERE guild_id=$1", payload.guild_id)
        if not cfg or not cfg["enabled"]:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(payload.channel_id)
        if channel is None:
            return
        try:
            msg = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden):
            return
        star_count = 0
        for r in msg.reactions:
            if str(r.emoji) == "⭐" or str(r.emoji) == cfg["emoji"]:
                star_count = r.count
                break
        await self._upsert_star(msg, star_count, guild, cfg)

    async def _upsert_star(self, msg: discord.Message, stars: int, guild: discord.Guild, cfg) -> None:
        threshold = cfg["threshold"] or 3
        sb_channel = guild.get_channel(int(cfg["channel_id"]))
        if sb_channel is None:
            return
        row = await get_db().fetchrow(
            "SELECT id, starboard_message_id FROM starred_messages WHERE guild_id=$1 AND source_message_id=$2",
            guild.id, msg.id,
        )
        if stars < threshold:
            # below threshold — remove from starboard if it was there
            if row and row["starboard_message_id"]:
                try:
                    old = await sb_channel.fetch_message(int(row["starboard_message_id"]))
                    await old.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
                await get_db().execute(
                    "UPDATE starred_messages SET starboard_message_id=NULL, stars=$1 WHERE id=$2",
                    stars, row["id"],
                )
            return
        embed = discord.Embed(description=msg.content or "", color=GOLD, timestamp=msg.created_at)
        embed.set_author(name=str(msg.author), icon_url=msg.author.display_avatar.url if msg.author.display_avatar else None)
        embed.add_field(name="Source", value=f"[Jump]({msg.jump_url})", inline=True)
        embed.add_field(name="Stars", value=f"★ {stars}", inline=True)
        embed.set_footer(text=f"BypassX · Starboard")
        if msg.attachments:
            embed.set_image(url=msg.attachments[0].url)
        if row:
            await get_db().execute(
                "UPDATE starred_messages SET stars=$1 WHERE id=$2", stars, row["id"]
            )
            if row["starboard_message_id"]:
                try:
                    sb_msg = await sb_channel.fetch_message(int(row["starboard_message_id"]))
                    await sb_msg.edit(content=f"★ **{stars}** · {msg.channel.mention}", embed=embed)
                    return
                except (discord.NotFound, discord.HTTPException):
                    pass
            sb_msg = await sb_channel.send(content=f"★ **{stars}** · {msg.channel.mention}", embed=embed)
            await get_db().execute(
                "UPDATE starred_messages SET starboard_message_id=$1 WHERE id=$2",
                sb_msg.id, row["id"],
            )
        else:
            sb_msg = await sb_channel.send(content=f"★ **{stars}** · {msg.channel.mention}", embed=embed)
            await get_db().execute(
                "INSERT INTO starred_messages (guild_id, source_message_id, source_channel_id, starboard_message_id, stars) VALUES ($1,$2,$3,$4,$5)",
                guild.id, msg.id, msg.channel.id, sb_msg.id, stars,
            )

    group = app_commands.Group(name="starboard", description="Configure the starboard.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="setup", description="Configure the starboard channel and threshold.")
    @is_admin()
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel, threshold: app_commands.Range[int, 1, 50] = 3):
        await get_db().execute(
            """
            INSERT INTO starboard_config (guild_id, channel_id, threshold, emoji, enabled)
            VALUES ($1,$2,$3,'star',TRUE)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2, threshold=$3, enabled=TRUE
            """,
            interaction.guild.id, channel.id, threshold,
        )
        await interaction.response.send_message(embed=embed_success("Starboard Configured", f"Channel: {channel.mention}\nThreshold: **{threshold} stars**\nEmoji: ⭐"))

    @group.command(name="disable", description="Disable the starboard.")
    @is_admin()
    async def disable(self, interaction: discord.Interaction):
        await get_db().execute("UPDATE starboard_config SET enabled=FALSE WHERE guild_id=$1", interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Starboard Disabled", "New stars will no longer be tracked."))

    @group.command(name="status", description="Show starboard configuration.")
    async def status(self, interaction: discord.Interaction):
        cfg = await get_db().fetchrow("SELECT * FROM starboard_config WHERE guild_id=$1", interaction.guild.id)
        if not cfg:
            await interaction.response.send_message(embed=embed_error("Not Configured", "Use `/starboard setup` first."), ephemeral=True)
            return
        embed = embed_premium("Starboard Status")
        embed.add_field(name="Channel", value=f"<#{cfg['channel_id']}>", inline=True)
        embed.add_field(name="Threshold", value=str(cfg["threshold"]), inline=True)
        embed.add_field(name="Enabled", value="✓" if cfg["enabled"] else "✕", inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Starboard(bot))
