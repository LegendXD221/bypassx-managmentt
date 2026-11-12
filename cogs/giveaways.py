"""Giveaways — create, end, re-roll, list giveaways with button entries."""
from __future__ import annotations

import datetime as dt
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import get_db
from utils import GOLD, ACCENT, embed_error, embed_info, embed_premium, embed_success, human_timedelta, is_admin, parse_duration, send_modlog


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="Enter", style=discord.ButtonStyle.success, emoji="🎉", custom_id="bypassx:giveaway_enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await get_db().execute(
                "INSERT INTO giveaway_participants (giveaway_id, user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                self.giveaway_id, interaction.user.id,
            )
        except Exception:
            pass
        await interaction.response.send_message(embed=embed_success("Entered", "You're in the giveaway!"), ephemeral=True)


def build_giveaway_embed(prize: str, host: discord.abc.User, ends_at: dt.datetime, winners: int, entries: int, ended: bool = False) -> discord.Embed:
    color = 0x6366F1 if not ended else 0xF5B544
    embed = discord.Embed(
        title=f"🎉 {prize}" if not ended else f"🎉 {prize} — Ended",
        color=color,
        timestamp=ends_at,
    )
    if not ended:
        embed.description = (
            f"Hosted by {host.mention}\n"
            f"Ends <t:{int(ends_at.timestamp())}:R> (<t:{int(ends_at.timestamp())}:F>)\n"
            f"**Winners:** {winners}  ·  **Entries:** {entries}\n\n"
            f"Click the **Enter** button below to participate."
        )
    else:
        embed.description = f"Hosted by {host.mention}\n**Winners:** {winners}  ·  **Entries:** {entries}"
    embed.set_footer(text="BypassX · Giveaways")
    return embed


