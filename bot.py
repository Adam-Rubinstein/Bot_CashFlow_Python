from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Message, Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Загрузка переменных из .env
load_dotenv()

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VAULT_PATH = os.getenv("VAULT_PATH")
# Опционально: SOCKS5/HTTP-прокси для доступа к api.telegram.org (см. README)
PROXY_URL = (os.getenv("PROXY_URL") or "").strip() or None


def parse_allowed_user_ids(raw: Optional[str]) -> Optional[set[int]]:
    """None — разрешены все; непустой set — только эти user id (Telegram int)."""
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


def _parse_utc_offset(raw: str) -> Optional[timezone]:
    """Принимает вид UTC+3, UTC+03:30, UTC-5 (без DST)."""
    m = re.match(r"^\s*UTC\s*([+-])(\d{1,2})(?::(\d{2}))?\s*$", raw, re.IGNORECASE)
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    hours = int(m.group(2))
    minutes = int(m.group(3) or 0)
    if minutes >= 60 or hours > 14:
        return None
    return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))


def _default_zone() -> timezone:
    return timezone(timedelta(hours=3))


def _user_zone() -> tzinfo:
    raw = (os.getenv("USER_TIMEZONE") or "").strip()
    if not raw:
        return _default_zone()
    parsed = _parse_utc_offset(raw)
    if parsed is not None:
        return parsed
    try:
        return ZoneInfo(raw)
    except Exception:
        logging.warning("Invalid USER_TIMEZONE=%r, using UTC+3", raw)
        return _default_zone()


USER_ZONE = _user_zone()


def message_event_datetime(message: Optional[Message], tz: tzinfo) -> datetime:
    """Время события в tz: Telegram отдаёт date в UTC."""
    if message is None or message.date is None:
        logging.warning("Message has no date, using current UTC time")
        return datetime.now(timezone.utc).astimezone(tz)
    d = message.date
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    else:
        d = d.astimezone(timezone.utc)
    return d.astimezone(tz)


def parse_message(text):
    """Парсит сообщение в формат: товар; источник; сумма[; +|вид деятельности]"""
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
        work = ""

        if len(parts) >= 4:
            tag = parts[3].strip()
            if tag == '+':
                woman = True
            elif tag:
                work = tag

        is_income = amount_str.startswith('+')
        amount_str = amount_str.replace('+', '').replace(' ', '').replace(',', '.')

        try:
            amount = float(amount_str)
            entries.append({
                'product': product,
                'source': source,
                'amount': amount,
                'is_income': is_income,
                'woman': woman,
                'work': work,
            })
        except ValueError:
            logging.warning("Ошибка парсинга: %s", amount_str)
            continue

    return entries


def get_file_path(for_date: datetime):
    """Возвращает путь к файлу для календарной даты for_date (в USER_ZONE)."""
    year = for_date.strftime('%Y')
    month_num = for_date.strftime('%m')
    month_name = for_date.strftime('%B')
    date_str = for_date.strftime('%d.%m.%Y')

    month_folder = f"{month_num}_{month_name}"
    folder_path = os.path.join(VAULT_PATH, year, month_folder)
    file_path = os.path.join(folder_path, f"{date_str}.md")

    os.makedirs(folder_path, exist_ok=True)
    return file_path


def _normalize_row(cells):
    """Приводит ячейки строки таблицы к [product, source, amount, woman_val, work_val]."""
    product, source, amount = cells[0], cells[1], cells[2]
    woman_val = ""
    work_val = ""
    if len(cells) >= 5:
        if cells[3].strip() == '+':
            woman_val = '+'
        work_val = cells[4].strip()
    elif len(cells) >= 4:
        v = cells[3].strip()
        if v == '+':
            woman_val = '+'
        elif v:
            work_val = v
    return [product, source, amount, woman_val, work_val]


def read_file(file_path):
    if not os.path.exists(file_path):
        return [], [], False, False, False, False

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    spending = []
    income = []
    spending_has_woman = False
    income_has_woman = False
    spending_has_work = False
    income_has_work = False

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
        # Пропускаем заголовки и разделители
        if '|' not in line or 'Product' in line or ':-' in line:
            continue

        # ВАЖНО: Не удаляем пробелы внутри строки!
        cells = [c.strip().replace(',', '.') for c in line.split('|') if c.strip()]
        if len(cells) >= 3:
            row = _normalize_row(cells)

            if in_spending:
                spending.append(row)
                if row[3]:
                    spending_has_woman = True
                if row[4]:
                    spending_has_work = True
            elif in_income:
                income.append(row)
                if row[3]:
                    income_has_woman = True
                if row[4]:
                    income_has_work = True

    return spending, income, spending_has_woman, income_has_woman, spending_has_work, income_has_work


