"""Auto-responder — trigger/response pairs (Carl-bot style)."""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_premium, embed_success, is_admin


class AutoResponder(commands.Cog):
    """Trigger-based auto responses for community servers."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or not message.content:
            return
        rows = await get_db().fetch("SELECT trigger, response, match_type, id FROM auto_responses WHERE guild_id=$1", message.guild.id)
        if not rows:
            return
        content_lower = message.content.lower()
        for r in rows:
            trigger = r["trigger"].lower()
            match_type = r["match_type"]
            hit = False
            if match_type == "exact":
                hit = content_lower == trigger
            elif match_type == "startswith":
                hit = content_lower.startswith(trigger)
            elif match_type == "regex":
                import re
                try:
                    hit = bool(re.search(trigger, message.content, re.IGNORECASE))
                except re.error:
                    continue
            else:  # contains
                hit = trigger in content_lower
            if hit:
                try:
                    await message.channel.send(r["response"].replace("{user}", message.author.mention).replace("{channel}", message.channel.mention))
                    await get_db().execute("UPDATE auto_responses SET uses = uses + 1 WHERE id=$1", r["id"])
                except discord.HTTPException:
                    pass
                break  # only fire the first match

    group = app_commands.Group(name="autoresponder", description="Configure trigger/response pairs.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="add", description="Add an auto-response.")
    @is_admin()
    async def add(self, interaction: discord.Interaction, trigger: str, response: str, match_type: str = "contains"):
        if match_type not in {"contains", "exact", "startswith", "regex"}:
            await interaction.response.send_message(embed=embed_error("Match type must be: contains, exact, startswith, or regex."), ephemeral=True)
            return
        try:
            await get_db().execute(
                "INSERT INTO auto_responses (guild_id, trigger, response, match_type, created_by) VALUES ($1,$2,$3,$4,$5)",
                interaction.guild.id, trigger, response, match_type, interaction.user.id,
            )
        except Exception:
            await interaction.response.send_message(embed=embed_error("A response with that trigger already exists."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Response Added", f"When a message **{match_type}** `{trigger}`, I'll respond with your message."))

    @group.command(name="remove", description="Remove an auto-response by trigger.")
    @is_admin()
    async def remove(self, interaction: discord.Interaction, trigger: str):
        await get_db().execute("DELETE FROM auto_responses WHERE guild_id=$1 AND trigger=$2", interaction.guild.id, trigger)
        await interaction.response.send_message(embed=embed_success("Response Removed", f"Auto-response for `{trigger}` deleted."))

    @group.command(name="list", description="List all auto-responses.")
    async def list(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT trigger, match_type, uses FROM auto_responses WHERE guild_id=$1 ORDER BY trigger", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Responses", "No auto-responses configured."))
            return
        embed = embed_premium("Auto-Responses", f"**{len(rows)}** response(s) configured.")
        for r in rows[:25]:
            embed.add_field(name=f"`{r['trigger']}`", value=f"Match: {r['match_type']} · Uses: {r['uses']}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoResponder(bot))
