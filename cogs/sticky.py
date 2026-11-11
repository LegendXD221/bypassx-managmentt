"""Sticky messages — a message that re-posts itself after N new messages.

Inspired by Carl-bot's sticky module. The bot remembers one sticky per channel,
re-posts it (deleting the previous) whenever the channel receives a configurable
number of new messages.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_premium, embed_success, is_admin

DEFAULT_THRESHOLD = 5  # re-post after this many new messages


class StickyMessages(commands.Cog):
    """Carl-style sticky messages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.counters: dict[int, int] = {}  # channel_id -> messages since last sticky

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or message.content is None:
            return
        rows = await get_db().fetch(
            "SELECT id, message_id FROM sticky_messages WHERE channel_id=$1",
            message.channel.id,
        )
        if not rows:
            return
        self.counters[message.channel.id] = self.counters.get(message.channel.id, 0) + 1
        if self.counters[message.channel.id] < DEFAULT_THRESHOLD:
            return
        self.counters[message.channel.id] = 0
        # Re-post all stickies in this channel (usually just one)
        for row in rows:
            old_id = int(row["message_id"])
            try:
                old = await message.channel.fetch_message(old_id)
                await old.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
            try:
                content_row = await get_db().fetchrow(
                    "SELECT content FROM sticky_messages WHERE id=$1", row["id"]
                )
                content = content_row["content"] if content_row else None
                if not content:
                    continue
                new_msg = await message.channel.send(content=content)
                await get_db().execute(
                    "UPDATE sticky_messages SET message_id=$1 WHERE id=$2",
                    new_msg.id, row["id"],
                )
            except discord.HTTPException:
                pass

    group = app_commands.Group(name="sticky", description="Sticky messages that re-post themselves.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="create", description="Create a sticky message in this channel.")
    @is_admin()
    async def create(self, interaction: discord.Interaction, message: str):
        existing = await get_db().fetchval(
            "SELECT id FROM sticky_messages WHERE channel_id=$1",
            interaction.channel.id,
        )
        if existing:
            await interaction.response.send_message(
                embed=embed_error("Sticky exists", "This channel already has a sticky. Remove it first with `/sticky remove`."),
                ephemeral=True,
            )
            return
        try:
            msg = await interaction.channel.send(message)
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed to post", str(exc)), ephemeral=True)
            return
        await get_db().execute(
            "INSERT INTO sticky_messages (guild_id, channel_id, message_id, content) VALUES ($1,$2,$3,$4)",
            interaction.guild.id, interaction.channel.id, msg.id, message,
        )
        await interaction.response.send_message(
            embed=embed_success("Sticky Created", f"Sticky message posted in {interaction.channel.mention}. It will re-post after every {DEFAULT_THRESHOLD} messages."),
            ephemeral=True,
        )

    @group.command(name="remove", description="Remove the sticky message from this channel.")
    @is_admin()
    async def remove(self, interaction: discord.Interaction):
        row = await get_db().fetchrow(
            "SELECT id, message_id FROM sticky_messages WHERE channel_id=$1",
            interaction.channel.id,
        )
        if not row:
            await interaction.response.send_message(embed=embed_error("No Sticky", "This channel has no sticky message."), ephemeral=True)
            return
        try:
            old = await interaction.channel.fetch_message(int(row["message_id"]))
            await old.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
        await get_db().execute("DELETE FROM sticky_messages WHERE id=$1", row["id"])
        self.counters.pop(interaction.channel.id, None)
        await interaction.response.send_message(embed=embed_success("Sticky Removed", "The sticky message has been removed."), ephemeral=True)

    @group.command(name="list", description="List all sticky messages in this server.")
    @is_admin()
    async def list(self, interaction: discord.Interaction):
        rows = await get_db().fetch(
            "SELECT channel_id, content FROM sticky_messages WHERE guild_id=$1",
            interaction.guild.id,
        )
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Stickies", "This server has no sticky messages."))
            return
        embed = embed_premium("Sticky Messages", f"**{len(rows)}** sticky message(s) active.")
        for r in rows[:15]:
            ch = interaction.guild.get_channel(int(r["channel_id"]))
            preview = (r["content"][:80] + "…") if len(r["content"]) > 80 else r["content"]
            embed.add_field(name=ch.mention if ch else f"`{r['channel_id']}`", value=preview, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StickyMessages(bot))
