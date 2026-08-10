"""Read an album cover photo with Claude vision.

Given the bytes of a photograph of a record sleeve, ask Claude to identify the
artist and album title and to write a short, knowledgeable comment about the
record. We use structured outputs so the response is always valid JSON.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass

import anthropic

from .config import get_settings

logger = logging.getLogger(__name__)

# JSON schema the model must fill in. `additionalProperties: false` and a
# complete `required` list are needed for structured outputs.
_SCHEMA = {
    "type": "object",
    "properties": {
        "artist": {
            "type": "string",
            "description": "The recording artist or band name. Empty string if unreadable.",
        },
        "album": {
            "type": "string",
            "description": "The album title. Empty string if unreadable.",
        },
        "comment": {
            "type": "string",
            "description": (
                "A short (1-2 sentence) knowledgeable comment about the album — "
                "its significance, sound, or notable facts. Empty if unknown."
            ),
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "How confident you are in the artist/album reading.",
        },
        "readable": {
            "type": "boolean",
            "description": "True if this looks like a record/album sleeve you could read.",
        },
    },
    "required": ["artist", "album", "comment", "confidence", "readable"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a vinyl record cataloguer. You are shown a photograph of a record "
    "sleeve (or CD/album cover). Read the artist and album title exactly as "
    "printed. If the image is not a record sleeve, or the text is unreadable, "
    "set readable to false and leave fields empty. Do not invent an album you "
    "cannot see. The comment should be accurate and concise."
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
    """Identify the artist/album from a cover photo using Claude vision."""
    settings = get_settings()
    if not settings.recognizer_configured:
        raise RecognizerError(
            "ANTHROPIC_API_KEY is not set — the AI recognizer is disabled."
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    media_type = _detect_media_type(image_bytes)
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Identify this record and describe it.",
                        },
                    ],
                }
            ],
        )
    except anthropic.APIError as exc:  # pragma: no cover - network dependent
        raise RecognizerError(f"Claude vision request failed: {exc}") from exc

    if response.stop_reason == "refusal":
        raise RecognizerError("The model declined to read this image.")

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise RecognizerError("Could not parse the recognizer response.") from exc

    return Recognition(
        artist=(data.get("artist") or "").strip(),
        album=(data.get("album") or "").strip(),
        comment=(data.get("comment") or "").strip(),
        confidence=data.get("confidence", "low"),
        readable=bool(data.get("readable", False)),
    )
