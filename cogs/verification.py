"""Verification gate — members click a button to gain access."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_success, is_admin

VERIFY_VIEW_ID = "bypassx:verify:button"


class VerifyView(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id
        btn = discord.ui.Button(label="Verify", style=discord.ButtonStyle.success, emoji="✅", custom_id=VERIFY_VIEW_ID)
        self.add_item(btn)


class Verification(commands.Cog):
    """Verification gate with button."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.data is None or interaction.data.get("component_type") != 2:
            return
        if interaction.data.get("custom_id") != VERIFY_VIEW_ID:
            return
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return
        cfg = await get_db().fetchrow("SELECT role_id FROM verification_config WHERE guild_id=$1", interaction.guild.id)
        if not cfg:
            return
        role = interaction.guild.get_role(int(cfg["role_id"]))
        if role is None or role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("Verification role is misconfigured. Please contact staff."), ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message(embed=embed_info("Already Verified", "You're already verified."), ephemeral=True)
            return
        try:
            await interaction.user.add_roles(role, reason="Verified via button")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I can't assign the verification role."), ephemeral=True)
            return
        await get_db().execute(
            "INSERT INTO user_verification (user_id, guild_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
            interaction.user.id, interaction.guild.id,
        )
        await interaction.response.send_message(embed=embed_success("Verified", f"Welcome to **{interaction.guild.name}**, {interaction.user.mention}! You're now verified."), ephemeral=True)

    group = app_commands.Group(name="verify", description="Verification gate configuration.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="setup", description="Post a verification panel and configure the verified role.")
    @is_admin()
    async def setup(self, interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel, title: str = "Verify to Access the Server", description: str = "Click the button below to verify and gain full access to the server."):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("That role is above me."), ephemeral=True)
            return
        embed = discord.Embed(title=title, description=description, color=0x57F287, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX Management • Verification System")
        view = VerifyView(role.id)
        msg = await channel.send(embed=embed, view=view)
        await get_db().execute(
            """
            INSERT INTO verification_config (guild_id, role_id, channel_id, message_id, verification_type)
            VALUES ($1,$2,$3,$4,'button')
            ON CONFLICT (guild_id) DO UPDATE SET role_id=$2, channel_id=$3, message_id=$4
            """,
            interaction.guild.id, role.id, channel.id, msg.id,
        )
        await interaction.response.send_message(embed=embed_success("Verification Configured", f"Panel posted in {channel.mention}. Members will get {role.mention} when they click Verify."))

    @group.command(name="status", description="Show verification config for this server.")
    @is_admin()
    async def status(self, interaction: discord.Interaction):
        cfg = await get_db().fetchrow("SELECT * FROM verification_config WHERE guild_id=$1", interaction.guild.id)
        if not cfg:
            await interaction.response.send_message(embed=embed_error("Verification is not set up. Use `/verify setup`."), ephemeral=True)
            return
        role = interaction.guild.get_role(int(cfg["role_id"]))
        channel = interaction.guild.get_channel(int(cfg["channel_id"])) if cfg["channel_id"] else None
        embed = embed_info("Verification Status", "Current configuration:")
        embed.add_field(name="Verified Role", value=role.mention if role else "missing")
        embed.add_field(name="Channel", value=channel.mention if channel else "missing")
        embed.add_field(name="Type", value=cfg["verification_type"])
        await interaction.response.send_message(embed=embed)

    @group.command(name="disable", description="Remove verification config (does not delete the message).")
    @is_admin()
    async def disable(self, interaction: discord.Interaction):
        await get_db().execute("DELETE FROM verification_config WHERE guild_id=$1", interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Verification Disabled", "Members can no longer verify via the button. Delete the panel message manually if desired."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Verification(bot))
