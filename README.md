# BypassX Management

> The all-in-one Discord management bot — built to surpass today's popular management bots.

BypassX Management is a free, open-source, asynchronous Discord bot built with **discord.py 2.x** and a **Neon Postgres** free-tier database backend. It bundles every management feature a modern server needs into a single, fast, slash-command-driven package — no economy bloat, just power tools for admins and moderators.

---

## Features

| Module | Highlights |
| --- | --- |
| **🛡️ Moderation** | Ban, unban, kick, softban, timeout, persistent role-based mute, warnings (with history), purge, slowmode, channel lockdown/unlock, nickname management |
| **🤖 AutoMod** | Sliding-window spam detection, word filter, link & Discord-invite filter, mention-spam protection, anti-raid with new-account detection and configurable threshold/action |
| **👋 Welcome / Leave** | Customisable welcome & leave messages with `{user}`, `{server}`, `{member_count}` placeholders, auto-role on join |
| **🎫 Tickets** | Button-driven ticket panels, claim & close controls, transcript saved to a file and DM'd to the opener, configurable staff role & category |
| **🎭 Roles** | Reaction-role panels, multi-role button panels (up to 5 roles per panel), self-assignable `/roles selfrole` toggle |
| **✅ Verification** | One-click verification gate with persistent buttons — members click to gain access |
| **📝 Logging** | Message edits/deletes, member join/leave, role & channel create/delete, voice activity, server updates |
| **🔐 Security** | Anti-nuke detection (auto-quarantine after 5 destructive actions/min), dangerous-permission alerts, member perms scanner, audit log reader |
| **⏰ Reminders** | Personal reminders with natural durations (`1h30m`, `2d`, `15m`) and due-fire background loop |
| **🏷️ Tags** | Per-server custom commands with use counter and ownership |
| **💤 AFK** | Set yourself AFK; bot replies to mentions and clears the status when you return |
| **🛠️ Utility** | Ping, uptime, server/user/role info, avatar, member count, server icon, first message, polls, bot info |
| **⚙️ Config** | Live per-guild configuration via `/config set`, `/config view`, `/config reset` |
| **👑 Owner** | `reload`, `sync`, `shutdown` for hot-reloading cogs without downtime |

Plus: rotating presence, persistent views (buttons keep working after a restart), graceful shutdown, comprehensive error handling.

---

## Tech Stack

- **Python 3.11+** (3.12 tested)
- **discord.py 2.3+** (full application commands support)
- **asyncpg** for async PostgreSQL access (Neon free tier)
- **python-dotenv** for configuration
- **psutil** for runtime metrics

---

## Getting Started

### 1. Prerequisites

- Python 3.11 or newer
- A Discord application with a bot token — create one at <https://discord.com/developers/applications>
- A Neon Postgres free-tier database — sign up at <https://neon.tech>

### 2. Install dependencies

```bash
git clone https://github.com/LegendXD221/bypassx-managmentt.git
cd bypassx-managmentt
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
| --- | --- |
| `BOT_TOKEN` | Your Discord bot token |
| `DATABASE_URL` | Neon Postgres connection string (`postgresql://user:pass@host/db?sslmode=require`) |
| `DEFAULT_PREFIX` | Legacy text-command prefix (default `bx!`) |
| `OWNER_ID` | Your Discord user ID (for owner-only commands) |
| `BOT_STATUS` | Optional custom status text |
| `ERROR_WEBHOOK_URL` | Optional webhook for critical error alerts |
| `DEBUG` | `true` for verbose logging |

### 4. Discord Developer Portal settings

In your application's **Bot** page, enable these **Privileged Gateway Intents**:

- ✅ Presence Intent
- ✅ Server Members Intent
- ✅ Message Content Intent

### 5. Invite the bot

Generate an invite URL with the required scopes & permissions:

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_APP_ID&permissions=8&scope=bot%20applications.commands
```

(`permissions=8` is Administrator — recommended during setup. Lock down permissions later for production.)

### 6. Run the bot

```bash
python main.py
```

The bot will automatically:
- Connect to your Neon database
- Create all required tables
- Load all cogs
- Sync slash commands globally

---

## Command Reference

Run `/help` in any server the bot is in for an interactive menu, or browse the [commands documentation](./docs/COMMANDS.md).

### Quick start for admins

```
/config view                              → See your server's current configuration
/config set field:log_channel            → Set the general log channel
/welcome setchannel                       → Set the welcome/leave channel
/welcome message message:Welcome {user}!  → Set the welcome message
/automod status                           → See AutoMod status
/automod addword word:example             → Add a word to the filter
/verify setup role:@Verified channel:#verify  → Post a verification panel
/ticket panel                             → Post a ticket panel
/roles buttonpanel                        → Post a button role panel
```

---

## Database

The bot uses Neon's free-tier serverless Postgres. The schema is auto-created on first run. Tables include:

- `guild_config` — per-guild settings
- `warnings`, `mutes` — moderation records
- `tickets`, `ticket_panels` — ticket system state
- `reaction_roles`, `filtered_words` — automod & roles
- `reminders`, `afk_users`, `tags` — utility features
- `mod_logs`, `audit_log` — action history
- `verification_config`, `anti_raid_config` — security config

---

## Project Structure

```
bypassx-managmentt/
├── main.py              # Entry point — loads cogs, opens DB, runs bot
├── config.py            # Environment configuration loader
├── database.py          # asyncpg pool, schema, helpers
├── utils.py             # Embeds, permission checks, helpers
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── WorkLog.md           # Development work log (read before starting work)
├── start.sh             # Linux/macOS start script
└── cogs/
    ├── admin.py
    ├── afk.py
    ├── automod.py
    ├── help_cog.py
    ├── logging_cog.py
    ├── moderation.py
    ├── reminders.py
    ├── roles.py
    ├── security.py
    ├── tags.py
    ├── tickets.py
    ├── utility.py
    ├── verification.py
    └── welcome.py
```

---

## Development

Read `WorkLog.md` before starting any work, and update it after every push.

### Adding a new cog

1. Create `cogs/your_cog.py` with a class extending `commands.Cog` and an `async def setup(bot)` function.
2. Add the cog name to the `cog_names` list in `main.py`.
3. Use `/reload cog:your_cog` if you're the owner (no restart needed).

### Running locally

```bash
python main.py
```

---

## License

MIT — see [LICENSE](./LICENSE).

---

## Disclaimer

This bot is provided as-is, free and open source. The developer is not responsible for misuse, data loss, or damage. Always test new configurations in a staging server before deploying to production.

## Links

- **Repository:** <https://github.com/LegendXD221/bypassx-managmentt>
- **Discord.py docs:** <https://discordpy.readthedocs.io>
- **Neon Postgres:** <https://neon.tech>