class Giveaways(commands.Cog):
    """Premium giveaway system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.giveaway_loop.start()

    @tasks.loop(seconds=15)
    async def giveaway_loop(self) -> None:
        rows = await get_db().fetch(
            "SELECT id, guild_id, channel_id, message_id, host_id, prize, winners_count, ends_at FROM giveaways WHERE ended=FALSE AND ends_at <= NOW() LIMIT 25"
        )
        for row in rows:
            await self._end_giveaway(row)

    @giveaway_loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    async def _end_giveaway(self, row) -> None:
        guild = self.bot.get_guild(int(row["guild_id"]))
        if guild is None:
            await get_db().execute("UPDATE giveaways SET ended=TRUE WHERE id=$1", row["id"])
            return
        channel = guild.get_channel(int(row["channel_id"]))
        if channel is None:
            await get_db().execute("UPDATE giveaways SET ended=TRUE WHERE id=$1", row["id"])
            return
        try:
            msg = await channel.fetch_message(int(row["message_id"]))
        except (discord.NotFound, discord.Forbidden):
            await get_db().execute("UPDATE giveaways SET ended=TRUE WHERE id=$1", row["id"])
            return

        participants = await get_db().fetch("SELECT user_id FROM giveaway_participants WHERE giveaway_id=$1", row["id"])
        winners_count = int(row["winners_count"]) or 1
        host = self.bot.get_user(int(row["host_id"])) or await self.bot.fetch_user(int(row["host_id"]))
        if not participants:
            embed = build_giveaway_embed(row["prize"], host, row["ends_at"], winners_count, len(participants), ended=True)
            embed.add_field(name="Winners", value="Nobody entered.", inline=False)
            try:
                await msg.edit(embed=embed, view=None)
                await channel.send(embed=embed_info("Giveaway Ended", f"No participants for **{row['prize']}**."))
            except discord.HTTPException:
                pass
        else:
            user_ids = [int(p["user_id"]) for p in participants]
            winners = random.sample(user_ids, min(winners_count, len(user_ids)))
            winners_text = ", ".join(f"<@{w}>" for w in winners)
            embed = build_giveaway_embed(row["prize"], host, row["ends_at"], winners_count, len(participants), ended=True)
            embed.add_field(name="Winners", value=winners_text, inline=False)
            try:
                await msg.edit(embed=embed, view=None)
                await channel.send(content=winners_text, embed=embed_premium("Giveaway Ended", f"Congratulations to the winner(s) of **{row['prize']}**!"))
            except discord.HTTPException:
                pass
        await get_db().execute("UPDATE giveaways SET ended=TRUE WHERE id=$1", row["id"])
        await send_modlog(guild, action="giveaway ended", moderator=host, details={"Prize": row["prize"], "Entries": len(participants)})

    group = app_commands.Group(name="giveaway", description="Create and manage giveaways.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="start", description="Start a new giveaway.")
    @is_admin()
    async def start(self, interaction: discord.Interaction, prize: str, duration: str, winners: app_commands.Range[int, 1, 50] = 1):
        seconds = parse_duration(duration)
        if seconds is None or seconds < 30:
            await interaction.response.send_message(embed=embed_error("Invalid Duration", "Use formats like `1h`, `30m`, `2d`. Minimum 30s."), ephemeral=True)
            return
        ends_at = discord.utils.utcnow() + dt.timedelta(seconds=seconds)
        embed = build_giveaway_embed(prize, interaction.user, ends_at, winners, 0)
        view = GiveawayView(giveaway_id=0)  # placeholder; will be replaced after insert
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        row = await get_db().fetchrow(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners_count, ends_at) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
            interaction.guild.id, interaction.channel.id, msg.id, interaction.user.id, prize, winners, ends_at,
        )
        # re-bind the view to the actual giveaway id
        view = GiveawayView(giveaway_id=row["id"])
        await msg.edit(view=view)
        await send_modlog(interaction.guild, action="giveaway started", moderator=interaction.user, details={"Prize": prize, "Winners": winners, "Ends": f"<t:{int(ends_at.timestamp())}:R>"})

    @group.command(name="end", description="End a giveaway early by its message ID.")
    @is_admin()
    async def end(self, interaction: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message(embed=embed_error("Invalid message ID."), ephemeral=True)
            return
        row = await get_db().fetchrow("SELECT * FROM giveaways WHERE guild_id=$1 AND message_id=$2 AND ended=FALSE", interaction.guild.id, mid)
        if not row:
            await interaction.response.send_message(embed=embed_error("Giveaway not found or already ended."), ephemeral=True)
            return
        await self._end_giveaway(row)
        await interaction.response.send_message(embed=embed_success("Giveaway Ended", "The giveaway has been ended."), ephemeral=True)

    @group.command(name="reroll", description="Re-roll the winner of an ended giveaway.")
    @is_admin()
    async def reroll(self, interaction: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message(embed=embed_error("Invalid message ID."), ephemeral=True)
            return
        row = await get_db().fetchrow("SELECT id, guild_id, prize FROM giveaways WHERE guild_id=$1 AND message_id=$2 AND ended=TRUE", interaction.guild.id, mid)
        if not row:
            await interaction.response.send_message(embed=embed_error("Giveaway not found."), ephemeral=True)
            return
        participants = await get_db().fetch("SELECT user_id FROM giveaway_participants WHERE giveaway_id=$1", row["id"])
        if not participants:
            await interaction.response.send_message(embed=embed_error("No participants to re-roll."), ephemeral=True)
            return
        winner = random.choice([int(p["user_id"]) for p in participants])
        await interaction.response.send_message(embed=embed_premium("Re-rolled", f"New winner of **{row['prize']}**:\n<@{winner}>"))

    @group.command(name="list", description="List active giveaways in this server.")
    async def list(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT prize, ends_at, winners_count FROM giveaways WHERE guild_id=$1 AND ended=FALSE ORDER BY ends_at", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Active Giveaways", "There are no ongoing giveaways."))
            return
        embed = embed_premium("Active Giveaways", f"**{len(rows)}** ongoing:")
        for r in rows[:10]:
            embed.add_field(name=r["prize"][:80], value=f"Ends <t:{int(r['ends_at'].timestamp())}:R>\nWinners: {r['winners_count']}", inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaways(bot))
