import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_password_hash_is_not_plaintext():
    hashed = hash_password("secret123")
    assert hashed != "secret123"


def test_access_token_roundtrip_carries_roles():
    token = create_access_token(user_id=42, roles=["QA Reviewer"])
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["roles"] == ["QA Reviewer"]
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    token = create_refresh_token(user_id=7)
    payload = decode_token(token)
    assert payload["sub"] == "7"
    assert payload["type"] == "refresh"


def test_decode_rejects_garbage_token():
    with pytest.raises(ValueError):
        decode_token("not.a.jwt")
