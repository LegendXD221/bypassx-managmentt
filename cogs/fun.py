"""Fun commands + text tools — 8ball, dice, RPS, mock, encode, etc.

Merged in v4 to fit Discord's 100-command limit.
"""
from __future__ import annotations

import base64 as b64
import datetime as dt
import hashlib
import random
import string
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import get_db
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


def to_mock(text: str) -> str:
    out = []
    upper = True
    for ch in text:
        if ch.isalpha():
            out.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            out.append(ch)
    return "".join(out)


class Fun(commands.Cog):
    """Fun + text tool commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- classic fun ----------

    @app_commands.command(name="8ball", description="Ask the magic 8-ball.")
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        embed = discord.Embed(title="🎱 Magic 8-Ball", color=GOLD, timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=random.choice(EIGHTBALL), inline=False)
        embed.set_footer(text="BypassX · Fun")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="dice", description="Roll dice. Format: 2d6 or just 6.")
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

    # ---------- text tools group ----------

    text = app_commands.Group(name="text", description="Text transformation tools.", default_permissions=None)

    @text.command(name="mock", description="Convert text to mock SpongeBob case.")
    async def text_mock(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message(embed=embed_premium("Mock Case", to_mock(text)))

    @text.command(name="reverse", description="Reverse a string.")
    async def text_reverse(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message(embed=embed_premium("Reversed", text[::-1]))

    @text.command(name="encode", description="Encode text (base64, binary, or hex).")
    async def text_encode(self, interaction: discord.Interaction, format: str, text: str):
        format = format.lower()
        try:
            if format == "base64":
                result = b64.b64encode(text.encode("utf-8")).decode("ascii")
            elif format == "binary":
                result = " ".join(format(b, "08b") for b in text.encode("utf-8"))
            elif format == "hex":
                result = text.encode("utf-8").hex(" ")
            else:
                await interaction.response.send_message(embed=embed_error("Format must be base64, binary, or hex."), ephemeral=True)
                return
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_premium(f"Encoded — {format}", f"```\n{result[:1800]}\n```"))

    @text.command(name="decode", description="Decode text (base64, binary, or hex).")
    async def text_decode(self, interaction: discord.Interaction, format: str, text: str):
        format = format.lower()
        try:
            if format == "base64":
                result = b64.b64decode(text.encode("ascii")).decode("utf-8", errors="replace")
            elif format == "binary":
                bits = text.replace(" ", "")
                result = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)).decode("utf-8", errors="replace")
            elif format == "hex":
                result = bytes.fromhex(text.replace(" ", "")).decode("utf-8", errors="replace")
            else:
                await interaction.response.send_message(embed=embed_error("Format must be base64, binary, or hex."), ephemeral=True)
                return
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_premium(f"Decoded — {format}", f"```\n{result[:1800]}\n```"))

    @text.command(name="length", description="Get character, word, and line counts.")
    async def text_length(self, interaction: discord.Interaction, text: str):
        embed = embed_premium("Text Length")
        embed.add_field(name="Characters", value=str(len(text)), inline=True)
        embed.add_field(name="Words", value=str(len(text.split())), inline=True)
        embed.add_field(name="Lines", value=str(text.count("\n") + 1), inline=True)
        await interaction.response.send_message(embed=embed)

    @text.command(name="vaporwave", description="Convert text to fullwidth vaporwave.")
    async def text_vaporwave(self, interaction: discord.Interaction, text: str):
        result = "".join(chr(0xFF01 + (ord(c) - 0x21)) if 0x21 <= ord(c) <= 0x7E else c for c in text)
        await interaction.response.send_message(embed=embed_premium("Vaporwave", result))

    @text.command(name="password", description="Generate a random secure password.")
    async def text_password(self, interaction: discord.Interaction, length: app_commands.Range[int, 8, 128] = 16, symbols: bool = True, numbers: bool = True):
        chars = string.ascii_letters
        if numbers:
            chars += string.digits
        if symbols:
            chars += "!@#$%^&*()-_=+[]{}<>?"
        pwd = "".join(random.choice(chars) for _ in range(length))
        await interaction.response.send_message(embed=embed_premium("Secure Password", f"```\n{pwd}\n```"), ephemeral=True)

    @text.command(name="sha256", description="Compute the SHA-256 hash of text.")
    async def text_sha256(self, interaction: discord.Interaction, text: str):
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        await interaction.response.send_message(embed=embed_premium("SHA-256", f"```\n{digest}\n```"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fun(bot))
