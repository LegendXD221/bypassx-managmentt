"""Utility commands — server info, user info, avatar, poll, ping, uptime, etc."""
from __future__ import annotations

import datetime as dt
import platform
import time
from typing import Optional

import discord
import psutil
from discord import app_commands
from discord.ext import commands

from config import config
from database import get_db
from utils import ACCENT, embed_info, embed_success, embed_warn, embed_error, human_timedelta


class Utility(commands.Cog):
    """General-purpose server & bot utilities."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.process = psutil.Process()

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000)
        color = 0x57F287 if latency_ms < 100 else (0xFEE75C if latency_ms < 250 else 0xED4245)
        embed = discord.Embed(title="🏓 Pong!", color=color, timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="Websocket", value=f"`{latency_ms}ms`")
        embed.add_field(name="API", value="measuring...")
        t0 = time.monotonic()
        await interaction.response.send_message(embed=embed)
        api_ms = round((time.monotonic() - t0) * 1000)
        embed.set_field_at(1, name="API", value=f"`{api_ms}ms`")
        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name="uptime", description="Show how long the bot has been running.")
    async def uptime(self, interaction: discord.Interaction):
        now = dt.datetime.now(dt.UTC)
        uptime = now - self.bot.start_time
        cpu_time = self.process.cpu_percent()
        mem = self.process.memory_info().rss / 1024 / 1024
        embed = embed_info("BypassX Uptime", f"Online for **{human_timedelta(uptime.total_seconds())}**")
        embed.add_field(name="Started", value=f"<t:{int(self.bot.start_time.timestamp())}:R>")
        embed.add_field(name="CPU", value=f"{cpu_time:.1f}%")
        embed.add_field(name="Memory", value=f"{mem:.1f} MB")
        embed.add_field(name="Python", value=platform.python_version())
        embed.add_field(name="discord.py", value=discord.__version__)
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Show detailed info about this server.")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = embed_info(f"Server Info — {guild.name}", "")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.text_channels) + len(guild.voice_channels)), inline=True)
        embed.add_field(name="Boost Tier", value=f"Tier {guild.premium_tier}", inline=True)
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count), inline=True)
        embed.add_field(name="Verification", value=str(guild.verification_level).capitalize(), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Show detailed info about a member.")
    @app_commands.guild_only()
    async def userinfo(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        if not isinstance(member, discord.Member):
            member = await interaction.guild.fetch_member(member.id)
        embed = embed_info(f"User Info — {member}", "")
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
        embed.add_field(name="Roles", value=f"{len(member.roles) - 1}", inline=True)
        if member.premium_since:
            embed.add_field(name="Boosting Since", value=f"<t:{int(member.premium_since.timestamp())}:R>", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Show a member's avatar in full resolution.")
    async def avatar(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        embed = embed_info(f"Avatar — {member}", "")
        if member.display_avatar:
            embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="Show information about a role.")
    @app_commands.guild_only()
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = embed_info(f"Role Info — {role.name}", "")
        if role.icon:
            embed.set_thumbnail(url=role.icon.url if isinstance(role.icon, discord.Asset) else None)
        embed.add_field(name="ID", value=f"`{role.id}`", inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(role.created_at.timestamp())}:R>", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="poll", description="Create a quick yes/no poll, or a multi-option poll.")
    @app_commands.describe(question="The poll question", option1="First option (leave empty for yes/no)", option2="Second option", option3="Third option", option4="Fourth option")
    @app_commands.guild_only()
    async def poll(self, interaction: discord.Interaction, question: str, option1: Optional[str] = None, option2: Optional[str] = None, option3: Optional[str] = None, option4: Optional[str] = None):
        options = [o for o in [option1, option2, option3, option4] if o]
        if not options:
            embed = discord.Embed(title="📊 Poll", description=question, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
            embed.set_footer(text=f"Poll by {interaction.user} • React below")
            await interaction.response.send_message(content="@everyone" if interaction.guild else None, embed=embed, allowed_mentions=discord.AllowedMentions(everyone=True))
            msg = await interaction.original_response()
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
            return
        if len(options) < 2:
            await interaction.response.send_message(embed=embed_error("Need at least 2 options for a multi-option poll."), ephemeral=True)
            return
        numbers_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        body = "\n".join(f"{numbers_emoji[i]} {opt}" for i, opt in enumerate(options))
        embed = discord.Embed(title="📊 Poll", description=f"**{question}**\n\n{body}", color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text=f"Poll by {interaction.user} • React with the matching number")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        for i in range(len(options)):
            await msg.add_reaction(numbers_emoji[i])

    @app_commands.command(name="membercount", description="Show the current member count.")
    @app_commands.guild_only()
    async def membercount(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = embed_info(f"Member Count — {guild.name}", f"**Total members:** {guild.member_count}")
        embed.add_field(name="Humans", value=str(sum(1 for m in guild.members if not m.bot)) if guild.member_count and guild.members else "…")
        embed.add_field(name="Bots", value=str(sum(1 for m in guild.members if m.bot)) if guild.member_count and guild.members else "…")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="servericon", description="Show the server icon.")
    @app_commands.guild_only()
    async def servericon(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild.icon:
            await interaction.response.send_message(embed=embed_error("This server has no icon."), ephemeral=True)
            return
        embed = embed_info(f"Server Icon — {guild.name}", "")
        embed.set_image(url=guild.icon.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="firstmessage", description="Get a link to the first message in this channel.")
    @app_commands.guild_only()
    async def first_message(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async for m in interaction.channel.history(limit=1, oldest_first=True):
                await interaction.followup.send(embed=embed_info("First Message", f"[Jump to first message]({m.jump_url})"), ephemeral=True)
                return
        except discord.HTTPException:
            pass
        await interaction.followup.send(embed=embed_error("Could not fetch history."), ephemeral=True)

    @app_commands.command(name="botinfo", description="Show information about the bot.")
    async def botinfo(self, interaction: discord.Interaction):
        embed = embed_info("BypassX Management", "The all-in-one management bot — moderation, automod, tickets, roles, verification, logging, and more.")
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)))
        embed.add_field(name="Slash Commands", value=str(len(self.bot.tree.get_commands())))
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms")
        embed.add_field(name="Library", value=f"discord.py {discord.__version__}")
        embed.add_field(name="Python", value=platform.python_version())
        embed.add_field(name="Uptime", value=human_timedelta((dt.datetime.now(dt.UTC) - self.bot.start_time).total_seconds()))
        embed.set_footer(text="BypassX Management • Free Tier")
        await interaction.response.send_message(embed=embed)

    # ---------- reaction polls (folded in v4) ----------

    rpoll = app_commands.Group(name="rpoll", description="Reaction polls.", default_permissions=None)

    @rpoll.command(name="create", description="Create a reaction poll with up to 9 options.")
    async def rpoll_create(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: str = "",
        option4: str = "",
        option5: str = "",
        option6: str = "",
        option7: str = "",
        option8: str = "",
        option9: str = "",
    ):
        POLL_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
        options = [o for o in [option1, option2, option3, option4, option5, option6, option7, option8, option9] if o]
        if len(options) < 2:
            await interaction.response.send_message(embed=embed_error("Need at least 2 options."), ephemeral=True)
            return
        body = "\n".join(f"{POLL_EMOJIS[i]} {opt}" for i, opt in enumerate(options))
        embed = discord.Embed(title=f"📊 {question}", description=body, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Reaction Poll")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        for i in range(len(options)):
            try:
                await msg.add_reaction(POLL_EMOJIS[i])
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
