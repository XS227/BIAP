"""Account operations for the production FIN auth database.

This module extends the existing SQLite-backed ``local_auth`` database used by
``biap-fin``. It deliberately does not create a second account store.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import json
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
from typing import Any

SAFE_EVENTS = {
    "install",
    "app_open",
    "signup",
    "login",
    "logout",
    "company_selected",
    "module_opened",
    "recommendation_viewed",
    "paper_order",
    "data_import",
    "password_reset_request",
    "password_reset_completed",
    "password_changed",
}
_SENSITIVE_KEY = re.compile(r"pass(word)?|token|secret|api.?key|authorization|cookie|raw|dataset|file.?data", re.I)


def _db_path() -> str:
    return os.environ.get("BIAP_AUTH_DB") or os.path.join(os.path.dirname(__file__), "biap_auth.sqlite3")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema() -> None:
    with _connect() as conn:
        user_columns = _column_names(conn, "users")
        if "last_login_at" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
        if "last_seen_at" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN last_seen_at TEXT")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_installations (
                installation_id TEXT PRIMARY KEY,
                user_id TEXT,
                platform TEXT,
                app_version TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_app_installations_user ON app_installations(user_id);
            CREATE INDEX IF NOT EXISTS idx_app_installations_last_seen ON app_installations(last_seen_at);

            CREATE TABLE IF NOT EXISTS app_activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                installation_id TEXT,
                event_type TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                platform TEXT,
                app_version TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_activity_user_created ON app_activity_events(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_activity_install_created ON app_activity_events(installation_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_activity_type_created ON app_activity_events(event_type, created_at DESC);

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_password_reset_expiry ON password_reset_tokens(expires_at);
            """
        )


def _clean_string(value: Any, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_len] if text else None


def safe_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in list(metadata.items())[:24]:
        key_text = str(key)[:80]
        if _SENSITIVE_KEY.search(key_text):
            continue
        if value is None or isinstance(value, (bool, int, float)):
            out[key_text] = value
        elif isinstance(value, str):
            out[key_text] = value[:240]
    return out


