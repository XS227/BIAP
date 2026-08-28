"""Local BIAP authentication routes for the FIN service.

This replaces the temporary dependency on the legacy Express auth host when
nginx explicitly routes /api/auth/* here. Passwords are stored as salted
PBKDF2-HMAC-SHA256 hashes using only Python's standard library. JWTs are HS256
and use the same BIAP_AUTH_JWT_SECRET consumed by analysis/auth.py, giving FIN
stable verified user ownership across fresh logins.
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
TOKEN_TTL_MINUTES = 15


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=512)
    fullName: str = Field(min_length=1, max_length=120)
    companyName: str | None = Field(default=None, max_length=160)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=512)


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
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_auth_db(db_path: str = DEFAULT_AUTH_DB) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                company_name TEXT,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
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
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def _public_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["user_id"],
        "userId": row["user_id"],
        "email": row["email"],
        "fullName": row["full_name"],
        "companyName": row["company_name"],
    }


def _issue_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "userId": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=TOKEN_TTL_MINUTES)).timestamp()),
    }
    return pyjwt.encode(payload, _jwt_secret(), algorithm="HS256")


def _auth_response(row: sqlite3.Row) -> dict:
    return {"accessToken": _issue_token(row["user_id"]), "user": _public_user(row)}


@router.post("/signup", status_code=201)
def signup(req: SignupRequest):
    _jwt_secret()  # fail closed before writing an account
    init_auth_db()
    email = _normalize_email(req.email)
    now = datetime.now(timezone.utc).isoformat()
    user_id = str(uuid4())
    encoded = _hash_password(req.password)
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    user_id, email, full_name, company_name, password_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    email,
                    req.fullName.strip(),
                    req.companyName.strip() if req.companyName else None,
                    encoded,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail={"error": "این ایمیل قبلاً ثبت شده است"}) from exc
    return _auth_response(row)


@router.post("/login")
def login(req: LoginRequest):
    _jwt_secret()
    init_auth_db()
    email = _normalize_email(req.email)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not _verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail={"error": "ایمیل یا رمز عبور نادرست است"})
    return _auth_response(row)
