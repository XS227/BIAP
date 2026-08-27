import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import admin_auth
from admin_store import hash_password, verify_password


def test_password_hash_roundtrip():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_password_hash_is_salted():
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b


def test_session_token_roundtrip(monkeypatch):
    monkeypatch.setenv("BIAP_ADMIN_JWT_SECRET", "test-secret")
    token = admin_auth.create_session_token("khabat")
    assert admin_auth.verify_session_token(token) == "khabat"


def test_session_token_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("BIAP_ADMIN_JWT_SECRET", "secret-a")
    token = admin_auth.create_session_token("khabat")
    monkeypatch.setenv("BIAP_ADMIN_JWT_SECRET", "secret-b")
    assert admin_auth.verify_session_token(token) is None


def test_unconfigured_secret_refuses_everyone(monkeypatch):
    monkeypatch.delenv("BIAP_ADMIN_JWT_SECRET", raising=False)
    assert not admin_auth.admin_panel_configured()
    assert admin_auth.verify_session_token("anything") is None
