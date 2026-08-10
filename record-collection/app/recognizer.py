"""Read an album cover photo with a vision model via OpenRouter.

OpenRouter exposes an OpenAI-compatible API, so we use the `openai` SDK pointed
at OpenRouter's base URL. Given the bytes of a photograph of a record sleeve, we
ask a vision-capable model to identify the artist and album and to write a short
comment. The model is asked to reply as JSON, which we parse defensively.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass

from openai import OpenAI, OpenAIError

from .config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a vinyl record cataloguer. You are shown a photograph of a record "
    "sleeve (or CD/album cover). Read the artist and album title exactly as "
    "printed. If the image is not a record sleeve, or the text is unreadable, "
    "set readable to false and leave the text fields empty. Do not invent an "
    "album you cannot see. Any comment must be accurate and concise.\n\n"
    "Respond with ONLY a JSON object (no markdown, no prose) with exactly these "
    "keys:\n"
    '  "artist"    (string) the artist/band, or "" if unreadable\n'
    '  "album"     (string) the album title, or "" if unreadable\n'
    '  "comment"   (string) a 1-2 sentence knowledgeable note, or ""\n'
    '  "confidence" (string) one of "high", "medium", "low"\n'
    '  "readable"  (boolean) true if this is a readable album sleeve'
)

_MEDIA_TYPES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",  # WEBP starts RIFF....WEBP
}


def _detect_media_type(data: bytes) -> str:
    for magic, media_type in _MEDIA_TYPES.items():
        if data.startswith(magic):
            if media_type == "image/webp" and data[8:12] != b"WEBP":
                continue
            return media_type
    # Default to JPEG — the most common phone-photo format.
    return "image/jpeg"


def _strip_code_fence(text: str) -> str:
    """Some models wrap JSON in ```json ... ``` fences; remove them."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


@dataclass
class Recognition:
    artist: str
    album: str
    comment: str
    confidence: str
    readable: bool


class RecognizerError(RuntimeError):
    """Raised when the recognizer cannot run or returns something unusable."""


def identify_album(image_bytes: bytes) -> Recognition:
    """Identify the artist/album from a cover photo using an OpenRouter model."""
    settings = get_settings()
    if not settings.recognizer_configured:
        raise RecognizerError(
            "OPENROUTER_API_KEY is not set — the AI recognizer is disabled."
        )

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )

    # Optional attribution headers for OpenRouter's rankings.
    extra_headers: dict[str, str] = {}
    if settings.openrouter_site_url:
        extra_headers["HTTP-Referer"] = settings.openrouter_site_url
    if settings.openrouter_app_name:
        extra_headers["X-Title"] = settings.openrouter_app_name

    media_type = _detect_media_type(image_bytes)
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{media_type};base64,{b64}"

    try:
        response = client.chat.completions.create(
            model=settings.openrouter_model,
            max_tokens=1024,
            response_format={"type": "json_object"},
            extra_headers=extra_headers or None,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Identify this record and describe it.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
        )
    except OpenAIError as exc:  # pragma: no cover - network dependent
        raise RecognizerError(f"OpenRouter request failed: {exc}") from exc

    choice = response.choices[0] if response.choices else None
    content = (choice.message.content if choice and choice.message else "") or ""
    if not content.strip():
        raise RecognizerError("The recognizer returned an empty response.")

    try:
        parsed = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as exc:
        raise RecognizerError("Could not parse the recognizer response.") from exc

    return Recognition(
        artist=(parsed.get("artist") or "").strip(),
        album=(parsed.get("album") or "").strip(),
        comment=(parsed.get("comment") or "").strip(),
        confidence=str(parsed.get("confidence", "low")).lower(),
        readable=bool(parsed.get("readable", False)),
    )
