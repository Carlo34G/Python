"""Pydantic schemas for request/response bodies."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecordOut(BaseModel):
    """A record as returned by the API.

    `id` is null only for an unsaved scan preview (e.g. a flagged duplicate the
    user hasn't confirmed yet); persisted records always carry an id.
    """

    id: int | None = None
    artist: str
    album: str
    release_date: str | None = None
    comment: str | None = None
    genre: str | None = None
    label: str | None = None
    country: str | None = None
    cover_image_url: str | None = None
    discogs_url: str | None = None
    source: str
    created_at: str | None = None


class RecordCreate(BaseModel):
    """Manual create / edit payload (used to confirm or correct a scan)."""

    artist: str = Field(min_length=1)
    album: str = Field(min_length=1)
    release_date: str | None = None
    comment: str | None = None
    genre: str | None = None
    label: str | None = None
    country: str | None = None
    cover_image_url: str | None = None
    discogs_url: str | None = None
    source: str = "manual"


class DuplicateInfo(BaseModel):
    is_duplicate: bool
    existing: RecordOut | None = None


class ScanResult(BaseModel):
    """What the upload endpoint returns after reading a photo."""

    record: RecordOut
    duplicate: DuplicateInfo
    recognizer_note: str | None = None
    discogs_matched: bool = False
