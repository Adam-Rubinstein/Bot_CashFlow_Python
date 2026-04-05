"""Интеграционные тесты receiver с подписью."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from security import SIGNATURE_HEADER, canonical_json_bytes, sign_body


@pytest.fixture
def receiver_app(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECEIVER_INSECURE_DEV", "1")
    monkeypatch.setenv("USER_TIMEZONE", "UTC+3")
    # Перезагрузка модуля с новыми env
    import importlib

    import receiver

    importlib.reload(receiver)
    return receiver.app


def test_receiver_insecure_accepts_unsigned(receiver_app):
    client = TestClient(receiver_app)
    payload = {
        "entries": [{"product": "a", "source": "b", "amount": 10.0, "is_income": False, "woman": False}],
        "event_ts": time.time(),
        "nonce": "test-nonce-uuid-0001",
    }
    r = client.post("/", json=payload)
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_receiver_secure_requires_signature(monkeypatch, tmp_path: Path):
    secret = "s" * 32
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECEIVER_INSECURE_DEV", "")
    monkeypatch.setenv("RECEIVER_SECRET", secret)
    monkeypatch.setenv("USER_TIMEZONE", "UTC+3")

    import importlib

    import receiver

    importlib.reload(receiver)
    client = TestClient(receiver.app)

    payload = {
        "entries": [{"product": "a", "source": "b", "amount": 1.0, "is_income": False, "woman": False}],
        "event_ts": time.time(),
        "nonce": "nonce-secure-0002",
    }
    body = canonical_json_bytes(payload)
    good = {SIGNATURE_HEADER: sign_body(secret, body)}

    r = client.post("/", content=body, headers=good)
    assert r.status_code == 200

    r2 = client.post("/", content=body, headers={SIGNATURE_HEADER: "v1=bad"})
    assert r2.status_code == 403

    # replay same nonce
    r3 = client.post("/", content=body, headers=good)
    assert r3.status_code == 403
