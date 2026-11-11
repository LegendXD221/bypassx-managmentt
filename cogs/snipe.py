"""Snipe — retrieve recently deleted or edited messages."""
from __future__ import annotations

import datetime as dt
from collections import deque
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import embed_error, embed_info, embed_premium, embed_warn


class SnipeEntry:
    __slots__ = ("author", "content", "channel", "deleted_at", "attachment_urls")

    def __init__(self, message: discord.Message):
        self.author = message.author
        self.content = message.content or ""
        self.channel = message.channel
        self.deleted_at = dt.datetime.now(dt.UTC)
        self.attachment_urls = [a.url for a in message.attachments][:3]


class EditEntry:
    __slots__ = ("author", "before", "after", "channel", "edited_at")

    def __init__(self, before: discord.Message, after: discord.Message):
        self.author = before.author
        self.before = before.content or ""
        self.after = after.content or ""
        self.channel = before.channel
        self.edited_at = dt.datetime.now(dt.UTC)


class Snipe(commands.Cog):
    """Snipe deleted & edited messages — Carl-bot style."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.deleted: dict[int, deque[SnipeEntry]] = {}  # channel_id -> recent deletes
        self.edited: dict[int, deque[EditEntry]] = {}
        self.max = 25

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        dq = self.deleted.setdefault(message.channel.id, deque(maxlen=self.max))
        dq.append(SnipeEntry(message))

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild is None or before.author.bot or before.content == after.content:
            return
        dq = self.edited.setdefault(before.channel.id, deque(maxlen=self.max))
        dq.append(EditEntry(before, after))

    @app_commands.command(name="snipe", description="Retrieve the most recently deleted message in this channel.")
    @app_commands.guild_only()
    async def snipe(self, interaction: discord.Interaction, index: app_commands.Range[int, 1, 25] = 1):
        dq = self.deleted.get(interaction.channel.id)
        if not dq or index > len(dq):
            await interaction.response.send_message(embed=embed_error("Nothing to Snipe", "No deleted messages in this channel recently."), ephemeral=True)
            return
        entry = list(dq)[-index]
        embed = discord.Embed(description=entry.content or "*(empty)*", color=0x6366F1, timestamp=entry.deleted_at)
        embed.set_author(name=str(entry.author), icon_url=entry.author.display_avatar.url if entry.author.display_avatar else None)
        embed.set_footer(text=f"BypassX · Snipe  •  #{index} of {len(dq)}")
        if entry.attachment_urls:
            embed.set_image(url=entry.attachment_urls[0])
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="editsnipe", description="Retrieve the most recently edited message.")
    @app_commands.guild_only()
    async def editsnipe(self, interaction: discord.Interaction, index: app_commands.Range[int, 1, 25] = 1):
        dq = self.edited.get(interaction.channel.id)
        if not dq or index > len(dq):
            await interaction.response.send_message(embed=embed_error("Nothing to Snipe", "No recent edits in this channel."), ephemeral=True)
            return
        entry = list(dq)[-index]
        embed = discord.Embed(color=0xF5B544, timestamp=entry.edited_at)
        embed.set_author(name=str(entry.author), icon_url=entry.author.display_avatar.url if entry.author.display_avatar else None)
        embed.add_field(name="Before", value=entry.before[:1024] or "*(empty)*", inline=False)
        embed.add_field(name="After", value=entry.after[:1024] or "*(empty)*", inline=False)
        embed.set_footer(text=f"BypassX · Edit Snipe  •  #{index} of {len(dq)}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clearsnipe", description="Clear the snipe cache in this channel (admin only).")
    @app_commands.default_permissions(manage_messages=True)
    async def clearsnipe(self, interaction: discord.Interaction):
        self.deleted.pop(interaction.channel.id, None)
        self.edited.pop(interaction.channel.id, None)
        await interaction.response.send_message(embed=embed_warn("Snipe Cleared", "Snipe cache for this channel has been wiped."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Snipe(bot))
