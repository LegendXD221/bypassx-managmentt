"""Extra utility commands — timezone converter, hex color, invite info.

Trimmed in v4 to fit Discord's 100-command limit.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import ACCENT, GOLD, embed_error, embed_info, embed_premium, embed_success


class UtilityExtra(commands.Cog):
    """Premium extra utilities for power users."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="timeconvert", description="Convert a time from one timezone to another.")
    @app_commands.describe(time="Time in 24h format, e.g. 14:30", from_tz="Source timezone offset like +0530 or -0500", to_tz="Target timezone offset")
    async def timeconvert(self, interaction: discord.Interaction, time: str, from_tz: str, to_tz: str):
        try:
            hours, minutes = map(int, time.split(":"))
        except (ValueError, AttributeError):
            await interaction.response.send_message(embed=embed_error("Invalid time format. Use HH:MM like `14:30`."), ephemeral=True)
            return
        def parse_tz(s: str) -> int:
            s = s.strip().lstrip("UTC").lstrip("utc")
            if not s:
                return 0
            sign = 1 if s[0] != "-" else -1
            s = s.lstrip("+-")
            if len(s) <= 2:
                return sign * int(s) * 60
            h = int(s[:-2])
            m = int(s[-2:])
            return sign * (h * 60 + m)
        try:
            src_offset = parse_tz(from_tz)
            dst_offset = parse_tz(to_tz)
        except ValueError:
            await interaction.response.send_message(embed=embed_error("Invalid timezone offset. Use ±HHMM, e.g. `+0530`."), ephemeral=True)
            return
        now = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        src_time = now + dt.timedelta(minutes=src_offset, hours=hours) + dt.timedelta(minutes=minutes)
        dst_time = src_time + dt.timedelta(minutes=dst_offset - src_offset)
        embed = embed_premium("Time Zone Converter")
        embed.add_field(name=f"Source ({from_tz})", value=f"**{hours:02d}:{minutes:02d}**", inline=True)
        embed.add_field(name=f"Target ({to_tz})", value=f"**{dst_time.hour:02d}:{dst_time.minute:02d}**", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="hex", description="Convert a hex color to RGB and preview it.")
    async def hex_cmd(self, interaction: discord.Interaction, color: str):
        try:
            hex_str = color.lstrip("#").strip()
            if len(hex_str) == 3:
                hex_str = "".join(c * 2 for c in hex_str)
            color_int = int(hex_str, 16)
            r = (color_int >> 16) & 255
            g = (color_int >> 8) & 255
            b = color_int & 255
        except (ValueError, TypeError):
            await interaction.response.send_message(embed=embed_error("Invalid hex. Use `#6366F1` or `6366F1`."), ephemeral=True)
            return
        embed = discord.Embed(title=f"#{hex_str.upper()}", color=color_int, timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="Hex", value=f"`#{hex_str.upper()}`", inline=True)
        embed.add_field(name="RGB", value=f"`rgb({r}, {g}, {b})`", inline=True)
        embed.add_field(name="Integer", value=f"`{color_int}`", inline=True)
        embed.set_footer(text="BypassX  •  Color Tools")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inviteinfo", description="Show info about a Discord invite.")
    async def inviteinfo(self, interaction: discord.Interaction, code: str):
        match = re.search(r"(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]+)", code)
        if match:
            code = match.group(1)
        try:
            invite = await self.bot.fetch_invite(code)
        except discord.NotFound:
            await interaction.response.send_message(embed=embed_error("Invite not found or expired."), ephemeral=True)
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        embed = embed_premium(f"Invite — {invite.code}")
        if invite.guild:
            embed.add_field(name="Server", value=invite.guild.name, inline=True)
            embed.add_field(name="Members", value=str(invite.approximate_member_count) if invite.approximate_member_count else "?", inline=True)
            embed.add_field(name="Online", value=str(invite.approximate_presence_count) if invite.approximate_presence_count else "?", inline=True)
        if invite.inviter:
            embed.add_field(name="Inviter", value=str(invite.inviter), inline=True)
        if invite.channel:
            embed.add_field(name="Channel", value=f"#{invite.channel.name}", inline=True)
        if invite.expires_at:
            embed.add_field(name="Expires", value=f"<t:{int(invite.expires_at.timestamp())}:R>", inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityExtra(bot))
