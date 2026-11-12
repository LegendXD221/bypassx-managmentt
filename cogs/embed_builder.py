"""Embed builder — premium interactive embed creator with save/load."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import ACCENT, embed_error, embed_info, embed_premium, embed_success, is_admin


class EmbedBuilder(commands.Cog):
    """Interactive embed builder with preset save/load."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="embed", description="Build and send custom embeds.", default_permissions=discord.Permissions(manage_messages=True))

    @group.command(name="send", description="Send a custom embed with all the bells & whistles.")
    @is_admin()
    async def send(self, interaction: discord.Interaction, title: str, description: str, color: str = "#6366F1", footer: str = None, image_url: str = None, thumbnail_url: str = None, author_name: str = None, channel: discord.TextChannel = None):
        try:
            color_int = int(color.lstrip("#"), 16)
        except (ValueError, TypeError):
            color_int = ACCENT
        embed = discord.Embed(title=title, description=description, color=color_int, timestamp=discord.utils.utcnow())
        if footer:
            embed.set_footer(text=footer)
        if image_url:
            embed.set_image(url=image_url)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        if author_name:
            embed.set_author(name=author_name)
        target = channel or interaction.channel
        try:
            await target.send(embed=embed)
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Embed Sent", f"Sent to {target.mention}."), ephemeral=True)

    @group.command(name="save", description="Save an embed preset by name for re-use.")
    @is_admin()
    async def save(self, interaction: discord.Interaction, name: str, title: str, description: str, color: str = "#6366F1", footer: str = None, image_url: str = None, thumbnail_url: str = None, author_name: str = None):
        try:
            color_int = int(color.lstrip("#"), 16)
        except (ValueError, TypeError):
            color_int = ACCENT
        await get_db().execute(
            """
            INSERT INTO saved_embeds (guild_id, name, title, description, color, footer, image_url, thumbnail_url, author_name, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (guild_id, name) DO UPDATE SET title=$3, description=$4, color=$5, footer=$6, image_url=$7, thumbnail_url=$8, author_name=$9
            """,
            interaction.guild.id, name.lower(), title, description, color_int, footer, image_url, thumbnail_url, author_name, interaction.user.id,
        )
        await interaction.response.send_message(embed=embed_success("Embed Saved", f"Preset `{name}` saved. Use `/embed post` to send it."))

    @group.command(name="post", description="Post a saved embed preset.")
    @is_admin()
    async def post(self, interaction: discord.Interaction, name: str, channel: discord.TextChannel = None):
        row = await get_db().fetchrow("SELECT * FROM saved_embeds WHERE guild_id=$1 AND name=$2", interaction.guild.id, name.lower())
        if not row:
            await interaction.response.send_message(embed=embed_error("Preset Not Found", "Use `/embed list` to see saved presets."), ephemeral=True)
            return
        embed = discord.Embed(title=row["title"] or None, description=row["description"] or None, color=row["color"] or ACCENT, timestamp=discord.utils.utcnow())
        if row["footer"]:
            embed.set_footer(text=row["footer"])
        if row["image_url"]:
            embed.set_image(url=row["image_url"])
        if row["thumbnail_url"]:
            embed.set_thumbnail(url=row["thumbnail_url"])
        if row["author_name"]:
            embed.set_author(name=row["author_name"])
        target = channel or interaction.channel
        try:
            await target.send(embed=embed)
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Embed Posted", f"Preset `{name}` sent to {target.mention}."), ephemeral=True)

    @group.command(name="list", description="List all saved embed presets.")
    async def list(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT name, title FROM saved_embeds WHERE guild_id=$1 ORDER BY name", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Presets", "No embeds saved."))
            return
        embed = embed_premium("Saved Embeds", f"**{len(rows)}** preset(s):")
        for r in rows[:25]:
            embed.add_field(name=r["name"], value=r["title"] or "—", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="delete", description="Delete a saved embed preset.")
    @is_admin()
    async def delete(self, interaction: discord.Interaction, name: str):
        await get_db().execute("DELETE FROM saved_embeds WHERE guild_id=$1 AND name=$2", interaction.guild.id, name.lower())
        await interaction.response.send_message(embed=embed_success("Preset Deleted", f"`{name}` has been removed."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EmbedBuilder(bot))
