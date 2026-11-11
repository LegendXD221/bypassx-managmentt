"""Fun commands — 8ball, dice, coinflip, choose, rps, wouldyourather, etc."""
from __future__ import annotations

import datetime as dt
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import ACCENT, GOLD, embed_error, embed_info, embed_premium, embed_success

EIGHTBALL = [
    "It is certain.", "Without a doubt.", "Yes — definitely.", "You may rely on it.",
    "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.",
    "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.",
    "Very doubtful.", "No.",
]

WYR = [
    "Be able to fly but only 1m off the ground, or be invisible but only when no one is looking?",
    "Have unlimited sushi for life or unlimited tacos for life?",
    "Always be 10 minutes late or 20 minutes early?",
    "Speak every language fluently or play every instrument perfectly?",
    "Live without music or without movies?",
    "Have a rewind button for life or a pause button?",
    "Be able to talk to animals or read minds?",
    "Always know the truth or never be lied to?",
    "Give up coffee or give up the internet for a year?",
    "Travel anywhere for free or eat anything for free?",
]


class Fun(commands.Cog):
    """Lightweight fun commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="8ball", description="Ask the magic 8-ball.")
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        embed = discord.Embed(title="🎱 Magic 8-Ball", color=GOLD, timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=random.choice(EIGHTBALL), inline=False)
        embed.set_footer(text="BypassX · Fun")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="dice", description="Roll some dice. Format: 2d6 or just 6.")
    async def dice(self, interaction: discord.Interaction, spec: str = "1d6"):
        try:
            if "d" in spec.lower():
                count, sides = spec.lower().split("d", 1)
                count = int(count)
                sides = int(sides)
            else:
                count, sides = 1, int(spec)
            if count < 1 or count > 100 or sides < 2 or sides > 1000:
                raise ValueError
        except (ValueError, TypeError):
            await interaction.response.send_message(embed=embed_error("Invalid format.", "Use `2d6`, `1d20`, or just `6`."), ephemeral=True)
            return
        rolls = [random.randint(1, sides) for _ in range(count)]
        embed = embed_premium("🎲 Dice Roll", f"**{count}d{sides}**\nResult: {', '.join(str(r) for r in rolls)}\nTotal: **{sum(rolls)}**")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Flip a coin.")
    async def coinflip(self, interaction: discord.Interaction):
        result = random.choice(["Heads", "Tails"])
        embed = embed_premium("🪙 Coin Flip", f"It landed on **{result}**.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="choose", description="Let the bot choose between options (separate with |).")
    async def choose(self, interaction: discord.Interaction, options: str):
        parts = [p.strip() for p in options.split("|") if p.strip()]
        if len(parts) < 2:
            await interaction.response.send_message(embed=embed_error("Need at least 2 options separated by `|`."), ephemeral=True)
            return
        choice = random.choice(parts)
        embed = embed_premium("🎯 Choice", f"I choose: **{choice}**\n\nFrom: {', '.join(parts)}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rps", description="Rock, paper, scissors.")
    async def rps(self, interaction: discord.Interaction, choice: str):
        choice = choice.lower()
        if choice not in {"rock", "paper", "scissors"}:
            await interaction.response.send_message(embed=embed_error("Choose rock, paper, or scissors."), ephemeral=True)
            return
        bot_choice = random.choice(["rock", "paper", "scissors"])
        wins = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
        if choice == bot_choice:
            result = "It's a tie!"
            color = GOLD
        elif wins[choice] == bot_choice:
            result = "You win!"
            color = 0x10B981
        else:
            result = "I win!"
            color = 0xE11D48
        embed = discord.Embed(title="✊ Rock · Paper · Scissors", color=color, timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="You", value=choice.title())
        embed.add_field(name="Bot", value=bot_choice.title())
        embed.add_field(name="Result", value=result, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="wouldyourather", description="Get a Would You Rather prompt.")
    async def wyr(self, interaction: discord.Interaction):
        embed = embed_premium("🤔 Would You Rather", random.choice(WYR))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="random", description="Pick a random number between two values.")
    async def random_num(self, interaction: discord.Interaction, minimum: int, maximum: int):
        if minimum >= maximum:
            await interaction.response.send_message(embed=embed_error("Minimum must be less than maximum."), ephemeral=True)
            return
        embed = embed_premium("🔢 Random Number", f"Between **{minimum}** and **{maximum}**:\n\n# **{random.randint(minimum, maximum)}**")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="meme", description="Get a random meme (placeholder text).")
    async def meme(self, interaction: discord.Interaction):
        embed = embed_premium("😂 Meme", "Why did the developer go broke? Because he used up all his cache.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun(bot))
