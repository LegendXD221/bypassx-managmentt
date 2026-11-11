"""Ticket system — panel-based ticket creation, claim, and close with transcript."""
from __future__ import annotations

import io
import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import embed_error, embed_info, embed_success, embed_warn, is_admin, send_modlog

TICKET_CATEGORY_NAME = "BypassX Tickets"
TRANSCRIPT_LIMIT = 500


class TicketView(discord.ui.View):
    def __init__(self, panel_id: int):
        super().__init__(timeout=None)
        self.panel_id = panel_id

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.success, emoji="🎫", custom_id="bypassx:ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # check existing open ticket
        existing = await get_db().fetchrow(
            "SELECT channel_id FROM tickets WHERE guild_id=$1 AND user_id=$2 AND closed=FALSE",
            interaction.guild.id, interaction.user.id,
        )
        if existing:
            ch = interaction.guild.get_channel(int(existing["channel_id"]))
            if ch:
                await interaction.response.send_message(embed=embed_error("You already have an open ticket.", f"Go to {ch.mention}."), ephemeral=True)
                return
            await get_db().execute("UPDATE tickets SET closed=TRUE WHERE channel_id=$1", existing["channel_id"])

        # staff role from guild config
        cfg = await get_db().get_guild_config(interaction.guild.id)
        staff_role_id = (cfg or {}).get("ticket_staff_role_id") if cfg else None
        # category
        cat_id = (cfg or {}).get("ticket_category_id") if cfg else None
        category = None
        if cat_id:
            category = interaction.guild.get_channel(int(cat_id))
        if category is None or not isinstance(category, discord.CategoryChannel):
            category = discord.utils.get(interaction.guild.categories, name=TICKET_CATEGORY_NAME)
            if category is None:
                try:
                    category = await interaction.guild.create_category(TICKET_CATEGORY_NAME)
                except discord.Forbidden:
                    await interaction.response.send_message(embed=embed_error("I can't create a ticket category."), ephemeral=True)
                    return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff_role_id:
            role = interaction.guild.get_role(int(staff_role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{interaction.user.name}"[:50],
                category=category,
                overwrites=overwrites,
                topic=f"Ticket by {interaction.user} ({interaction.user.id})",
                reason=f"Ticket opened by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I can't create the ticket channel."), ephemeral=True)
            return

        await get_db().execute(
            "INSERT INTO tickets (guild_id, channel_id, user_id) VALUES ($1,$2,$3)",
            interaction.guild.id, channel.id, interaction.user.id,
        )

        embed = embed_info("Ticket Opened", f"Hello {interaction.user.mention}! A staff member will be with you shortly.\nTo close this ticket, use the button below or `/ticket close`.")
        if staff_role_id:
            role = interaction.guild.get_role(int(staff_role_id))
            if role:
                embed.description += f"\n\n**Tagging support staff:** {role.mention}"
        await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView())
        await interaction.response.send_message(embed=embed_success("Ticket Created", f"Your ticket has been created: {channel.mention}"), ephemeral=True)
        await send_modlog(interaction.guild, action="ticket • opened", target=interaction.user, details={"Channel": channel.mention})


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, emoji="✋", custom_id="bypassx:ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            return
        row = await get_db().fetchrow("SELECT id, claimed_by FROM tickets WHERE channel_id=$1 AND closed=FALSE", interaction.channel.id)
        if not row:
            await interaction.response.send_message(embed=embed_error("This isn't an open ticket."), ephemeral=True)
            return
        if row["claimed_by"]:
            await interaction.response.send_message(embed=embed_error("Already claimed."), ephemeral=True)
            return
        await get_db().execute("UPDATE tickets SET claimed_by=$1 WHERE id=$2", interaction.user.id, row["id"])
        button.disabled = True
        button.label = f"Claimed by {interaction.user.name}"
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(embed=embed_success("Ticket Claimed", f"{interaction.user.mention} has claimed this ticket."))

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="bypassx:ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await close_ticket(interaction)


