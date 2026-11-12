"""Premium ticket system with dropdown category selection and multi-button panels.

Each panel can be created with:
  • `/ticket panel` — single-button panel (classic, v1 compatible)
  • `/ticket panel-v3` — premium dropdown panel with multiple categories
  • `/ticket addcategory` — add a category option to a v3 panel
  • `/ticket close`, `/ticket add`, `/ticket remove`, etc.

Categories are stored in `ticket_categories` and allow routing tickets to
different staff roles and channels based on what the user picks.
"""
from __future__ import annotations

import io
import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from utils import ACCENT, GOLD, embed_error, embed_info, embed_premium, embed_success, embed_warn, is_admin, send_modlog

TICKET_CATEGORY_NAME = "BypassX Tickets"
TRANSCRIPT_LIMIT = 500


# ============================================================
# Persistent views
# ============================================================

class TicketControlView(discord.ui.View):
    """In-ticket control buttons — Claim, Close, Notify."""

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
            await interaction.response.send_message(embed=embed_error("Already claimed.", f"Claimed by <@{row['claimed_by']}>."), ephemeral=True)
            return
        await get_db().execute("UPDATE tickets SET claimed_by=$1 WHERE id=$2", interaction.user.id, row["id"])
        button.disabled = True
        button.label = f"Claimed by {interaction.user.name}"
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(embed=embed_success("Ticket Claimed", f"{interaction.user.mention} has claimed this ticket."))

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="bypassx:ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await close_ticket(interaction)

    @discord.ui.button(label="Notify", style=discord.ButtonStyle.secondary, emoji="🔔", custom_id="bypassx:ticket_notify")
    async def notify(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await get_db().fetchrow("SELECT user_id FROM tickets WHERE channel_id=$1 AND closed=FALSE", interaction.channel.id)
        if not row:
            await interaction.response.send_message(embed=embed_error("Not an open ticket."), ephemeral=True)
            return
        cfg = await get_db().get_guild_config(interaction.guild.id)
        staff_role_id = (cfg or {}).get("ticket_staff_role_id") if cfg else None
        if not staff_role_id:
            await interaction.response.send_message(embed=embed_error("No staff role configured."), ephemeral=True)
            return
        role = interaction.guild.get_role(int(staff_role_id))
        if not role:
            await interaction.response.send_message(embed=embed_error("Staff role missing."), ephemeral=True)
            return
        await interaction.response.send_message(content=role.mention, embed=embed_warn("Staff Notified", f"{interaction.user.mention} has requested staff attention."), allowed_mentions=discord.AllowedMentions(roles=True))
        await interaction.channel.send(f"{role.mention}", delete_after=1)


class TicketDropdownView(discord.ui.View):
    """Premium v3 panel — a dropdown to pick the ticket category."""

    def __init__(self, panel_id: int, options: list[dict]):
        super().__init__(timeout=None)
        self.panel_id = panel_id
        if options:
            select = discord.ui.Select(
                placeholder="Choose a category…",
                min_values=1,
                max_values=1,
                options=[discord.SelectOption(
                    label=o["label"][:100],
                    description=(o.get("description") or "")[:100],
                    emoji=o.get("emoji"),
                    value=str(o["id"]),
                ) for o in options[:25]],
                custom_id=f"bypassx:ticket_dropdown:{panel_id}",
            )
            select.callback = self.on_pick
            self.add_item(select)
        # also keep a quick "General" button for those who prefer buttons
        general_btn = discord.ui.Button(label="General", style=discord.ButtonStyle.success, emoji="🎫", custom_id=f"bypassx:ticket_open_general:{panel_id}")
        general_btn.callback = self.open_general
        self.add_item(general_btn)

    async def on_pick(self, interaction: discord.Interaction) -> None:
        if interaction.data is None:
            return
        cat_id = int(interaction.data["values"][0])
        cat_row = await get_db().fetchrow("SELECT * FROM ticket_categories WHERE id=$1", cat_id)
        if not cat_row:
            await interaction.response.send_message(embed=embed_error("That category no longer exists."), ephemeral=True)
            return
        await open_ticket(interaction, category_row=cat_row)

    async def open_general(self, interaction: discord.Interaction) -> None:
        await open_ticket(interaction, category_row=None)


# ============================================================
# Ticket creation / closing logic
# ============================================================

async def open_ticket(interaction: discord.Interaction, *, category_row=None) -> None:
    guild = interaction.guild
    if guild is None:
        return

    # check existing open ticket
    existing = await get_db().fetchrow(
        "SELECT channel_id FROM tickets WHERE guild_id=$1 AND user_id=$2 AND closed=FALSE",
        guild.id, interaction.user.id,
    )
    if existing:
        ch = guild.get_channel(int(existing["channel_id"]))
        if ch:
            await interaction.response.send_message(
                embed=embed_error("Ticket already open", f"You already have an open ticket: {ch.mention}."),
                ephemeral=True,
            )
            return
        await get_db().execute("UPDATE tickets SET closed=TRUE WHERE channel_id=$1", existing["channel_id"])

    cfg = await get_db().get_guild_config(guild.id)

    # staff role: prefer per-category, fallback to guild config
    staff_role_id = None
    if category_row and category_row["staff_role_id"]:
        staff_role_id = int(category_row["staff_role_id"])
    elif cfg and cfg.get("ticket_staff_role_id"):
        staff_role_id = int(cfg["ticket_staff_role_id"])

    # category: prefer per-category, fallback to guild config
    category = None
    if category_row and category_row["category_id"]:
        category = guild.get_channel(int(category_row["category_id"]))
    elif cfg and cfg.get("ticket_category_id"):
        category = guild.get_channel(int(cfg["ticket_category_id"]))
    if category is None or not isinstance(category, discord.CategoryChannel):
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if category is None:
            try:
                category = await guild.create_category(TICKET_CATEGORY_NAME)
            except discord.Forbidden:
                await interaction.response.send_message(embed=embed_error("I can't create a ticket category."), ephemeral=True)
                return

    # channel name based on category
    cat_label = (category_row["label"] if category_row else "general").lower().replace(" ", "-")[:20] if category_row else "general"
    channel_name = f"ticket-{cat_label}-{interaction.user.name}"[:50]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
    }
    if staff_role_id:
        role = guild.get_role(staff_role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Ticket by {interaction.user} ({interaction.user.id}) — category: {cat_label}",
            reason=f"Ticket opened by {interaction.user}",
        )
    except discord.Forbidden:
        await interaction.response.send_message(embed=embed_error("I can't create the ticket channel."), ephemeral=True)
        return
    except discord.HTTPException as exc:
        await interaction.response.send_message(embed=embed_error("Failed", str(exc)), ephemeral=True)
        return

    await get_db().execute(
        "INSERT INTO tickets (guild_id, channel_id, user_id) VALUES ($1,$2,$3)",
        guild.id, channel.id, interaction.user.id,
    )

    # premium embed
    embed = discord.Embed(
        title="✦  Ticket Opened",
        description=(
            f"Welcome {interaction.user.mention}.\n\n"
            f"A staff member will be with you shortly. While you wait, please describe your issue in detail.\n\n"
            f"**Category:** {cat_label.title()}\n"
            f"**Channel:** {channel.mention}\n"
        ),
        color=ACCENT,
        timestamp=dt.datetime.now(dt.UTC),
    )
    embed.set_footer(text="BypassX  •  Tickets  •  Use the buttons below to manage")
    if staff_role_id:
        role = guild.get_role(staff_role_id)
        if role:
            embed.add_field(name="Staff Role", value=role.mention, inline=True)
    await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView(), allowed_mentions=discord.AllowedMentions(users=True))

    await interaction.response.send_message(
        embed=embed_success("Ticket Created", f"Your ticket has been opened: {channel.mention}"),
        ephemeral=True,
    )
    await send_modlog(guild, action="ticket opened", target=interaction.user, details={"Channel": channel.mention, "Category": cat_label})


