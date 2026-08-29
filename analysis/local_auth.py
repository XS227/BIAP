"""Local BIAP authentication routes for the FIN service.

Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes. Short-lived HS256
access JWTs are paired with opaque, rotating refresh tokens stored only as
SHA-256 hashes. A stolen database therefore cannot be used as a refresh-token
source, and an expired access JWT can be renewed without re-entering a password.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
import sqlite3
from uuid import uuid4

import jwt as pyjwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/auth", tags=["auth"])

DEFAULT_AUTH_DB = os.environ.get(
    "BIAP_AUTH_DB",
    os.path.join(os.path.dirname(__file__), "biap_auth.sqlite3"),
)
PBKDF2_ITERATIONS = 310_000
ACCESS_TOKEN_TTL_MINUTES = max(15, int(os.environ.get("BIAP_ACCESS_TOKEN_TTL_MINUTES", "60")))
REFRESH_TOKEN_TTL_DAYS = max(1, int(os.environ.get("BIAP_REFRESH_TOKEN_TTL_DAYS", "30")))


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=512)
    fullName: str = Field(min_length=1, max_length=120)
    companyName: str | None = Field(default=None, max_length=160)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=512)


class RefreshRequest(BaseModel):
    refreshToken: str = Field(min_length=32, max_length=512)


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=400, detail={"error": "ایمیل معتبر وارد کنید"})
    return email


def _jwt_secret() -> str:
    secret = os.environ.get("BIAP_AUTH_JWT_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail={"error": "authentication is not configured"})
    return secret


def _connect(db_path: str = DEFAULT_AUTH_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_auth_db(db_path: str = DEFAULT_AUTH_DB) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                company_name TEXT,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS refresh_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                replaced_by_hash TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_refresh_sessions_user
                ON refresh_sessions(user_id, expires_at);
            """
        )


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _public_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["user_id"],
        "userId": row["user_id"],
        "email": row["email"],
        "fullName": row["full_name"],
        "companyName": row["company_name"],
    }


def _issue_access_token(user_id: str) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)
    payload = {"userId": user_id, "iat": int(now.timestamp()), "exp": int(expires.timestamp())}
    return pyjwt.encode(payload, _jwt_secret(), algorithm="HS256"), int(expires.timestamp())


def _refresh_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_refresh_token(conn: sqlite3.Connection, user_id: str) -> str:
    raw = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO refresh_sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (_refresh_hash(raw), user_id, now.isoformat(), (now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)).isoformat()),
    )
    return raw


def _auth_response(row: sqlite3.Row, conn: sqlite3.Connection) -> dict:
    access_token, access_exp = _issue_access_token(row["user_id"])
    refresh_token = _new_refresh_token(conn, row["user_id"])
    return {
        "accessToken": access_token,
        "accessTokenExpiresAt": access_exp,
        "refreshToken": refresh_token,
        "refreshTokenTtlDays": REFRESH_TOKEN_TTL_DAYS,
        "user": _public_user(row),
    }


@router.post("/signup", status_code=201)
def signup(req: SignupRequest):
    _jwt_secret()
    init_auth_db()
    email = _normalize_email(req.email)
    now = datetime.now(timezone.utc).isoformat()
    user_id = str(uuid4())
    encoded = _hash_password(req.password)
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO users (
                    user_id, email, full_name, company_name, password_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, email, req.fullName.strip(), req.companyName.strip() if req.companyName else None, encoded, now, now),
            )
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return _auth_response(row, conn)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail={"error": "این ایمیل قبلاً ثبت شده است"}) from exc


@router.post("/login")
def login(req: LoginRequest):
    _jwt_secret()
    init_auth_db()
    email = _normalize_email(req.email)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None or not _verify_password(req.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail={"error": "ایمیل یا رمز عبور نادرست است"})
        return _auth_response(row, conn)


@router.post("/refresh")
def refresh(req: RefreshRequest):
    _jwt_secret()
    init_auth_db()
    token_hash = _refresh_hash(req.refreshToken)
    now = datetime.now(timezone.utc)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = conn.execute(
            "SELECT token_hash, user_id, expires_at, revoked_at FROM refresh_sessions WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if session is None or session["revoked_at"] is not None:
            raise HTTPException(status_code=401, detail={"error": "refresh token is invalid"})
        try:
            expires_at = datetime.fromisoformat(session["expires_at"])
        except ValueError as exc:
            raise HTTPException(status_code=401, detail={"error": "refresh token is invalid"}) from exc
        if expires_at <= now:
            conn.execute("UPDATE refresh_sessions SET revoked_at = ? WHERE token_hash = ?", (now.isoformat(), token_hash))
            raise HTTPException(status_code=401, detail={"error": "refresh token expired"})
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (session["user_id"],)).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail={"error": "user no longer exists"})
        access_token, access_exp = _issue_access_token(row["user_id"])
        replacement = secrets.token_urlsafe(48)
        replacement_hash = _refresh_hash(replacement)
        conn.execute(
            "UPDATE refresh_sessions SET revoked_at = ?, replaced_by_hash = ? WHERE token_hash = ?",
            (now.isoformat(), replacement_hash, token_hash),
        )
        conn.execute(
            "INSERT INTO refresh_sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (replacement_hash, row["user_id"], now.isoformat(), (now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)).isoformat()),
        )
        return {
            "accessToken": access_token,
            "accessTokenExpiresAt": access_exp,
            "refreshToken": replacement,
            "refreshTokenTtlDays": REFRESH_TOKEN_TTL_DAYS,
            "user": _public_user(row),
        }
