"""Runtime configuration, read from environment variables.

Everything the app needs is pulled from the environment (or a `.env` file that
you load into it). Keeping this in one place makes it obvious what has to be set
before the app will run.
"""

from __future__ import annotations

import os
from functools import lru_cache


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Container for every configurable value, resolved once at startup."""

    def __init__(self) -> None:
        # --- Claude vision ---
        self.anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
        self.anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")

        # --- Discogs ---
        # Two ways to authenticate for read-only database search:
        #   1. A personal access token (single field), or
        #   2. An application Consumer Key + Secret.
        # If both are set, the token takes precedence.
        self.discogs_token: str = os.getenv("DISCOGS_TOKEN", "")
        self.discogs_consumer_key: str = os.getenv("DISCOGS_CONSUMER_KEY", "")
        self.discogs_consumer_secret: str = os.getenv("DISCOGS_CONSUMER_SECRET", "")
        self.discogs_user_agent: str = os.getenv(
            "DISCOGS_USER_AGENT", "RecordCollectionDB/1.0"
        )

        # --- Database ---
        self.database_url: str = os.getenv(
            "DATABASE_URL", "sqlite:///./records.db"
        )

        # --- Google Sheets backup (optional) ---
        self.google_sheets_enabled: bool = _as_bool(
            os.getenv("GOOGLE_SHEETS_ENABLED"), default=False
        )
        self.google_service_account_file: str = os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_FILE", ""
        )
        self.google_sheet_id: str = os.getenv("GOOGLE_SHEET_ID", "")
        self.google_sheet_worksheet: str = os.getenv(
            "GOOGLE_SHEET_WORKSHEET", "Collection"
        )

    @property
    def recognizer_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def discogs_configured(self) -> bool:
        return bool(
            self.discogs_token
            or (self.discogs_consumer_key and self.discogs_consumer_secret)
        )

    def discogs_auth_params(self) -> dict[str, str]:
        """Return the auth querystring params Discogs expects for search.

        Prefers a personal access token; otherwise uses the Consumer
        Key + Secret pair. Empty dict if nothing is configured.
        """
        if self.discogs_token:
            return {"token": self.discogs_token}
        if self.discogs_consumer_key and self.discogs_consumer_secret:
            return {
                "key": self.discogs_consumer_key,
                "secret": self.discogs_consumer_secret,
            }
        return {}


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
