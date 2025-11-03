import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# Загрузи переменные из .env
load_dotenv()

# НАСТРОЙКИ
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VAULT_PATH = os.getenv("VAULT_PATH")

# Шаблон файла
TEMPLATE = """### Расходы и доходы за {date}

 ### Tags: #Spending
---
## *Spending:*

| Product |  Source   |   Sum    |
| :-----: | :-------: | :------: |
{spending_rows}

---
## *Income:*

| Product |  Source   |   Sum    |
| :-----: | :-------: | :------: |
{income_rows}

---
"""


def parse_message(text):
    """Парсит сообщение в формат: товар, источник, сумма"""
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    entries = []

    for line in lines:
        parts = [p.strip() for p in line.split(',')]
        if len(parts) != 3:
            continue

        product, source, amount_str = parts

        is_income = amount_str.startswith('+')
        amount_str = amount_str.replace('+', '').replace(' ', '')

        try:
            amount = float(amount_str)
            entries.append({
                'product': product,
                'source': source,
                'amount': amount,
                'is_income': is_income
            })
        except ValueError:
            continue

    return entries


def get_file_path():
    """Возвращает путь к файлу текущей даты"""
    now = datetime.now()
    year = now.strftime('%Y')
    month_num = now.strftime('%m')
    month_name = now.strftime('%B')
    date_str = now.strftime('%d.%m.%Y')

    month_folder = f"{month_num}_{month_name}"
    folder_path = os.path.join(VAULT_PATH, year, month_folder)
    file_path = os.path.join(folder_path, f"{date_str}.md")

    os.makedirs(folder_path, exist_ok=True)
    return file_path


def read_file(file_path):
    """Читает файл и возвращает списки расходов/доходов"""
    if not os.path.exists(file_path):
        return [], []

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    spending = []
    income = []

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

        if '|' not in line or 'Product' in line or '---' in line:
            continue

        cells = [c.strip().replace(',', '.') for c in line.split('|') if c.strip()]
        if len(cells) >= 3:
            if in_spending:
                spending.append(cells)
            elif in_income:
                income.append(cells)

    return spending, income


def write_file(file_path, spending, income):
    """Записывает данные в файл"""
    now = datetime.now()
    date_str = now.strftime('%d.%m.%Y')

    spending_rows = ""
    for s in spending:
        amount_float = float(s[2])
        if amount_float == int(amount_float):
            amount = str(int(amount_float))
        else:
            amount = str(amount_float).replace('.', ',')
        spending_rows += f"| {s[0]} | {s[1]} | {amount} |\n"

    income_rows = ""
    for i in income:
        amount_float = float(i[2])
        if amount_float == int(amount_float):
            amount = str(int(amount_float))
        else:
            amount = str(amount_float).replace('.', ',')
        income_rows += f"| {i[0]} | {i[1]} | {amount} |\n"

    if not spending_rows:
        spending_rows = "| | | |\n"
    if not income_rows:
        income_rows = "| | | |\n"

    content = TEMPLATE.format(
        date=date_str,
        spending_rows=spending_rows,
        income_rows=income_rows
    )

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    entries = parse_message(text)

    if not entries:
        await update.message.reply_text("Invalid format! Example:\nfood, store, 350")
        return

    file_path = get_file_path()
    spending, income = read_file(file_path)

    for entry in entries:
        row = [entry['product'], entry['source'], str(entry['amount'])]
        if entry['is_income']:
            income.append(row)
        else:
            spending.append(row)

    write_file(file_path, spending, income)

    await update.message.reply_text(
        f"Added {len(entries)} records to {os.path.basename(file_path)}"
    )


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started!")
    app.run_polling()


if __name__ == '__main__':
    main()
