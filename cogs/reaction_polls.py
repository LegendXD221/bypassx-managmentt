"""Reaction polls — create polls with emoji reactions and timed auto-end."""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import get_db
from utils import ACCENT, embed_error, embed_info, embed_premium, embed_success, is_admin

POLL_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class ReactionPolls(commands.Cog):
    """Reaction-based polls with timed auto-end."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_loop.start()

    @tasks.loop(seconds=30)
    async def poll_loop(self) -> None:
        rows = await get_db().fetch(
            "SELECT id, guild_id, channel_id, message_id, question, options, ends_at FROM reaction_polls WHERE ended=FALSE AND ends_at IS NOT NULL AND ends_at <= NOW() LIMIT 25"
        )
        for row in rows:
            await self._end_poll(row)

    @poll_loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    async def _end_poll(self, row) -> None:
        guild = self.bot.get_guild(int(row["guild_id"]))
        if guild is None:
            await get_db().execute("UPDATE reaction_polls SET ended=TRUE WHERE id=$1", row["id"])
            return
        channel = guild.get_channel(int(row["channel_id"]))
        if channel is None:
            await get_db().execute("UPDATE reaction_polls SET ended=TRUE WHERE id=$1", row["id"])
            return
        try:
            msg = await channel.fetch_message(int(row["message_id"]))
        except (discord.NotFound, discord.Forbidden):
            await get_db().execute("UPDATE reaction_polls SET ended=TRUE WHERE id=$1", row["id"])
            return
        options = json.loads(row["options"]) if isinstance(row["options"], str) else row["options"]
        results = []
        for i, opt in enumerate(options):
            count = 0
            for r in msg.reactions:
                if str(r.emoji) == POLL_EMOJIS[i]:
                    count = r.count - 1 if r.count > 0 else 0
                    break
            results.append((opt, count))
        total = sum(c for _, c in results)
        embed = embed_premium(f"Poll Ended — {row['question']}", f"Total votes: **{total}**")
        for opt, count in results:
            pct = (count / total * 100) if total else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            embed.add_field(name=opt, value=f"`{bar}`  **{count}** ({pct:.0f}%)", inline=False)
        try:
            await msg.edit(embed=embed)
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass
        await get_db().execute("UPDATE reaction_polls SET ended=TRUE WHERE id=$1", row["id"])

    group = app_commands.Group(name="poll", description="Create timed reaction polls.", default_permissions=None)

    @group.command(name="create", description="Create a reaction poll with up to 10 options.")
    @app_commands.describe(question="Poll question", duration="Duration like 1h, 30m, 2d (optional)", option1="First option", option2="Second option", option3="Third option", option4="Fourth option", option5="Fifth option", option6="Sixth option", option7="Seventh option", option8="Eighth option", option9="Ninth option", option10="Tenth option")
    async def create(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        duration: Optional[str] = None,
        option3: Optional[str] = None,
        option4: Optional[str] = None,
        option5: Optional[str] = None,
        option6: Optional[str] = None,
        option7: Optional[str] = None,
        option8: Optional[str] = None,
        option9: Optional[str] = None,
        option10: Optional[str] = None,
    ):
        options = [o for o in [option1, option2, option3, option4, option5, option6, option7, option8, option9, option10] if o]
        if len(options) < 2:
            await interaction.response.send_message(embed=embed_error("Need at least 2 options."), ephemeral=True)
            return
        ends_at = None
        if duration:
            from utils import parse_duration
            seconds = parse_duration(duration)
            if seconds is None or seconds < 60:
                await interaction.response.send_message(embed=embed_error("Invalid duration. Use `1h`, `30m`, `2d`. Min 1m."), ephemeral=True)
                return
            ends_at = discord.utils.utcnow() + dt.timedelta(seconds=seconds)
        body = "\n".join(f"{POLL_EMOJIS[i]} {opt}" for i, opt in enumerate(options))
        embed = discord.Embed(title=f"📊 {question}", description=body, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text=f"BypassX  •  Poll  •  {'Ends' if ends_at else 'No end'} {f'<t:{int(ends_at.timestamp())}:R>' if ends_at else ''}")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        for i in range(len(options)):
            try:
                await msg.add_reaction(POLL_EMOJIS[i])
            except discord.HTTPException:
                pass
        await get_db().execute(
            "INSERT INTO reaction_polls (guild_id, channel_id, message_id, question, options, ends_at) VALUES ($1,$2,$3,$4,$5,$6)",
            interaction.guild.id, interaction.channel.id, msg.id, question, json.dumps(options), ends_at,
        )

    @group.command(name="end", description="End a poll early by message ID.")
    @is_admin()
    async def end(self, interaction: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message(embed=embed_error("Invalid message ID."), ephemeral=True)
            return
        row = await get_db().fetchrow("SELECT * FROM reaction_polls WHERE guild_id=$1 AND message_id=$2 AND ended=FALSE", interaction.guild.id, mid)
        if not row:
            await interaction.response.send_message(embed=embed_error("Poll not found or already ended."), ephemeral=True)
            return
        await self._end_poll(row)
        await interaction.response.send_message(embed=embed_success("Poll Ended", "Results posted."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReactionPolls(bot))