def format_amount(amount_float):
    """Форматирует число с пробелом как разделитель тысяч"""
    if amount_float == int(amount_float):
        amount = str(int(amount_float))
    else:
        amount = str(amount_float).replace('.', ',')

    # Добавляем пробел как разделитель тысяч
    parts = amount.split(',')
    integer_part = parts[0]

    # Форматируем целую часть с пробелами
    if len(integer_part) > 3:
        formatted_int = ' '.join([integer_part[max(0, i - 3):i] for i in range(len(integer_part), 0, -3)][::-1])
    else:
        formatted_int = integer_part

    if len(parts) > 1:
        return formatted_int + ',' + parts[1]
    else:
        return formatted_int


def build_table(rows, has_woman, has_work):
    """Строит строки таблицы"""
    show_flags = has_woman or has_work
    table_rows = ""
    for row in rows:
        amount_float = float(row[2].replace(' ', '').replace(',', '.'))
        amount = format_amount(amount_float)

        if show_flags:
            woman_val = row[3] if len(row) >= 4 else ""
            work_val = row[4] if len(row) >= 5 else ""
            table_rows += f"|   {row[0]}   |  {row[1]}  | {amount} |   {woman_val}   |   {work_val}   |\n"
        else:
            table_rows += f"|   {row[0]}   |  {row[1]}  | {amount} |\n"

    if not table_rows:
        if show_flags:
            table_rows = "|   |   |   |   |   |\n"
        else:
            table_rows = "|   |   |   |\n"

    return table_rows


def write_file(file_path, spending, income, spending_has_woman, income_has_woman,
               spending_has_work, income_has_work, title_date: datetime):
    """Записывает данные в файл"""
    date_str = title_date.strftime('%d.%m.%Y')

    spending_rows = build_table(spending, spending_has_woman, spending_has_work)
    income_rows = build_table(income, income_has_woman, income_has_work)

    if spending_has_woman or spending_has_work:
        spending_header = "| Product | Source |  Sum  | Woman | Work |\n|:-------:|:------:|:-----:|:-----:|:----:|"
    else:
        spending_header = "| Product | Source |  Sum  |\n|:-------:|:------:|:-----:|"

    if income_has_woman or income_has_work:
        income_header = "| Product | Source | Sum | Woman | Work |\n| :-----: | :----: | :-: | :-----: | :----: |"
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if not user_may_use_bot(uid, ALLOWED_USER_IDS):
        logging.warning("Отклонено сообщение от user_id=%s (не в ALLOWED_USER_IDS)", uid)
        return

    text = update.message.text
    event_dt = message_event_datetime(update.message, USER_ZONE)
    logging.info("Получено сообщение: %s (event date in USER_TIMEZONE: %s)", text, event_dt.date())

    entries = parse_message(text)
    logging.info("Распарсено entries: %s", entries)

    if not entries:
        await update.message.reply_text(
            "Invalid format! Example:\nProduct; Source; Sum\nOR\nProduct; Source; Sum; +\nOR\nProduct; Source; Sum; Mentoring"
        )
        return

    file_path = get_file_path(event_dt)
    spending, income, spending_has_woman, income_has_woman, spending_has_work, income_has_work = read_file(file_path)

    for entry in entries:
        if entry['woman']:
            if entry['is_income']:
                income_has_woman = True
            else:
                spending_has_woman = True
        if entry['work']:
            if entry['is_income']:
                income_has_work = True
            else:
                spending_has_work = True

    for entry in entries:
        woman_val = "+" if entry['woman'] else ""
        work_val = entry['work']
        row = [entry['product'], entry['source'], str(entry['amount']), woman_val, work_val]
        if entry['is_income']:
            income.append(row)
        else:
            spending.append(row)

    write_file(
        file_path, spending, income,
        spending_has_woman, income_has_woman,
        spending_has_work, income_has_work,
        event_dt,
    )

    await update.message.reply_text(
        f"Added {len(entries)} records to {os.path.basename(file_path)}"
    )


def main():
    builder = ApplicationBuilder().token(TELEGRAM_TOKEN)
    if PROXY_URL:
        builder = builder.proxy(PROXY_URL).get_updates_proxy(PROXY_URL)
        logging.info("Using proxy for Bot API and getUpdates")
    app = builder.build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("USER_TIMEZONE=%s", os.getenv("USER_TIMEZONE") or "(default UTC+3)")
    if ALLOWED_USER_IDS is None:
        logging.info("ALLOWED_USER_IDS=(any user)")
    else:
        logging.info("ALLOWED_USER_IDS=%s", sorted(ALLOWED_USER_IDS))
    logging.info("Bot started!")
    app.run_polling()


if __name__ == '__main__':
    main()