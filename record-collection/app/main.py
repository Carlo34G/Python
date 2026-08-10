"""FastAPI application for the Record Collection Database.

Endpoints
---------
GET  /                       -> the web UI
GET  /api/health             -> service + integration status
GET  /api/records            -> list the collection (optional ?q= search)
POST /api/records/upload     -> upload a cover photo, scan, and store
POST /api/records            -> add/confirm a record manually
DELETE /api/records/{id}     -> remove a record
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import discogs, sheets
from .config import get_settings
from .database import get_session, init_db
from .models import Record
from .recognizer import RecognizerError, identify_album
from .schemas import DuplicateInfo, RecordCreate, RecordOut, ScanResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Record Collection Database", version="1.0.0", lifespan=lifespan
)

# Create tables at import time too, so the app is usable even when the lifespan
# hasn't run (e.g. a TestClient used without its context manager).
init_db()

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _find_duplicate(session: Session, artist: str, album: str) -> Record | None:
    """Case-insensitive match on artist + album."""
    stmt = select(Record).where(
        Record.artist.ilike(artist.strip()),
        Record.album.ilike(album.strip()),
    )
    return session.execute(stmt).scalars().first()


def _persist(session: Session, record: Record) -> Record:
    session.add(record)
    session.commit()
    session.refresh(record)
    # Best-effort off-box backup; never blocks the request.
    sheets.backup_record(record)
    return record


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "recognizer_configured": settings.recognizer_configured,
        "discogs_configured": settings.discogs_configured,
        "sheets_backup_enabled": settings.google_sheets_enabled,
        "model": settings.openrouter_model,
    }


@app.get("/api/records", response_model=list[RecordOut])
def list_records(
    q: str | None = Query(default=None, description="Search artist/album"),
    session: Session = Depends(get_session),
) -> list[RecordOut]:
    stmt = select(Record).order_by(Record.created_at.desc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Record.artist.ilike(like), Record.album.ilike(like)))
    records = session.execute(stmt).scalars().all()
    return [RecordOut(**r.to_dict()) for r in records]


@app.post("/api/records/upload", response_model=ScanResult)
async def upload_record(
    file: UploadFile = File(...),
    save: bool = Query(default=True, description="Persist the record after scanning"),
    session: Session = Depends(get_session),
) -> ScanResult:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file upload.")

    try:
        recognition = identify_album(image_bytes)
    except RecognizerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not recognition.readable or not (recognition.artist or recognition.album):
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not read an album from this photo. Try a clearer, "
                "straight-on shot of the sleeve — or add it manually."
            ),
        )

    # Enrich with Discogs.
    match = discogs.search_release(recognition.artist, recognition.album)
    discogs_matched = match is not None

    record = Record(
        artist=recognition.artist,
        album=recognition.album,
        comment=recognition.comment or None,
        source="photo",
        release_date=match.release_date if match else None,
        genre=match.genre if match else None,
        label=match.label if match else None,
        country=match.country if match else None,
        cover_image_url=match.cover_image_url if match else None,
        discogs_url=match.discogs_url if match else None,
    )

    # Duplicate check against the existing collection.
    existing = _find_duplicate(session, record.artist, record.album)
    duplicate = DuplicateInfo(
        is_duplicate=existing is not None,
        existing=RecordOut(**existing.to_dict()) if existing else None,
    )

    note = None
    if recognition.confidence != "high":
        note = (
            f"Recognizer confidence was '{recognition.confidence}'. "
            "Double-check the artist and album."
        )

    # If it's a duplicate we still return the scan, but don't auto-save — let the
    # UI ask the user whether to add it anyway.
    if save and not duplicate.is_duplicate:
        record = _persist(session, record)

    return ScanResult(
        record=RecordOut(**record.to_dict()),
        duplicate=duplicate,
        recognizer_note=note,
        discogs_matched=discogs_matched,
    )


@app.post("/api/records", response_model=RecordOut, status_code=201)
def create_record(
    payload: RecordCreate,
    session: Session = Depends(get_session),
) -> RecordOut:
    record = Record(**payload.model_dump())
    record = _persist(session, record)
    return RecordOut(**record.to_dict())


@app.delete("/api/records/{record_id}", status_code=204)
def delete_record(
    record_id: int,
    session: Session = Depends(get_session),
) -> None:
    record = session.get(Record, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    session.delete(record)
    session.commit()
