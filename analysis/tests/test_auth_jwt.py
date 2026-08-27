from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from auth import require_user_id

SECRET = "test-only-secret-do-not-use-in-prod"


def _token(user_id="user-123", secret=SECRET, expires_delta=timedelta(minutes=15), **extra_claims):
    payload = {"userId": user_id, **extra_claims}
    if expires_delta is not None:
        payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return pyjwt.encode(payload, secret, algorithm="HS256")


def test_falls_back_to_hash_when_secret_not_configured(monkeypatch):
    monkeypatch.delenv("BIAP_AUTH_JWT_SECRET", raising=False)
    user_id = require_user_id(authorization="Bearer some-opaque-session-token")
    assert not user_id.startswith("jwt:")
    assert len(user_id) == 24


def test_same_raw_token_hashes_to_the_same_id_without_secret(monkeypatch):
    monkeypatch.delenv("BIAP_AUTH_JWT_SECRET", raising=False)
    a = require_user_id(authorization="Bearer same-token")
    b = require_user_id(authorization="Bearer same-token")
    assert a == b


def test_valid_jwt_is_verified_and_yields_the_userid_claim(monkeypatch):
    monkeypatch.setenv("BIAP_AUTH_JWT_SECRET", SECRET)
    token = _token(user_id="abc-real-user-uuid")
    user_id = require_user_id(authorization=f"Bearer {token}")
    assert user_id == "jwt:abc-real-user-uuid"


def test_expired_jwt_is_rejected_outright_not_downgraded_to_hash(monkeypatch):
    monkeypatch.setenv("BIAP_AUTH_JWT_SECRET", SECRET)
    token = _token(expires_delta=timedelta(minutes=-1))
    with pytest.raises(HTTPException) as exc_info:
        require_user_id(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_jwt_signed_with_wrong_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("BIAP_AUTH_JWT_SECRET", SECRET)
    token = _token(secret="a-completely-different-secret")
    with pytest.raises(HTTPException) as exc_info:
        require_user_id(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_garbage_token_is_rejected_not_silently_hashed_when_secret_configured(monkeypatch):
    monkeypatch.setenv("BIAP_AUTH_JWT_SECRET", SECRET)
    with pytest.raises(HTTPException) as exc_info:
        require_user_id(authorization="Bearer not-a-real-jwt-at-all")
    assert exc_info.value.status_code == 401


def test_jwt_without_userid_claim_is_rejected(monkeypatch):
    monkeypatch.setenv("BIAP_AUTH_JWT_SECRET", SECRET)
    payload = {"exp": datetime.now(timezone.utc) + timedelta(minutes=15)}
    token = pyjwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        require_user_id(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_missing_token_is_rejected_regardless_of_jwt_mode(monkeypatch):
    monkeypatch.setenv("BIAP_AUTH_JWT_SECRET", SECRET)
    with pytest.raises(HTTPException) as exc_info:
        require_user_id(authorization=None)
    assert exc_info.value.status_code == 401


def test_two_different_real_users_get_different_ownership_ids(monkeypatch):
    monkeypatch.setenv("BIAP_AUTH_JWT_SECRET", SECRET)
    token_a = _token(user_id="user-a")
    token_b = _token(user_id="user-b")
    assert require_user_id(authorization=f"Bearer {token_a}") != require_user_id(
        authorization=f"Bearer {token_b}"
    )
