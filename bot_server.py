"""bot_server.py — запускается на VPS.
Получает сообщения от Telegram и пересылает распарсенные данные на ПК (туннель + HMAC).

Запуск:
    python bot_server.py

Переменные окружения (в .env на сервере):
    TELEGRAM_TOKEN    — токен бота
    RECEIVER_URL      — HTTPS предпочтительно (ngrok/cloudflared) или HTTP туннель
    RECEIVER_SECRET   — общий секрет ≥24 символов (тот же, что на ПК в receiver)
    ALLOWED_USER_IDS  — список разрешённых user id (через запятую)
    PROXY_URL         — опционально: SOCKS5/HTTP для Bot API
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from typing import Optional

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from security import MIN_SECRET_LEN, SIGNATURE_HEADER, canonical_json_bytes, sign_body

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RECEIVER_URL = (os.getenv("RECEIVER_URL") or "").strip().rstrip("/")
RECEIVER_SECRET = os.getenv("RECEIVER_SECRET", "")
PROXY_URL = (os.getenv("PROXY_URL") or "").strip() or None


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

    msg_date = update.message.date
    event_ts = msg_date.timestamp()

    # Через обратный SSH keep-alive HTTP часто рвётся («Server disconnected without sending a response»):
    # без переиспользования TCP (Limits + Connection: close) и коротких повторов с новым nonce.
    limits = httpx.Limits(max_keepalive_connections=0)
    timeout = httpx.Timeout(15.0, connect=10.0)
    last_net_err: Optional[BaseException] = None

    for attempt in range(3):
        payload = {
            "entries": entries,
            "event_ts": event_ts,
            "nonce": str(uuid.uuid4()),
        }
        body_bytes = canonical_json_bytes(payload)
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            SIGNATURE_HEADER: sign_body(RECEIVER_SECRET, body_bytes),
            "Connection": "close",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
                resp = await client.post(f"{RECEIVER_URL}/", content=body_bytes, headers=headers)
                resp.raise_for_status()
                result = resp.json()
            await update.message.reply_text(
                f"Added {result['count']} records to {result['file']}"
            )
            return
        except httpx.HTTPStatusError as e:
            logging.exception("Ошибка отправки на receiver (HTTP)")
            await update.message.reply_text(f"Ошибка связи с ПК: {e}")
            return
        except httpx.RequestError as e:
            last_net_err = e
            logging.warning("Попытка %s/3, сеть до receiver: %s", attempt + 1, e)
            if attempt < 2:
                await asyncio.sleep(0.4 * (attempt + 1))
        except Exception as e:
            logging.exception("Ошибка отправки на receiver")
            await update.message.reply_text(f"Ошибка связи с ПК: {e}")
            return

    logging.exception("Ошибка отправки на receiver после повторов")
    await update.message.reply_text(f"Ошибка связи с ПК: {last_net_err}")


def main():
    if not RECEIVER_URL:
        raise RuntimeError("RECEIVER_URL не задан в .env")
    if len(RECEIVER_SECRET) < MIN_SECRET_LEN:
        raise RuntimeError(
            f"RECEIVER_SECRET должен быть не короче {MIN_SECRET_LEN} символов "
            "(общий ключ с receiver.py на ПК)."
        )

    builder = ApplicationBuilder().token(TELEGRAM_TOKEN)
    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
        logging.info("Using PROXY_URL for Bot API and getUpdates")
    app = builder.build()
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
