"""Тесты HMAC и канонического JSON для VPS → receiver."""
from __future__ import annotations

import pytest

from security import (
    MIN_SECRET_LEN,
    canonical_json_bytes,
    sign_body,
    verify_signature,
)


def test_min_secret_exported():
    assert MIN_SECRET_LEN == 24


def test_sign_verify_roundtrip():
    secret = "x" * 32
    payload = {"entries": [], "event_ts": 1.0, "nonce": "abc-def-123"}
    body = canonical_json_bytes(payload)
    sig = sign_body(secret, body)
    assert verify_signature(secret, body, sig)
    assert not verify_signature(secret + "!", body, sig)
    assert not verify_signature(secret, body, None)
    assert not verify_signature(secret, body, "v1=deadbeef")


def test_canonical_stable_for_unicode():
    secret = "y" * 24
    p1 = {"event_ts": 1.0, "entries": [{"product": "Еда", "source": "Маг", "amount": 1.0, "is_income": False, "woman": False}], "nonce": "n"}
    b1 = canonical_json_bytes(p1)
    b2 = canonical_json_bytes(p1)
    assert b1 == b2
    assert sign_body(secret, b1) == sign_body(secret, b2)