async def close_ticket(interaction: discord.Interaction, *, reason: Optional[str] = None) -> None:
    row = await get_db().fetchrow("SELECT user_id, claimed_by FROM tickets WHERE channel_id=$1 AND closed=FALSE", interaction.channel.id)
    if not row:
        await interaction.response.send_message(embed=embed_error("This isn't an open ticket channel."), ephemeral=True)
        return
    channel = interaction.channel
    msgs: list[discord.Message] = []
    try:
        async for m in channel.history(limit=TRANSCRIPT_LIMIT, oldest_first=True):
            msgs.append(m)
    except discord.HTTPException:
        pass

    transcript_lines = [
        "BypassX Management — Ticket Transcript",
        f"Channel: #{channel.name}  ({channel.id})",
        f"Opener ID: {row['user_id']}",
        f"Closed by: {interaction.user} ({interaction.user.id})",
        f"Closed at: {dt.datetime.now(dt.UTC).isoformat()}",
        f"Reason: {reason or 'No reason provided'}",
        "=" * 60, "",
    ]
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
        if opener:
            await opener.send(
                embed=embed_info("Ticket Closed", f"Your ticket in **{interaction.guild.name}** was closed.\nReason: {reason or 'No reason provided'}"),
                file=discord.File(buf, filename=f"transcript-{channel.name}.txt"),
            )
    except discord.Forbidden:
        pass

    await get_db().execute("UPDATE tickets SET closed=TRUE WHERE channel_id=$1", channel.id)
    await interaction.response.send_message(embed=embed_warn("Ticket Closing", "Saving transcript and deleting in 5 seconds…"))
    await send_modlog(interaction.guild, action="ticket closed", target=opener, moderator=interaction.user, reason=reason, details={"Channel": channel.mention})
    await discord.utils.sleep_until(discord.utils.utcnow() + dt.timedelta(seconds=5))
    try:
        await channel.delete(reason=f"Ticket closed by {interaction.user}")
    except discord.HTTPException:
        pass


