"""Help command — comprehensive interactive help menu with premium look."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils import ACCENT, GOLD, embed_premium

HELP_MODULES = [
    ("🛡  Moderation",       "ban, unban, kick, softban, timeout, mute, warn, warnings, purge, slowmode, lockdown, unlock, nickname", "Moderation"),
    ("📋  Mod Extras",       "note add / view / clear · history · memberinfo", "ModerationExtra"),
    ("🤖  AutoMod",           "automod toggle / status / addword / removeword / listwords / mentionthreshold / antiraidconfig", "AutoMod"),
    ("🛡  Anti-Nuke",         "antinuke whitelist / unwhitelist / whitelistlist / check", "AntiNukeWhitelist"),
    ("👋  Welcome",           "welcome setchannel / message / leavemessage / test / autorole / placeholders", "Welcome"),
    ("🎫  Tickets",           "ticket panel / panel-v3 / addcategory / removecategory / categories / close / add / remove / setstaffrole / setcategory", "Tickets"),
    ("🎭  Roles",             "roles buttonpanel / reactionrole / selfrole", "Roles"),
    ("▼  Dropdown Roles",    "dropdownroles create / addoption / removeoption / list", "DropdownRoles"),
    ("✅  Verification",      "verify setup / status / disable", "Verification"),
    ("📝  Logging",           "logging setchannel / setmodlog / disable", "Logging"),
    ("🔐  Security",          "security scan / audit / permscheck", "Security"),
    ("⏰  Reminders",         "remind / reminders / cancelreminder / remindme", "Reminders"),
    ("🏷  Tags",              "tag / tagcreate / tagdelete / taglist", "Tags"),
    ("💤  AFK",               "afk", "AFK"),
    ("📌  Sticky",            "sticky create / remove / list", "StickyMessages"),
    ("⭐  Starboard",         "starboard setup / disable / status", "Starboard"),
    ("🎉  Giveaways",         "giveaway start / end / reroll / list", "Giveaways"),
    ("✦  Levels",             "rank view / leaderboard · levels toggle / channel / reward / rewards / reset", "Levels"),
    ("👤  Profiles",          "profile view / bio / title / color / clear", "Profiles"),
    ("🎨  Color Roles",       "color set / clear", "ColorRoles"),
    ("🔐  Captcha",           "captcha setup / disable · verify-captcha answer", "Captcha"),
    ("💬  Auto Responder",    "autoresponder add / remove / list", "AutoResponder"),
    ("📊  Server Stats",      "serverstats setup / disable", "ServerStats"),
    ("🔊  Voice Tools",       "voice move / massmove / mute / unmute / deafen / undeafen / disconnect", "VcTools"),
    ("🔊  Temp Voice",        "tempvoice setup / status", "TempVoice"),
    ("🎯  Snipe",             "snipe / editsnipe / clearsnipe", "Snipe"),
    ("🎨  Embeds",            "embed send / save / post / list / delete", "EmbedBuilder"),
    ("⚙  Premium Panels",     "panel info / custom / roles", "PremiumPanels"),
    ("📅  Scheduled",          "schedule add / list / remove / pause / resume", "ScheduledAnnouncements"),
    ("📊  Polls",             "poll create / end · strawpoll", "ReactionPolls"),
    ("★  Reputation",        "rep view / leaderboard / give", "Reputation"),
    ("🎲  Fun",               "8ball / dice / coinflip / choose / rps / wouldyourather / random / meme", "Fun"),
    ("💾  Role Persistence",   "rolepersistence toggle / status / clear", "RolePersistence"),
    ("🎂  Birthdays",         "birthday set / view / upcoming / remove · birthdays channel / role", "Birthdays"),
    ("🔒  Lockdown",          "lockdownall / unlockall / lockdownstatus", "LockdownAll"),
    ("❝  Quotes",            "quote add / random / view / list / delete", "Quotes"),
    ("⚖  Mass Actions",      "mass roleadd / roleremove / ban / kick / nickname", "MassActions"),
    ("🔤  Text Tools",        "mock / reverse / encode / decode / length / vaporwave / password / sha256", "TextTools"),
    ("🛠  Utility",           "ping / uptime / serverinfo / userinfo / avatar / roleinfo / poll / membercount / servericon / firstmessage / botinfo", "Utility"),
    ("✦  Utility Extra",      "timeconvert / hex / rgb / base64 / inviteinfo / rolelist / channelinfo / emojiinfo / listchannels / permissions", "UtilityExtra"),
    ("⚙  Config",             "config set / view / reset", "Admin"),
    ("👑  Owner",             "eval / sql / listguilds / leaveguild / botstats / broadcast / maintenance / reloadall", "Owner"),
]


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)
        self.bot = bot
        options = [
            discord.SelectOption(label=(name.split("  ", 1)[1] if "  " in name else name), description=desc[:100], value=name)
            for name, desc, _ in HELP_MODULES
        ]
        sel = discord.ui.Select(placeholder="Browse command categories…", options=options, min_values=1, max_values=1)
        sel.callback = self.on_select
        self.add_item(sel)

    async def on_select(self, interaction: discord.Interaction) -> None:
        value = interaction.data["values"][0]
        matching = [(n, d, cog) for n, d, cog in HELP_MODULES if n == value]
        if not matching:
            return
        name, desc, cog_name = matching[0]
        embed = discord.Embed(title=name, description=f"Commands in this module:\n\n`{desc}`", color=ACCENT, timestamp=discord.utils.utcnow())
        embed.set_footer(text="BypassX  •  Premium")
        cog = self.bot.get_cog(cog_name)
        if cog:
            cmds = sorted([c for c in cog.walk_app_commands() if isinstance(c, app_commands.Command)], key=lambda c: c.qualified_name)
            if cmds:
                lines = []
                for c in cmds[:25]:
                    desc_text = c.description or "—"
                    lines.append(f"• `/{c.qualified_name}` — {desc_text}")
                embed.add_field(name="Commands", value="\n".join(lines), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)


class Help(commands.Cog):
    """Interactive help menu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show the BypassX command menu.")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="BypassX Management",
            description=(
                "The all-in-one Discord management bot.\n"
                "Pick a category from the dropdown to browse commands, or scroll through the modules below."
            ),
            color=ACCENT,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="BypassX  •  Premium")
        # split modules into compact groups to fit Discord's 25-field limit
        for name, desc, _ in HELP_MODULES[:25]:
            embed.add_field(name=name, value=f"`{desc}`", inline=False)
        await interaction.response.send_message(embed=embed, view=HelpView(self.bot))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
