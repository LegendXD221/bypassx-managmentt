"""Quotes — save memorable messages and retrieve them later."""
from __future__ import annotations

import datetime as dt
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import ACCENT, GOLD, embed_error, embed_info, embed_premium, embed_success, is_admin


class Quotes(commands.Cog):
    """Quote storage and retrieval — Carl-bot inspired."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="quote", description="Save & view quotes.", default_permissions=None)

    @group.command(name="add", description="Save a quote from a message (use message link or text).")
    async def add(self, interaction: discord.Interaction, message: str, author: Optional[discord.Member] = None):
        if len(message) > 1500:
            await interaction.response.send_message(embed=embed_error("Quote too long."), ephemeral=True)
            return
        author_name = author.mention if author else "Unknown"
        author_id = author.id if author else None
        await get_db().execute(
            "INSERT INTO quotes (guild_id, quoter_id, author_id, author_name, content, channel_id) VALUES ($1,$2,$3,$4,$5,$6)",
            interaction.guild.id, interaction.user.id, author_id, author_name, message, interaction.channel.id,
        )
        await interaction.response.send_message(embed=embed_success("Quote Saved", f"Added quote from **{author_name}**."))

    @group.command(name="random", description="Show a random quote from this server.")
    async def random_quote(self, interaction: discord.Interaction):
        row = await get_db().fetchrow("SELECT * FROM quotes WHERE guild_id=$1 ORDER BY RANDOM() LIMIT 1", interaction.guild.id)
        if not row:
            await interaction.response.send_message(embed=embed_info("No Quotes", "Use `/quote add` to add some."))
            return
        embed = discord.Embed(description=f"\"{row['content']}\"", color=GOLD, timestamp=row["created_at"])
        embed.set_author(name=row["author_name"] or "Unknown")
        embed.set_footer(text=f"BypassX · Quote #{row['id']} · saved by <@{row['quoter_id']}>")
        await interaction.response.send_message(embed=embed)

    @group.command(name="view", description="View a specific quote by ID.")
    async def view(self, interaction: discord.Interaction, quote_id: int):
        row = await get_db().fetchrow("SELECT * FROM quotes WHERE guild_id=$1 AND id=$2", interaction.guild.id, quote_id)
        if not row:
            await interaction.response.send_message(embed=embed_error("Quote not found."), ephemeral=True)
            return
        embed = discord.Embed(description=f"\"{row['content']}\"", color=ACCENT, timestamp=row["created_at"])
        embed.set_author(name=row["author_name"] or "Unknown")
        embed.set_footer(text=f"BypassX · Quote #{row['id']}")
        await interaction.response.send_message(embed=embed)

    @group.command(name="list", description="List recent quotes.")
    async def list(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT id, author_name, content FROM quotes WHERE guild_id=$1 ORDER BY id DESC LIMIT 15", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Quotes", "No quotes saved yet."))
            return
        embed = embed_premium("Recent Quotes")
        for r in rows[:15]:
            preview = (r["content"][:80] + "…") if len(r["content"]) > 80 else r["content"]
            embed.add_field(name=f"#{r['id']} · {r['author_name']}", value=preview, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="delete", description="Delete a quote by ID.")
    @is_admin()
    async def delete(self, interaction: discord.Interaction, quote_id: int):
        await get_db().execute("DELETE FROM quotes WHERE guild_id=$1 AND id=$2", interaction.guild.id, quote_id)
        await interaction.response.send_message(embed=embed_success("Quote Deleted", f"Removed quote #{quote_id}."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quotes(bot))
