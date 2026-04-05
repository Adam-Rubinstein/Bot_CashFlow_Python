"""Тесты импорта истории Telegram (scripts/import_telegram_backlog.py)."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_backlog_module(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-token")
    monkeypatch.setenv("USER_TIMEZONE", "UTC+3")
    name = "telegram_backlog_import_test"
    if name in sys.modules:
        del sys.modules[name]
    p = ROOT / "scripts" / "import_telegram_backlog.py"
    spec = importlib.util.spec_from_file_location(name, p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    # bot уже мог быть импортирован раньше со старым VAULT_PATH
    import bot as bot_mod

    monkeypatch.setattr(bot_mod, "VAULT_PATH", str(tmp_path))
    return mod


def test_parse_export_line_spending_woman(monkeypatch, tmp_path: Path):
    m = _load_backlog_module(monkeypatch, tmp_path)
    line = "[27.03.2026 13:39] Adam: Деньги; Даша; 2000; +"
    out = m.parse_export_line(line)
    assert out is not None
    dt, entry = out
    assert dt.date().isoformat() == "2026-03-27"
    assert entry["product"] == "Деньги"
    assert entry["amount"] == 2000.0
    assert entry["woman"] is True
    assert entry["is_income"] is False


def test_parse_export_line_income(monkeypatch, tmp_path: Path):
    m = _load_backlog_module(monkeypatch, tmp_path)
    line = "[02.04.2026 15:49] Adam: Зарплата; Работа МИЭТ; +26144"
    out = m.parse_export_line(line)
    assert out is not None
    _dt, entry = out
    assert entry["is_income"] is True
    assert entry["amount"] == 26144.0


def test_merge_section_appends_and_dedupes(monkeypatch, tmp_path: Path):
    m = _load_backlog_module(monkeypatch, tmp_path)
    tz = m.USER_ZONE
    t1 = datetime(2026, 3, 28, 3, 47, tzinfo=tz)
    t2 = datetime(2026, 3, 28, 9, 55, tzinfo=tz)
    existing = [["Такси", "Яндекс", "999", ""]]
    new = [
        (t2, ["Такси", "Яндекс", "479", ""]),
        (t1, ["Такси", "Яндекс", "2308", ""]),
    ]
    merged = m.merge_section(existing, new)
    assert len(merged) == 3
    assert merged[0][2] == "999"
    # sorted by time: 2308 before 479
    assert merged[1][2] == "2308"
    assert merged[2][2] == "479"


def test_main_writes_markdown(monkeypatch, tmp_path: Path):
    m = _load_backlog_module(monkeypatch, tmp_path)
    m.BACKLOG = """
[10.05.2026 12:00] Adam: TestRow; SourceX; 100
"""
    m.main()
    # Имя месяца в папке — locale (%B), ищем любую папку 2026/05_*
    y2026 = tmp_path / "2026"
    assert y2026.is_dir()
    month_dirs = [p for p in y2026.iterdir() if p.is_dir() and p.name.startswith("05_")]
    assert len(month_dirs) == 1
    f = month_dirs[0] / "10.05.2026.md"
    assert f.is_file()
    text = f.read_text(encoding="utf-8")
    assert "TestRow" in text
    assert "100" in text
