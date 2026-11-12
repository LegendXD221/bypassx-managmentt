# BypassX Management

> The all-in-one Discord management bot — built to surpass today's popular management bots.

A free, open-source, asynchronous Discord bot built with **discord.py 2.x** and a **Neon Postgres** free-tier backend. It bundles every management feature a modern server needs into a single, fast, slash-command-driven package — designed with a minimal, aesthetic, premium visual theme.

Inspired by the best of Dyno, Carl-bot, Sapphire, Wick, Sterix, and Hedwig — all unified in one bot.

---

## v2 Highlights

Beyond the v1 core (moderation, automod, tickets, roles, verification, logging, security, utility, reminders, tags, AFK, admin, help), **v2** adds 17 new modules:

| Module | Highlights |
| --- | --- |
| **📌 Sticky Messages** | Carl-style stickies that re-post after N new messages |
| **⭐ Starboard** | Star a message to feature it; configurable threshold & channel |
| **🎉 Giveaways** | Button-entry giveaways with auto-end, re-roll, and participant tracking |
| **✦ Levels** | XP/leveling system with progress bars, role rewards, leaderboard, configurable per-server |
| **👤 Profiles** | Per-guild user profiles with bio, title, custom color, badges |
| **🔐 Captcha** | Wick-style captcha verification gate with difficulty & auto-kick for unverified |
| **💬 Auto Responder** | Trigger/response pairs (contains / exact / startswith / regex match) |
| **📊 Server Stats** | Live voice-channel counters: members, humans, bots, channels, roles, boosts, online |
| **🔊 Temp Voice** | Join a creator channel to spawn your own temporary voice room |
| **🎯 Snipe** | Retrieve recently deleted or edited messages (last 25 per channel) |
| **🎨 Embed Builder** | Build & send custom embeds; save & re-use named presets |
| **🎲 Fun** | 8ball, dice (NdM), coinflip, choose, RPS, would-you-rather, random, meme |
| **💾 Role Persistence** | Restore member roles automatically when they rejoin |
| **🎂 Birthdays** | Track member birthdays; auto-announce & assign a birthday role |
| **🔒 Lockdown All** | Server-wide lock & unlock in one command |
| **❝ Quotes** | Save memorable quotes, view by ID or random |
| **⚖ Mass Actions** | Mass role add/remove, mass ban, mass kick, mass nickname |
| **👑 Owner Commands** | eval, sql, listguilds, leaveguild, botstats, broadcast, maintenance, reloadall |

The v2 schema adds **22 new tables** (starboard, giveaways, XP, profiles, captcha, auto-responses, server stats, temp voice, quotes, role persistence, birthdays, custom commands, saved embeds, lockdown state, anti-nuke whitelist, nickname history, scheduled announcements, and more), with idempotent ALTERs on the existing `guild_config` table.

---

## Premium Visual Theme

- **Palette:** Indigo primary (`#6366F1`), muted gold accent (`#F5B544`), emerald success, rose danger
- **Consistent footer:** every embed carries the BypassX mark
- **Clean typography:** no emoji soup, refined glyphs (★ ✦ ♔ ◆)
- **Borders:** minimal — fields separated by whitespace, not visual clutter

---

## v1 Core Features

| Module | Highlights |
| --- | --- |
| **🛡 Moderation** | Ban, unban, kick, softban, timeout, persistent role-based mute, warnings (with history), purge, slowmode, channel lockdown/unlock, nickname management |
| **🤖 AutoMod** | Sliding-window spam detection, word filter, link & Discord-invite filter, mention-spam protection, anti-raid with new-account detection |
| **👋 Welcome / Leave** | Customisable messages with `{user}`, `{server}`, `{member_count}` placeholders, auto-role on join |
| **🎫 Tickets** | Button-driven ticket panels, claim & close controls, transcript saved and DM'd to the opener |
| **🎭 Roles** | Reaction-role panels, multi-role button panels, self-assignable toggle |
| **✅ Verification** | One-click verification gate with persistent button |
| **📝 Logging** | Message edits/deletes, member join/leave, role & channel create/delete, voice activity, server updates |
| **🔐 Security** | Anti-nuke detection (auto-quarantine after 5 destructive actions/min), dangerous-permission alerts, audit log reader |
| **⏰ Reminders** | Personal reminders with natural durations and due-fire background loop |
| **🏷 Tags** | Per-server custom commands with use counter |
| **💤 AFK** | Mark yourself AFK; bot replies to mentions and clears on return |
| **🛠 Utility** | Ping, uptime, server/user/role info, avatar, member count, server icon, first message, polls, bot info |
| **⚙ Config** | Live per-guild configuration via `/config set/view/reset` |

Plus: rotating presence, persistent views (buttons keep working after restart), graceful shutdown, comprehensive error handling.

---

## Tech Stack

- **Python 3.11+** (3.12 tested)
- **discord.py 2.3+** (full application commands support)
- **asyncpg** for async PostgreSQL access (Neon free tier)
- **python-dotenv**, **psutil**, **orjson**

---

## Getting Started

### 1. Prerequisites
- Python 3.11+
- A Discord application with a bot token — <https://discord.com/developers/applications>
- A Neon Postgres free-tier database — <https://neon.tech>

### 2. Install
```bash
git clone https://github.com/LegendXD221/bypassx-managmentt.git
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
- ✅ Presence Intent
- ✅ Server Members Intent
- ✅ Message Content Intent

### 5. Invite
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_APP_ID&permissions=8&scope=bot%20applications.commands
```

### 6. Run
```bash
python main.py
```

The bot automatically connects to Neon, creates all 36 tables, loads 31 cogs, syncs slash commands globally, and starts background loops for reminders, mute expiry, giveaways, captcha kicks, server stats, birthdays, and presence rotation.

---

## Project Structure

```
bypassx-managmentt/
├── main.py                # entry point
├── config.py              # env loader
├── database.py            # asyncpg pool + 36-table schema
├── utils.py               # premium embed system + helpers
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── WorkLog.md
├── LICENSE
├── start.sh / start.bat
└── cogs/
    ├── admin.py            ├── moderation.py       ├── automod.py
    ├── welcome.py          ├── tickets.py          ├── roles.py
    ├── verification.py     ├── utility.py          ├── logging_cog.py
    ├── reminders.py        ├── tags.py             ├── afk.py
    ├── security.py         ├── sticky.py           ├── starboard.py
    ├── giveaways.py        ├── levels.py           ├── profiles.py
    ├── captcha.py           ├── autoresponder.py    ├── serverstats.py
    ├── tempchannels.py      ├── snipe.py            ├── embed_builder.py
    ├── fun.py               ├── role_persistence.py ├── owner.py
    ├── mass_actions.py      ├── birthdays.py        ├── lockdown_all.py
    ├── quotes.py            └── help_cog.py
```

---

## Command Modules

Run `/help` in any server for an interactive dropdown menu. The 31 cogs expose **100+ slash commands**.

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

---

## Links
- **Repository:** <https://github.com/LegendXD221/bypassx-managmentt>
- **discord.py docs:** <https://discordpy.readthedocs.io>
- **Neon Postgres:** <https://neon.tech>
