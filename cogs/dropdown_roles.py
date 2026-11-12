"""Dropdown role picker — members pick one or more roles from a dropdown.

Inspired by Carl-bot & Sapphire's role menus, with a premium aesthetic.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import ACCENT, embed_error, embed_info, embed_premium, embed_success, is_admin


class DropdownRolePanelView(discord.ui.View):
    """Persistent view with a select dropdown that toggles multiple roles at once."""

    def __init__(self, panel_id: int, options: list[dict], min_values: int = 0, max_values: int = 25, placeholder: str = "Select roles…"):
        super().__init__(timeout=None)
        self.panel_id = panel_id
        if not options:
            return
        select = discord.ui.Select(
            placeholder=placeholder or "Select roles…",
            min_values=min_values,
            max_values=min(max_values, len(options)) or 1,
            options=[discord.SelectOption(
                label=o["label"][:100],
                description=(o.get("description") or "")[:100],
                emoji=o.get("emoji"),
                value=str(o["role_id"]),
            ) for o in options[:25]],
            custom_id=f"bypassx:dropdown_role:{panel_id}",
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction) -> None:
        if interaction.data is None or interaction.guild is None:
            return
        if not isinstance(interaction.user, discord.Member):
            return
        selected_ids = [int(v) for v in interaction.data.get("values", [])]
        # fetch all options for this panel
        rows = await get_db().fetch("SELECT role_id FROM dropdown_role_options WHERE panel_id=$1", self.panel_id)
        all_role_ids = [int(r["role_id"]) for r in rows]
        added = []
        removed = []
        for rid in all_role_ids:
            role = interaction.guild.get_role(rid)
            if role is None or role >= interaction.guild.me.top_role:
                continue
            try:
                if rid in selected_ids and role not in interaction.user.roles:
                    await interaction.user.add_roles(role, reason="Dropdown role pick")
                    added.append(role.mention)
                elif rid not in selected_ids and role in interaction.user.roles:
                    await interaction.user.remove_roles(role, reason="Dropdown role pick")
                    removed.append(role.mention)
            except discord.Forbidden:
                pass
        parts = []
        if added:
            parts.append(f"✓ Added: {', '.join(added)}")
        if removed:
            parts.append(f"✕ Removed: {', '.join(removed)}")
        msg = "\n".join(parts) if parts else "No changes."
        await interaction.response.send_message(embed=embed_success("Roles Updated", msg), ephemeral=True)


class DropdownRoles(commands.Cog):
    """Premium dropdown-based role picker."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="dropdownroles", description="Create dropdown-based role pickers.", default_permissions=discord.Permissions(manage_roles=True))

    @group.command(name="create", description="Create a dropdown role panel.")
    @is_admin()
    async def create(self, interaction: discord.Interaction, title: str, description: str = "Pick one or more roles below.", placeholder: str = "Select roles…", min_values: app_commands.Range[int, 0, 25] = 0, max_values: app_commands.Range[int, 1, 25] = 25):
        embed = discord.Embed(title=title, description=description, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Premium  •  Role Picker")
        # post first, then insert (so we know the message id)
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        row = await get_db().fetchrow(
            "INSERT INTO dropdown_role_panels (guild_id, channel_id, message_id, title, description, placeholder, min_values, max_values) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id",
            interaction.guild.id, interaction.channel.id, msg.id, title, description, placeholder, min_values, max_values,
        )
        # empty view for now
        view = DropdownRolePanelView(panel_id=int(row["id"]), options=[], min_values=min_values, max_values=max_values, placeholder=placeholder)
        await msg.edit(view=view)
        await interaction.followup.send(embed=embed_success("Panel Created", f"Panel ID **{row['id']}**. Now use `/dropdownroles addoption` to add roles."), ephemeral=True)

    @group.command(name="addoption", description="Add a role option to a dropdown role panel.")
    @is_admin()
    async def add_option(self, interaction: discord.Interaction, panel_id: int, role: discord.Role, label: str, description: str = "", emoji: str = ""):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("That role is above me."), ephemeral=True)
            return
        panel = await get_db().fetchrow("SELECT * FROM dropdown_role_panels WHERE id=$1 AND guild_id=$2", panel_id, interaction.guild.id)
        if not panel:
            await interaction.response.send_message(embed=embed_error("Panel not found."), ephemeral=True)
            return
        existing_count = await get_db().fetchval("SELECT COUNT(*) FROM dropdown_role_options WHERE panel_id=$1", panel_id)
        if existing_count >= 25:
            await interaction.response.send_message(embed=embed_error("Maximum 25 options per panel."), ephemeral=True)
            return
        await get_db().execute(
            "INSERT INTO dropdown_role_options (panel_id, role_id, label, description, emoji) VALUES ($1,$2,$3,$4,$5)",
            panel_id, role.id, label, description or None, emoji or None,
        )
        await self._refresh_panel(interaction.guild, panel)
        await interaction.response.send_message(embed=embed_success("Option Added", f"`{label}` → {role.mention}"))

    @group.command(name="removeoption", description="Remove a role option from a dropdown panel.")
    @is_admin()
    async def remove_option(self, interaction: discord.Interaction, panel_id: int, label: str):
        await get_db().execute("DELETE FROM dropdown_role_options WHERE panel_id=$1 AND label=$2", panel_id, label)
        panel = await get_db().fetchrow("SELECT * FROM dropdown_role_panels WHERE id=$1 AND guild_id=$2", panel_id, interaction.guild.id)
        if panel:
            await self._refresh_panel(interaction.guild, panel)
        await interaction.response.send_message(embed=embed_success("Option Removed", f"`{label}` removed from panel {panel_id}."))

    @group.command(name="list", description="List all dropdown role panels in this server.")
    async def list_panels(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT id, title, channel_id, message_id FROM dropdown_role_panels WHERE guild_id=$1 ORDER BY id", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Panels", "No dropdown role panels yet."))
            return
        embed = embed_premium("Dropdown Role Panels", f"**{len(rows)}** panel(s):")
        for r in rows[:15]:
            opts = await get_db().fetch("SELECT label FROM dropdown_role_options WHERE panel_id=$1", r["id"])
            opts_str = ", ".join(o["label"] for o in opts[:10]) or "—"
            embed.add_field(name=f"Panel #{r['id']} — {r['title']}", value=f"Channel: <#{r['channel_id']}>\nOptions: {opts_str}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _refresh_panel(self, guild: discord.Guild, panel) -> None:
        ch = guild.get_channel(int(panel["channel_id"]))
        if ch is None:
            return
        try:
            msg = await ch.fetch_message(int(panel["message_id"]))
        except (discord.NotFound, discord.Forbidden):
            return
        opts_rows = await get_db().fetch("SELECT role_id, label, description, emoji FROM dropdown_role_options WHERE panel_id=$1", int(panel["id"]))
        options = [{"role_id": int(r["role_id"]), "label": r["label"], "description": r["description"], "emoji": r["emoji"]} for r in opts_rows]
        view = DropdownRolePanelView(
            panel_id=int(panel["id"]),
            options=options,
            min_values=int(panel["min_values"]),
            max_values=int(panel["max_values"]),
            placeholder=panel["placeholder"],
        )
        try:
            await msg.edit(view=view)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DropdownRoles(bot))
