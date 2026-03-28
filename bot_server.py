"""bot_server.py — запускается на VPS.
Получает сообщения от Telegram и пересылает распарсенные данные на ПК через bore-туннель.

Запуск:
    python bot_server.py

Переменные окружения (в .env на сервере):
    TELEGRAM_TOKEN    — токен бота
    RECEIVER_URL      — адрес receiver.py на ПК, например http://bore.pub:54655
    RECEIVER_SECRET   — общий секрет (должен совпадать с receiver.py)
    ALLOWED_USER_IDS  — список разрешённых user id (через запятую)
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RECEIVER_URL = (os.getenv("RECEIVER_URL") or "").strip().rstrip("/")
RECEIVER_SECRET = os.getenv("RECEIVER_SECRET", "")


def parse_allowed_user_ids(raw: Optional[str]) -> Optional[set[int]]:
    if raw is None or not str(raw).strip():
        return None
    out: set[int] = set()
    for part in re.split(r"[\s,;]+", raw.strip()):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            logging.warning("ALLOWED_USER_IDS: пропуск нечислового фрагмента %r", part)
    if not out:
        logging.warning("ALLOWED_USER_IDS не содержит валидных id — бот никому не ответит")
        return set()
    return out


ALLOWED_USER_IDS = parse_allowed_user_ids(os.getenv("ALLOWED_USER_IDS"))


def user_may_use_bot(user_id: Optional[int], allowed: Optional[set[int]]) -> bool:
    if allowed is None:
        return True
    if user_id is None:
        return False
    return user_id in allowed


def parse_message(text):
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    entries = []
    for line in lines:
        parts = [p.strip() for p in line.split(';')]
        if len(parts) < 3:
            continue
        product = parts[0].strip()
        source = parts[1].strip()
        amount_str = parts[2].strip()
        woman = False
        if len(parts) >= 4 and parts[3].strip() == '+':
            woman = True
        is_income = amount_str.startswith('+')
        amount_str = amount_str.replace('+', '').replace(' ', '').replace(',', '.')
        try:
            amount = float(amount_str)
            entries.append({
                'product': product,
                'source': source,
                'amount': amount,
                'is_income': is_income,
                'woman': woman
            })
        except ValueError:
            logging.warning("Ошибка парсинга: %s", amount_str)
            continue
    return entries


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if not user_may_use_bot(uid, ALLOWED_USER_IDS):
        logging.warning("Отклонено сообщение от user_id=%s", uid)
        return

    text = update.message.text
    logging.info("Получено сообщение: %s", text)

    entries = parse_message(text)
    if not entries:
        await update.message.reply_text("Invalid format! Example:\nProduct; Source; Sum\nOR\nProduct; Source; Sum; +")
        return

    # Время сообщения в UTC (unix timestamp)
    msg_date = update.message.date
    event_ts = msg_date.timestamp()

    payload = {
        "entries": entries,
        "event_ts": event_ts,
    }

    headers = {"Content-Type": "application/json"}
    if RECEIVER_SECRET:
        headers["X-Secret"] = RECEIVER_SECRET

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{RECEIVER_URL}/", content=json.dumps(payload), headers=headers)
            resp.raise_for_status()
            result = resp.json()
            await update.message.reply_text(
                f"Added {result['count']} records to {result['file']}"
            )
    except Exception as e:
        logging.exception("Ошибка отправки на receiver")
        await update.message.reply_text(f"Ошибка связи с ПК: {e}")


def main():
    if not RECEIVER_URL:
        raise RuntimeError("RECEIVER_URL не задан в .env")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("RECEIVER_URL=%s", RECEIVER_URL)
    if ALLOWED_USER_IDS is None:
        logging.info("ALLOWED_USER_IDS=(any user)")
    else:
        logging.info("ALLOWED_USER_IDS=%s", sorted(ALLOWED_USER_IDS))
    logging.info("Bot server started!")
    app.run_polling()


if __name__ == '__main__':
    main()
