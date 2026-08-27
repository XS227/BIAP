"""Local admin operator accounts for the BIAP ops/admin panel.

Deliberately independent of the mobile app's user accounts. FIN has no
verified way to check a bearer token against the existing auth backend on
port 4000 (no `/api/auth/me`-style endpoint has been found -- see
TASKS.md item 4), so admin identity is not derived from that system. This
store is its own small, separate concept: a short list of named operators
(Khabat, Nasrin, ...) who run BIAP day-to-day, distinct from end users.

Uses sqlite3 like audit_store.py, for the same reason: durable state with
no new dependency. Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib
`hashlib`, no new dependency) -- adequate for a small internal operator
list, not meant to scale to end-user authentication.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import os
import secrets
import sqlite3
from typing import Optional


DEFAULT_DB_PATH = os.environ.get(
    "BIAP_ADMIN_DB",
    os.path.join(os.path.dirname(__file__), "biap_admin.sqlite3"),
)

_PBKDF2_ITERATIONS = 310_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations_str, salt, expected_hex = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return hmac.compare_digest(digest.hex(), expected_hex)


class AdminStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS admin_operators (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def has_any_operator(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM admin_operators LIMIT 1").fetchone()
        return row is not None

    def create_operator(self, username: str, password: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO admin_operators (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, hash_password(password), _now_iso()),
            )

    def verify_operator(self, username: str, password: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM admin_operators WHERE username = ?", (username,)
            ).fetchone()
        if row is None:
            # Still run a hash to keep timing similar whether or not the
            # username exists, avoiding a cheap username-enumeration oracle.
            hash_password(password)
            return False
        return verify_password(password, row["password_hash"])

    def list_operators(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT username FROM admin_operators ORDER BY username").fetchall()
        return [row["username"] for row in rows]


def bootstrap_from_env(store: AdminStore) -> None:
    """Create the first operator from env vars if the operator table is empty.

    Only fires when no operator exists yet, so it never resets a password
    for an already-provisioned deployment just because the env vars are
    still set in the unit file.
    """
    if store.has_any_operator():
        return
    username = os.environ.get("BIAP_ADMIN_BOOTSTRAP_USER", "")
    password = os.environ.get("BIAP_ADMIN_BOOTSTRAP_PASSWORD", "")
    if username and password:
        store.create_operator(username, password)
