"""Central configuration for the Health Companion bot.

All settings come from environment variables (see .env.example). Nothing secret
is hard-coded. Import ``settings`` and ``profile`` from here everywhere else.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional at runtime (e.g. when env is injected by Docker)
    pass


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_float(name: str, default: float) -> float:
    raw = _get(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    try:
        return int(float(raw)) if raw else default
    except ValueError:
        return default


@dataclass
class Profile:
    """The user's physical profile, used for BMR/TDEE and target maths."""

    sex: str = "male"
    age: int = 50
    height_cm: float = 175.0
    start_weight_kg: float = 120.0
    goal_weight_kg: float = 95.0
    activity_factor: float = 1.35
    daily_deficit: int = 700
    # Fixed context that personalises the AI consultant.
    ethnicity: str = "Filipino"
    location: str = "Singapore"
    smoker_quitting: bool = True

    @classmethod
    def from_env(cls) -> "Profile":
        sex = _get("USER_SEX", "male").lower()
        if sex not in ("male", "female"):
            sex = "male"
        return cls(
            sex=sex,
            age=_get_int("USER_AGE", 50),
            height_cm=_get_float("USER_HEIGHT_CM", 175.0),
            start_weight_kg=_get_float("USER_START_WEIGHT_KG", 120.0),
            goal_weight_kg=_get_float("USER_GOAL_WEIGHT_KG", 95.0),
            activity_factor=_get_float("USER_ACTIVITY_FACTOR", 1.35),
            daily_deficit=_get_int("USER_DAILY_DEFICIT", 700),
        )


@dataclass
class Settings:
    telegram_token: str = ""
    allowed_user_ids: List[int] = field(default_factory=list)

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    firecrawl_api_key: str = ""
    firecrawl_base_url: str = "https://api.firecrawl.dev"

    nutritionix_app_id: str = ""
    nutritionix_app_key: str = ""

    sparky_base_url: str = ""
    sparky_email: str = ""
    sparky_password: str = ""
    sparky_api_key: str = ""

    database_path: str = "./health_companion.db"

    @classmethod
    def from_env(cls) -> "Settings":
        ids_raw = _get("TELEGRAM_ALLOWED_USER_IDS")
        ids: List[int] = []
        for part in ids_raw.split(","):
            part = part.strip()
            if part:
                try:
                    ids.append(int(part))
                except ValueError:
                    pass
        return cls(
            telegram_token=_get("TELEGRAM_BOT_TOKEN"),
            allowed_user_ids=ids,
            openrouter_api_key=_get("OPENROUTER_API_KEY"),
            openrouter_model=_get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            openrouter_base_url=_get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            firecrawl_api_key=_get("FIRECRAWL_API_KEY"),
            firecrawl_base_url=_get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev"),
            nutritionix_app_id=_get("NUTRITIONIX_APP_ID"),
            nutritionix_app_key=_get("NUTRITIONIX_APP_KEY"),
            sparky_base_url=_get("SPARKY_BASE_URL").rstrip("/"),
            sparky_email=_get("SPARKY_EMAIL"),
            sparky_password=_get("SPARKY_PASSWORD"),
            sparky_api_key=_get("SPARKY_API_KEY"),
            database_path=_get("DATABASE_PATH", "./health_companion.db"),
        )

    def is_user_allowed(self, user_id: int) -> bool:
        # Empty allow-list means "allow everyone" (only sensible for private testing).
        return not self.allowed_user_ids or user_id in self.allowed_user_ids


settings = Settings.from_env()
profile = Profile.from_env()
