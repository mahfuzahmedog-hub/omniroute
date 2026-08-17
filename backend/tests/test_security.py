"""Unit tests for password hashing and JWT access tokens."""

from __future__ import annotations

import uuid

from forge.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_plaintext_and_verifies() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_hash_is_salted() -> None:
    # Two hashes of the same password must differ (random salt).
    assert hash_password("same") != hash_password("same")


def test_long_password_over_72_bytes_is_handled() -> None:
    long_password = "a" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)


def test_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    assert decode_access_token(token) == str(user_id)


def test_expired_token_rejected() -> None:
    token = create_access_token(uuid.uuid4(), expires_minutes=-1)
    assert decode_access_token(token) is None


def test_tampered_token_rejected() -> None:
    token = create_access_token(uuid.uuid4())
    assert decode_access_token(token + "tampered") is None
