"""Configuration loader for BypassX Management bot."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    """Runtime configuration loaded from environment."""

    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    default_prefix: str = field(default_factory=lambda: os.getenv("DEFAULT_PREFIX", "bx!"))
    owner_id: int = field(default_factory=lambda: _get_int("OWNER_ID", 0))
    bot_status: str = field(default_factory=lambda: os.getenv("BOT_STATUS", "managing servers | /help"))
    error_webhook_url: str = field(default_factory=lambda: os.getenv("ERROR_WEBHOOK_URL", ""))
    debug: bool = field(default_factory=lambda: _get_bool("DEBUG", False))

    @property
    def is_valid(self) -> bool:
        return bool(self.bot_token) and bool(self.database_url)

    def validate(self) -> list[str]:
        issues: list[str] = []
        if not self.bot_token:
            issues.append("BOT_TOKEN is missing — set it in your .env file.")
        if not self.database_url:
            issues.append("DATABASE_URL is missing — get a free Neon Postgres DB at https://neon.tech")
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            issues.append("DATABASE_URL should be a postgresql:// connection string.")
        return issues


config = Config()
