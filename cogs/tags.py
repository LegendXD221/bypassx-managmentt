"""Tags — server-specific custom commands/text snippets."""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_success, is_admin


class Tags(commands.Cog):
    """Create, edit, and call custom tags."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="tag", description="Display a saved tag.")
    @app_commands.describe(name="Tag name")
    @app_commands.guild_only()
    async def tag(self, interaction: discord.Interaction, name: str):
        row = await get_db().fetchrow("SELECT content, owner_id, uses FROM tags WHERE guild_id=$1 AND name=$2", interaction.guild.id, name.lower())
        if not row:
            await interaction.response.send_message(embed=embed_error("Tag not found.", f"Use `/tag create` to make it."), ephemeral=True)
            return
        await get_db().execute("UPDATE tags SET uses = uses + 1 WHERE guild_id=$1 AND name=$2", interaction.guild.id, name.lower())
        await interaction.response.send_message(content=row["content"])

    @app_commands.command(name="tagcreate", description="Create a custom tag.")
    @app_commands.describe(name="Tag name (no spaces)", content="Tag content (text/markdown)")
    @app_commands.guild_only()
    async def tag_create(self, interaction: discord.Interaction, name: str, content: str):
        name = name.strip().lower()
        if " " in name or len(name) > 50:
            await interaction.response.send_message(embed=embed_error("Tag name can't contain spaces and must be ≤50 chars."), ephemeral=True)
            return
        if len(content) > 1900:
            await interaction.response.send_message(embed=embed_error("Tag content too long (max 1900 chars)."), ephemeral=True)
            return
        try:
            await get_db().execute(
                "INSERT INTO tags (guild_id, name, content, owner_id) VALUES ($1,$2,$3,$4)",
                interaction.guild.id, name, content, interaction.user.id,
            )
        except asyncpg_unique_violation:  # type: ignore[name-defined]
            await interaction.response.send_message(embed=embed_error("A tag with that name already exists."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Tag Created", f"Tag `{name}` has been saved. Use `/tag name:{name}` to display it."))

    @app_commands.command(name="tagdelete", description="Delete a tag (owner or admin only).")
    @app_commands.describe(name="Tag name")
    @app_commands.guild_only()
    async def tag_delete(self, interaction: discord.Interaction, name: str):
        row = await get_db().fetchrow("SELECT owner_id FROM tags WHERE guild_id=$1 AND name=$2", interaction.guild.id, name.lower())
        if not row:
            await interaction.response.send_message(embed=embed_error("Tag not found."), ephemeral=True)
            return
        is_owner = row["owner_id"] == interaction.user.id
        is_admin_user = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_guild
        if not (is_owner or is_admin_user):
            await interaction.response.send_message(embed=embed_error("You can only delete your own tags (or be an admin)."), ephemeral=True)
            return
        await get_db().execute("DELETE FROM tags WHERE guild_id=$1 AND name=$2", interaction.guild.id, name.lower())
        await interaction.response.send_message(embed=embed_success("Tag Deleted", f"Tag `{name}` has been removed."))

    @app_commands.command(name="taglist", description="List all tags in this server.")
    @app_commands.guild_only()
    async def tag_list(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT name, uses FROM tags WHERE guild_id=$1 ORDER BY name", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Tags", "No tags have been created in this server yet."))
            return
        listing = "\n".join(f"`{r['name']}` — {r['uses']} uses" for r in rows[:30])
        embed = embed_info(f"Tags — {interaction.guild.name}", listing)
        embed.set_footer(text=f"Showing {min(len(rows), 30)} of {len(rows)} tags")
        await interaction.response.send_message(embed=embed)


# Capture asyncpg's UniqueViolation without importing the module at the top
try:
    import asyncpg  # noqa: E402
    asyncpg_unique_violation = asyncpg.UniqueViolationError
except Exception:  # noqa: BLE001
    asyncpg_unique_violation = Exception  # fallback so the except clause still works


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tags(bot))
