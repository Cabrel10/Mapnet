"""Unit tests for Auth service."""
from unittest.mock import patch, MagicMock
from app.security import get_password_hash, verify_password, create_access_token, decode_token


def test_password_hash():
    hashed = get_password_hash("secret")
    assert verify_password("secret", hashed)
    assert not verify_password("wrong", hashed)


def test_token_roundtrip():
    token = create_access_token({"sub": "driver1", "role": "driver"})
    payload = decode_token(token)
    assert payload["sub"] == "driver1"
    assert payload["role"] == "driver"
