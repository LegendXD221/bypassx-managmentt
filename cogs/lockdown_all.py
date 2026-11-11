"""Server-wide lockdown — lock & unlock all text channels at once (Wick-style)."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_premium, embed_success, embed_warn, is_admin, send_modlog


class LockdownAll(commands.Cog):
    """Lock down the entire server with one command."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _lock_all(self, guild: discord.Guild, reason: str, exclude: list[int]) -> int:
        locked = 0
        for ch in guild.text_channels:
            if ch.id in exclude:
                continue
            try:
                ow = ch.overwrites_for(guild.default_role)
                if ow.send_messages is False:
                    continue
                ow.send_messages = False
                await ch.set_permissions(guild.default_role, overwrite=ow, reason=f"Server lockdown: {reason}")
                locked += 1
            except discord.HTTPException:
                pass
        await get_db().execute(
            "INSERT INTO guild_lockdown_state (guild_id, locked, locked_at) VALUES ($1,TRUE,NOW()) ON CONFLICT (guild_id) DO UPDATE SET locked=TRUE, locked_at=NOW()",
            guild.id,
        )
        return locked

    async def _unlock_all(self, guild: discord.Guild) -> int:
        unlocked = 0
        for ch in guild.text_channels:
            try:
                ow = ch.overwrites_for(guild.default_role)
                if ow.send_messages is False:
                    ow.send_messages = None
                    await ch.set_permissions(guild.default_role, overwrite=ow, reason="Server unlock")
                    unlocked += 1
            except discord.HTTPException:
                pass
        await get_db().execute(
            "INSERT INTO guild_lockdown_state (guild_id, locked) VALUES ($1,FALSE) ON CONFLICT (guild_id) DO UPDATE SET locked=FALSE, locked_at=NULL",
            guild.id,
        )
        return unlocked

    @app_commands.command(name="lockdownall", description="Lock every text channel in the server.")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    async def lockdown_all(self, interaction: discord.Interaction, reason: str = "Server lockdown", exclude_category: Optional[discord.CategoryChannel] = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        exclude_ids = [c.id for c in exclude_category.text_channels] if exclude_category else []
        # always exclude mod-log channels so staff can still coordinate
        cfg = await get_db().get_guild_config(interaction.guild.id)
        for col in ["log_channel_id", "mod_log_channel_id"]:
            if cfg and cfg.get(col):
                exclude_ids.append(int(cfg[col]))
        # also exclude staff channels
        n = await self._lock_all(interaction.guild, reason, list(set(exclude_ids)))
        await interaction.followup.send(embed=embed_warn("Server Locked Down", f"Locked **{n}** text channels.\nReason: {reason}"), ephemeral=False)
        await send_modlog(interaction.guild, action="server lockdown", moderator=interaction.user, reason=reason, details={"Channels": n})

    @app_commands.command(name="unlockall", description="Unlock every text channel in the server.")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    async def unlock_all(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        n = await self._unlock_all(interaction.guild)
        await interaction.followup.send(embed=embed_success("Server Unlocked", f"Unlocked **{n}** text channels."), ephemeral=False)
        await send_modlog(interaction.guild, action="server unlock", moderator=interaction.user, details={"Channels": n})

    @app_commands.command(name="lockdownstatus", description="Show whether the server is currently locked down.")
    async def lockdown_status(self, interaction: discord.Interaction):
        row = await get_db().fetchrow("SELECT locked, locked_at FROM guild_lockdown_state WHERE guild_id=$1", interaction.guild.id)
        if not row or not row["locked"]:
            await interaction.response.send_message(embed=embed_info("Lockdown Status", "Server is **not** locked down."))
            return
        embed = embed_warn("Lockdown Active", f"Locked since <t:{int(row['locked_at'].timestamp())}:R>.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LockdownAll(bot))
