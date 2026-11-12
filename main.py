"""BypassX Management — entry point.

A comprehensive all-in-one Discord management bot built on discord.py 2.x with
a Neon Postgres free-tier backend. Loads all cogs, opens the DB pool, registers
slash commands, and runs the bot.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Optional

import discord
from discord.ext import commands, tasks

from config import config
from database import Database, db as db_singleton, get_db
from utils import ACCENT, embed_info

# ----- logging -------------------------------------------------------------
LOG_LEVEL = logging.DEBUG if config.debug else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)-22s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# asyncpg & discord noise reduction
logging.getLogger("discord").setLevel(logging.WARNING if not config.debug else logging.INFO)
logging.getLogger("discord.http").setLevel(logging.WARNING)
logging.getLogger("asyncpg").setLevel(logging.WARNING)
log = logging.getLogger("bypassx.main")

# ----- intents -------------------------------------------------------------
intents = discord.Intents.all()
# message content + members + server messages are required for full management
# functionality. They must be enabled in the Discord Developer Portal too.


class BypassXBot(commands.Bot):
    """Custom bot subclass with startup instrumentation."""

    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.default_prefix),
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True,
        )
        self.start_time = discord.utils.utcnow()
        self.launch_time: Optional[float] = None

    async def setup_hook(self) -> None:
        """Load cogs, sync slash commands, start background tasks."""
        import time as _t
        self.launch_time = _t.monotonic()

        cog_names = [
            # v1 core
            "cogs.admin",
            "cogs.moderation",
            "cogs.automod",
            "cogs.welcome",
            "cogs.tickets",
            "cogs.roles",
            "cogs.utility",
            "cogs.logging_cog",
            "cogs.verification",
            "cogs.reminders",
            "cogs.tags",
            "cogs.afk",
            "cogs.security",
            # v2 expansion
            "cogs.sticky",
            "cogs.starboard",
            "cogs.giveaways",
            "cogs.levels",
            "cogs.profiles",
            "cogs.captcha",
            "cogs.autoresponder",
            "cogs.serverstats",
            "cogs.tempchannels",
            "cogs.snipe",
            "cogs.embed_builder",
            "cogs.fun",
            "cogs.role_persistence",
            "cogs.owner",
            "cogs.mass_actions",
            "cogs.birthdays",
            "cogs.lockdown_all",
            "cogs.quotes",
            # v3 expansion — components v2, premium panels, more AIO commands
            "cogs.dropdown_roles",
            "cogs.premium_panels",
            "cogs.utility_extra",
            "cogs.vc_tools",
            "cogs.moderation_extra",
            "cogs.scheduled_announcements",
            "cogs.reaction_polls",
            "cogs.anti_nuke_whitelist",
            "cogs.reputation",
            "cogs.color_roles",
            "cogs.text_tools",
            # help last so it sees all commands
            "cogs.help_cog",
        ]
        loaded = 0
        for name in cog_names:
            try:
                await self.load_extension(name)
                loaded += 1
                log.info("Loaded extension: %s", name)
            except Exception as exc:  # noqa: BLE001
                log.exception("Failed to load %s: %s", name, exc)
        log.info("Loaded %d/%d cogs.", loaded, len(cog_names))

        # Start background loops
        self.reminder_loop.start()
        self.mute_expiry_loop.start()
        self.presence_loop.start()

    async def on_ready(self) -> None:
        log.info("===========================================================")
        log.info("BypassX Management is online.")
        log.info("Logged in as: %s (ID: %s)", self.user, self.user.id)
        log.info("Connected to %d guilds, %d channels.", len(self.guilds), sum(len(g.channels) for g in self.guilds))
        log.info("===========================================================")

        # Sync global slash commands
        try:
            synced = await self.tree.sync()
            log.info("Synced %d application commands.", len(synced))
        except Exception as exc:  # noqa: BLE001
            log.exception("Slash command sync failed: %s", exc)

    # ----- background loops --------------------------------------------------

    @tasks.loop(seconds=30)
    async def reminder_loop(self) -> None:
        """Fire due reminders."""
        try:
            from cogs.reminders import fire_due_reminders
            await fire_due_reminders(self)
        except Exception as exc:  # noqa: BLE001
            log.exception("reminder_loop error: %s", exc)

    @tasks.loop(seconds=60)
    async def mute_expiry_loop(self) -> None:
        """Re-apply or remove expired mutes."""
        try:
            from cogs.moderation import process_expired_mutes
            await process_expired_mutes(self)
        except Exception as exc:  # noqa: BLE001
            log.exception("mute_expiry_loop error: %s", exc)

    @tasks.loop(minutes=2)
    async def presence_loop(self) -> None:
        """Rotate bot presence across stats for engagement."""
        if not self.guilds:
            return
        stats = [
            discord.Activity(type=discord.ActivityType.watching, name=f"{len(self.guilds)} servers"),
            discord.Activity(type=discord.ActivityType.listening, name="/help"),
            discord.Activity(type=discord.ActivityType.playing, name="BypassX • /help"),
            discord.Activity(type=discord.ActivityType.watching, name=f"{sum(g.member_count or 0 for g in self.guilds)} members"),
        ]
        # cycle through
        idx = (discord.utils.utcnow().minute // 2) % len(stats)
        try:
            await self.change_presence(status=discord.Status.online, activity=stats[idx])
        except discord.HTTPException:
            pass

    @reminder_loop.before_loop
    @mute_expiry_loop.before_loop
    @presence_loop.before_loop
    async def _wait_ready(self) -> None:
        await self.wait_until_ready()

    # ----- global error handling -------------------------------------------

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:  # type: ignore[override]
        if isinstance(error, commands.CommandNotFound):
            return
        log.warning("Command error in %s: %s", ctx.command, error)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands_errors.AppCommandError) -> None:  # type: ignore[name-defined]
        from utils import embed_error
        msg = "Something went wrong running that command."
        if isinstance(error, app_commands_errors.CheckFailure):  # type: ignore[name-defined]
            msg = "You don't have permission to use this command."
        elif isinstance(error, app_commands_errors.CommandOnCooldown):  # type: ignore[name-defined]
            msg = f"This command is on cooldown. Try again in {error.retry_after:.1f}s."
        elif isinstance(error, app_commands_errors.NoPrivateMessage):  # type: ignore[name-defined]
            msg = "This command can only be used inside a server."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed_error("Error", msg), ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed_error("Error", msg), ephemeral=True)
        except discord.HTTPException:
            pass


# late import so the type annotation above resolves
from discord import app_commands as app_commands_errors  # noqa: E402


async def main() -> None:
    issues = config.validate()
    if issues:
        log.error("Configuration is incomplete:")
        for i in issues:
            log.error("  - %s", i)
        log.error("Fill in your .env file (see .env.example) and try again.")
        sys.exit(1)

    # Connect to the database first
    database = Database(config.database_url)
    try:
        await database.connect()
    except Exception as exc:  # noqa: BLE001
        log.exception("Could not start database: %s", exc)
        sys.exit(2)
    # publish the singleton so cogs can reach it via get_db()
    import database as db_module
    db_module.db = database

    bot = BypassXBot()

    # Start the keep-alive HTTP server (needed for Render free tier 24/7).
    from keepalive import KeepAlive
    keepalive = KeepAlive(bot)

    # graceful shutdown
    stop_event = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        log.info("Shutdown signal received, stopping...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, RuntimeError):
            # windows / no event loop
            signal.signal(sig, lambda *a: stop_event.set())

    bot_task = asyncio.create_task(bot.start(config.bot_token, reconnect=True))

    # Wait until the bot is ready, then start the keep-alive HTTP server.
    async def _start_keepalive_after_ready():
        try:
            await bot.wait_until_ready()
            await keepalive.start()
        except Exception as exc:  # noqa: BLE001
            log.exception("Keep-alive server failed: %s", exc)

    keepalive_task = asyncio.create_task(_start_keepalive_after_ready())

    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait({bot_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    if stop_task in done:
        log.info("Closing bot gracefully...")
        keepalive_task.cancel()
        try:
            await keepalive.stop()
        except Exception:  # noqa: BLE001
            pass
        await bot.close()
        await database.close()
    else:
        # bot_task exited first (crashed or logged out)
        log.warning("Bot task ended unexpectedly.")
        stop_task.cancel()
        try:
            await keepalive.stop()
        except Exception:  # noqa: BLE001
            pass
        await database.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted.")
