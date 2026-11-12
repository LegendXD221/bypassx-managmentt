"""Extra utility commands — timezone converter, color tools, invite info, role list, channel info, etc."""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import ACCENT, GOLD, embed_error, embed_info, embed_premium, embed_success, human_timedelta


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

    @app_commands.command(name="rgb", description="Convert RGB to hex.")
    async def rgb_cmd(self, interaction: discord.Interaction, r: app_commands.Range[int, 0, 255], g: app_commands.Range[int, 0, 255], b: app_commands.Range[int, 0, 255]):
        color_int = (r << 16) + (g << 8) + b
        hex_str = f"{color_int:06X}"
        embed = discord.Embed(title=f"rgb({r}, {g}, {b})", color=color_int, timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="Hex", value=f"`#{hex_str}`", inline=True)
        embed.add_field(name="Integer", value=f"`{color_int}`", inline=True)
        embed.set_footer(text="BypassX  •  Color Tools")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="base64", description="Encode or decode base64.")
    @app_commands.describe(mode="encode or decode", text="Text to encode/decode")
    async def base64(self, interaction: discord.Interaction, mode: str, text: str):
        import base64 as b64
        mode = mode.lower()
        try:
            if mode == "encode":
                result = b64.b64encode(text.encode("utf-8")).decode("ascii")
            elif mode == "decode":
                result = b64.b64decode(text.encode("ascii")).decode("utf-8", errors="replace")
            else:
                await interaction.response.send_message(embed=embed_error("Mode must be `encode` or `decode`."), ephemeral=True)
                return
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        embed = embed_premium(f"Base64 {mode.title()}", f"```\n{result[:1800]}\n```")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inviteinfo", description="Show info about a Discord invite.")
    async def inviteinfo(self, interaction: discord.Interaction, code: str):
        # extract code from URL if needed
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

    @app_commands.command(name="rolelist", description="List all roles in this server.")
    @app_commands.guild_only()
    async def rolelist(self, interaction: discord.Interaction):
        roles = sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True)
        embed = embed_premium(f"Roles — {interaction.guild.name}", f"**{len(roles)}** roles:")
        chunks = [roles[i:i + 10] for i in range(0, len(roles), 10)]
        for chunk in chunks[:5]:
            value = "\n".join(f"• {r.mention} ({r.name}) — {len(r.members)} members" for r in chunk if not r.is_default())
            embed.add_field(name="\u200b", value=value or "—", inline=False)
        if len(roles) > 50:
            embed.set_footer(text=f"Showing first 50 of {len(roles)} roles")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="channelinfo", description="Show info about a channel.")
    @app_commands.guild_only()
    async def channelinfo(self, interaction: discord.Interaction, channel: Optional[discord.abc.GuildChannel] = None):
        channel = channel or interaction.channel
        embed = embed_premium(f"Channel Info — #{channel.name}")
        embed.add_field(name="ID", value=f"`{channel.id}`", inline=True)
        embed.add_field(name="Type", value=str(channel.type), inline=True)
        embed.add_field(name="Category", value=channel.category.mention if channel.category else "None", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(channel.created_at.timestamp())}:R>", inline=True)
        if hasattr(channel, "topic") and channel.topic:
            embed.add_field(name="Topic", value=channel.topic[:1024], inline=False)
        if hasattr(channel, "nsfw"):
            embed.add_field(name="NSFW", value="Yes" if channel.nsfw else "No", inline=True)
        if hasattr(channel, "slowmode_delay"):
            embed.add_field(name="Slowmode", value=f"{channel.slowmode_delay}s", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="emojiinfo", description="Show info about a custom emoji.")
    async def emojiinfo(self, interaction: discord.Interaction, emoji: str):
        match = re.search(r"<a?:(\w+):(\d+)>", emoji)
        if not match:
            await interaction.response.send_message(embed=embed_error("Use a custom emoji."), ephemeral=True)
            return
        name, eid = match.group(1), match.group(2)
        animated = emoji.startswith("<a:")
        ext = "gif" if animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{eid}.{ext}"
        embed = embed_premium(f"Emoji — :{name}:")
        embed.add_field(name="Name", value=name, inline=True)
        embed.add_field(name="ID", value=f"`{eid}`", inline=True)
        embed.add_field(name="Animated", value="Yes" if animated else "No", inline=True)
        embed.set_image(url=url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="listchannels", description="List all channels in this server.")
    @app_commands.guild_only()
    async def listchannels(self, interaction: discord.Interaction):
        embed = embed_premium(f"Channels — {interaction.guild.name}")
        text = "\n".join(f"#{c.name}" for c in interaction.guild.text_channels[:20])
        voice = "\n".join(f"🔊 {c.name}" for c in interaction.guild.voice_channels[:20])
        if text:
            embed.add_field(name="Text Channels", value=text or "None", inline=True)
        if voice:
            embed.add_field(name="Voice Channels", value=voice or "None", inline=True)
        embed.set_footer(text=f"Total: {len(interaction.guild.text_channels)} text · {len(interaction.guild.voice_channels)} voice")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="permissions", description="Show your effective permissions in this channel.")
    @app_commands.guild_only()
    async def permissions(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(embed=embed_error("Member not found."), ephemeral=True)
            return
        perms = interaction.channel.permissions_for(member)
        allowed = [name for name, val in perms if val]
        embed = embed_premium(f"Permissions — {member}", f"**{len(allowed)}** permissions granted in {interaction.channel.mention}:")
        chunks = [allowed[i:i + 12] for i in range(0, len(allowed), 12)]
        for i, chunk in enumerate(chunks[:5], 1):
            embed.add_field(name=f"Page {i}", value=", ".join(f"`{p}`" for p in chunk), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remindme", description="Quick reminder in the current channel (alias of /remind).")
    async def remindme(self, interaction: discord.Interaction, duration: str, message: str):
        from cogs.reminders import Reminders
        # delegate to the existing reminders cog logic by inserting directly
        from utils import parse_duration
        from database import get_db
        seconds = parse_duration(duration)
        if seconds is None or seconds < 30:
            await interaction.response.send_message(embed=embed_error("Invalid duration. Use formats like `15m`, `1h30m`, `2d`. Min 30s."), ephemeral=True)
            return
        expires_at = discord.utils.utcnow() + dt.timedelta(seconds=seconds)
        await get_db().execute(
            "INSERT INTO reminders (guild_id, user_id, channel_id, message, expires_at) VALUES ($1,$2,$3,$4,$5)",
            interaction.guild.id if interaction.guild else None, interaction.user.id, interaction.channel.id if interaction.channel else None, message, expires_at,
        )
        from utils import human_timedelta
        await interaction.response.send_message(embed=embed_success("Reminder Set", f"I'll remind you in **{human_timedelta(seconds)}** (<t:{int(expires_at.timestamp())}:R>).\n**Message:** {message}"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilityExtra(bot))
