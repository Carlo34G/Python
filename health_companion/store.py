"""Local SQLite store — the bot's own source of truth.

Sparky sync (see sparky.py) is best-effort on top of this, so nothing you log is
ever lost even if Sparky is unreachable or its beta API changes shape.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import List, Tuple

from config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS weight_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    weight_kg REAL   NOT NULL,
    logged_on TEXT   NOT NULL,          -- YYYY-MM-DD
    created_at TEXT  NOT NULL
);
CREATE TABLE IF NOT EXISTS food_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    description TEXT NOT NULL,
    calories REAL    NOT NULL,
    protein_g REAL   NOT NULL DEFAULT 0,
    logged_on TEXT   NOT NULL,
    created_at TEXT  NOT NULL
);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(settings.database_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript(_SCHEMA)


def add_weight(user_id: int, weight_kg: float, on: str | None = None) -> None:
    on = on or date.today().isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO weight_log (user_id, weight_kg, logged_on, created_at) VALUES (?,?,?,?)",
            (user_id, weight_kg, on, datetime.utcnow().isoformat()),
        )


def add_food(user_id: int, description: str, calories: float, protein_g: float = 0.0,
             on: str | None = None) -> None:
    on = on or date.today().isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO food_log (user_id, description, calories, protein_g, logged_on, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (user_id, description, calories, protein_g, on, datetime.utcnow().isoformat()),
        )


def latest_weight(user_id: int) -> float | None:
    with _conn() as con:
        row = con.execute(
            "SELECT weight_kg FROM weight_log WHERE user_id=? ORDER BY logged_on DESC, id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return row["weight_kg"] if row else None


def weight_history(user_id: int, limit: int = 30) -> List[Tuple[str, float]]:
    """Return [(date, weight)] oldest-first, up to `limit` most recent points."""
    with _conn() as con:
        rows = con.execute(
            "SELECT logged_on, weight_kg FROM weight_log WHERE user_id=? "
            "ORDER BY logged_on DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [(r["logged_on"], r["weight_kg"]) for r in reversed(rows)]


def calories_on(user_id: int, on: str | None = None) -> Tuple[float, float]:
    """Return (total_calories, total_protein) logged on a given day (default today)."""
    on = on or date.today().isoformat()
    with _conn() as con:
        row = con.execute(
            "SELECT COALESCE(SUM(calories),0) c, COALESCE(SUM(protein_g),0) p "
            "FROM food_log WHERE user_id=? AND logged_on=?",
            (user_id, on),
        ).fetchone()
    return (round(row["c"], 1), round(row["p"], 1))
