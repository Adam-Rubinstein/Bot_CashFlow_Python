"""
Импорт исторических строк вида «[DD.MM.YYYY HH:MM] Adam: …» в vault (как bot.py).
Запуск из корня проекта: python scripts/import_telegram_backlog.py
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import datetime, time
from pathlib import Path

# Корень проекта (родитель scripts/)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import bot as bot_mod

parse_message = bot_mod.parse_message
get_file_path = bot_mod.get_file_path
read_file = bot_mod.read_file
write_file = bot_mod.write_file
USER_ZONE = bot_mod.USER_ZONE

# Вставьте сюда строки из истории Telegram (одна операция = одна строка)
BACKLOG = r"""
[27.03.2026 13:39] Adam: Деньги; Даша; 2000; +
[27.03.2026 20:52] Adam: Еда; Много лосося; 9264; +
[28.03.2026 03:47] Adam: Такси; Яндекс; 2308; +
[28.03.2026 04:29] Adam: Еда; Много лосося; +4000; +
[28.03.2026 09:55] Adam: Такси; Яндекс; 479
[28.03.2026 19:32] Adam: Еда; Много лосося; +2800; +
[28.03.2026 20:08] Adam: Еда; Вкус вилл; 875,45; +
[29.03.2026 18:16] Adam: Еда; OZON; 1707
[29.03.2026 19:03] Adam: Еда; OZON; +69,55
[30.03.2026 17:12] Adam: Еда; Cofix; 600; +
[01.04.2026 13:23] Adam: Еда; Pho Viet; 900
[01.04.2026 14:01] Adam: Еда; KFC; 239
[02.04.2026 00:51] Adam: Подписки; Perplexity; 1628,70
[02.04.2026 15:49] Adam: Зарплата; Работа МИЭТ; +26144
[03.04.2026 20:09] Adam: Такси; Яндекс; 1635
[03.04.2026 21:49] Adam: Еда; Додо; 4275
[03.04.2026 21:49] Adam: Еда; Додо; +1720
[04.04.2026 17:17] Adam: Еда; Лаки Кинг; 2140,42
[04.04.2026 19:14] Adam: Еда; Додо; +860
"""

LINE_RE = re.compile(
    r"^\[(?P<d>\d{2})\.(?P<m>\d{2})\.(?P<y>\d{4})\s+(?P<H>\d{2}):(?P<M>\d{2})\]\s*Adam:\s*(?P<body>.+)$"
)


def entry_to_row(entry: dict) -> list[str]:
    w = "+" if entry["woman"] else ""
    return [entry["product"], entry["source"], str(entry["amount"]), w]


def row_key(row: list[str]) -> tuple:
    return tuple(c.strip() for c in row[:4]) if len(row) >= 4 else tuple(row)


def merge_section(
    existing: list[list[str]],
    timed_new: list[tuple[datetime, list[str]]],
) -> list[list[str]]:
    seen = {row_key(r) for r in existing}
    out = [list(r) for r in existing]
    for _dt, row in sorted(timed_new, key=lambda x: x[0]):
        k = row_key(row)
        if k not in seen:
            out.append(row)
            seen.add(k)
    return out


def main() -> None:
    if not bot_mod.VAULT_PATH:
        raise SystemExit("VAULT_PATH не задан в .env")

    by_date: dict = defaultdict(list)  # date -> list[tuple[datetime, dict]]

    for raw in BACKLOG.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            print(f"Пропуск (формат): {line[:80]}")
            continue
        g = m.groupdict()
        dt = datetime(
            int(g["y"]),
            int(g["m"]),
            int(g["d"]),
            int(g["H"]),
            int(g["M"]),
            tzinfo=USER_ZONE,
        )
        body = g["body"].strip()
        entries = parse_message(body)
        if not entries:
            print(f"Пропуск (парсинг суммы): {line[:80]}")
            continue
        if len(entries) > 1:
            print(f"Несколько записей в одной строке, берём первую: {line[:60]}")
        by_date[dt.date()].append((dt, entries[0]))

    for d in sorted(by_date.keys()):
        timed = by_date[d]
        title_dt = datetime.combine(d, time(12, 0), tzinfo=USER_ZONE)
        path = get_file_path(title_dt)

        spend_new: list[tuple[datetime, list[str]]] = []
        inc_new: list[tuple[datetime, list[str]]] = []
        for dt, entry in timed:
            row = entry_to_row(entry)
            if entry["is_income"]:
                inc_new.append((dt, row))
            else:
                spend_new.append((dt, row))

        sp, inc, sh, ih = read_file(path)
        sp = merge_section(sp, spend_new)
        inc = merge_section(inc, inc_new)

        sh = any(len(r) >= 4 and r[3].strip() for r in sp)
        ih = any(len(r) >= 4 and r[3].strip() for r in inc)

        write_file(path, sp, inc, sh, ih, title_dt)
        print(f"OK {d} -> {path} (расходов {len(sp)}, доходов {len(inc)})")

    print("Готово.")


if __name__ == "__main__":
    main()
