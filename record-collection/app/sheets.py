"""Optional Google Sheets backup.

Every record added to the local database is also appended to a Google Sheet so
you have an off-box copy of your collection. This is strictly best-effort: if it
is not configured, or the network hiccups, the local database is unaffected.
"""

from __future__ import annotations

import logging

from .config import get_settings
from .models import Record

logger = logging.getLogger(__name__)

_HEADER = [
    "id",
    "artist",
    "album",
    "release_date",
    "comment",
    "genre",
    "label",
    "country",
    "discogs_url",
    "created_at",
]

# Scope needed to read/write spreadsheets.
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _row(record: Record) -> list[str]:
    d = record.to_dict()
    return [str(d.get(col, "") or "") for col in _HEADER]


def _open_worksheet():
    """Return the configured worksheet, creating the header row if needed."""
    import gspread
    from google.oauth2.service_account import Credentials

    settings = get_settings()
    creds = Credentials.from_service_account_file(
        settings.google_service_account_file, scopes=_SCOPES
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(settings.google_sheet_id)

    try:
        worksheet = spreadsheet.worksheet(settings.google_sheet_worksheet)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=settings.google_sheet_worksheet, rows=1000, cols=len(_HEADER)
        )
        worksheet.append_row(_HEADER)

    # Make sure the header exists on an otherwise-empty sheet.
    if not worksheet.get_all_values():
        worksheet.append_row(_HEADER)

    return worksheet


def backup_record(record: Record) -> bool:
    """Append one record to the backup sheet. Returns True on success."""
    settings = get_settings()
    if not settings.google_sheets_enabled:
        return False
    if not (settings.google_service_account_file and settings.google_sheet_id):
        logger.warning("Google Sheets backup enabled but not fully configured.")
        return False

    try:
        worksheet = _open_worksheet()
        worksheet.append_row(_row(record), value_input_option="USER_ENTERED")
        return True
    except Exception as exc:  # noqa: BLE001 - backup must never break a request
        logger.warning("Google Sheets backup failed: %s", exc)
        return False
