"""Basic API tests that stub out the network-dependent pieces.

Run with:  pytest  (from the record-collection/ directory)
"""

from __future__ import annotations

import os
import tempfile

# Point the app at a throwaway SQLite file BEFORE importing it, since the
# settings/engine are created at import time.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["GOOGLE_SHEETS_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import discogs, main, recognizer  # noqa: E402
from app.recognizer import Recognition  # noqa: E402

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _stub_integrations(monkeypatch):
    """Replace the AI recognizer and Discogs with deterministic fakes."""

    def fake_identify(_image_bytes):
        return Recognition(
            artist="Miles Davis",
            album="Kind of Blue",
            comment="A landmark 1959 modal jazz album.",
            confidence="high",
            readable=True,
        )

    def fake_search(_artist, _album):
        return discogs.DiscogsMatch(
            release_date="1959",
            genre="Jazz",
            label="Columbia",
            country="US",
            cover_image_url="https://example.com/cover.jpg",
            discogs_url="https://www.discogs.com/release/1",
        )

    monkeypatch.setattr(main, "identify_album", fake_identify)
    monkeypatch.setattr(recognizer, "identify_album", fake_identify)
    monkeypatch.setattr(discogs, "search_release", fake_search)
    monkeypatch.setattr(main.discogs, "search_release", fake_search)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["recognizer_configured"] is True


def test_upload_creates_record():
    files = {"file": ("cover.jpg", b"\xff\xd8\xff fake jpeg bytes", "image/jpeg")}
    r = client.post("/api/records/upload", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["record"]["artist"] == "Miles Davis"
    assert body["record"]["release_date"] == "1959"
    assert body["discogs_matched"] is True
    assert body["duplicate"]["is_duplicate"] is False


def test_duplicate_detected_on_second_upload():
    files = {"file": ("cover.jpg", b"\xff\xd8\xff fake jpeg bytes", "image/jpeg")}
    # First upload persists the record.
    client.post("/api/records/upload", files=files)
    # Second upload of the same album should flag a duplicate.
    r = client.post("/api/records/upload", files=files)
    assert r.status_code == 200
    assert r.json()["duplicate"]["is_duplicate"] is True


def test_list_and_search():
    r = client.get("/api/records")
    assert r.status_code == 200
    assert any(rec["album"] == "Kind of Blue" for rec in r.json())

    r = client.get("/api/records", params={"q": "miles"})
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_manual_create_and_delete():
    payload = {"artist": "Nina Simone", "album": "Pastel Blues"}
    r = client.post("/api/records", json=payload)
    assert r.status_code == 201
    record_id = r.json()["id"]

    r = client.delete(f"/api/records/{record_id}")
    assert r.status_code == 204

    r = client.delete(f"/api/records/{record_id}")
    assert r.status_code == 404
