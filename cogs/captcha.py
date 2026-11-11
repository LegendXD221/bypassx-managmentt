"""Captcha verification gate — Wick-style. New members must solve a captcha to gain access."""
from __future__ import annotations

import datetime as dt
import random
import string
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import get_db
from utils import ACCENT, DANGER, SUCCESS, WARN, embed_error, embed_info, embed_premium, embed_success, is_admin

DIFFICULTIES = {
    "easy":   (5, string.ascii_uppercase + string.digits),
    "medium": (6, string.ascii_uppercase + string.digits + "!@#$%"),
    "hard":   (8, string.ascii_letters + string.digits + "!@#$%^&*"),
}


class CaptchaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        btn = discord.ui.Button(label="Verify Now", style=discord.ButtonStyle.success, emoji="✅", custom_id="bypassx:captcha:start")
        btn.callback = self.start_captcha
        self.add_item(btn)

    async def start_captcha(self, interaction: discord.Interaction):
        cfg = await get_db().fetchrow("SELECT * FROM captcha_config WHERE guild_id=$1", interaction.guild.id)
        if not cfg or not cfg["enabled"]:
            await interaction.response.send_message(embed=embed_error("Captcha is not enabled."), ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member):
            return
        # already verified?
        if cfg["role_id"]:
            role = interaction.guild.get_role(int(cfg["role_id"]))
            if role and role in member.roles:
                await interaction.response.send_message(embed=embed_info("Already Verified", "You're already verified."), ephemeral=True)
                return
        length, alphabet = DIFFICULTIES.get(cfg["difficulty"], DIFFICULTIES["medium"])
        answer = "".join(random.choice(alphabet) for _ in range(length))
        await get_db().execute(
            "INSERT INTO captcha_pending (user_id, guild_id, answer) VALUES ($1,$2,$3) ON CONFLICT (user_id, guild_id) DO UPDATE SET answer=$3, attempts=0, created_at=NOW()",
            member.id, interaction.guild.id, answer,
        )
        # build a tasteful captcha embed
        embed = discord.Embed(title="Verification Required", color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.description = (
            f"To verify, type the code below in this DM or in the verification channel using `/verify answer`:\n\n"
            f"```\n{answer}\n```\n\n"
            f"You have **3 attempts**. After that you'll need a new code."
        )
        embed.set_footer(text="BypassX · Captcha")
        # try DM first
        try:
            await member.send(embed=embed)
            await interaction.response.send_message(embed=embed_success("Captcha Sent", "Check your DMs for the verification code, then use `/verify answer`."), ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed, ephemeral=True)


class Captcha(commands.Cog):
    """Wick-style captcha verification."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.kick_loop.start()

    @tasks.loop(minutes=2)
    async def kick_loop(self) -> None:
        rows = await get_db().fetch("SELECT * FROM captcha_config WHERE enabled=TRUE AND kick_unverified_minutes > 0")
        for cfg in rows:
            guild = self.bot.get_guild(int(cfg["guild_id"]))
            if guild is None:
                continue
            cutoff = discord.utils.utcnow() - dt.timedelta(minutes=int(cfg["kick_unverified_minutes"]))
            role = guild.get_role(int(cfg["role_id"])) if cfg["role_id"] else None
            for member in guild.members:
                if member.bot:
                    continue
                if role and role in member.roles:
                    continue
                if member.joined_at and member.joined_at < cutoff and not member.guild_permissions.manage_guild:
                    try:
                        await member.kick(reason="Unverified — captcha timeout")
                    except discord.HTTPException:
                        pass

    @kick_loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await get_db().fetchrow("SELECT * FROM captcha_config WHERE guild_id=$1 AND enabled=TRUE", member.guild.id)
        if not cfg:
            return
        if not cfg["channel_id"]:
            return
        channel = member.guild.get_channel(int(cfg["channel_id"]))
        if channel is None:
            return
        embed = discord.Embed(title="Welcome — Verification Required", color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.description = (
            f"Welcome to **{member.guild.name}**, {member.mention}.\n\n"
            f"To gain access to the server, please click the **Verify Now** button below."
        )
        embed.set_footer(text="BypassX · Captcha")
        try:
            await channel.send(content=member.mention, embed=embed, view=CaptchaView(), allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException:
            pass

    group = app_commands.Group(name="captcha", description="Configure captcha verification.", default_permissions=discord.Permissions(administrator=True))

    @group.command(name="setup", description="Configure the captcha verification gate.")
    @is_admin()
    async def setup(self, interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel, difficulty: str = "medium", kick_unverified_minutes: app_commands.Range[int, 0, 10080] = 0):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("That role is above me."), ephemeral=True)
            return
        if difficulty not in DIFFICULTIES:
            await interaction.response.send_message(embed=embed_error("Difficulty must be easy, medium, or hard."), ephemeral=True)
            return
        await get_db().execute(
            """
            INSERT INTO captcha_config (guild_id, enabled, role_id, channel_id, difficulty, kick_unverified_minutes)
            VALUES ($1,TRUE,$2,$3,$4,$5)
            ON CONFLICT (guild_id) DO UPDATE SET enabled=TRUE, role_id=$2, channel_id=$3, difficulty=$4, kick_unverified_minutes=$5
            """,
            interaction.guild.id, role.id, channel.id, difficulty, kick_unverified_minutes,
        )
        await interaction.response.send_message(
            embed=embed_success("Captcha Configured", f"Role: {role.mention}\nChannel: {channel.mention}\nDifficulty: **{difficulty}**\nAuto-kick after: {kick_unverified_minutes if kick_unverified_minutes else 'disabled (0)'} minutes")
        )

    @group.command(name="disable", description="Disable captcha verification.")
    @is_admin()
    async def disable(self, interaction: discord.Interaction):
        await get_db().execute("UPDATE captcha_config SET enabled=FALSE WHERE guild_id=$1", interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Captcha Disabled", "New members will no longer be challenged."))

    verify = app_commands.Group(name="verify-captcha", description="Captcha verification commands.", default_permissions=None)

    @verify.command(name="answer", description="Submit your captcha answer.")
    async def answer(self, interaction: discord.Interaction, code: str):
        row = await get_db().fetchrow("SELECT answer, attempts FROM captcha_pending WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
        if not row:
            await interaction.response.send_message(embed=embed_error("No pending captcha.", "Click the Verify Now button in the verification channel to start."), ephemeral=True)
            return
        if int(row["attempts"]) >= 3:
            await get_db().execute("DELETE FROM captcha_pending WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
            await interaction.response.send_message(embed=embed_error("Out of attempts", "Click Verify Now to generate a new code."), ephemeral=True)
            return
        if code.strip().upper() == row["answer"].upper():
            cfg = await get_db().fetchrow("SELECT role_id FROM captcha_config WHERE guild_id=$1", interaction.guild.id)
            if cfg and cfg["role_id"]:
                role = interaction.guild.get_role(int(cfg["role_id"]))
                if role:
                    try:
                        await interaction.user.add_roles(role, reason="Verified via captcha")
                    except discord.HTTPException:
                        pass
            await get_db().execute("DELETE FROM captcha_pending WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
            await interaction.response.send_message(embed=embed_success("Verified", f"Welcome to **{interaction.guild.name}**! You now have full access."), ephemeral=True)
        else:
            await get_db().execute("UPDATE captcha_pending SET attempts = attempts + 1 WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
            remaining = 3 - int(row["attempts"]) - 1
            await interaction.response.send_message(embed=embed_error("Incorrect", f"That code doesn't match. {remaining} attempt(s) remaining."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Captcha(bot))