# ============================================================
# Cog
# ============================================================

class Tickets(commands.Cog):
    """Premium ticket system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register the in-ticket control view so it persists across restarts
        bot.add_view(TicketControlView())
        # Register any saved dropdown panels (loaded lazily on interaction)

    group = app_commands.Group(name="ticket", description="Ticket system management.", default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name="panel", description="Post a classic single-button ticket panel.")
    @app_commands.describe(title="Panel title", description="Panel description")
    @is_admin()
    async def create_panel(self, interaction: discord.Interaction, title: str = "Support Tickets", description: str = "Click the button below to open a private ticket with the staff team."):
        embed = discord.Embed(title=title, description=description, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Tickets")
        view = _LegacySingleButtonView()
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        await get_db().execute(
            "INSERT INTO ticket_panels (guild_id, channel_id, message_id, title, description) VALUES ($1,$2,$3,$4,$5)",
            interaction.guild.id, interaction.channel.id, msg.id, title, description,
        )

    @group.command(name="panel-v3", description="Post a premium dropdown ticket panel with category selection.")
    @app_commands.describe(title="Panel title", description="Panel description")
    @is_admin()
    async def create_panel_v3(self, interaction: discord.Interaction, title: str = "Support", description: str = "Select a category below that matches your issue, then click General to open a ticket."):
        embed = discord.Embed(title=title, description=description, color=ACCENT, timestamp=dt.datetime.now(dt.UTC))
        embed.set_footer(text="BypassX  •  Premium  •  Tickets")
        # post with empty options first; admins add categories via /ticket addcategory
        view = TicketDropdownView(panel_id=0, options=[])
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        row = await get_db().fetchrow(
            "INSERT INTO ticket_panels_v3 (guild_id, channel_id, message_id, title, description, color, selection_type) VALUES ($1,$2,$3,$4,$5,$6,'dropdown') RETURNING id",
            interaction.guild.id, interaction.channel.id, msg.id, title, description, ACCENT,
        )
        # rebind the view to the real panel id and add the dropdown if categories exist
        cats = await get_db().fetch("SELECT * FROM ticket_categories WHERE guild_id=$1 AND panel_id=0 ORDER BY id", interaction.guild.id)
        options = [_category_row_to_dict(c) for c in cats]
        view = TicketDropdownView(panel_id=int(row["id"]), options=options)
        await msg.edit(view=view)
        await interaction.followup.send(embed=embed_success("Premium Panel Posted", f"Panel ID **{row['id']}**.\nUse `/ticket addcategory panel_id:{row['id']} …` to add category options."), ephemeral=True)

    @group.command(name="addcategory", description="Add a category option to a v3 ticket panel.")
    @is_admin()
    async def add_category(self, interaction: discord.Interaction, panel_id: int, label: str, description: str = "", emoji: str = "", category: Optional[discord.CategoryChannel] = None, staff_role: Optional[discord.Role] = None):
        if emoji and len(emoji) > 50:
            await interaction.response.send_message(embed=embed_error("Emoji too long."), ephemeral=True)
            return
        panel = await get_db().fetchrow("SELECT * FROM ticket_panels_v3 WHERE id=$1 AND guild_id=$2", panel_id, interaction.guild.id)
        if not panel:
            await interaction.response.send_message(embed=embed_error("Panel not found."), ephemeral=True)
            return
        await get_db().execute(
            "INSERT INTO ticket_categories (guild_id, panel_id, label, description, emoji, category_id, staff_role_id, button_style) VALUES ($1,$2,$3,$4,$5,$6,$7,'secondary')",
            interaction.guild.id, panel_id, label, description or None, emoji or None, category.id if category else None, staff_role.id if staff_role else None,
        )
        # rebuild the panel dropdown
        await self._refresh_panel(interaction.guild, panel)
        await interaction.response.send_message(embed=embed_success("Category Added", f"`{label}` added to panel **{panel_id}**."))

    @group.command(name="removecategory", description="Remove a category option from a v3 panel.")
    @is_admin()
    async def remove_category(self, interaction: discord.Interaction, panel_id: int, label: str):
        await get_db().execute("DELETE FROM ticket_categories WHERE panel_id=$1 AND guild_id=$2 AND label=$3", panel_id, interaction.guild.id, label)
        panel = await get_db().fetchrow("SELECT * FROM ticket_panels_v3 WHERE id=$1 AND guild_id=$2", panel_id, interaction.guild.id)
        if panel:
            await self._refresh_panel(interaction.guild, panel)
        await interaction.response.send_message(embed=embed_success("Category Removed", f"`{label}` removed."))

    @group.command(name="categories", description="List categories for a v3 panel.")
    @is_admin()
    async def list_categories(self, interaction: discord.Interaction, panel_id: int):
        rows = await get_db().fetch("SELECT label, description, emoji, category_id, staff_role_id FROM ticket_categories WHERE panel_id=$1 AND guild_id=$2 ORDER BY id", panel_id, interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=embed_info("No Categories", "Use `/ticket addcategory` to add some."))
            return
        embed = embed_premium(f"Panel {panel_id} — Categories", f"**{len(rows)}** categories:")
        for r in rows:
            cat_mention = f"<#{r['category_id']}>" if r["category_id"] else "—"
            role_mention = f"<@&{r['staff_role_id']}>" if r["staff_role_id"] else "—"
            embed.add_field(name=f"{r['emoji'] or ''} {r['label']}", value=f"Desc: {r['description'] or '—'}\nCategory: {cat_mention}\nStaff: {role_mention}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _refresh_panel(self, guild: discord.Guild, panel) -> None:
        ch = guild.get_channel(int(panel["channel_id"]))
        if ch is None:
            return
        try:
            msg = await ch.fetch_message(int(panel["message_id"]))
        except (discord.NotFound, discord.Forbidden):
            return
        cats = await get_db().fetch("SELECT * FROM ticket_categories WHERE guild_id=$1 AND panel_id=$2 ORDER BY id", guild.id, int(panel["id"]))
        options = [_category_row_to_dict(c) for c in cats]
        view = TicketDropdownView(panel_id=int(panel["id"]), options=options)
        try:
            await msg.edit(view=view)
        except discord.HTTPException:
            pass

    @group.command(name="close", description="Close the ticket in this channel.")
    @app_commands.describe(reason="Reason for closing")
    async def close_cmd(self, interaction: discord.Interaction, reason: Optional[str] = None):
        await close_ticket(interaction, reason=reason)

    @group.command(name="add", description="Add a user to the current ticket channel.")
    @is_admin()
    async def add_user(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True, attach_files=True)
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

    @group.command(name="setcategory", description="Set the default category where tickets are created.")
    @is_admin()
    async def set_category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await get_db().set_guild_field(interaction.guild.id, "ticket_category_id", category.id)
        await interaction.response.send_message(embed=embed_success("Ticket Category Set", f"New tickets will be created under {category.mention}."))


def _category_row_to_dict(row) -> dict:
    return {
        "id": int(row["id"]),
        "label": row["label"],
        "description": row["description"],
        "emoji": row["emoji"],
        "category_id": int(row["category_id"]) if row["category_id"] else None,
        "staff_role_id": int(row["staff_role_id"]) if row["staff_role_id"] else None,
    }


class _LegacySingleButtonView(discord.ui.View):
    """Backward-compatible single-button panel for v1 `/ticket panel`."""

    def __init__(self):
        super().__init__(timeout=None)
        btn = discord.ui.Button(label="Open Ticket", style=discord.ButtonStyle.success, emoji="🎫", custom_id="bypassx:ticket_open")
        btn.callback = self.open_ticket
        self.add_item(btn)

    async def open_ticket(self, interaction: discord.Interaction):
        await open_ticket(interaction, category_row=None)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
