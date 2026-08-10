"""Look up authoritative release details on Discogs (free API).

Discogs has no image search, so we search by the artist/album text that the
recognizer read off the cover, then take the best matching release for its
release date, genre, label, country, and cover art.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from .config import get_settings

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.discogs.com/database/search"
_TIMEOUT = 15


@dataclass
class DiscogsMatch:
    release_date: str | None
    genre: str | None
    label: str | None
    country: str | None
    cover_image_url: str | None
    discogs_url: str | None


def _first(value: list | None) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def search_release(artist: str, album: str) -> DiscogsMatch | None:
    """Return the best Discogs release match, or None if nothing/unconfigured."""
    settings = get_settings()
    if not settings.discogs_configured:
        logger.info("Discogs token not set — skipping release lookup.")
        return None
    if not (artist or album):
        return None

    query = f"{artist} {album}".strip()
    params = {
        "q": query,
        "type": "release",
        "token": settings.discogs_token,
        "per_page": 5,
    }
    headers = {"User-Agent": settings.discogs_user_agent}

    try:
        resp = requests.get(
            _SEARCH_URL, params=params, headers=headers, timeout=_TIMEOUT
        )
        resp.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        logger.warning("Discogs lookup failed: %s", exc)
        return None

    results = resp.json().get("results", [])
    if not results:
        return None

    best = results[0]
    release_id = best.get("id")
    discogs_url = (
        f"https://www.discogs.com/release/{release_id}" if release_id else None
    )

    return DiscogsMatch(
        release_date=str(best["year"]) if best.get("year") else None,
        genre=_first(best.get("genre")) or _first(best.get("style")),
        label=_first(best.get("label")),
        country=best.get("country"),
        cover_image_url=best.get("cover_image") or best.get("thumb"),
        discogs_url=discogs_url,
    )
