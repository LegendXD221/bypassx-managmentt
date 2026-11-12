"""Owner-only commands — eval, sql, leaveguild, listguilds, botstats, broadcast, maintenance."""
from __future__ import annotations

import datetime as dt
import platform
from typing import Optional

import discord
import psutil
from discord import app_commands
from discord.ext import commands

from config import config
from database import get_db
from utils import ACCENT, DANGER, GOLD, SUCCESS, embed_error, embed_info, embed_premium, embed_success, embed_warn, human_timedelta, is_owner


class Owner(commands.Cog):
    """Owner-only power commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.process = psutil.Process()
        self.maintenance = False

    @app_commands.command(name="eval", description="(Owner) Evaluate a Python expression.")
    async def eval_cmd(self, interaction: discord.Interaction, code: str):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        try:
            result = eval(code, {"bot": self.bot, "discord": discord, "db": get_db(), "config": config, "interaction": interaction, "psutil": psutil, "platform": platform}, {})
            await interaction.response.send_message(embed=embed_premium("Eval Result", f"```py\n{str(result)[:1500]}\n```"))
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(embed=embed_error("Eval Failed", f"```py\n{type(exc).__name__}: {exc}\n```"))

    @app_commands.command(name="sql", description="(Owner) Run a SQL query (read-only recommended).")
    async def sql(self, interaction: discord.Interaction, query: str):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        try:
            q = query.strip()
            if q.lower().startswith("select") or q.lower().startswith("with") or q.lower().startswith("show"):
                rows = await get_db().fetch(query)
                if not rows:
                    await interaction.response.send_message(embed=embed_info("SQL", "No rows returned."))
                    return
                cols = list(rows[0].keys())
                lines = [" | ".join(cols)]
                for r in rows[:15]:
                    lines.append(" | ".join(str(r[c])[:30] for c in cols))
                await interaction.response.send_message(embed=embed_premium("SQL Result", f"```\n{chr(10).join(lines)[:1900]}\n```"))
            else:
                status = await get_db().execute(query)
                await interaction.response.send_message(embed=embed_success("SQL Executed", f"`{status}`"))
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(embed=embed_error("SQL Failed", f"```{type(exc).__name__}: {exc}\n```"), ephemeral=True)

    @app_commands.command(name="listguilds", description="(Owner) List all servers the bot is in.")
    async def list_guilds(self, interaction: discord.Interaction):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        embed = embed_premium("Connected Guilds", f"**{len(self.bot.guilds)}** servers:")
        for g in self.bot.guilds[:25]:
            embed.add_field(name=g.name[:40], value=f"`{g.id}` · {g.member_count} members", inline=False)
        if len(self.bot.guilds) > 25:
            embed.set_footer(text=f"Showing first 25 of {len(self.bot.guilds)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leaveguild", description="(Owner) Leave a server by ID.")
    async def leave_guild(self, interaction: discord.Interaction, guild_id: str):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message(embed=embed_error("Invalid ID."), ephemeral=True)
            return
        guild = self.bot.get_guild(gid)
        if guild is None:
            await interaction.response.send_message(embed=embed_error("Guild not found."), ephemeral=True)
            return
        await guild.leave()
        await interaction.response.send_message(embed=embed_success("Left Guild", f"Left **{guild.name}** (`{gid}`)."))

    @app_commands.command(name="botstats", description="(Owner) Detailed bot statistics.")
    async def botstats(self, interaction: discord.Interaction):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        uptime = (dt.datetime.now(dt.UTC) - self.bot.start_time).total_seconds()
        mem = self.process.memory_info().rss / 1024 / 1024
        cpu = self.process.cpu_percent(interval=0.1)
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        total_channels = sum(len(g.channels) for g in self.bot.guilds)
        embed = embed_premium("BypassX · Bot Stats")
        embed.add_field(name="Uptime", value=human_timedelta(uptime), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency*1000)}ms", inline=True)
        embed.add_field(name="Memory", value=f"{mem:.1f} MB", inline=True)
        embed.add_field(name="CPU", value=f"{cpu:.1f}%", inline=True)
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Members", value=f"{total_members:,}", inline=True)
        embed.add_field(name="Channels", value=str(total_channels), inline=True)
        embed.add_field(name="Slash Commands", value=str(len(self.bot.tree.get_commands())), inline=True)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="broadcast", description="(Owner) Broadcast an announcement to all servers.")
    async def broadcast(self, interaction: discord.Interaction, message: str):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_warn("Broadcasting", f"Sending to {len(self.bot.guilds)} guilds..."), ephemeral=True)
        sent = 0
        for g in self.bot.guilds:
            try:
                # find first channel we can post in
                for ch in g.text_channels:
                    if ch.permissions_for(g.me).send_messages:
                        await ch.send(embed=embed_premium("📢 Announcement", message))
                        sent += 1
                        break
            except discord.HTTPException:
                pass
        await interaction.edit_original_response(embed=embed_success("Broadcast Done", f"Sent to **{sent}** guilds."))

    @app_commands.command(name="maintenance", description="(Owner) Toggle maintenance mode.")
    async def maintenance(self, interaction: discord.Interaction, enabled: Optional[bool] = None):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        self.maintenance = enabled if enabled is not None else not self.maintenance
        if self.maintenance:
            await self.bot.change_presence(status=discord.Status.do_not_disturb, activity=discord.Activity(type=discord.ActivityType.watching, name="🔧 Maintenance"))
        else:
            await self.bot.change_presence(status=discord.Status.online, activity=None)
        await interaction.response.send_message(embed=embed_warn("Maintenance Mode", f"Now **{'ON' if self.maintenance else 'OFF'}**."))

    @app_commands.command(name="reloadall", description="(Owner) Reload every cog.")
    async def reload_all(self, interaction: discord.Interaction):
        if interaction.user.id != config.owner_id:
            await interaction.response.send_message(embed=embed_error("Owner only."), ephemeral=True)
            return
        cog_names = [name for name, _ in self.bot.cogs.items()]
        ok = 0
        failed = []
        for name in cog_names:
            module = self.bot.cogs[name].__module__ if hasattr(self.bot.cogs[name], "__module__") else f"cogs.{name.lower()}"
            try:
                await self.bot.reload_extension(module)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{name}: {exc}")
        msg = f"Reloaded **{ok}** cogs."
        if failed:
            msg += f"\n\nFailed: {len(failed)}\n" + "\n".join(failed[:5])
        await interaction.response.send_message(embed=embed_success("Reload Done", msg), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Owner(bot))
