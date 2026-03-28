"""receiver.py — запускается на вашем ПК.
Принимает данные от bot_server.py через bore-туннель и пишет .md файлы в Obsidian.

Запуск:
    python receiver.py
"""
from __future__ import annotations

import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo
import re

from dotenv import load_dotenv

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

load_dotenv()

VAULT_PATH = os.getenv("VAULT_PATH")
RECEIVER_PORT = int(os.getenv("RECEIVER_PORT", "8080"))
RECEIVER_SECRET = os.getenv("RECEIVER_SECRET", "")


def _parse_utc_offset(raw: str) -> Optional[timezone]:
    m = re.match(r"^\s*UTC\s*([+-])(\d{1,2})(?::(\d{2}))?\s*$", raw, re.IGNORECASE)
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    hours = int(m.group(2))
    minutes = int(m.group(3) or 0)
    if minutes >= 60 or hours > 14:
        return None
    return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))


def _user_zone() -> tzinfo:
    raw = (os.getenv("USER_TIMEZONE") or "").strip()
    if not raw:
        return timezone(timedelta(hours=3))
    parsed = _parse_utc_offset(raw)
    if parsed is not None:
        return parsed
    try:
        return ZoneInfo(raw)
    except Exception:
        return timezone(timedelta(hours=3))


USER_ZONE = _user_zone()


def get_file_path(for_date: datetime):
    year = for_date.strftime('%Y')
    month_num = for_date.strftime('%m')
    month_name = for_date.strftime('%B')
    date_str = for_date.strftime('%d.%m.%Y')
    month_folder = f"{month_num}_{month_name}"
    folder_path = os.path.join(VAULT_PATH, year, month_folder)
    file_path = os.path.join(folder_path, f"{date_str}.md")
    os.makedirs(folder_path, exist_ok=True)
    return file_path


def read_file(file_path):
    if not os.path.exists(file_path):
        return [], [], False, False
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    spending = []
    income = []
    spending_has_woman = False
    income_has_woman = False
    in_spending = False
    in_income = False
    for line in content.split('\n'):
        if '## *Spending:*' in line:
            in_spending = True
            in_income = False
            continue
        if '## *Income:*' in line:
            in_spending = False
            in_income = True
            continue
        if '|' not in line or 'Product' in line or ':-' in line:
            continue
        cells = [c.strip().replace(',', '.') for c in line.split('|') if c.strip()]
        if len(cells) >= 3:
            has_woman_col = len(cells) >= 4
            if in_spending:
                spending.append(cells)
                if has_woman_col and cells[3].strip():
                    spending_has_woman = True
            elif in_income:
                income.append(cells)
                if has_woman_col and cells[3].strip():
                    income_has_woman = True
    return spending, income, spending_has_woman, income_has_woman


def format_amount(amount_float):
    if amount_float == int(amount_float):
        amount = str(int(amount_float))
    else:
        amount = str(amount_float).replace('.', ',')
    parts = amount.split(',')
    integer_part = parts[0]
    if len(integer_part) > 3:
        formatted_int = ' '.join([integer_part[max(0, i - 3):i] for i in range(len(integer_part), 0, -3)][::-1])
    else:
        formatted_int = integer_part
    if len(parts) > 1:
        return formatted_int + ',' + parts[1]
    return formatted_int


def build_table(rows, has_woman):
    table_rows = ""
    for row in rows:
        amount_float = float(row[2].replace(' ', '').replace(',', '.'))
        amount = format_amount(amount_float)
        if has_woman:
            woman_val = row[3] if len(row) >= 4 else ""
            table_rows += f"|   {row[0]}   |  {row[1]}  | {amount} |   {woman_val}   |\n"
        else:
            table_rows += f"|   {row[0]}   |  {row[1]}  | {amount} |\n"
    if not table_rows:
        table_rows = "|   |   |   |   |\n" if has_woman else "|   |   |   |\n"
    return table_rows


def write_file(file_path, spending, income, spending_has_woman, income_has_woman, title_date: datetime):
    date_str = title_date.strftime('%d.%m.%Y')
    spending_rows = build_table(spending, spending_has_woman)
    income_rows = build_table(income, income_has_woman)
    if spending_has_woman:
        spending_header = "| Product | Source |  Sum  | Woman |\n|:-------:|:------:|:-----:|:-----:|"
    else:
        spending_header = "| Product | Source |  Sum  |\n|:-------:|:------:|:-----:|"
    if income_has_woman:
        income_header = "| Product | Source | Sum | Woman |\n| :-----: | :----: | :-: | :-----: |"
    else:
        income_header = "| Product | Source | Sum |\n| :-----: | :----: | :-: |"
    content = f"""### Расходы и доходы за {date_str}

 ### Tags: #Spending
---
## *Spending:*

{spending_header}
{spending_rows}
---
## *Income:*

{income_header}
{income_rows}
---
"""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logging.info(format, *args)

    def do_POST(self):
        try:
            if RECEIVER_SECRET:
                token = self.headers.get("X-Secret", "")
                if token != RECEIVER_SECRET:
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Forbidden")
                    logging.warning("Неверный секрет в запросе")
                    return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)

            entries = data["entries"]
            event_ts = data["event_ts"]
            event_dt = datetime.fromtimestamp(event_ts, tz=timezone.utc).astimezone(USER_ZONE)

            file_path = get_file_path(event_dt)
            spending, income, spending_has_woman, income_has_woman = read_file(file_path)

            for entry in entries:
                if entry['woman']:
                    if entry['is_income']:
                        income_has_woman = True
                    else:
                        spending_has_woman = True

            for entry in entries:
                woman_val = "+" if entry['woman'] else ""
                row = [entry['product'], entry['source'], str(entry['amount']), woman_val]
                if entry['is_income']:
                    income.append(row)
                else:
                    spending.append(row)

            write_file(file_path, spending, income, spending_has_woman, income_has_woman, event_dt)
            logging.info("Записано %d entries в %s", len(entries), file_path)

            response = json.dumps({"ok": True, "file": os.path.basename(file_path), "count": len(entries)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response)

        except Exception as e:
            logging.exception("Ошибка обработки запроса")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())


def main():
    server = HTTPServer(("0.0.0.0", RECEIVER_PORT), RequestHandler)
    logging.info("Receiver запущен на порту %d", RECEIVER_PORT)
    logging.info("VAULT_PATH=%s", VAULT_PATH)
    server.serve_forever()


if __name__ == '__main__':
    main()
