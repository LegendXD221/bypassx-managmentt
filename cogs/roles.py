"""Reaction roles & button-role self-assignable roles."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_success, is_admin


class RolePanelView(discord.ui.View):
    """Dynamic view with one toggle button per role.

    Buttons are created at runtime; custom_id encodes the role id so the
    interaction persists across restarts.
    """

    def __init__(self, entries: list[tuple[int, str, discord.ButtonStyle, Optional[str]]]):
        super().__init__(timeout=None)
        for role_id, label, style, emoji in entries:
            btn = discord.ui.Button(
                label=label,
                style=style,
                emoji=emoji,
                custom_id=f"bypassx:role:{role_id}",
            )
            self.add_item(btn)


class Roles(commands.Cog):
    """Self-assignable roles via buttons and reaction roles via emoji."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.member is None or payload.member.bot:
            return
        rows = await get_db().fetch("SELECT role_id, emoji FROM reaction_roles WHERE message_id=$1", payload.message_id)
        if not rows:
            return
        emoji_str = str(payload.emoji)
        match = None
        for r in rows:
            if r["emoji"] == emoji_str:
                match = r["role_id"]
                break
        if match is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(int(match)) if guild else None
        if role is None or role >= guild.me.top_role:
            return
        try:
            await payload.member.add_roles(role, reason="Reaction role")
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return
        rows = await get_db().fetch("SELECT role_id, emoji FROM reaction_roles WHERE message_id=$1", payload.message_id)
        if not rows:
            return
        emoji_str = str(payload.emoji)
        match = None
        for r in rows:
            if r["emoji"] == emoji_str:
                match = r["role_id"]
                break
        if match is None:
            return
        role = guild.get_role(int(match)) if guild else None
        if role is None:
            return
        try:
            await member.remove_roles(role, reason="Reaction role removed")
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        # handle button role toggle
        if interaction.data is None or interaction.data.get("component_type") != 2:
            return
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("bypassx:role:"):
            return
        try:
            role_id = int(custom_id.split(":")[2])
        except (ValueError, IndexError):
            return
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return
        role = interaction.guild.get_role(role_id)
        if role is None or role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("This role is no longer available."), ephemeral=True)
            return
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Self-role toggle")
                await interaction.response.send_message(embed=embed_success("Role Removed", f"You no longer have {role.mention}."), ephemeral=True)
            else:
                await interaction.user.add_roles(role, reason="Self-role toggle")
                await interaction.response.send_message(embed=embed_success("Role Added", f"You now have {role.mention}."), ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I can't assign that role."), ephemeral=True)

    # ---------------- button roles -----------------------------------------

    group = app_commands.Group(name="roles", description="Self-assignable role management.", default_permissions=discord.Permissions(manage_roles=True))

    @group.command(name="buttonpanel", description="Post a panel of button roles. Members click to toggle.")
    @is_admin()
    async def button_panel(self, interaction: discord.Interaction, title: str, description: str, role1: discord.Role, label1: str, role2: Optional[discord.Role] = None, label2: Optional[str] = None, role3: Optional[discord.Role] = None, label3: Optional[str] = None, role4: Optional[discord.Role] = None, label4: Optional[str] = None, role5: Optional[discord.Role] = None, label5: Optional[str] = None):
        if any(r and r >= interaction.guild.me.top_role for r in [role1, role2, role3, role4, role5]):
            await interaction.response.send_message(embed=embed_error("One or more roles are above me."), ephemeral=True)
            return
        entries: list[tuple[int, str, discord.ButtonStyle, Optional[str]]] = []
        pairs = [(role1, label1), (role2, label2), (role3, label3), (role4, label4), (role5, label5)]
        for i, (r, l) in enumerate(pairs):
            if r is None or not l:
                continue
            styles = [discord.ButtonStyle.primary, discord.ButtonStyle.success, discord.ButtonStyle.secondary, discord.ButtonStyle.danger, discord.ButtonStyle.primary]
            entries.append((r.id, l, styles[i % len(styles)], None))
        if not entries:
            await interaction.response.send_message(embed=embed_error("You must provide at least role1 + label1."), ephemeral=True)
            return
        embed = discord.Embed(title=title, description=description, color=0x5865F2, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX Management • Click a button to toggle a role")
        view = RolePanelView(entries)
        await interaction.response.send_message(embed=embed, view=view)

    @group.command(name="reactionrole", description="Post a reaction-role message. Members react with the emoji to get the role.")
    @is_admin()
    async def reaction_role(self, interaction: discord.Interaction, title: str, description: str, role: discord.Role, emoji: str):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("That role is above me."), ephemeral=True)
            return
        embed = discord.Embed(title=title, description=description, color=0x5865F2, timestamp=dt.datetime.now(dt.UTC))
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Emoji", value=emoji, inline=True)
        embed.set_footer(text=f"React with {emoji} to receive the role")
        msg = await interaction.channel.send(embed=embed)
        try:
            await msg.add_reaction(emoji)
        except discord.HTTPException:
            await interaction.response.send_message(embed=embed_error("That emoji isn't valid."), ephemeral=True)
            return
        await get_db().execute(
            "INSERT INTO reaction_roles (guild_id, message_id, channel_id, emoji, role_id) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (message_id, emoji) DO NOTHING",
            interaction.guild.id, msg.id, interaction.channel.id, emoji, role.id,
        )
        await interaction.response.send_message(embed=embed_success("Reaction Role Posted", f"Members can now react with {emoji} to get {role.mention}."), ephemeral=True)

    @group.command(name="selfrole", description="Give yourself a self-assignable role.")
    async def selfrole(self, interaction: discord.Interaction, role: discord.Role):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("That role isn't self-assignable."), ephemeral=True)
            return
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Self-role toggle")
                await interaction.response.send_message(embed=embed_success("Role Removed", f"You no longer have {role.mention}."), ephemeral=True)
            else:
                await interaction.user.add_roles(role, reason="Self-role")
                await interaction.response.send_message(embed=embed_success("Role Added", f"You now have {role.mention}."), ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I can't assign that role."), ephemeral=True)

    # ---------- color roles (folded in v4) ----------

    color = app_commands.Group(name="color", description="Custom color roles.", default_permissions=None)

    @color.command(name="set", description="Set your name color with a hex code. Creates a personal role.")
    async def color_set(self, interaction: discord.Interaction, hex_color: str):
        try:
            hex_str = hex_color.lstrip("#").strip()
            if len(hex_str) == 3:
                hex_str = "".join(c * 2 for c in hex_str)
            color_int = int(hex_str, 16)
        except (ValueError, TypeError):
            await interaction.response.send_message(embed=embed_error("Invalid hex. Use `#6366F1` or `6366F1`."), ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member):
            return
        row = await get_db().fetchrow("SELECT role_id FROM user_color_roles WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
        role = None
        if row:
            role = interaction.guild.get_role(int(row["role_id"]))
        if role is None:
            try:
                role = await interaction.guild.create_role(name=interaction.user.name, color=color_int, reason=f"Color role for {interaction.user}")
                target_pos = min(interaction.user.top_role.position + 1, interaction.guild.me.top_role.position - 1)
                if target_pos > 0:
                    try:
                        await role.edit(position=target_pos)
                    except discord.HTTPException:
                        pass
                await interaction.user.add_roles(role, reason="Color role")
                await get_db().execute(
                    "INSERT INTO user_color_roles (user_id, guild_id, role_id, color) VALUES ($1,$2,$3,$4) ON CONFLICT (user_id, guild_id) DO UPDATE SET role_id=$3, color=$4",
                    interaction.user.id, interaction.guild.id, role.id, color_int,
                )
            except discord.Forbidden:
                await interaction.response.send_message(embed=embed_error("I need Manage Roles permission."), ephemeral=True)
                return
            except discord.HTTPException as exc:
                await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
                return
        else:
            try:
                await role.edit(color=color_int, reason=f"Color update by {interaction.user}")
                await get_db().execute("UPDATE user_color_roles SET color=$1 WHERE user_id=$2 AND guild_id=$3", color_int, interaction.user.id, interaction.guild.id)
            except discord.HTTPException as exc:
                await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
                return
        embed = discord.Embed(title="✦ Color Set", description=f"Your name color is now `#{hex_str.upper()}`.", color=color_int, timestamp=discord.utils.utcnow())
        embed.set_footer(text="BypassX  •  Premium")
        await interaction.response.send_message(embed=embed)

    @color.command(name="clear", description="Remove your custom color role.")
    async def color_clear(self, interaction: discord.Interaction):
        row = await get_db().fetchrow("SELECT role_id FROM user_color_roles WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
        if not row:
            await interaction.response.send_message(embed=embed_error("You don't have a custom color."), ephemeral=True)
            return
        role = interaction.guild.get_role(int(row["role_id"]))
        if role:
            try:
                await role.delete(reason=f"Color cleared by {interaction.user}")
            except discord.HTTPException:
                pass
        await get_db().execute("DELETE FROM user_color_roles WHERE user_id=$1 AND guild_id=$2", interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed_success("Color Cleared", "Your custom color role has been removed."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
