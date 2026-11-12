"""Security — anti-nuke detection, dangerous permission alerts, role hierarchy protection."""
from __future__ import annotations

import asyncio
import datetime as dt
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_success, embed_warn, is_admin, send_modlog

# Permissions that are considered dangerous when granted to non-staff
DANGEROUS_PERMS = {
    "administrator": discord.Permissions(administrator=True),
    "ban_members": discord.Permissions(ban_members=True),
    "kick_members": discord.Permissions(kick_members=True),
    "manage_guild": discord.Permissions(manage_guild=True),
    "manage_roles": discord.Permissions(manage_roles=True),
    "manage_channels": discord.Permissions(manage_channels=True),
    "manage_webhooks": discord.Permissions(manage_webhooks=True),
    "manage_emojis": discord.Permissions(manage_emojis=True),
    "mention_everyone": discord.Permissions(mention_everyone=True),
    "view_audit_log": discord.Permissions(view_audit_log=True),
}


class Security(commands.Cog):
    """Anti-nuke and dangerous-permission alerts."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.action_window: Dict[Tuple[int, int], Deque[float]] = defaultdict(lambda: deque(maxlen=30))
        self.locked_guilds: set[int] = set()

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self._audit(role.guild, action="role_create", actor=None, target=role, severity="low")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._audit(role.guild, action="role_delete", actor=None, target=role, severity="high")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._audit(channel.guild, action="channel_create", actor=None, target=channel, severity="low")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self._audit(channel.guild, action="channel_delete", actor=None, target=channel, severity="high")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        await self._audit(guild, action="ban", actor=None, target=user, severity="high")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        # check if recent ban wave
        if member.guild is None:
            return
        # Get the audit log entry, if available
        try:
            async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 30:
                    await self._audit(member.guild, action="kick", actor=entry.user, target=member, severity="medium")
                    break
        except discord.Forbidden:
            pass

    async def _audit(self, guild: discord.Guild, *, action: str, actor: discord.abc.User | None, target=None, severity: str = "low") -> None:
        """Look up the responsible moderator from the audit log and emit alerts."""
        if guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=5):
                    if entry.user.id == guild.me.id:
                        continue
                    if entry.target and target and entry.target.id == getattr(target, "id", None):
                        actor = entry.user
                        break
            except discord.Forbidden:
                pass

        if actor and not actor.bot and actor.id != guild.owner_id:
            self.action_window[(guild.id, actor.id)].append(asyncio.get_event_loop().time())
            recent = sum(1 for t in self.action_window[(guild.id, actor.id)] if t > asyncio.get_event_loop().time() - 60)
            # anti-nuke: >5 destructive actions in 60s
            if recent >= 5 and severity in ("high", "medium"):
                await self._quarantine(guild, actor, reason=f"Anti-nuke: {recent} destructive actions in 60s")
                return
            # alert on dangerous actions
            if severity == "high":
                await self._alert(guild, actor, action, target)

    async def _alert(self, guild: discord.Guild, actor: discord.abc.User, action: str, target) -> None:
        cfg = await get_db().get_guild_config(guild.id)
        channel_id = (cfg or {}).get("mod_log_channel_id") if cfg else None
        if not channel_id:
            channel_id = (cfg or {}).get("log_channel_id") if cfg else None
        if not channel_id:
            return
        ch = guild.get_channel(int(channel_id))
        if ch is None:
            return
        embed = embed_warn("⚠️ High-Severity Action", f"**{actor}** performed `{action}` on `{getattr(target, 'name', target)}`")
        embed.add_field(name="Actor", value=f"{actor.mention} (`{actor.id}`)")
        embed.add_field(name="Action", value=action)
        embed.add_field(name="Time", value=f"<t:{int(discord.utils.utcnow().timestamp())}:R>")
        try:
            await ch.send(content=f"<@{guild.owner_id}>", embed=embed, allowed_mentions=discord.AllowedMentions(users=False, everyone=False))
        except discord.HTTPException:
            pass

    async def _quarantine(self, guild: discord.Guild, actor: discord.abc.User, reason: str) -> None:
        """Quarantine a malicious actor — strip dangerous roles & timeout."""
        member = guild.get_member(actor.id)
        if member is None:
            return
        try:
            await member.timeout(discord.utils.utcnow() + dt.timedelta(hours=1), reason=reason)
        except discord.HTTPException:
            pass
        # strip roles with dangerous permissions
        for role in list(member.roles):
            if role.is_default() or role.is_integration() or role.is_bot_managed():
                continue
            if any(getattr(role.permissions, p, False) for p in DANGEROUS_PERMS):
                try:
                    await member.remove_roles(role, reason=reason)
                except discord.HTTPException:
                    pass
        await send_modlog(guild, action="anti-nuke • quarantine", target=actor, details={"Reason": reason})

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """Alert when dangerous permissions are added to a role."""
        for perm_name, perm in DANGEROUS_PERMS.items():
            before_val = getattr(before.permissions, perm_name, False)
            after_val = getattr(after.permissions, perm_name, False)
            if not before_val and after_val:
                cfg = await get_db().get_guild_config(after.guild.id)
                channel_id = (cfg or {}).get("mod_log_channel_id") if cfg else None
                if not channel_id:
                    channel_id = (cfg or {}).get("log_channel_id") if cfg else None
                if not channel_id:
                    return
                ch = after.guild.get_channel(int(channel_id))
                if ch is None:
                    return
                embed = embed_warn("⚠️ Dangerous Permission Added", f"Role {after.mention} was granted **{perm_name}**.")
                # try to find who did it
                try:
                    async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_update):
                        if entry.target.id == after.id:
                            embed.add_field(name="By", value=f"{entry.user.mention} (`{entry.user.id}`)")
                            break
                except discord.Forbidden:
                    pass
                try:
                    await ch.send(embed=embed)
                except discord.HTTPException:
                    pass
                break

    # ---------------- commands --------------------------------------------

    group = app_commands.Group(name="security", description="Security & anti-nuke configuration.", default_permissions=discord.Permissions(administrator=True))

    @group.command(name="scan", description="Scan for members with dangerous permissions.")
    @is_admin()
    async def scan(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        flagged: list[tuple[discord.Member, list[str]]] = []
        for member in interaction.guild.members:
            if member.bot or member.id == interaction.guild.owner_id:
                continue
            perms = []
            for perm_name in DANGEROUS_PERMS:
                if getattr(member.guild_permissions, perm_name, False):
                    perms.append(perm_name)
            if perms:
                flagged.append((member, perms))
        if not flagged:
            await interaction.followup.send(embed=embed_success("No Issues Found", "No members have dangerous permissions."))
            return
        embed = embed_warn("⚠️ Members with Dangerous Permissions", f"Found **{len(flagged)}** members.")
        for member, perms in flagged[:20]:
            embed.add_field(name=str(member), value=", ".join(f"`{p}`" for p in perms), inline=False)
        if len(flagged) > 20:
            embed.set_footer(text=f"Showing first 20 of {len(flagged)}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @group.command(name="audit", description="Show recent audit log entries for this server.")
    @is_admin()
    async def audit(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 25] = 10):
        if not interaction.guild.me.guild_permissions.view_audit_log:
            await interaction.response.send_message(embed=embed_error("I need View Audit Log permission."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = embed_info("Audit Log", f"Last {limit} entries:")
        try:
            async for entry in interaction.guild.audit_logs(limit=limit):
                ts = int(entry.created_at.timestamp())
                target_name = getattr(entry.target, "name", str(entry.target))
                embed.add_field(name=f"{entry.action} • <t:{ts}:R>", value=f"**By:** {entry.user.mention}\n**Target:** {target_name}\n**Reason:** {entry.reason or 'None'}", inline=False)
        except discord.Forbidden:
            await interaction.followup.send(embed=embed_error("I can't read the audit log."), ephemeral=True)
            return
        await interaction.followup.send(embed=embed, ephemeral=True)

    @group.command(name="permscheck", description="Check effective permissions for a member.")
    @is_admin()
    async def permscheck(self, interaction: discord.Interaction, member: discord.Member):
        perms = member.guild_permissions
        embed = embed_info(f"Permissions — {member}", "")
        flags = []
        for perm_name, val in perms:
            if val:
                flags.append(perm_name)
        # split into dangerous vs normal
        dangerous = [p for p in flags if p in DANGEROUS_PERMS]
        normal = [p for p in flags if p not in DANGEROUS_PERMS]
        embed.add_field(name=f"Dangerous ({len(dangerous)})", value=", ".join(f"`{p}`" for p in dangerous) or "None", inline=False)
        embed.add_field(name=f"Other ({len(normal)})", value=", ".join(f"`{p}`" for p in normal) or "None", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- anti-nuke whitelist (folded in v4) ----------

    @group.command(name="whitelist", description="Whitelist a user from anti-nuke actions.")
    @is_admin()
    async def whitelist_add(self, interaction: discord.Interaction, member: discord.Member):
        await get_db().execute(
            "INSERT INTO anti_nuke_whitelist (guild_id, user_id, added_by) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
            interaction.guild.id, member.id, interaction.user.id,
        )
        await interaction.response.send_message(embed=embed_success("Whitelisted", f"{member.mention} is now exempt from anti-nuke."))

    @group.command(name="unwhitelist", description="Remove a user from the anti-nuke whitelist.")
    @is_admin()
    async def whitelist_remove(self, interaction: discord.Interaction, member: discord.Member):
        await get_db().execute("DELETE FROM anti_nuke_whitelist WHERE guild_id=$1 AND user_id=$2", interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed_success("Removed", f"{member.mention} is no longer whitelisted."))

    @group.command(name="whitelistlist", description="List all whitelisted users.")
    @is_admin()
    async def whitelist_list(self, interaction: discord.Interaction):
        rows = await get_db().fetch("SELECT user_id FROM anti_nuke_whitelist WHERE guild_id=$1 ORDER BY user_id", interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("Empty", "No whitelisted users."))
            return
        embed = embed_premium("Anti-Nuke Whitelist", f"**{len(rows)}** whitelisted users:")
        for r in rows[:25]:
            member = interaction.guild.get_member(int(r["user_id"]))
            embed.add_field(name=f"`{r['user_id']}`", value=member.mention if member else "Not in server", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Security(bot))
