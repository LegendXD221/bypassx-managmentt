"""Admin configuration — set channels, roles, prefixes, enable/disable modules."""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from database import get_db
from utils import embed_error, embed_info, embed_success, is_admin


class Admin(commands.Cog):
    """Owner & admin commands for configuring the bot per-guild."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- owner only -------------------------------------------

    @app_commands.command(name="reload", description="(Owner) Reload a cog.")
    @app_commands.describe(cog="Cog name, e.g. moderation")
    async def reload_cog(self, interaction: discord.Interaction, cog: str):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await interaction.response.send_message(embed=embed_success("Reloaded", f"Cog `{cog}` reloaded."))
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(embed=embed_error("Reload failed", str(exc)), ephemeral=True)

    @app_commands.command(name="sync", description="(Owner) Force sync slash commands.")
    async def sync_cmd(self, interaction: discord.Interaction):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        synced = await self.bot.tree.sync()
        await interaction.followup.send(embed=embed_success("Synced", f"Synced **{len(synced)}** commands globally."), ephemeral=True)

    @app_commands.command(name="shutdown", description="(Owner) Gracefully shut down the bot.")
    async def shutdown(self, interaction: discord.Interaction):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_warn("Shutting Down", "Bot is going offline..."))
        import asyncio
        await asyncio.sleep(2)
        await self.bot.close()

    # ---------------- guild config -----------------------------------------

    group = app_commands.Group(name="config", description="Configure BypassX for this server.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="set", description="Set a config option for this server.")
    @is_admin()
    async def set_field(self, interaction: discord.Interaction, field: str, role: Optional[discord.Role] = None, channel: Optional[discord.TextChannel] = None):
        field = field.lower()
        mapping = {
            "log_channel": ("log_channel_id", "channel"),
            "modlog_channel": ("mod_log_channel_id", "channel"),
            "welcome_channel": ("welcome_channel_id", "channel"),
            "auto_role": ("auto_role_id", "role"),
            "mute_role": ("mute_role_id", "role"),
            "verification_role": ("verification_role_id", "role"),
            "ticket_category": ("ticket_category_id", "channel"),
            "ticket_staff_role": ("ticket_staff_role_id", "role"),
        }
        if field not in mapping:
            await interaction.response.send_message(embed=embed_error("Unknown field", f"Available: {', '.join(mapping)}"), ephemeral=True)
            return
        column, kind = mapping[field]
        if kind == "role" and role is None:
            await interaction.response.send_message(embed=embed_error("You must provide a role for this field."), ephemeral=True)
            return
        if kind == "channel" and channel is None:
            await interaction.response.send_message(embed=embed_error("You must provide a channel for this field."), ephemeral=True)
            return
        value = (role or channel).id
        await get_db().set_guild_field(interaction.guild.id, column, value)
        await interaction.response.send_message(embed=embed_success("Config Updated", f"`{field}` set to {(role or channel).mention}."))

    @group.command(name="view", description="View current configuration for this server.")
    @is_admin()
    async def view(self, interaction: discord.Interaction):
        cfg = await get_db().get_guild_config(interaction.guild.id)
        embed = embed_info(f"BypassX Config — {interaction.guild.name}", "")
        def role_mention(rid):
            r = interaction.guild.get_role(int(rid)) if rid else None
            return r.mention if r else "*(not set)*"
        def channel_mention(cid):
            c = interaction.guild.get_channel(int(cid)) if cid else None
            return c.mention if c else "*(not set)*"
        embed.add_field(name="Log Channel", value=channel_mention(cfg["log_channel_id"]), inline=True)
        embed.add_field(name="Mod-Log Channel", value=channel_mention(cfg["mod_log_channel_id"]), inline=True)
        embed.add_field(name="Welcome Channel", value=channel_mention(cfg["welcome_channel_id"]), inline=True)
        embed.add_field(name="Auto Role", value=role_mention(cfg["auto_role_id"]), inline=True)
        embed.add_field(name="Mute Role", value=role_mention(cfg["mute_role_id"]), inline=True)
        embed.add_field(name="Verification Role", value=role_mention(cfg["verification_role_id"]), inline=True)
        embed.add_field(name="Ticket Category", value=channel_mention(cfg["ticket_category_id"]), inline=True)
        embed.add_field(name="Ticket Staff Role", value=role_mention(cfg["ticket_staff_role_id"]), inline=True)
        embed.add_field(name="Anti-Spam", value="✅" if cfg["anti_spam_enabled"] else "❌", inline=True)
        embed.add_field(name="Word Filter", value="✅" if cfg["word_filter_enabled"] else "❌", inline=True)
        embed.add_field(name="Link Filter", value="✅" if cfg["link_filter_enabled"] else "❌", inline=True)
        embed.add_field(name="Anti-Raid", value="✅" if cfg["anti_raid_enabled"] else "❌", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="reset", description="Reset all configuration for this server (cannot be undone).")
    @is_admin()
    async def reset(self, interaction: discord.Interaction):
        await get_db().execute("DELETE FROM guild_config WHERE guild_id=$1", interaction.guild.id)
        await get_db().ensure_guild(interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Config Reset", "All settings have been reset to defaults."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
