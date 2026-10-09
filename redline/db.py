"""SQLite storage for users, sessions, document access and per-user history."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  created REAL NOT NULL DEFAULT (strftime('%s','now')));
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL, created REAL NOT NULL DEFAULT (strftime('%s','now')));
CREATE TABLE IF NOT EXISTS members(
  doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY(doc_id, user_id));
CREATE TABLE IF NOT EXISTS history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stack TEXT NOT NULL CHECK(stack IN ('undo','redo')), op TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS history_idx ON history(doc_id, user_id, stack, id);
CREATE TABLE IF NOT EXISTS activity(
  id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id), at REAL NOT NULL DEFAULT (strftime('%s','now')),
  summary TEXT NOT NULL);
"""


def data_dir() -> Path:
    """Where PDFs and the database live. Read each call so tests can redirect it."""
    d = Path(os.environ.get("REDLINE_DATA", Path(tempfile.gettempdir()) / "redline"))
    (d / "docs").mkdir(parents=True, exist_ok=True)
    return d


@lru_cache(maxsize=None)
def _init(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()


@contextmanager
def connect():
    path = str(data_dir() / "redline.db")
    if not os.path.exists(path):
        _init.cache_clear()  # database file was removed while running: rebuild it
    _init(path)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()
