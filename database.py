"""
database.py
Manages a SQLite database for storing subscribers and monitoring state.

Tables:
  subscribers   - chat IDs of users who opted in to alerts
  monitor_state - last check timestamps and next check countdown
"""

import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")


def _connect() -> sqlite3.Connection:
    """Open a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """Create tables if they don't exist yet. Called once on startup."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id     INTEGER PRIMARY KEY,
                username    TEXT,
                joined_at   TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitor_state (
                key         TEXT PRIMARY KEY,
                last_check  TEXT,
                next_check  TEXT,
                status      TEXT DEFAULT 'ok'
            )
        """)
        conn.commit()
    print("[DB] Database initialised.")


# ---------------------------
# SUBSCRIBER MANAGEMENT
# ---------------------------

def add_subscriber(chat_id: int, username: str | None = None) -> bool:
    """
    Add a subscriber. Returns True if newly added, False if already exists.
    """
    with _connect() as conn:
        existing = conn.execute(
            "SELECT chat_id FROM subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()

        if existing:
            return False

        conn.execute(
            "INSERT INTO subscribers (chat_id, username, joined_at) VALUES (?, ?, ?)",
            (chat_id, username or "unknown", _now())
        )
        conn.commit()
        return True


def remove_subscriber(chat_id: int) -> bool:
    """
    Remove a subscriber. Returns True if removed, False if wasn't subscribed.
    """
    with _connect() as conn:
        existing = conn.execute(
            "SELECT chat_id FROM subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()

        if not existing:
            return False

        conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return True


def is_subscribed(chat_id: int) -> bool:
    """Check if a chat_id is subscribed."""
    with _connect() as conn:
        result = conn.execute(
            "SELECT chat_id FROM subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return result is not None


def get_all_subscribers() -> list[int]:
    """Return list of all subscribed chat IDs."""
    with _connect() as conn:
        rows = conn.execute("SELECT chat_id FROM subscribers").fetchall()
        return [row[0] for row in rows]


def get_subscriber_count() -> int:
    """Return total number of subscribers."""
    with _connect() as conn:
        result = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()
        return result[0] if result else 0


# ---------------------------
# MONITOR STATE TRACKING
# ---------------------------

def update_monitor_state(key: str, last_check: str, next_check: str, status: str = "ok") -> None:
    """Upsert a monitor state entry."""
    with _connect() as conn:
        conn.execute("""
            INSERT INTO monitor_state (key, last_check, next_check, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                last_check = excluded.last_check,
                next_check = excluded.next_check,
                status     = excluded.status
        """, (key, last_check, next_check, status))
        conn.commit()


def get_monitor_state(key: str) -> dict | None:
    """Get a monitor state entry by key."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT key, last_check, next_check, status FROM monitor_state WHERE key = ?",
            (key,)
        ).fetchone()
        if row:
            return {
                "key":        row[0],
                "last_check": row[1],
                "next_check": row[2],
                "status":     row[3],
            }
        return None


def get_all_monitor_states() -> list[dict]:
    """Get all monitor state entries."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT key, last_check, next_check, status FROM monitor_state"
        ).fetchall()
        return [
            {"key": r[0], "last_check": r[1], "next_check": r[2], "status": r[3]}
            for r in rows
        ]


# ---------------------------
# HELPERS
# ---------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
