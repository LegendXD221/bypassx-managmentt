"""Help command — comprehensive interactive help menu."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

HELP_MODULES = [
    ("🛡️ Moderation", "ban, unban, kick, timeout, untimeout, mute, unmute, warn, warnings, clearwarnings, purge, slowmode, lockdown, unlock, softban, nickname", "Moderation"),
    ("🤖 AutoMod", "automod toggle / status / addword / removeword / listwords / mentionthreshold / antiraidconfig", "AutoMod"),
    ("👋 Welcome", "welcome setchannel / message / leavemessage / test / autorole / placeholders", "Welcome"),
    ("🎫 Tickets", "ticket panel / close / add / remove / setstaffrole / setcategory", "Tickets"),
    ("🎭 Roles", "roles buttonpanel / reactionrole / selfrole", "Roles"),
    ("✅ Verification", "verify setup / status / disable", "Verification"),
    ("📝 Logging", "logging setchannel / setmodlog / disable", "Logging"),
    ("🔐 Security", "security scan / audit / permscheck", "Security"),
    ("⏰ Reminders", "remind / reminders / cancelreminder", "Reminders"),
    ("🏷️ Tags", "tag / tagcreate / tagdelete / taglist", "Tags"),
    ("💤 AFK", "afk", "AFK"),
    ("🛠️ Utility", "ping / uptime / serverinfo / userinfo / avatar / roleinfo / poll / membercount / servericon / firstmessage / botinfo", "Utility"),
    ("⚙️ Config", "config set / view / reset", "Admin"),
    ("👑 Owner", "reload / sync / shutdown", "Admin"),
]


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)
        self.bot = bot
        # add one select option per module
        options = [
            discord.SelectOption(label=name.split(" ", 1)[1] if " " in name else name, emoji=name.split(" ")[0], description=desc[:100], value=name)
            for name, desc, _ in HELP_MODULES
        ]
        sel = discord.ui.Select(placeholder="Browse command categories...", options=options, min_values=1, max_values=1)
        sel.callback = self.on_select
        self.add_item(sel)

    async def on_select(self, interaction: discord.Interaction) -> None:
        value = interaction.data["values"][0]
        matching = [(n, d, cog) for n, d, cog in HELP_MODULES if n == value]
        if not matching:
            return
        name, desc, cog_name = matching[0]
        embed = discord.Embed(title=f"{name} — Commands", description=f"Here are the commands in this module:\n\n`{desc}`", color=0x5865F2)
        # list actual commands in this cog
        cog = self.bot.get_cog(cog_name)
        if cog:
            cmds = [c for c in cog.walk_app_commands() if isinstance(c, app_commands.Command)]
            if cmds:
                lines = []
                for c in cmds[:25]:
                    desc_text = c.description or "—"
                    lines.append(f"• `/{c.qualified_name}` — {desc_text}")
                embed.add_field(name="Commands", value="\n".join(lines), inline=False)
        embed.set_footer(text="BypassX Management • /help")
        await interaction.response.edit_message(embed=embed, view=self)


class Help(commands.Cog):
    """Interactive help menu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show the BypassX command menu.")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="BypassX Management", description="The all-in-one Discord management bot.\n\nUse the dropdown below to browse commands by category, or scroll through the modules.", color=0x5865F2)
        for name, desc, _ in HELP_MODULES:
            embed.add_field(name=name, value=f"`{desc}`", inline=False)
        embed.set_footer(text="BypassX Management • Made for power users")
        await interaction.response.send_message(embed=embed, view=HelpView(self.bot))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
