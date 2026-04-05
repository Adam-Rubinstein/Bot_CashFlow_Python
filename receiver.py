from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo
import re

from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv
import uvicorn

from security import MIN_SECRET_LEN, SIGNATURE_HEADER, verify_signature

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

load_dotenv()

VAULT_PATH = os.getenv("VAULT_PATH")
RECEIVER_PORT = int(os.getenv("RECEIVER_PORT", "8080"))
RECEIVER_HOST = (os.getenv("RECEIVER_HOST") or "127.0.0.1").strip()
RECEIVER_SECRET = os.getenv("RECEIVER_SECRET", "")
RECEIVER_INSECURE_DEV = (os.getenv("RECEIVER_INSECURE_DEV") or "").strip().lower() in (
    "1",
    "true",
    "yes",
)
RECEIVER_MAX_SKEW_SEC = float(os.getenv("RECEIVER_MAX_SKEW_SEC", "600"))
RECEIVER_NONCE_TTL_SEC = float(os.getenv("RECEIVER_NONCE_TTL_SEC", "600"))

app = FastAPI()

_nonce_lock = asyncio.Lock()
_seen_nonces: dict[str, float] = {}


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
    spending, income = [], []
    spending_has_woman = income_has_woman = False
    in_spending = in_income = False
    for line in content.split('\n'):
        if '## *Spending:*' in line:
            in_spending, in_income = True, False
            continue
        if '## *Income:*' in line:
            in_spending, in_income = False, True
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
        formatted_int = ' '.join([integer_part[max(0, i-3):i] for i in range(len(integer_part), 0, -3)][::-1])
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


async def _nonce_ok(nonce: str) -> bool:
    if not nonce or not isinstance(nonce, str) or len(nonce) < 8:
        return False
    now = time.time()
    async with _nonce_lock:
        dead = [k for k, exp in _seen_nonces.items() if exp < now]
        for k in dead:
            del _seen_nonces[k]
        if nonce in _seen_nonces:
            return False
        _seen_nonces[nonce] = now + RECEIVER_NONCE_TTL_SEC
        return True


@app.post("/")
async def handle(request: Request):
    body = await request.body()

    if not RECEIVER_INSECURE_DEV:
        if len(RECEIVER_SECRET) < MIN_SECRET_LEN:
            logging.error("RECEIVER_SECRET слишком короткий или не задан")
            return Response(content="Forbidden", status_code=403)
        sig = request.headers.get(SIGNATURE_HEADER)
        if not verify_signature(RECEIVER_SECRET, body, sig):
            logging.warning("Неверная подпись или отсутствует %s", SIGNATURE_HEADER)
            return Response(content="Forbidden", status_code=403)
    try:
        data = json.loads(body.decode("utf-8"))
        entries = data["entries"]
        event_ts = data["event_ts"]
        nonce = data.get("nonce")
        if not RECEIVER_INSECURE_DEV:
            if not await _nonce_ok(nonce):
                logging.warning("Повтор nonce или невалидный nonce")
                return Response(content="Forbidden", status_code=403)
        now_ts = time.time()
        if abs(float(event_ts) - now_ts) > RECEIVER_MAX_SKEW_SEC:
            logging.warning(
                "event_ts вне допустимого окна (skew > %s сек)", RECEIVER_MAX_SKEW_SEC
            )
            return Response(content="Forbidden", status_code=403)

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
        return {"ok": True, "file": os.path.basename(file_path), "count": len(entries)}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logging.warning("Некорректное тело запроса: %s", e)
        return Response(content="Bad Request", status_code=400)
    except Exception as e:
        logging.exception("Ошибка обработки запроса")
        return Response(content=str(e), status_code=500)


def _validate_startup() -> None:
    if not VAULT_PATH:
        raise SystemExit("VAULT_PATH не задан в .env")
    if RECEIVER_INSECURE_DEV:
        logging.warning(
            "RECEIVER_INSECURE_DEV включён — без HMAC/nonce-политики; только для локальных тестов"
        )
        return
    if len(RECEIVER_SECRET) < MIN_SECRET_LEN:
        raise SystemExit(
            f"Задайте RECEIVER_SECRET не короче {MIN_SECRET_LEN} символов "
            f"(или RECEIVER_INSECURE_DEV=1 только для разработки)."
        )


if __name__ == '__main__':
    _validate_startup()
    logging.info(
        "Receiver: host=%s port=%s secure=%s",
        RECEIVER_HOST,
        RECEIVER_PORT,
        not RECEIVER_INSECURE_DEV,
    )
    logging.info("VAULT_PATH=%s", VAULT_PATH)
    uvicorn.run(app, host=RECEIVER_HOST, port=RECEIVER_PORT)
