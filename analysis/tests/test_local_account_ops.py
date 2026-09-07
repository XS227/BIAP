from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

import account_ops_local as ops


def _base_db(path: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                company_name TEXT,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE refresh_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                replaced_by_hash TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("u1", "user@example.com", "Test User", None, "old-hash", now, now),
        )
        conn.execute(
            "INSERT INTO refresh_sessions VALUES (?, ?, ?, ?, NULL, NULL)",
            ("refresh-hash", "u1", now, (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()),
        )


def test_activity_admin_views_and_sensitive_metadata_are_safe(tmp_path, monkeypatch):
    db = tmp_path / "auth.sqlite3"
    _base_db(str(db))
    monkeypatch.setenv("BIAP_AUTH_DB", str(db))

    assert ops.record_activity(
        "login",
        user_id="u1",
        installation_id="install-1",
        platform="android",
        app_version="1.2.3",
        metadata={"screen": "login", "password": "must-not-be-stored", "apiKey": "secret"},
    )
    assert not ops.record_activity("unknown_event", user_id="u1")

    summary = ops.account_summary()
    assert summary["registeredUsers"] == 1
    assert summary["approximateInstalls"] == 1
    assert summary["activeSessions"] == 1
    assert summary["activeUsers24h"] == 1
    assert summary["appVersions"] == [{"version": "1.2.3", "installs": 1}]

    users = ops.list_users()
    assert users[0]["email"] == "user@example.com"
    assert users[0]["last_login_at"]
    assert users[0]["platform"] == "android"

    events = ops.list_activity(user_id="u1")
    assert events[0]["event_type"] == "login"
    assert events[0]["metadata_json"] == {"screen": "login"}


def test_password_reset_is_one_time_and_revokes_refresh_sessions(tmp_path, monkeypatch):
    db = tmp_path / "auth.sqlite3"
    _base_db(str(db))
    monkeypatch.setenv("BIAP_AUTH_DB", str(db))

    token = ops.issue_password_reset_token("u1")
    assert token and len(token) == 12
    assert ops.consume_password_reset_token(token, "new-hash") == "u1"
    assert ops.consume_password_reset_token(token, "another-hash") is None

    with sqlite3.connect(db) as conn:
        password_hash = conn.execute("SELECT password_hash FROM users WHERE user_id = 'u1'").fetchone()[0]
        revoked_at = conn.execute("SELECT revoked_at FROM refresh_sessions WHERE user_id = 'u1'").fetchone()[0]
        stored_token = conn.execute("SELECT token_hash FROM password_reset_tokens").fetchone()[0]
    assert password_hash == "new-hash"
    assert revoked_at is not None
    assert stored_token != token


def test_smtp_absence_fails_safe(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    assert ops.send_password_reset_email("user@example.com", "ABCDEF123456") == {
        "configured": False,
        "sent": False,
    }


def test_local_auth_exposes_mobile_account_routes():
    import local_auth

    paths = {route.path for route in local_auth.router.routes}
    assert {
        "/auth/logout",
        "/auth/forgot-password",
        "/auth/reset-password",
        "/auth/change-password",
        "/auth/activity/event",
    } <= paths
