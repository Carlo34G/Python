"""ORM models for the record collection."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Record(Base):
    """One vinyl record in the collection."""

    __tablename__ = "records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Core, curated fields.
    artist: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    album: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    release_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Extra detail pulled from Discogs.
    genre: Mapped[str | None] = mapped_column(String(256), nullable=True)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discogs_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provenance / bookkeeping.
    source: Mapped[str] = mapped_column(String(32), default="photo")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "artist": self.artist,
            "album": self.album,
            "release_date": self.release_date,
            "comment": self.comment,
            "genre": self.genre,
            "label": self.label,
            "country": self.country,
            "cover_image_url": self.cover_image_url,
            "discogs_url": self.discogs_url,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
