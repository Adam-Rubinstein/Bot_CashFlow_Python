"""Подпись запросов VPS → receiver: HMAC-SHA256 по каноническому JSON."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

SIGNATURE_HEADER = "X-Body-Signature"
SIGNATURE_PREFIX = "v1="

# Минимальная длина общего секрета (байты в UTF-8 — для паролей/ключей).
MIN_SECRET_LEN = 24


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Одинаковая сериализация на отправителе и проверяющей стороне."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign_body(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + mac


def verify_signature(secret: str, body: bytes, header_value: str | None) -> bool:
    if not header_value or not header_value.startswith(SIGNATURE_PREFIX):
        return False
    got = header_value[len(SIGNATURE_PREFIX) :].strip().lower()
    if len(got) != 64:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, got)
