"""Keep-alive HTTP server for Render free tier 24/7 uptime.

Render's free web services spin down after 15 minutes of no inbound HTTP
traffic. This module exposes a tiny aiohttp web server on $PORT so Render
considers the service "live", and a self-ping loop that periodically hits
the service's public URL to prevent spin-down.

To get true 24/7 on free tier, also set up an external uptime pinger
(UptimeRobot, cron-job.org, etc.) hitting the service URL every 5–10 min.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import aiohttp
from aiohttp import web

log = logging.getLogger("bypassx.keepalive")


class KeepAlive:
    """Small aiohttp web server + self-ping loop."""

    def __init__(self, bot):
        self.bot = bot
        self.port: int = int(os.getenv("PORT", "10000"))
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.ping_task: Optional[asyncio.Task] = None
        self.session: Optional[aiohttp.ClientSession] = None
        # Render assigns this once the service is up
        self.public_url: Optional[str] = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")

    async def _handler(self, request: web.Request) -> web.Response:
        path = request.path
        if path == "/" or path == "/health" or path == "/healthz":
            guilds = len(self.bot.guilds) if self.bot.guilds else 0
            latency_ms = round(self.bot.latency * 1000) if self.bot.latency else 0
            return web.json_response({
                "status": "ok",
                "service": "bypassx-management",
                "online": self.bot.is_ready(),
                "guilds": guilds,
                "latency_ms": latency_ms,
                "uptime_seconds": int((discord.utils.utcnow() - self.bot.start_time).total_seconds()) if hasattr(self.bot, "start_time") else 0,
            })
        if path == "/ping":
            return web.Response(text="pong")
        return web.Response(text="BypassX Management — running", status=200)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._handler)
        app.router.add_get("/health", self._handler)
        app.router.add_get("/healthz", self._handler)
        app.router.add_get("/ping", self._handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await self.site.start()
        log.info("Keep-alive HTTP server listening on 0.0.0.0:%d", self.port)
        # start self-ping loop
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        self.ping_task = asyncio.create_task(self._self_ping_loop())

    async def _self_ping_loop(self) -> None:
        """Ping our own public URL every 5 minutes to prevent Render spin-down.

        If no public URL is set (e.g. local dev), this is a no-op.
        """
        await self.bot.wait_until_ready()
        if not self.public_url:
            log.info("No public URL configured; self-ping disabled (use external pinger).")
            return
        url = self.public_url.rstrip("/") + "/ping"
        log.info("Self-ping target: %s", url)
        while not self.bot.is_closed():
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        log.debug("Self-ping OK (%d)", resp.status)
                    else:
                        log.warning("Self-ping non-200: %d", resp.status)
            except Exception as exc:  # noqa: BLE001
                log.warning("Self-ping failed: %s", exc)
            await asyncio.sleep(300)  # 5 minutes

    async def stop(self) -> None:
        if self.ping_task and not self.ping_task.done():
            self.ping_task.cancel()
            try:
                await self.ping_task
            except asyncio.CancelledError:
                pass
        if self.session:
            await self.session.close()
        if self.runner:
            await self.runner.cleanup()
        log.info("Keep-alive server stopped.")


# late import so the type annotation resolves
import discord  # noqa: E402
