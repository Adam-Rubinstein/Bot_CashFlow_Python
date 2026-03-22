"""Тесты логики бота без реального Telegram API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from bot import (
    _parse_utc_offset,
    format_amount,
    message_event_datetime,
    parse_allowed_user_ids,
    parse_message,
    user_may_use_bot,
)


class TestParseMessage:
    def test_basic_line(self):
        e = parse_message("Еда; Лента; 1755.5")
        assert len(e) == 1
        assert e[0]["product"] == "Еда"
        assert e[0]["source"] == "Лента"
        assert e[0]["amount"] == 1755.5
        assert e[0]["is_income"] is False
        assert e[0]["woman"] is False

    def test_income_plus_prefix(self):
        e = parse_message("a; b; +100")
        assert e[0]["is_income"] is True
        assert e[0]["amount"] == 100.0

    def test_woman_flag(self):
        e = parse_message("a; b; 10; +")
        assert e[0]["woman"] is True

    def test_multiline(self):
        e = parse_message("a; b; 1\nx; y; +2")
        assert len(e) == 2
        assert e[1]["is_income"] is True

    def test_skip_short_line(self):
        assert parse_message("a; b") == []


class TestParseAllowedUserIds:
    def test_none_and_empty_means_all(self):
        assert parse_allowed_user_ids(None) is None
        assert parse_allowed_user_ids("") is None
        assert parse_allowed_user_ids("   ") is None

    def test_single_and_list(self):
        assert parse_allowed_user_ids("12345") == {12345}
        assert parse_allowed_user_ids("1, 2, 3") == {1, 2, 3}
        assert parse_allowed_user_ids("1;2") == {1, 2}

    def test_invalid_only_yields_empty_set(self):
        assert parse_allowed_user_ids("abc") == set()


class TestUserMayUseBot:
    def test_allow_all(self):
        assert user_may_use_bot(1, None) is True
        assert user_may_use_bot(None, None) is True

    def test_whitelist(self):
        assert user_may_use_bot(5, {5, 7}) is True
        assert user_may_use_bot(6, {5, 7}) is False
        assert user_may_use_bot(None, {5}) is False


class TestParseUtcOffset:
    def test_examples(self):
        assert _parse_utc_offset("UTC+3").utcoffset(None) == timedelta(hours=3)
        assert _parse_utc_offset("utc-5").utcoffset(None) == timedelta(hours=-5)
        assert _parse_utc_offset("UTC+03:30").utcoffset(None) == timedelta(hours=3, minutes=30)

    def test_invalid(self):
        assert _parse_utc_offset("") is None
        assert _parse_utc_offset("Europe/Moscow") is None


class TestMessageEventDatetime:
    def test_uses_message_date_in_tz(self):
        tz = _parse_utc_offset("UTC+3")
        assert tz is not None
        msg = MagicMock()
        msg.date = datetime(2025, 3, 10, 21, 0, 0, tzinfo=timezone.utc)
        local = message_event_datetime(msg, tz)
        assert local.date().isoformat() == "2025-03-11"
        assert local.utcoffset() == timedelta(hours=3)


class TestFormatAmount:
    def test_thousands(self):
        assert format_amount(12345.0) == "12 345"
        assert format_amount(12345.5) == "12 345,5"


class TestGetFilePath:
    def test_builds_path_under_vault(self, monkeypatch, tmp_path):
        import bot as m

        monkeypatch.setattr(m, "VAULT_PATH", str(tmp_path))
        tz = m._parse_utc_offset("UTC+3")
        assert tz is not None
        dt = datetime(2025, 3, 10, 15, 0, 0, tzinfo=tz)
        p = m.get_file_path(dt)
        assert p.endswith("10.03.2025.md")
        assert (tmp_path / "2025").is_dir()

