"""Premium info panels with dropdown navigation.

A single persistent embed with a dropdown that switches between modules:
overview, rules, channels, roles, faq, support. Pure aesthetic — minimal
content, lots of whitespace, premium footer.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import ACCENT, GOLD, embed_error, embed_info, embed_premium, embed_success, is_admin


class PremiumPanelView(discord.ui.View):
    def __init__(self, modules: list[tuple[str, str, str]]):
        """modules: list of (label, description, content) tuples."""
        super().__init__(timeout=None)
        if not modules:
            return
        select = discord.ui.Select(
            placeholder="Navigate…",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=label[:100], description=desc[:100] if desc else None, value=str(i)) for i, (label, desc, _c) in enumerate(modules[:25])],
            custom_id="bypassx:premium_panel:navigate",
        )
        self.modules = modules
        select.callback = self.on_pick
        self.add_item(select)

    async def on_pick(self, interaction: discord.Interaction) -> None:
        if interaction.data is None:
            return
        try:
            idx = int(interaction.data["values"][0])
        except (ValueError, IndexError):
            return
        if idx >= len(self.modules):
            await interaction.response.send_message(embed=embed_error("Module not found."), ephemeral=True)
            return
        label, _desc, content = self.modules[idx]
        embed = discord.Embed(title=label, description=content, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Premium")
        await interaction.response.edit_message(embed=embed, view=self)


class PremiumPanels(commands.Cog):
    """Aesthetic info panels with dropdown navigation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="panel", description="Post premium info panels with dropdown navigation.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="info", description="Post a multi-section info panel with dropdown navigation.")
    @is_admin()
    @app_commands.describe(
        title="Panel title",
        overview="Overview content (markdown supported)",
        rules="Rules content",
        channels="Channels guide content",
        roles="Roles info content",
        faq="FAQ content",
        support="Support info content",
    )
    async def info_panel(
        self,
        interaction: discord.Interaction,
        title: str,
        overview: str = "Welcome to our community.",
        rules: str = "Be respectful. No spam. Follow Discord TOS.",
        channels: str = "See channel topics for details.",
        roles: str = "Roles are assignable via the role picker.",
        faq: str = "Ask in #support if you need help.",
        support: str = "Open a ticket to reach staff.",
    ):
        modules = [
            ("Overview", "Start here", overview),
            ("Rules", "Server rules", rules),
            ("Channels", "Channel guide", channels),
            ("Roles", "Role info", roles),
            ("FAQ", "Frequently asked", faq),
            ("Support", "Get help", support),
        ]
        embed = discord.Embed(title=title, description=overview, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Premium  •  Use the dropdown to navigate")
        view = PremiumPanelView(modules)
        await interaction.response.send_message(embed=embed, view=view)

    @group.command(name="custom", description="Post a custom info panel with up to 6 sections.")
    @is_admin()
    async def custom_panel(
        self,
        interaction: discord.Interaction,
        title: str,
        section1_label: str,
        section1_content: str,
        section2_label: str = "",
        section2_content: str = "",
        section3_label: str = "",
        section3_content: str = "",
        section4_label: str = "",
        section4_content: str = "",
        section5_label: str = "",
        section5_content: str = "",
        section6_label: str = "",
        section6_content: str = "",
    ):
        modules: list[tuple[str, str, str]] = [(section1_label, "", section1_content)]
        for i in range(2, 7):
            label = locals().get(f"section{i}_label", "")
            content = locals().get(f"section{i}_content", "")
            if label and content:
                modules.append((label, "", content))
        embed = discord.Embed(title=title, description=section1_content, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Premium")
        view = PremiumPanelView(modules)
        await interaction.response.send_message(embed=embed, view=view)

    @group.command(name="roles", description="Post a premium role-picker panel that uses buttons (max 5).")
    @is_admin()
    async def roles_panel(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        role1: discord.Role,
        label1: str,
        role2: Optional[discord.Role] = None,
        label2: Optional[str] = None,
        role3: Optional[discord.Role] = None,
        label3: Optional[str] = None,
        role4: Optional[discord.Role] = None,
        label4: Optional[str] = None,
        role5: Optional[discord.Role] = None,
        label5: Optional[str] = None,
    ):
        if any(r and r >= interaction.guild.me.top_role for r in [role1, role2, role3, role4, role5]):
            await interaction.response.send_message(embed=embed_error("One or more roles are above me."), ephemeral=True)
            return
        pairs = [(role1, label1), (role2, label2), (role3, label3), (role4, label4), (role5, label5)]
        entries: list[tuple[int, str]] = []
        for r, l in pairs:
            if r is None or not l:
                continue
            entries.append((r.id, l))
        if not entries:
            await interaction.response.send_message(embed=embed_error("Provide at least role1 + label1."), ephemeral=True)
            return
        embed = discord.Embed(title=title, description=description, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Premium  •  Click to toggle a role")
        view = _ButtonRolesView(entries)
        await interaction.response.send_message(embed=embed, view=view)


class _ButtonRolesView(discord.ui.View):
    def __init__(self, entries: list[tuple[int, str]]):
        super().__init__(timeout=None)
        styles = [discord.ButtonStyle.primary, discord.ButtonStyle.success, discord.ButtonStyle.secondary, discord.ButtonStyle.danger, discord.ButtonStyle.primary]
        for i, (rid, label) in enumerate(entries[:5]):
            btn = discord.ui.Button(label=label, style=styles[i % len(styles)], custom_id=f"bypassx:role:{rid}")
            btn.callback = self._make_callback(rid)
            self.add_item(btn)

    def _make_callback(self, role_id: int):
        async def cb(interaction: discord.Interaction):
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return
            role = interaction.guild.get_role(role_id)
            if role is None or role >= interaction.guild.me.top_role:
                await interaction.response.send_message(embed=embed_error("Role unavailable."), ephemeral=True)
                return
            try:
                if role in interaction.user.roles:
                    await interaction.user.remove_roles(role, reason="Self-role toggle")
                    await interaction.response.send_message(embed=embed_success("Removed", f"You no longer have {role.mention}."), ephemeral=True)
                else:
                    await interaction.user.add_roles(role, reason="Self-role toggle")
                    await interaction.response.send_message(embed=embed_success("Added", f"You now have {role.mention}."), ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(embed=embed_error("I can't manage that role."), ephemeral=True)
        return cb


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PremiumPanels(bot))
