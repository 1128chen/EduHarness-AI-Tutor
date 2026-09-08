"""零依赖认证模块测试：口令哈希 + HMAC Token 签名/篡改/过期。"""
from __future__ import annotations

import pytest

from eduharness.application.auth import (
    TokenError,
    create_token,
    hash_password,
    verify_password,
    verify_token,
)

SECRET = "unit-test-secret"


def test_password_hash_round_trip() -> None:
    stored = hash_password("s3cret-pw")
    assert stored != "s3cret-pw"
    assert verify_password("s3cret-pw", stored)
    assert not verify_password("wrong-pw", stored)


def test_password_hash_carries_salt() -> None:
    assert hash_password("same") != hash_password("same")


def test_token_round_trip_carries_claims() -> None:
    token = create_token(
        {"sub": "t1", "username": "demo", "role": "teacher"},
        secret=SECRET,
        ttl_seconds=600,
    )
    payload = verify_token(token, secret=SECRET)
    assert payload["sub"] == "t1"
    assert payload["role"] == "teacher"


def test_token_rejects_tampered_signature() -> None:
    token = create_token({"sub": "t1", "role": "teacher"}, secret=SECRET, ttl_seconds=600)
    header, payload, signature = token.split(".")
    forged = f"{header}.{payload}.a" + signature[1:]
    with pytest.raises(TokenError):
        verify_token(forged, secret=SECRET)


def test_token_rejects_wrong_secret() -> None:
    token = create_token({"sub": "t1"}, secret=SECRET, ttl_seconds=600)
    with pytest.raises(TokenError):
        verify_token(token, secret="other-secret")


def test_token_expired() -> None:
    token = create_token({"sub": "t1"}, secret=SECRET, ttl_seconds=-5)
    with pytest.raises(TokenError):
        verify_token(token, secret=SECRET)


def test_token_rejects_garbage() -> None:
    with pytest.raises(TokenError):
        verify_token("not.a.jwt", secret=SECRET)
