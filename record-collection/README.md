# 🎵 Record Collection Database

A small web app for cataloguing your vinyl. Upload a photo of a sleeve — **Claude
vision** reads the artist and album and writes a short comment, **Discogs** fills
in the release date, genre, label and cover art, and everything is stored in a
local **SQLite** database with an optional **Google Sheets** backup. A duplicate
check warns you before you add a record you already own, so you don't
double-purchase.

Built with **FastAPI** and designed to run in **Docker** on `srv-02`.

---

## How it works

```
 photo ──▶ Claude vision ──▶ {artist, album, comment}
                                   │
                                   ▼
                             Discogs search ──▶ release date, genre, label, cover
                                   │
                                   ▼
                          SQLite (source of truth)
                                   │
                                   ▼
                    Google Sheet backup  (optional, best-effort)
```

Because Discogs has no image search, the photo is first read by the AI to get
searchable text; that text is then matched against Discogs for authoritative
details.

---

## Quick start (local)

```bash
cd record-collection
cp .env.example .env          # then edit .env (see Configuration below)
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://localhost:8000>.

## Run on srv-02 with Docker

```bash
cd record-collection
cp .env.example .env          # fill in ANTHROPIC_API_KEY and DISCOGS_TOKEN
docker compose up -d --build
```

The app listens on port **8000**. Point your reverse proxy (nginx/Caddy/Traefik)
at `srv-02:8000`, or change the published port in `docker-compose.yml`.

Your data lives in `./data` on the host (mounted at `/data` in the container),
so it survives restarts and rebuilds.

---

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | Claude vision recognizer. Get one at console.anthropic.com |
| `ANTHROPIC_MODEL` | No | Vision model. Default `claude-opus-5`. **Set to `claude-haiku-4-5` to cut cost** — it reads covers well |
| `DISCOGS_TOKEN` | Recommended | Free Discogs token for release details. discogs.com/settings/developers |
| `DISCOGS_USER_AGENT` | No | Sent to Discogs (they require a User-Agent) |
| `DATABASE_URL` | No | SQLite path. Default is the mounted `/data/records.db` |
| `GOOGLE_SHEETS_ENABLED` | No | `true` to turn on the backup |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | If backup on | Path to a Google service-account JSON key |
| `GOOGLE_SHEET_ID` | If backup on | The spreadsheet ID from its URL |
| `GOOGLE_SHEET_WORKSHEET` | No | Tab name to write to (default `Collection`) |

### Cost note

- **Discogs is completely free** — no per-call charge, ~60 requests/minute.
- The **only** paid piece is the Claude vision call, roughly a fraction of a
  cent per photo on `claude-opus-5`, and cheaper still on `claude-haiku-4-5`.
  Switch models with `ANTHROPIC_MODEL` — no code change needed.

### Enabling the Google Sheets backup

1. In Google Cloud, create a **service account** and download its JSON key.
2. Enable the **Google Sheets API** for that project.
3. Create a spreadsheet and **share it with the service-account email** (as
   Editor). Copy the spreadsheet ID from its URL.
4. Put the JSON key on the host (e.g. `./data/service_account.json`) and set
   `GOOGLE_SHEETS_ENABLED=true`, `GOOGLE_SERVICE_ACCOUNT_FILE`, and
   `GOOGLE_SHEET_ID` in `.env`.

The backup is best-effort: if it fails or is disabled, the local database is
never affected.

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/api/health` | Service + integration status |
| `GET` | `/api/records?q=` | List / search the collection |
| `POST` | `/api/records/upload` | Upload a cover photo (multipart `file`) |
| `POST` | `/api/records` | Add / confirm a record (JSON) |
| `DELETE` | `/api/records/{id}` | Remove a record |

---

## Tests

```bash
cd record-collection
pip install pytest
pytest
```

The tests stub out the Claude and Discogs calls, so they run offline.
