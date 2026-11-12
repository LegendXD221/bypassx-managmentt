"""Text tools — text transformations and lookups."""
from __future__ import annotations

import base64 as b64
import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import ACCENT, embed_error, embed_info, embed_premium


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


def to_ascii_art(text: str) -> str:
    """Tiny inline ascii-ifier — single-line block letters are too big, so we just
    wrap text in a stylised box."""
    border = "═" * (len(text) + 4)
    return f"╔{border}╗\n║  {text}  ║\n╚{border}╝"


class TextTools(commands.Cog):
    """Text transformation utilities."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="mock", description="Convert text to mock SpongeBob case.")
    async def mock(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message(embed=embed_premium("Mock Case", to_mock(text)))

    @app_commands.command(name="reverse", description="Reverse a string.")
    async def reverse(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message(embed=embed_premium("Reversed", text[::-1]))

    @app_commands.command(name="encode", description="Encode text in various formats.")
    @app_commands.describe(format="base64, binary, or hex", text="Text to encode")
    async def encode(self, interaction: discord.Interaction, format: str, text: str):
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

    @app_commands.command(name="decode", description="Decode text in various formats.")
    @app_commands.describe(format="base64, binary, or hex", text="Text to decode")
    async def decode(self, interaction: discord.Interaction, format: str, text: str):
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

    @app_commands.command(name="length", description="Get the character and word count of text.")
    async def length(self, interaction: discord.Interaction, text: str):
        embed = embed_premium("Text Length")
        embed.add_field(name="Characters", value=str(len(text)), inline=True)
        embed.add_field(name="Words", value=str(len(text.split())), inline=True)
        embed.add_field(name="Lines", value=str(text.count("\n") + 1), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="vaporwave", description="Convert text to fullwidth vaporwave.")
    async def vaporwave(self, interaction: discord.Interaction, text: str):
        result = "".join(chr(0xFF01 + (ord(c) - 0x21)) if 0x21 <= ord(c) <= 0x7E else c for c in text)
        await interaction.response.send_message(embed=embed_premium("Vaporwave", result))

    @app_commands.command(name="password", description="Generate a random secure password.")
    @app_commands.describe(length="Length (8-128)", symbols="Include symbols", numbers="Include numbers")
    async def password(self, interaction: discord.Interaction, length: app_commands.Range[int, 8, 128] = 16, symbols: bool = True, numbers: bool = True):
        import random
        import string
        chars = string.ascii_letters
        if numbers:
            chars += string.digits
        if symbols:
            chars += "!@#$%^&*()-_=+[]{}<>?"
        pwd = "".join(random.choice(chars) for _ in range(length))
        await interaction.response.send_message(embed=embed_premium("Secure Password", f"```\n{pwd}\n```"), ephemeral=True)

    @app_commands.command(name="sha256", description="Compute the SHA-256 hash of text.")
    async def sha256(self, interaction: discord.Interaction, text: str):
        import hashlib
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        await interaction.response.send_message(embed=embed_premium("SHA-256", f"```\n{digest}\n```"))

    @app_commands.command(name="strawpoll", description="Alias for /poll create. Quick straw poll with up to 4 options.")
    async def strawpoll(self, interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = "", option4: str = ""):
        # delegate to reaction_polls by calling the create command path manually
        from cogs.reaction_polls import ReactionPolls, POLL_EMOJIS
        options = [o for o in [option1, option2, option3, option4] if o]
        body = "\n".join(f"{POLL_EMOJIS[i]} {opt}" for i, opt in enumerate(options))
        embed = discord.Embed(title=f"📊 {question}", description=body, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Straw Poll")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        for i in range(len(options)):
            try:
                await msg.add_reaction(POLL_EMOJIS[i])
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TextTools(bot))
