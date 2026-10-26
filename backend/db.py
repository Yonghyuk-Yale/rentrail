"""SQLite storage. One file, created on first start, no server to install."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from config import DATA_DIR, DB_PATH

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  pw_hash TEXT NOT NULL, salt TEXT NOT NULL, lang TEXT DEFAULT 'en',
  demo_today TEXT, is_demo INTEGER DEFAULT 0, created_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT, expires_at TEXT
);
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, name TEXT, mime TEXT,
  sha256 TEXT, size INTEGER, path TEXT, meta TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS leases (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT, file_id INTEGER,
  page_count INTEGER, card TEXT, analysis_meta TEXT, run_id INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS inspections (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, lease_id INTEGER, sublet_id INTEGER,
  kind TEXT NOT NULL, title TEXT, inspected_on TEXT, status TEXT DEFAULT 'draft',
  result TEXT, run_id INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY, inspection_id INTEGER NOT NULL, file_id INTEGER NOT NULL,
  parent_file_id INTEGER, room TEXT, label TEXT, t_seconds REAL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS disputes (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, lease_id INTEGER, move_in_id INTEGER,
  move_out_id INTEGER, deduction_file_id INTEGER, facts TEXT, result TEXT, run_id INTEGER,
  status TEXT DEFAULT 'draft', created_at TEXT
);
CREATE TABLE IF NOT EXISTS sublets (
  id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, subtenant_id INTEGER, lease_id INTEGER,
  invite_code TEXT UNIQUE, start_date TEXT, end_date TEXT, monthly_rent REAL, deposit REAL,
  utilities TEXT, status TEXT DEFAULT 'draft', docs TEXT, handoff_id INTEGER, return_id INTEGER,
  settlement TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY, sublet_id INTEGER NOT NULL, ts TEXT, kind TEXT, amount REAL,
  from_party TEXT, to_party TEXT, method TEXT, masked_account TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS bills (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, lease_id INTEGER, file_id INTEGER,
  kind TEXT, result TEXT, run_id INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks_done (
  user_id INTEGER, task_key TEXT, done_at TEXT, PRIMARY KEY (user_id, task_key)
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY, user_id INTEGER, kind TEXT, title TEXT, status TEXT,
  started_at TEXT, finished_at TEXT, input_tokens INTEGER DEFAULT 0, cached_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0, error TEXT, ref TEXT, result TEXT
);
CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, role TEXT, content TEXT, run_id INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_calls (
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, seq INTEGER, agent TEXT, caller TEXT,
  purpose TEXT, input_preview TEXT, output TEXT, input_tokens INTEGER DEFAULT 0,
  cached_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, requests INTEGER DEFAULT 0,
  cost_usd REAL DEFAULT 0, ms INTEGER, status TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS safety_events (
  id INTEGER PRIMARY KEY, user_id INTEGER, run_id INTEGER, kind TEXT, detail TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, category TEXT, title TEXT, body TEXT,
  building TEXT, rating INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, user_id INTEGER, body TEXT, is_ai INTEGER DEFAULT 0,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS likes (post_id INTEGER, user_id INTEGER, PRIMARY KEY (post_id, user_id));
CREATE TABLE IF NOT EXISTS prechecks (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, earlier_id INTEGER, later_id INTEGER,
  result TEXT, run_id INTEGER, created_on TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
        _conn.executescript(SCHEMA)
        _migrate(_conn)
    return _conn


# Columns added after v1. Each is added once if missing, so old databases keep working.
MIGRATIONS = [
    ("users", "mode", "TEXT DEFAULT 'tenant'"),        # tenant | sublessor | subtenant
    ("leases", "kind", "TEXT DEFAULT 'lease'"),         # lease | sublease
    ("leases", "sublet_id", "INTEGER"),
    ("leases", "signed_on", "TEXT"),
    ("bills", "issued_on", "TEXT"),                     # statement date (the bill exists from this day)
    ("sublets", "listed_on", "TEXT"),
    ("sublets", "matched_on", "TEXT"),
    ("sublets", "docs_on", "TEXT"),
    ("ledger", "ref", "TEXT"),                          # e.g. utility:<bill_id>
]


def _migrate(c: sqlite3.Connection) -> None:
    for table, col, decl in MIGRATIONS:
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    c.commit()


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    with _lock:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def q(sql: str, params: tuple | list = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


def one(sql: str, params: tuple | list = ()) -> dict | None:
    rows = q(sql, params)
    return rows[0] if rows else None


def ex(sql: str, params: tuple | list = ()) -> int:
    with tx() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def insert(table: str, **values: Any) -> int:
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    return ex(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))


def update(table: str, row_id: int, **values: Any) -> None:
    sets = ", ".join(f"{k} = ?" for k in values)
    ex(f"UPDATE {table} SET {sets} WHERE id = ?", [*values.values(), row_id])


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def reset_all() -> None:
    """Drop every table (used by the demo reset)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
        if DB_PATH.exists():
            DB_PATH.unlink()
