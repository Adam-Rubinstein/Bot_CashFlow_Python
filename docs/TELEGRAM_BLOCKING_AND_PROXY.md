# Блокировка Telegram и доступ бота к Bot API

## Важно: MTProto-прокси из клиента Telegram ≠ прокси для `bot.py`

| Что | Протокол | Кто использует |
|-----|----------|----------------|
| **MTProto proxy** (MTPROTO в настройках Telegram: хост, порт, секрет) | MTProto | Приложения Telegram (мобильный/десктопный клиент) |
| **Этот проект** (`python-telegram-bot`) | **HTTPS** к `https://api.telegram.org` | Long polling / методы Bot API |

Библиотека бота ходит в **HTTP(S)**, а не в MTProto. Параметры MTProto (порт `1443`, hex-ключ и т.д.) **нельзя** подставить в `PROXY_URL` — они для другого стека протоколов.

Поддерживаемые варианты для кода: **`PROXY_URL` в формате SOCKS5 или HTTP** (как в Telegram Desktop для SOCKS5/HTTP, не для MTProto).

Справка по типам прокси в экосистеме Telegram: клиентские MTProto-прокси описаны в [документации Telegram](https://core.telegram.org/mtproto); Bot API — отдельный [HTTP-интерфейс](https://core.telegram.org/bots/api).

---

## Решение 1 (рекомендуется): бот на VPS, файлы на ПК

Идея: **Telegram опрашивает сервер**, где `api.telegram.org` обычно доступен; на ПК нужен только **приём HTTP** от вашего туннеля.

1. **На ПК:** `VAULT_PATH`, `USER_TIMEZONE`, `RECEIVER_SECRET`, запуск `python receiver.py` (порт по умолчанию `8080`).
2. **Туннель** (исходящее соединение с ПК наружу): [bore](https://github.com/ekzhang/bore), ngrok, Cloudflare Tunnel и т.п. — получаете публичный URL вида `http://bore.pub:xxxxx`.
3. **На VPS:** `.env` с `TELEGRAM_TOKEN`, `RECEIVER_URL=<URL туннеля>`, тот же `RECEIVER_SECRET`, `ALLOWED_USER_IDS`; запуск `python bot_server.py`.

Исходящий трафик с ПК идёт к сервису туннеля, а не к `api.telegram.org` напрямую — обход региональной блокировки Bot API на ПК.

**Безопасность:** используйте **HTTPS** у туннеля по возможности; общий секрет **не короче 24 символов**; подпись запросов HMAC и одноразовый `nonce` (реализовано в коде). Чеклист: [RECEIVER_SECURITY.md](./RECEIVER_SECURITY.md). Ограничение `ALLOWED_USER_IDS` в боте — кто может писать в Telegram.

---

## Решение 2: SOCKS5 или HTTP-прокси для `bot.py` на ПК

Если хотите оставить **только `bot.py` локально**, нужен прокси, который пропускает **HTTPS** до `api.telegram.org`:

- Поднять на VPS **SOCKS5** (например `microsocks`, `3proxy`, Dante) или **HTTP CONNECT**, открыть порт в firewall, задать логин/пароль.
- В `.env` на ПК:  
  `PROXY_URL=socks5://user:pass@62.60.186.183:ПОРТ`  
  или `http://...` для HTTP-прокси.

**Не путать** с MTProto на `1443`: для `PROXY_URL` нужен отдельный сервис SOCKS5/HTTP.

---

## Решение 3: VPN на ПК

Полноценный VPN (WireGuard/OpenVPN и т.д.), при котором маршрут до `api.telegram.org` идёт через незаблокированный канал. Тогда `bot.py` можно запускать без `PROXY_URL` (или с корпоративным прокси, если требуется).

---

## VPS

| Параметр | Значение |
|----------|----------|
| Публичный IPv4 | `62.60.186.183` |
| SSH | `ssh root@62.60.186.183` |
| Каталог `bot_server.py` | `/opt/app/bot-cashflow` (см. [deploy/README.md](../deploy/README.md)) |

На этом же сервере может быть запущен **MTProto-прокси** (например порт `1443` и секрет в клиенте) — он полезен для **приложения Telegram**, но **не заменяет** SOCKS5/HTTP для Python-бота и не является `RECEIVER_URL` для split-режима.

---

## Краткая схема выбора

```mermaid
flowchart LR
  subgraph pc [ПК — файлы .md]
    R[receiver.py]
    B[bot.py]
  end
  subgraph vps [VPS 62.60.186.183]
    S[bot_server.py]
    P[SOCKS5 optional]
  end
  TG[Telegram Bot API]
  T[tunnel bore/ngrok]
  S --> TG
  S --> T
  T --> R
  B --> P
  P --> TG
```

- **Файлы только на ПК + блокировка API на ПК:** `bot_server` на VPS → туннель → `receiver` на ПК.
- **Только bot.py на ПК:** SOCKS5/HTTP на VPS или VPN на ПК.

---

## Переменные окружения (напоминание)

| Режим | Где что задаётся |
|-------|------------------|
| Локальный `bot.py` + обход | `PROXY_URL` в `.env` на ПК |
| `bot_server.py` на VPS | `RECEIVER_URL`, `RECEIVER_SECRET`; при необходимости `PROXY_URL` на VPS (если сам VPS не достучится до Telegram) |
| `receiver.py` на ПК | `VAULT_PATH`, `USER_TIMEZONE`, `RECEIVER_SECRET`, `RECEIVER_PORT` |
