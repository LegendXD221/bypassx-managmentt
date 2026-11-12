# BypassX Management

> The all-in-one Discord management bot — built to surpass today's popular management bots.

A free, open-source, asynchronous Discord bot built with **discord.py 2.x** and a **Neon Postgres** free-tier backend. It bundles every management feature a modern server needs into a single, fast, slash-command-driven package — designed with a minimal, aesthetic, premium visual theme.

Inspired by the best of Dyno, Carl-bot, Sapphire, Wick, Sterix, and Hedwig — all unified in one bot.

---

## v3 Highlights

Beyond the v1 core (moderation, automod, tickets, roles, verification, logging, security, utility, reminders, tags, AFK, admin, help) and the **v2 expansion** (17 new modules: sticky, starboard, giveaways, levels, profiles, captcha, auto-responder, server stats, temp voice, snipe, embed builder, fun, role persistence, birthdays, lockdown, quotes, mass actions, owner commands), **v3** adds:

### Components v2 (dropdowns & buttons)
- **🎫 Premium ticket panel** with dropdown category selection (`/ticket panel-v3`)
- **▼ Dropdown role picker** — toggle multiple roles from one menu
- **⚙ Premium info panels** with dropdown navigation (Overview / Rules / Channels / Roles / FAQ / Support)
- **Premium button panels** for role assignment

### 12 new AIO cogs
| Module | Highlights |
| --- | --- |
| **📋 Mod Extras** | Private mod notes, member history lookup, memberinfo |
| **🔊 Voice Tools** | move, mass-move, mute, unmute, deafen, undeafen, disconnect |
| **📅 Scheduled Announcements** | Recurring messages with pause/resume |
| **📊 Reaction Polls** | Timed polls with auto-end and result bars |
| **🛡 Anti-Nuke Whitelist** | Exempt trusted staff from anti-nuke actions |
| **★ Reputation** | "thanks @user" detection, leaderboard, manual give |
| **🎨 Color Roles** | Members set a custom hex color for their own role |
| **🔤 Text Tools** | mock, reverse, encode/decode (b64/binary/hex), password, sha256, vaporwave |
| **✦ Utility Extra** | timezone converter, hex/rgb, invite info, role list, channel info, emoji info |
| **💾 Role Persistence** | Restore member roles when they rejoin |

---

## Premium Visual Theme

- **Palette:** Indigo primary (`#6366F1`), muted gold accent (`#F5B544`), emerald success, rose danger
- **Consistent footer:** every embed carries the BypassX mark
- **Clean typography:** no emoji soup, refined glyphs (★ ✦ ♔ ◆)
- **Borders:** minimal — fields separated by whitespace, not visual clutter

---

## Tech Stack

- **Python 3.12**
- **discord.py 2.3+** (full application commands support)
- **asyncpg** for async PostgreSQL access (Neon free tier)
- **aiohttp** for the Render keep-alive HTTP server
- **python-dotenv**, **psutil**, **orjson**

---

## Getting Started

### 1. Prerequisites
- Python 3.11+
- A Discord application with a bot token — <https://discord.com/developers/applications>
- A Neon Postgres free-tier database — <https://neon.tech>
- A Render account (free tier supported) — <https://render.com>

### 2. Install
```bash
git clone <your-repo-url>
cd bypassx-managmentt
pip install -r requirements.txt
```

### 3. Configure
```bash
cp .env.example .env
```
Fill in `BOT_TOKEN`, `DATABASE_URL` (Neon connection string), and `OWNER_ID` (your Discord user ID).

### 4. Discord Developer Portal
Enable all three **Privileged Gateway Intents** in your application's Bot page:
- Presence Intent
- Server Members Intent
- Message Content Intent

### 5. Run locally
```bash
python main.py
```

---

## Deploy on Render (free tier, 24/7)

The bot ships with a built-in keep-alive HTTP server (`keepalive.py`) that:
1. Binds to `$PORT` (provided by Render)
2. Exposes `/health`, `/ping`, and `/` endpoints for Render's health checks
3. Self-pings every 5 minutes to prevent Render's 15-minute spin-down

### Steps
1. Push the code to your GitHub repo.
2. In Render, create a new **Web Service** from your repo.
3. Configure:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Plan:** Free
   - **Health Check Path:** `/health`
4. Add the following **environment variables** (in Render's dashboard or via API):
   - `BOT_TOKEN` — your Discord bot token
   - `DATABASE_URL` — Neon Postgres connection string
   - `OWNER_ID` — your Discord user ID
   - `DEFAULT_PREFIX` — `bx!`
   - `BOT_STATUS` — `/help`
   - `DEBUG` — `false`
5. Deploy. Render will assign a public URL like `https://bypassx-management.onrender.com`.
6. *(Optional but recommended for true 24/7)* Set up a free external uptime pinger (e.g. UptimeRobot, cron-job.org) to hit `https://<your-app>.onrender.com/health` every 5 minutes. This prevents Render's free-tier sleep even further.

The `render.yaml` Blueprint file in this repo can also be used for one-click deploys.

---

## Project Structure

```
bypassx-managmentt/
├── main.py                # entry point — loads cogs, opens DB, runs bot + keep-alive
├── config.py              # env loader
├── database.py            # asyncpg pool + schema (45 tables, v3 expansion)
├── utils.py               # premium embed system + helpers
├── keepalive.py           # Render keep-alive HTTP server
├── render.yaml            # Render Blueprint
├── .python-version        # pins Python 3.12.6
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── WorkLog.md
├── LICENSE
├── start.sh / start.bat
└── cogs/                  # 43 cogs (14 v1 + 17 v2 + 11 v3 + help_cog)
```

---

## Command Modules

Run `/help` in any server for an interactive dropdown menu. The **43 cogs** expose **130+ slash commands** across 42 modules.

---

## Development

Read `WorkLog.md` before starting any work, and update it after every push.

### Adding a new cog
1. Create `cogs/your_cog.py` with a class extending `commands.Cog` and an `async def setup(bot)`.
2. Add the cog name to `cog_names` in `main.py`.
3. Use `/reloadall` (owner only) to hot-reload without restarting.

---

## License

MIT — see [LICENSE](./LICENSE).