def record_activity(
    event_type: str,
    *,
    user_id: str | None = None,
    installation_id: str | None = None,
    platform: str | None = None,
    app_version: str | None = None,
    metadata: Any = None,
) -> bool:
    if event_type not in SAFE_EVENTS:
        return False
    ensure_schema()
    install = _clean_string(installation_id, 160)
    platform = _clean_string(platform, 32)
    app_version = _clean_string(app_version, 64)
    now = _now()
    clean_metadata = safe_metadata(metadata)

    with _connect() as conn:
        if install:
            conn.execute(
                """
                INSERT INTO app_installations (
                    installation_id, user_id, platform, app_version, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(installation_id) DO UPDATE SET
                    user_id = COALESCE(excluded.user_id, app_installations.user_id),
                    platform = COALESCE(excluded.platform, app_installations.platform),
                    app_version = COALESCE(excluded.app_version, app_installations.app_version),
                    last_seen_at = excluded.last_seen_at
                """,
                (install, user_id, platform, app_version, now, now),
            )
        if user_id:
            if event_type == "login":
                conn.execute(
                    "UPDATE users SET last_login_at = ?, last_seen_at = ?, updated_at = ? WHERE user_id = ?",
                    (now, now, now, user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET last_seen_at = ?, updated_at = ? WHERE user_id = ?",
                    (now, now, user_id),
                )
        conn.execute(
            """
            INSERT INTO app_activity_events (
                user_id, installation_id, event_type, metadata_json, platform, app_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, install, event_type, json.dumps(clean_metadata, ensure_ascii=False), platform, app_version, now),
        )
    return True


def issue_password_reset_token(user_id: str, ttl_minutes: int = 30) -> str:
    ensure_schema()
    ttl = max(5, min(int(ttl_minutes or 30), 120))
    token = secrets.token_hex(6).upper()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    with _connect() as conn:
        conn.execute(
            "UPDATE password_reset_tokens SET consumed_at = COALESCE(consumed_at, ?) WHERE user_id = ? AND consumed_at IS NULL",
            (now.isoformat(), user_id),
        )
        conn.execute(
            "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at, consumed_at, created_at) VALUES (?, ?, ?, NULL, ?)",
            (token_hash, user_id, (now + timedelta(minutes=ttl)).isoformat(), now.isoformat()),
        )
    return token


def consume_password_reset_token(token: str, new_password_hash: str) -> str | None:
    ensure_schema()
    normalized = str(token or "").strip().upper()
    token_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT token_hash, user_id, expires_at, consumed_at FROM password_reset_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None or row["consumed_at"]:
            conn.rollback()
            return None
        try:
            expires_at = datetime.fromisoformat(row["expires_at"])
        except (TypeError, ValueError):
            conn.rollback()
            return None
        if expires_at <= now:
            conn.execute("UPDATE password_reset_tokens SET consumed_at = ? WHERE token_hash = ?", (now.isoformat(), token_hash))
            conn.commit()
            return None
        user_id = str(row["user_id"])
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
            (new_password_hash, now.isoformat(), user_id),
        )
        conn.execute("UPDATE password_reset_tokens SET consumed_at = ? WHERE token_hash = ?", (now.isoformat(), token_hash))
        conn.execute(
            "UPDATE refresh_sessions SET revoked_at = COALESCE(revoked_at, ?) WHERE user_id = ?",
            (now.isoformat(), user_id),
        )
        conn.commit()
        return user_id


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_FROM"))


def send_password_reset_email(email: str, token: str) -> dict[str, bool]:
    if not smtp_configured():
        return {"configured": False, "sent": False}

    host = os.environ["SMTP_HOST"].strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "")
    sender = os.environ["SMTP_FROM"].strip()
    secure = os.environ.get("SMTP_SECURE", "").strip().lower() == "true" or port == 465

    message = EmailMessage()
    message["From"] = f"BIAP <{sender}>"
    message["To"] = email
    message["Subject"] = "کد بازیابی رمز عبور BIAP"
    message.set_content(
        f"کد یک‌بارمصرف بازیابی رمز عبور BIAP:\n\n{token}\n\n"
        "این کد تا ۳۰ دقیقه معتبر است. اگر شما این درخواست را نداده‌اید، این پیام را نادیده بگیرید."
    )

    try:
        context = ssl.create_default_context()
        if secure:
            with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as smtp:
                if username or password:
                    smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                if username or password:
                    smtp.login(username, password)
                smtp.send_message(message)
        return {"configured": True, "sent": True}
    except (OSError, smtplib.SMTPException, ssl.SSLError):
        return {"configured": True, "sent": False}


def account_summary() -> dict[str, Any]:
    ensure_schema()
    with _connect() as conn:
        registered = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        installs = int(conn.execute("SELECT COUNT(*) FROM app_installations").fetchone()[0])
        active_sessions = int(
            conn.execute(
                "SELECT COUNT(*) FROM refresh_sessions WHERE revoked_at IS NULL AND julianday(expires_at) > julianday('now')"
            ).fetchone()[0]
        )
        active = {}
        for key, modifier in (("activeUsers24h", "-1 day"), ("activeUsers7d", "-7 day"), ("activeUsers30d", "-30 day")):
            active[key] = int(
                conn.execute(
                    """
                    SELECT COUNT(DISTINCT user_id) FROM app_activity_events
                    WHERE user_id IS NOT NULL AND julianday(created_at) >= julianday('now', ?)
                    """,
                    (modifier,),
                ).fetchone()[0]
            )
        versions = [
            {"version": row["version"], "installs": int(row["installs"])}
            for row in conn.execute(
                """
                SELECT COALESCE(NULLIF(app_version, ''), 'unknown') AS version, COUNT(*) AS installs
                FROM app_installations GROUP BY 1 ORDER BY installs DESC, version ASC LIMIT 30
                """
            ).fetchall()
        ]
    return {
        "registeredUsers": registered,
        "approximateInstalls": installs,
        "activeSessions": active_sessions,
        **active,
        "appVersions": versions,
    }


def list_users(limit: int = 200) -> list[dict[str, Any]]:
    ensure_schema()
    limit = max(1, min(int(limit or 200), 500))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                u.user_id AS id,
                u.email,
                u.full_name,
                'free' AS plan,
                1 AS is_active,
                u.created_at,
                u.last_login_at,
                u.last_seen_at,
                (
                    SELECT COUNT(*) FROM refresh_sessions s
                    WHERE s.user_id = u.user_id
                      AND s.revoked_at IS NULL
                      AND julianday(s.expires_at) > julianday('now')
                ) AS active_sessions,
                (
                    SELECT ai.app_version FROM app_installations ai
                    WHERE ai.user_id = u.user_id ORDER BY ai.last_seen_at DESC LIMIT 1
                ) AS app_version,
                (
                    SELECT ai.platform FROM app_installations ai
                    WHERE ai.user_id = u.user_id ORDER BY ai.last_seen_at DESC LIMIT 1
                ) AS platform
            FROM users u
            ORDER BY COALESCE(u.last_seen_at, u.last_login_at, u.created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_installs(limit: int = 250) -> list[dict[str, Any]]:
    ensure_schema()
    limit = max(1, min(int(limit or 250), 1000))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT installation_id, user_id, platform, app_version, first_seen_at, last_seen_at
            FROM app_installations ORDER BY last_seen_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_activity(limit: int = 300, user_id: str | None = None) -> list[dict[str, Any]]:
    ensure_schema()
    limit = max(1, min(int(limit or 300), 1000))
    if user_id:
        where = "WHERE e.user_id = ?"
        params: tuple[Any, ...] = (user_id, limit)
    else:
        where = ""
        params = (limit,)
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT e.id, e.user_id, u.email, e.installation_id, e.event_type, e.metadata_json,
                   e.platform, e.app_version, e.created_at
            FROM app_activity_events e
            LEFT JOIN users u ON u.user_id = e.user_id
            {where}
            ORDER BY e.created_at DESC LIMIT ?
            """,
            params,
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["metadata_json"] = json.loads(item.get("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["metadata_json"] = {}
        items.append(item)
    return items
