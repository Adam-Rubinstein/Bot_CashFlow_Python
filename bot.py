import logging
import os
from datetime import datetime, timezone
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


def _user_zone() -> ZoneInfo:
    raw = (os.getenv("USER_TIMEZONE") or "").strip()
    if not raw:
        return ZoneInfo("Europe/Moscow")
    try:
        return ZoneInfo(raw)
    except Exception:
        logging.warning("Invalid USER_TIMEZONE=%r, using Europe/Moscow", raw)
        return ZoneInfo("Europe/Moscow")


USER_ZONE = _user_zone()


def message_event_datetime(message: Optional[Message]) -> datetime:
    """Время события в USER_ZONE: Telegram отдаёт date в UTC."""
    tz = USER_ZONE
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
    """Парсит сообщение в формат: товар; источник; сумма[; +]"""
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    entries = []

    for line in lines:
        # Разбиваем по точке с запятой
        parts = [p.strip() for p in line.split(';')]

        if len(parts) < 3:
            continue

        product = parts[0].strip()
        source = parts[1].strip()
        amount_str = parts[2].strip()
        woman = False

        # Проверяем, есть ли + в конце (4-й элемент)
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
        # Пропускаем заголовки и разделители
        if '|' not in line or 'Product' in line or ':-' in line:
            continue

        # ВАЖНО: Не удаляем пробелы внутри строки!
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


def build_table(rows, has_woman):
    """Строит строки таблицы"""
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
        if has_woman:
            table_rows = "|   |   |   |   |\n"
        else:
            table_rows = "|   |   |   |\n"

    return table_rows


def write_file(file_path, spending, income, spending_has_woman, income_has_woman, title_date: datetime):
    """Записывает данные в файл"""
    date_str = title_date.strftime('%d.%m.%Y')

    spending_rows = build_table(spending, spending_has_woman)
    income_rows = build_table(income, income_has_woman)

    # Строим таблицы с правильными разделителями
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    event_dt = message_event_datetime(update.message)
    logging.info("Получено сообщение: %s (event date in USER_TIMEZONE: %s)", text, event_dt.date())

    entries = parse_message(text)
    logging.info("Распарсено entries: %s", entries)

    if not entries:
        await update.message.reply_text("Invalid format! Example:\nProduct; Source; Sum\nOR\nProduct; Source; Sum; +")
        return

    file_path = get_file_path(event_dt)
    spending, income, spending_has_woman, income_has_woman = read_file(file_path)

    # Проверяем, есть ли новые записи с woman = True
    for entry in entries:
        if entry['woman']:
            if entry['is_income']:
                income_has_woman = True
            else:
                spending_has_woman = True

    # Добавляем новые записи
    for entry in entries:
        woman_val = "+" if entry['woman'] else ""
        row = [entry['product'], entry['source'], str(entry['amount']), woman_val]
        if entry['is_income']:
            income.append(row)
        else:
            spending.append(row)

    write_file(file_path, spending, income, spending_has_woman, income_has_woman, event_dt)

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

    logging.info("USER_TIMEZONE=%s", os.getenv("USER_TIMEZONE") or "(default Europe/Moscow)")
    logging.info("Bot started!")
    app.run_polling()


if __name__ == '__main__':
    main()