async def close_ticket(interaction: discord.Interaction, *, reason: Optional[str] = None) -> None:
    row = await get_db().fetchrow("SELECT user_id, claimed_by FROM tickets WHERE channel_id=$1 AND closed=FALSE", interaction.channel.id)
    if not row:
        await interaction.response.send_message(embed=embed_error("This isn't an open ticket channel."), ephemeral=True)
        return
    channel = interaction.channel
    # build transcript
    msgs: list[discord.Message] = []
    try:
        async for m in channel.history(limit=TRANSCRIPT_LIMIT, oldest_first=True):
            msgs.append(m)
    except discord.HTTPException:
        pass

    transcript_lines = [f"BypassX Management — Ticket Transcript",
                        f"Channel: #{channel.name}  ({channel.id})",
                        f"Opener ID: {row['user_id']}",
                        f"Closed by: {interaction.user} ({interaction.user.id})",
                        f"Closed at: {dt.datetime.now(dt.UTC).isoformat()}",
                        f"Reason: {reason or 'No reason provided'}",
                        "=" * 60, ""]
    for m in msgs:
        author = m.author
        ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        transcript_lines.append(f"[{ts}] {author}: {m.content}")
        for a in m.attachments:
            transcript_lines.append(f"  [attachment: {a.filename} ({a.size} bytes)]")

    transcript = "\n".join(transcript_lines)
    buf = io.BytesIO(transcript.encode("utf-8"))
    buf.seek(0)

    opener = interaction.guild.get_member(int(row["user_id"])) or await interaction.bot.fetch_user(int(row["user_id"]))
    try:
        if isinstance(opener, discord.Member) or opener:
            await opener.send(embed=embed_info("Ticket Closed", f"Your ticket in **{interaction.guild.name}** was closed.\nReason: {reason or 'No reason provided'}"),
                              file=discord.File(buf, filename=f"transcript-{channel.name}.txt"))
    except discord.Forbidden:
        pass

    await get_db().execute("UPDATE tickets SET closed=TRUE WHERE channel_id=$1", channel.id)
    await interaction.response.send_message(embed=embed_warn("Ticket Closing", "Saving transcript and deleting in 5 seconds..."))
    await send_modlog(interaction.guild, action="ticket • closed", target=opener, moderator=interaction.user, reason=reason, details={"Channel": channel.mention})
    await discord.utils.sleep_until(discord.utils.utcnow() + dt.timedelta(seconds=5))
    try:
        await channel.delete(reason=f"Ticket closed by {interaction.user}")
    except discord.HTTPException:
        pass


class Tickets(commands.Cog):
    """Ticket panel management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(TicketView(panel_id=0))
        bot.add_view(TicketControlView())

    group = app_commands.Group(name="ticket", description="Ticket system management.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="panel", description="Post a ticket panel that members can click to open a ticket.")
    @app_commands.describe(title="Panel title", description="Panel description")
    @is_admin()
    async def create_panel(self, interaction: discord.Interaction, title: str = "Support Tickets", description: str = "Click the button below to open a private ticket with the staff team."):
        embed = discord.Embed(title=title, description=description, color=0x5865F2, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX Management • Ticket System")
        await interaction.response.send_message(embed=embed, view=TicketView(panel_id=0))
        msg = await interaction.original_response()
        await get_db().execute(
            "INSERT INTO ticket_panels (guild_id, channel_id, message_id, title, description) VALUES ($1,$2,$3,$4,$5)",
            interaction.guild.id, interaction.channel.id, msg.id, title, description,
        )

    @group.command(name="close", description="Close the ticket in this channel.")
    @app_commands.describe(reason="Reason for closing")
    async def close_cmd(self, interaction: discord.Interaction, reason: Optional[str] = None):
        await close_ticket(interaction, reason=reason)

    @group.command(name="add", description="Add a user to the current ticket channel.")
    @is_admin()
    async def add_user(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        except discord.HTTPException:
            await interaction.response.send_message(embed=embed_error("Failed to add user."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("User Added", f"{member.mention} can now see this ticket."))

    @group.command(name="remove", description="Remove a user from the current ticket channel.")
    @is_admin()
    async def remove_user(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await interaction.channel.set_permissions(member, view_channel=False)
        except discord.HTTPException:
            await interaction.response.send_message(embed=embed_error("Failed to remove user."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("User Removed", f"{member.mention} can no longer see this ticket."))

    @group.command(name="setstaffrole", description="Set the role that has access to all tickets.")
    @is_admin()
    async def set_staff_role(self, interaction: discord.Interaction, role: discord.Role):
        await get_db().set_guild_field(interaction.guild.id, "ticket_staff_role_id", role.id)
        await interaction.response.send_message(embed=embed_success("Staff Role Set", f"{role.mention} will be added to all new tickets."))

    @group.command(name="setcategory", description="Set the category where tickets are created.")
    @is_admin()
    async def set_category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await get_db().set_guild_field(interaction.guild.id, "ticket_category_id", category.id)
        await interaction.response.send_message(embed=embed_success("Ticket Category Set", f"New tickets will be created under {category.mention}."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
