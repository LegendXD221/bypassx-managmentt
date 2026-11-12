"""Moderation suite — ban, kick, timeout, warn, purge, slowmode, lockdown, etc."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import (
    embed_error,
    embed_info,
    embed_success,
    embed_warn,
    human_timedelta,
    is_admin,
    is_mod,
    parse_duration,
    send_modlog,
)

MOD_PERMS = discord.Permissions(
    manage_messages=True, kick_members=True, ban_members=True, manage_roles=True, moderate_members=True
)


class Moderation(commands.Cog):
    """All-in-one moderation toolkit."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- helpers ----------------------------------------------

    @staticmethod
    async def _can_act(interaction: discord.Interaction, target: discord.Member) -> bool:
        if interaction.guild is None:
            return False
        mod = interaction.user
        assert isinstance(mod, discord.Member)
        if target.id == mod.id:
            await interaction.response.send_message(embed=embed_error("You can't moderate yourself."), ephemeral=True)
            return False
        if target.id == interaction.guild.owner_id:
            await interaction.response.send_message(embed=embed_error("I can't touch the server owner."), ephemeral=True)
            return False
        if target.top_role >= mod.top_role and mod.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                embed=embed_error("That member outranks or equals you in the role hierarchy."),
                ephemeral=True,
            )
            return False
        me = interaction.guild.me
        if target.top_role >= me.top_role:
            await interaction.response.send_message(
                embed=embed_error("That member outranks me — I can't act on them."),
                ephemeral=True,
            )
            return False
        return True

    # ---------------- ban ---------------------------------------------------

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(member="Member to ban", reason="Reason for the ban", delete_days="Days of messages to delete (0-7)")
    @is_mod()
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None, delete_days: app_commands.Range[int, 0, 7] = 1):
        if not await self._can_act(interaction, member):
            return
        try:
            await member.ban(reason=f"{interaction.user} ({interaction.user.id}): {reason or 'No reason provided'}", delete_message_days=delete_days)
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I lack the Ban Members permission."), ephemeral=True)
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embed_success("Member Banned", f"{member.mention} has been banned.\n**Reason:** {reason or 'No reason provided'}")
        )
        await send_modlog(interaction.guild, action="ban", target=member, moderator=interaction.user, reason=reason)

    # ---------------- unban -------------------------------------------------

    @app_commands.command(name="unban", description="Unban a user by ID or username#discrim.")
    @app_commands.describe(user_id="User ID to unban")
    @is_mod()
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str):
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message(embed=embed_error("Invalid user ID."), ephemeral=True)
            return
        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=f"{interaction.user} ({interaction.user.id})")
        except discord.NotFound:
            await interaction.response.send_message(embed=embed_error("That user isn't banned."), ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I lack permission to unban."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("User Unbanned", f"{user} has been unbanned."))
        await send_modlog(interaction.guild, action="unban", target=user, moderator=interaction.user)

    # ---------------- kick --------------------------------------------------

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="Member to kick", reason="Reason")
    @is_mod()
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        if not await self._can_act(interaction, member):
            return
        try:
            await member.kick(reason=f"{interaction.user} ({interaction.user.id}): {reason or 'No reason'}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I lack the Kick Members permission."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Member Kicked", f"{member.mention} has been kicked.\n**Reason:** {reason or 'No reason provided'}"))
        await send_modlog(interaction.guild, action="kick", target=member, moderator=interaction.user, reason=reason)

    # ---------------- timeout / mute ---------------------------------------

    @app_commands.command(name="timeout", description="Timeout a member for a duration (e.g. '1h30m').")
    @app_commands.describe(member="Member to timeout", duration="Duration like 10m, 1h, 2d", reason="Reason")
    @is_mod()
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = None):
        if not await self._can_act(interaction, member):
            return
        seconds = parse_duration(duration)
        if seconds is None or seconds < 1:
            await interaction.response.send_message(embed=embed_error("Invalid duration. Use formats like `10m`, `1h30m`, `2d`."), ephemeral=True)
            return
        if seconds > 28 * 24 * 3600:
            await interaction.response.send_message(embed=embed_error("Discord limits timeouts to 28 days."), ephemeral=True)
            return
        until = discord.utils.utcnow() + dt.timedelta(seconds=seconds)
        try:
            await member.timeout(until, reason=f"{interaction.user}: {reason or 'No reason'}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I lack permission to timeout that member."), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embed_success("Member Timed Out", f"{member.mention} is timed out for **{human_timedelta(seconds)}**.\n**Reason:** {reason or 'No reason provided'}")
        )
        await send_modlog(interaction.guild, action="timeout", target=member, moderator=interaction.user, reason=reason, details={"Duration": human_timedelta(seconds)})

    @app_commands.command(name="untimeout", description="Remove a timeout from a member.")
    @is_mod()
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        try:
            await member.timeout(None, reason=f"{interaction.user}: {reason or 'Removed'}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I lack permission."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Timeout Removed", f"{member.mention} is no longer timed out."))
        await send_modlog(interaction.guild, action="untimeout", target=member, moderator=interaction.user, reason=reason)

    # ---------------- mute (role-based, persistent across rejoins) --------

    @app_commands.command(name="mute", description="Mute a member using a configured mute role (persistent).")
    @app_commands.describe(member="Member to mute", duration="Duration like 1h30m (optional, leave blank for indefinite)", reason="Reason")
    @is_mod()
    @app_commands.default_permissions(manage_roles=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: Optional[str] = None, reason: Optional[str] = None):
        if not await self._can_act(interaction, member):
            return
        cfg = await get_db().get_guild_config(interaction.guild.id)
        mute_role_id = (cfg or {}).get("mute_role_id") if cfg else None
        if not mute_role_id:
            await interaction.response.send_message(
                embed=embed_error("No mute role configured.", "An admin must use `/config set mute_role` first."),
                ephemeral=True,
            )
            return
        mute_role = interaction.guild.get_role(int(mute_role_id))
        if mute_role is None or mute_role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("The mute role is invalid or above me."), ephemeral=True)
            return
        seconds = parse_duration(duration) if duration else None
        expires_at = None
        if seconds:
            expires_at = discord.utils.utcnow() + dt.timedelta(seconds=seconds)
        try:
            await member.add_roles(mute_role, reason=f"Muted by {interaction.user}: {reason or 'No reason'}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I can't assign the mute role."), ephemeral=True)
            return
        await get_db().execute(
            "INSERT INTO mutes (guild_id, user_id, moderator_id, reason, expires_at, active) VALUES ($1,$2,$3,$4,$5,TRUE)",
            interaction.guild.id, member.id, interaction.user.id, reason, expires_at,
        )
        await interaction.response.send_message(
            embed=embed_success(
                "Member Muted",
                f"{member.mention} has been muted{f' for **{human_timedelta(seconds)}**' if seconds else ''}.\n**Reason:** {reason or 'No reason provided'}",
            )
        )
        await send_modlog(interaction.guild, action="mute", target=member, moderator=interaction.user, reason=reason, details={"Duration": human_timedelta(seconds) if seconds else "indefinite"})

    @app_commands.command(name="unmute", description="Remove a member's mute role.")
    @is_mod()
    @app_commands.default_permissions(manage_roles=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        cfg = await get_db().get_guild_config(interaction.guild.id)
        mute_role_id = (cfg or {}).get("mute_role_id") if cfg else None
        if not mute_role_id:
            await interaction.response.send_message(embed=embed_error("No mute role configured."), ephemeral=True)
            return
        mute_role = interaction.guild.get_role(int(mute_role_id))
        if mute_role and mute_role in member.roles:
            try:
                await member.remove_roles(mute_role, reason=f"Unmuted by {interaction.user}")
            except discord.Forbidden:
                pass
        await get_db().execute(
            "UPDATE mutes SET active = FALSE WHERE guild_id = $1 AND user_id = $2 AND active = TRUE",
            interaction.guild.id, member.id,
        )
        await interaction.response.send_message(embed=embed_success("Member Unmuted", f"{member.mention} is no longer muted."))
        await send_modlog(interaction.guild, action="unmute", target=member, moderator=interaction.user, reason=reason)

    # ---------------- warn --------------------------------------------------

    @app_commands.command(name="warn", description="Warn a member. Warnings are stored permanently.")
    @app_commands.describe(member="Member to warn", reason="Reason")
    @is_mod()
    @app_commands.default_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if member.bot:
            await interaction.response.send_message(embed=embed_error("You can't warn a bot."), ephemeral=True)
            return
        await get_db().execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES ($1,$2,$3,$4)",
            interaction.guild.id, member.id, interaction.user.id, reason,
        )
        count = await get_db().fetchval(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = $1 AND user_id = $2",
            interaction.guild.id, member.id,
        )
        await interaction.response.send_message(
            embed=embed_warn("Member Warned", f"{member.mention} has been warned.\n**Reason:** {reason}\n**Total warnings:** {count}")
        )
        await send_modlog(interaction.guild, action="warn", target=member, moderator=interaction.user, reason=reason, details={"Total": count})

    @app_commands.command(name="warnings", description="List warnings for a member.")
    @app_commands.describe(member="Member (defaults to yourself)")
    @is_mod()
    @app_commands.default_permissions(manage_messages=True)
    async def warnings(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        rows = await get_db().fetch(
            "SELECT reason, moderator_id, created_at FROM warnings WHERE guild_id = $1 AND user_id = $2 ORDER BY created_at DESC LIMIT 25",
            interaction.guild.id, member.id,
        )
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Warnings", f"{member.mention} has a clean record."))
            return
        embed = embed_info(f"Warnings for {member}", f"Total: **{len(rows)}** (showing last 25)")
        for r in rows:
            mod = self.bot.get_user(r["moderator_id"]) or await self.bot.fetch_user(r["moderator_id"])
            embed.add_field(
                name=f"• {r['created_at'].strftime('%Y-%m-%d %H:%M UTC')}",
                value=f"**Reason:** {r['reason']}\nBy: {mod.mention if mod else r['moderator_id']}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member.")
    @is_admin()
    @app_commands.default_permissions(manage_guild=True)
    async def clear_warnings(self, interaction: discord.Interaction, member: discord.Member):
        await get_db().execute("DELETE FROM warnings WHERE guild_id = $1 AND user_id = $2", interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed_success("Warnings Cleared", f"All warnings for {member.mention} have been removed."))
        await send_modlog(interaction.guild, action="clear-warnings", target=member, moderator=interaction.user)

    # ---------------- purge -------------------------------------------------

    @app_commands.command(name="purge", description="Bulk delete recent messages.")
    @app_commands.describe(amount="Number of messages (1-1000)", member="Filter by member (optional)")
    @is_mod()
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000], member: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        deleted = 0
        if member:
            def check(m: discord.Message) -> bool:
                return m.author.id == member.id
            try:
                deleted = len(await interaction.channel.purge(limit=amount + 5, check=check, bulk=True))
            except discord.HTTPException:
                pass
        else:
            try:
                deleted = len(await interaction.channel.purge(limit=amount, bulk=True))
            except discord.HTTPException:
                pass
        await interaction.followup.send(embed=embed_success("Purge Complete", f"Deleted **{deleted}** messages."), ephemeral=True)
        await send_modlog(interaction.guild, action="purge", moderator=interaction.user, details={"Channel": interaction.channel.mention, "Count": deleted, "Filter": member.mention if member else "None"})

    # ---------------- slowmode ----------------------------------------------

    @app_commands.command(name="slowmode", description="Set slowmode for the current channel.")
    @app_commands.describe(seconds="Seconds (0-21600). 0 disables.")
    @is_mod()
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        try:
            await interaction.channel.edit(slowmode_delay=seconds)
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I can't edit this channel."), ephemeral=True)
            return
        if seconds == 0:
            await interaction.response.send_message(embed=embed_success("Slowmode Disabled", "Slowmode has been turned off in this channel."))
        else:
            await interaction.response.send_message(embed=embed_success("Slowmode Set", f"Slowmode set to **{human_timedelta(seconds)}** in this channel."))

    # ---------------- lockdown ---------------------------------------------

    @app_commands.command(name="lockdown", description="Lock the current channel — @everyone loses send permission.")
    @is_mod()
    @app_commands.default_permissions(manage_channels=True)
    async def lockdown(self, interaction: discord.Interaction):
        ov = interaction.channel.overwrites_for(interaction.guild.default_role)
        if ov.send_messages is False:
            await interaction.response.send_message(embed=embed_warn("Already Locked", "This channel is already locked down."), ephemeral=True)
            return
        try:
            await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False, reason=f"Lockdown by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I lack permission to manage this channel."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_warn("Channel Locked", "This channel is now in lockdown."))
        await send_modlog(interaction.guild, action="lockdown", moderator=interaction.user, details={"Channel": interaction.channel.mention})

    @app_commands.command(name="unlock", description="Unlock a channel previously locked down.")
    @is_mod()
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        try:
            await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None, reason=f"Unlock by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I lack permission."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Channel Unlocked", "Lockdown has been lifted."))
        await send_modlog(interaction.guild, action="unlock", moderator=interaction.user, details={"Channel": interaction.channel.mention})

    # ---------------- softban / hackban ------------------------------------

    @app_commands.command(name="softban", description="Ban then unban a member to purge their recent messages.")
    @app_commands.describe(member="Member to softban", reason="Reason")
    @is_mod()
    @app_commands.default_permissions(ban_members=True)
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        if not await self._can_act(interaction, member):
            return
        try:
            await member.ban(reason=f"Softban by {interaction.user}: {reason or ''}", delete_message_days=7)
            await member.unban(reason="Softban completion")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I lack ban permissions."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Member Softbanned", f"{member.mention} was softbanned (7 days of messages cleared)."))
        await send_modlog(interaction.guild, action="softban", target=member, moderator=interaction.user, reason=reason)

    # ---------------- nickname ----------------------------------------------

    @app_commands.command(name="nickname", description="Change a member's nickname.")
    @app_commands.describe(member="Member", nickname="New nickname (leave empty to reset)")
    @is_mod()
    @app_commands.default_permissions(manage_nicknames=True)
    async def nickname(self, interaction: discord.Interaction, member: discord.Member, nickname: Optional[str] = None):
        if member.top_role >= interaction.guild.me.top_role and member.id != interaction.guild.owner_id:
            await interaction.response.send_message(embed=embed_error("That member outranks me."), ephemeral=True)
            return
        try:
            await member.edit(nick=nickname or None, reason=f"Nickname change by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I lack the Manage Nicknames permission."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Nickname Updated", f"New nickname for {member.mention}: **{nickname or '(reset)'}**"))

    # ---------------- mod notes (folded from moderation_extra) -------------

    note = app_commands.Group(name="note", description="Private moderator notes on members.", default_permissions=discord.Permissions(manage_messages=True))

    @note.command(name="add", description="Add a private mod note about a member.")
    @is_mod()
    async def note_add(self, interaction: discord.Interaction, member: discord.Member, note: str):
        await get_db().execute(
            "INSERT INTO mod_notes (guild_id, user_id, moderator_id, note) VALUES ($1,$2,$3,$4)",
            interaction.guild.id, member.id, interaction.user.id, note,
        )
        await interaction.response.send_message(embed=embed_success("Note Added", f"Private note saved for {member.mention}."), ephemeral=True)

    @note.command(name="view", description="View private mod notes for a member.")
    @is_mod()
    async def note_view(self, interaction: discord.Interaction, member: discord.Member):
        rows = await get_db().fetch(
            "SELECT note, moderator_id, created_at FROM mod_notes WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 15",
            interaction.guild.id, member.id,
        )
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Notes", f"No private notes for {member.mention}."), ephemeral=True)
            return
        embed = embed_premium(f"Mod Notes — {member}", f"**{len(rows)}** note(s):")
        for r in rows[:15]:
            mod = self.bot.get_user(int(r["moderator_id"])) or await self.bot.fetch_user(int(r["moderator_id"]))
            embed.add_field(name=f"<t:{int(r['created_at'].timestamp())}:R>", value=f"{r['note']}\n— {mod.mention if mod else r['moderator_id']}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @note.command(name="clear", description="Clear all mod notes for a member.")
    @is_mod()
    async def note_clear(self, interaction: discord.Interaction, member: discord.Member):
        await get_db().execute("DELETE FROM mod_notes WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed_success("Notes Cleared", f"All notes for {member.mention} removed."), ephemeral=True)

    @app_commands.command(name="history", description="Show a member's full moderation history.")
    @is_mod()
    @app_commands.default_permissions(manage_messages=True)
    async def history(self, interaction: discord.Interaction, member: discord.Member):
        warnings = await get_db().fetch("SELECT reason, created_at FROM warnings WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 10", interaction.guild.id, member.id)
        mutes = await get_db().fetch("SELECT reason, created_at FROM mutes WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 10", interaction.guild.id, member.id)
        notes_count = await get_db().fetchval("SELECT COUNT(*) FROM mod_notes WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        embed = embed_premium(f"History — {member}", f"Warnings: **{len(warnings)}** · Mutes: **{len(mutes)}** · Notes: **{notes_count}**")
        if warnings:
            embed.add_field(name="⚠ Recent Warnings", value="\n".join(f"• {r['reason']} — <t:{int(r['created_at'].timestamp())}:R>" for r in warnings[:5]), inline=False)
        if mutes:
            embed.add_field(name="🔇 Recent Mutes", value="\n".join(f"• {r['reason'] or 'No reason'} — <t:{int(r['created_at'].timestamp())}:R>" for r in mutes[:5]), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="memberinfo", description="Show detailed mod-facing info about a member.")
    @is_mod()
    @app_commands.default_permissions(manage_messages=True)
    async def memberinfo(self, interaction: discord.Interaction, member: discord.Member):
        warnings = await get_db().fetchval("SELECT COUNT(*) FROM warnings WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        notes = await get_db().fetchval("SELECT COUNT(*) FROM mod_notes WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        embed = embed_premium(f"Member Info — {member}")
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "—", inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
        embed.add_field(name="Roles", value=str(len(member.roles) - 1), inline=True)
        embed.add_field(name="Warnings", value=str(warnings), inline=True)
        embed.add_field(name="Mod Notes", value=str(notes), inline=True)
        embed.add_field(name="Timeout", value=f"<t:{int(member.timed_out_until.timestamp())}:R>" if member.timed_out_until else "None", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------- mute expiry processor (called from background task) --------

async def process_expired_mutes(bot: commands.Bot) -> None:
    """Walk through active mutes whose expires_at has passed and remove the role."""
    from database import get_db
    rows = await get_db().fetch(
        "SELECT id, guild_id, user_id FROM mutes WHERE active = TRUE AND expires_at IS NOT NULL AND expires_at <= NOW()"
    )
    for row in rows:
        guild = bot.get_guild(int(row["guild_id"]))
        if not guild:
            continue
        member = guild.get_member(int(row["user_id"]))
        cfg = await get_db().get_guild_config(guild.id)
        mute_role_id = (cfg or {}).get("mute_role_id") if cfg else None
        if mute_role_id and member:
            role = guild.get_role(int(mute_role_id))
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Mute expired")
                except discord.HTTPException:
                    pass
        await get_db().execute("UPDATE mutes SET active = FALSE WHERE id = $1", row["id"])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
