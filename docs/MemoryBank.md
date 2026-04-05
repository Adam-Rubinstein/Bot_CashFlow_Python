# Memory Bank — Bot CashFlow (Python / Telegram)

Единый источник контекста по продукту и коду. Агенты и разработчики **дополняют** этот файл: архитектурные решения — в соответствующие разделы; ход работы — в **[Журнал](#журнал)** (после сессии или значимого шага).

## Протокол для ИИ-агента

1. **Перед работой:** прочитать этот файл (цель, стек, режимы запуска, переменные окружения, последние записи журнала).
2. **Во время и после работы:** записать в [Журнал](#журнал) значимые действия: что сделано, какие файлы затронуты, команды при необходимости.
3. **Формат записи:** подзаголовок `### YYYY-MM-DD` при первой записи за день, далее маркированный список; кратко, без дублирования всего diff.
4. **Обновление базы знаний:** если изменились формат сообщений, схема файлов vault, env, тесты или схема VPS+receiver — обновить соответствующий раздел выше, не только журнал.

## Цель

Telegram-бот для учёта **расходов и доходов**: пользователь шлёт строки в формате `Товар; Источник; Сумма`, бот дописывает записи в дневные **Markdown**-файлы в структуре по годам/месяцам (совместимо с Obsidian vault).

## Стек

| Компонент | Выбор |
|-----------|--------|
| Runtime | Python 3.x |
| Telegram | **python-telegram-bot** 21.x (`telegram.ext`) |
| Конфиг | `python-dotenv`, `.env` |
| Прокси к Bot API | опционально `PROXY_URL` (SOCKS5/HTTP), пакет `httpx[socks]`; **не MTProto** — см. [TELEGRAM_BLOCKING_AND_PROXY.md](./TELEGRAM_BLOCKING_AND_PROXY.md) |
| Разделённый режим (VPS → ПК) | **httpx** (клиент на сервере), **FastAPI + uvicorn** (приёмник на ПК) |
| Тесты | `pytest`, см. `tests/test_bot_core.py` |

## Репозиторий Git

- **GitHub:** [https://github.com/Adam-Rubinstein/Bot_CashFlow_Python](https://github.com/Adam-Rubinstein/Bot_CashFlow_Python) — ветка по умолчанию `master`, публикация изменений: `git push origin master` (или настроенный remote).
- **Типичный путь на ПК (Windows):** `D:\Desktop\Projects\Bot_CashFlow_Python`.

## Режимы работы

### A. Локально: `bot.py`

- Long polling к Telegram, запись **на той же машине** в `VAULT_PATH`.
- Дата дня для имени файла и заголовка — из **времени сообщения Telegram (UTC)**, переведённого в `USER_TIMEZONE` (не системные часы сервера).
- Опционально `PROXY_URL`, если `api.telegram.org` недоступен (только **SOCKS5/HTTP**, не MTProto из настроек клиента Telegram).

### Блокировка Telegram на ПК

Если **локально** не доходит до `api.telegram.org`, а файлы нужны **на ПК**: используйте split-режим (**`bot_server.py` на VPS** + **`receiver.py` на ПК** + туннель bore/ngrok), либо **SOCKS5/HTTP** на VPS в `PROXY_URL`, либо VPN на ПК. Подробно: [TELEGRAM_BLOCKING_AND_PROXY.md](./TELEGRAM_BLOCKING_AND_PROXY.md).

**VPS:** IPv4 `62.60.186.183`, SSH `ssh root@62.60.186.183`. Установка и systemd для `bot_server.py`: [deploy/README.md](../deploy/README.md). MTProto-прокси на сервере (например порт `1443`) работает для **клиента Telegram**, не для `python-telegram-bot`.

### B. VPS + туннель + ПК: `bot_server.py` + `receiver.py`

- **`bot_server.py`** (на VPS): принимает апдейты Telegram, парсит те же строки, **POST JSON** на URL приёмника: `{"entries": [...], "event_ts": <unix float>}`.
- **`receiver.py`** (на ПК, в локальной сети или за туннелем): FastAPI `POST /`, проверка `X-Secret` при необходимости, конвертация `event_ts` → `USER_TIMEZONE`, запись в `VAULT_PATH` на ПК.
- Связка типично с **bore** или аналогом: публичный URL туннеля указывается в `RECEIVER_URL` на сервере. Пример локального запуска см. `bot.example.bat` (bore на порт `8080`, затем `receiver.py`).

Переменные для режима B (дополнительно к общим):

| Переменная | Где | Назначение |
|------------|-----|------------|
| `RECEIVER_URL` | только `bot_server.py` | Базовый URL приёмника, без завершающего `/` не обязателен (код обрезает). |
| `RECEIVER_SECRET` | `bot_server.py` и `receiver.py` | Общий секрет в заголовке `X-Secret`. |
| `RECEIVER_PORT` | `receiver.py` | Порт uvicorn (по умолчанию `8080`). |
| `PROXY_URL` | `bot_server.py` | Опционально, если на **VPS** нет прямого доступа к Bot API (редко). |

На сервере в `.env` **нет** `VAULT_PATH` для `bot_server.py` — файлы не пишутся на VPS.

### Защита туннеля VPS → ПК

Запросы к `receiver` подписываются **HMAC-SHA256** общим секретом (тело JSON в каноническом виде), в заголовке `X-Body-Signature`; в теле есть одноразовый **`nonce`** и проверка **времени** (`event_ts`). Секрет ≥24 символов. По умолчанию приёмник слушает **`127.0.0.1`** (`RECEIVER_HOST`). Подробно: [RECEIVER_SECURITY.md](./RECEIVER_SECURITY.md).

## Формат сообщения пользователя

- Одна или несколько строк; каждая строка: `product; source; amount[; +]`.
- **Расход:** сумма без префикса, например `Еда; Лента; 1755.5`.
- **Доход:** сумма с ведущим `+` в поле суммы, например `Зарплата; Работа; +50000`.
- Четвёртое поле **`+`** (ровно четвёртая часть после `;`) — флаг «woman» (в таблице колонка Woman / `+`).

Парсер: `parse_message` в `bot.py` / `bot_server.py` (логика совпадает).

## Файлы vault (Markdown)

- Путь: `{VAULT_PATH}/{YYYY}/{MM_MonthName}/{DD.MM.YYYY}.md`.
- Внутри: секции `## *Spending:*` и `## *Income:*`, markdown-таблицы; при появлении флага woman добавляется колонка Woman.

## Переменные окружения (сводка)

| Переменная | Обязательность | Описание |
|------------|----------------|----------|
| `TELEGRAM_TOKEN` | да | Токен BotFather. |
| `VAULT_PATH` | да для `bot.py` и `receiver.py` | Абсолютный путь к корню хранилища `.md`. |
| `USER_TIMEZONE` | нет | `UTC±H[:MM]` или IANA (`Europe/Moscow`); иначе UTC+3. |
| `ALLOWED_USER_IDS` | нет | Whitelist числовых Telegram user id; пусто = все. |
| `PROXY_URL` | нет | `bot.py` и опционально `bot_server.py`. |

Полный шаблон: `.env.example`.

## Деплой и эксплуатация (сервер)

Пошаговая установка `bot_server.py` на VPS: [deploy/README.md](../deploy/README.md). Юнит systemd: [deploy/cashflow-bot-server.service.example](../deploy/cashflow-bot-server.service.example).

### Репозиторий и папки локально

| Что | Где |
|-----|-----|
| Клон GitHub | [Bot_CashFlow_Python](https://github.com/Adam-Rubinstein/Bot_CashFlow_Python) |
| Типичный путь на ПК (Windows) | `D:\Desktop\Projects\Bot_CashFlow_Python` |
| Точки входа | `python bot.py`, `python bot_server.py`, `python receiver.py` |
| Деплой-артефакты | `deploy/README.md`, `deploy/cashflow-bot-server.service.example` |

### Production VPS

| Параметр | Значение |
|----------|----------|
| **IPv4** | `62.60.186.183` |
| **Вход по SSH** | `ssh root@62.60.186.183` |
| **Пользователь systemd в примерах** | `root` |

### Пути на сервере

| Путь | Назначение |
|------|------------|
| `/opt/app/bot-cashflow` | Каталог репозитория (см. `deploy/README.md`) |
| `/opt/app/bot-cashflow/.env` | `TELEGRAM_TOKEN`, `RECEIVER_URL`, `RECEIVER_SECRET` и т.д. (без `VAULT_PATH`) |

### systemd: имя сервиса и команды

| Действие | Команда (на сервере, после SSH) |
|----------|--------------------------------|
| Статус | `systemctl status cashflow-bot-server` |
| Перезапуск | `systemctl restart cashflow-bot-server` |
| Автозапуск | `systemctl enable cashflow-bot-server` |
| Логи | `journalctl -u cashflow-bot-server -f` |

### Обновление кода на сервере

```bash
cd /opt/app/bot-cashflow
git pull
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart cashflow-bot-server
```

В проде для split-режима используется **long polling** на стороне `bot_server.py`; webhook на сервере не настроен.

### Автоматизированный split (без bore/ngrok)

На **VPS** `RECEIVER_URL=http://127.0.0.1:18080` — трафик идёт в **обратный SSH-туннель** с ПК: на сервере слушает `127.0.0.1:18080`, на ПК приёмник `receiver.py` на `127.0.0.1:8080`. На **Windows** скрипт [scripts/start_split_tunnel.ps1](../scripts/start_split_tunnel.ps1) поднимает `receiver` и `ssh -R …` в фоне (**без окна** `ssh.exe`, чтобы не закрыть случайно). Автозапуск при входе в Windows: ключ реестра `HKCU\...\Run` → `BotCashFlowSplitTunnel`. Деплой на VPS: [deploy/remote_bootstrap.sh](../deploy/remote_bootstrap.sh) и systemd `cashflow-bot-server`.

## Репозиторий: файлы и входные точки

| Файл | Назначение |
|------|------------|
| `bot.py` | Локальный бот + запись в vault на этой машине. |
| `bot_server.py` | Бот на VPS, пересылает распарсенные записи на `RECEIVER_URL`. |
| `receiver.py` | HTTP-приёмник на ПК, пишет в локальный `VAULT_PATH`. |
| `bot.example.bat` / `bot.bat` | Windows: bore + фоновый `receiver.py` (gitignore у `bot.bat`). |
| `security.py` | HMAC и канонический JSON для `bot_server` → `receiver`. |

## Тесты

- `pytest` из корня проекта.
- `tests/test_bot_core.py` — парсинг, ACL, таймзона, формат сумм, `get_file_path`.
- `tests/test_security.py`, `tests/test_receiver_security.py` — подпись и приёмник.

## Лицензия

LGPL v3.0 — см. `LICENSE` в корне.

## Связанные документы

- [README.md](../README.md) — установка, прокси, синхронизация vault с VPS, ограничение очереди Bot API (~24 ч).
- [deploy/README.md](../deploy/README.md) — установка и обновление `bot_server.py` на VPS.
- [TELEGRAM_BLOCKING_AND_PROXY.md](./TELEGRAM_BLOCKING_AND_PROXY.md) — блокировки, MTProto vs Bot API, split-режим.
- [RECEIVER_SECURITY.md](./RECEIVER_SECURITY.md) — HMAC, nonce, HTTPS туннеля, `RECEIVER_HOST`.
- `docs/REAL_DEPLOYMENT_DATA.local.md` — локальная копия с `RECEIVER_SECRET` для ПК и VPS (файл в `.gitignore`, в репозиторий не попадает). Шаблон: [REAL_DEPLOYMENT_DATA.template.md](./REAL_DEPLOYMENT_DATA.template.md).
- Репозиторий на GitHub: [Adam-Rubinstein/Bot_CashFlow_Python](https://github.com/Adam-Rubinstein/Bot_CashFlow_Python).

## Журнал

### 2026-04-07

- Скрипт `start_split_tunnel.ps1`: для `ssh` используется `-WindowStyle Hidden`, чтобы не показывалось отдельное окно (случайное закрытие).
- Добавлен [scripts/import_telegram_backlog.py](../scripts/import_telegram_backlog.py): импорт строк `[DD.MM.YYYY HH:MM] Adam: …` в vault по `USER_TIMEZONE`, слияние с уже существующими дневными `.md`.


### 2026-04-06

- Развёрнуто на VPS `62.60.186.183`: `/opt/app/bot-cashflow`, systemd `cashflow-bot-server`, `.env` с `RECEIVER_URL=http://127.0.0.1:18080` (обратный SSH с ПК). На Windows: скрипт `scripts/start_split_tunnel.ps1`, автозапуск через `HKCU\...\Run\BotCashFlowSplitTunnel`. Код запушен в GitHub; VPS обновлён `git pull`.
- Сгенерирован общий `RECEIVER_SECRET` (RNG), записан в корневой `.env` и в `docs/REAL_DEPLOYMENT_DATA.local.md` (в `.gitignore`); добавлен шаблон `docs/REAL_DEPLOYMENT_DATA.template.md`.
- Реализована защита канала VPS → ПК: [security.py](../security.py) (HMAC-SHA256, канонический JSON), [receiver.py](../receiver.py) (подпись, nonce anti-replay, окно `event_ts`, привязка к `127.0.0.1` по умолчанию), [bot_server.py](../bot_server.py) (подпись тела, обязательный секрет ≥24 символов). Документация: [RECEIVER_SECURITY.md](./RECEIVER_SECURITY.md); обновлены [deploy/README.md](../deploy/README.md), [.env.example](../.env.example). Тесты: `tests/test_security.py`, `tests/test_receiver_security.py`.

### 2026-04-05

- Добавлены [deploy/README.md](../deploy/README.md), [deploy/cashflow-bot-server.service.example](../deploy/cashflow-bot-server.service.example); в Memory Bank — раздел **«Деплой и эксплуатация (сервер)»** (IP, SSH, пути, systemd, обновление).
- Добавлен [TELEGRAM_BLOCKING_AND_PROXY.md](./TELEGRAM_BLOCKING_AND_PROXY.md): MTProto не подходит для Bot API; рекомендации split / SOCKS5 / VPN. В `bot_server.py` — опциональный `PROXY_URL` (как в `bot.py`).
- Зафиксирован URL репозитория: [github.com/Adam-Rubinstein/Bot_CashFlow_Python](https://github.com/Adam-Rubinstein/Bot_CashFlow_Python) — раздел **«Репозиторий Git»** в Memory Bank, ссылка в [README.md](../README.md).
- Первичное наполнение Memory Bank по коду (`bot.py`, `bot_server.py`, `receiver.py`).
- В `requirements.txt` добавлены зависимости `fastapi` и `uvicorn` для `receiver.py` (раньше использовались в коде, но не были перечислены).
- Добавлено Cursor-правило `.cursor/rules/memory-bank.mdc`; в [README.md](../README.md) — раздел «Документация» и краткий сценарий split (VPS + receiver).
- В [.env.example](../.env.example) добавлены закомментированные переменные для `bot_server` / `receiver`.
