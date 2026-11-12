"""Anti-nuke whitelist — manage users exempt from the security module."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_premium, embed_success, is_admin


class AntiNukeWhitelist(commands.Cog):
    """Manage the security/anti-nuke whitelist."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="antinuke", description="Anti-nuke configuration.", default_permissions=discord.Permissions(administrator=True))

    @group.command(name="whitelist", description="Whitelist a user from anti-nuke actions.")
    @is_admin()
    async def whitelist_add(self, interaction: discord.Interaction, member: discord.Member):
        await get_db().execute(
            "INSERT INTO anti_nuke_whitelist (guild_id, user_id, added_by) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
            interaction.guild.id, member.id, interaction.user.id,
        )
        await interaction.response.send_message(embed=embed_success("Whitelisted", f"{member.mention} is now exempt from anti-nuke."))

    @group.command(name="unwhitelist", description="Remove a user from the anti-nuke whitelist.")
    @is_admin()
    async def whitelist_remove(self, interaction: discord.Interaction, member: discord.Member):
        await get_db().execute("DELETE FROM anti_nuke_whitelist WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed_success("Removed", f"{member.mention} is no longer whitelisted."))

    @group.command(name="whitelistlist", description="List all whitelisted users.")
    @is_admin()
    async def whitelist_list(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT user_id FROM anti_nuke_whitelist WHERE guild_id=$1 ORDER BY user_id", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("Whitelist Empty", "No whitelisted users."))
            return
        embed = embed_premium("Anti-Nuke Whitelist", f"**{len(rows)}** whitelisted users:")
        for r in rows[:25]:
            member = interaction.guild.get_member(int(r["user_id"]))
            embed.add_field(name=f"`{r['user_id']}`", value=member.mention if member else "Not in server", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="check", description="Check if a user is whitelisted.")
    async def check(self, interaction: discord.Interaction, member: discord.Member):
        row = await get_db().fetchrow("SELECT added_by FROM anti_nuke_whitelist WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        if not row:
            await interaction.response.send_message(embed=embed_info("Not Whitelisted", f"{member.mention} is **not** whitelisted."))
            return
        embed = embed_premium("Whitelisted", f"{member.mention} is whitelisted by <@{row['added_by']}>.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiNukeWhitelist(bot))
