# Безопасность канала VPS → ПК (receiver)

## Угрозы

| Риск | Мера в коде |
|------|-------------|
| Подслушивание туннеля (HTTP без TLS) | Использовать **HTTPS** у туннеля ([ngrok](https://ngrok.com/), [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/), платный bore с TLS и т.д.); в `RECEIVER_URL` указывать `https://...`. Клиент `httpx` проверяет сертификат по умолчанию. |
| Угадывание URL туннеля и подделка запросов | **HMAC-SHA256** по телу запроса (`X-Body-Signature: v1=<hex>`), секрет **не** передаётся в каждом запросе (в отличие от старого `X-Secret`). |
| Слабый секрет | Минимум **24 символа**; лучше 32+ случайных символа. Генерация: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Одинаковый секрет в `.env` на VPS (`bot_server`) и на ПК (`receiver`). |
| Повтор старого запроса (replay) | Одноразовый **`nonce`** (UUID) + хранение на приёмнике; повтор того же nonce → `403`. Окно **event_ts** относительно часов приёмника (`RECEIVER_MAX_SKEW_SEC`, по умолчанию 600 с). |
| Приёмник торчит в локальную сеть | По умолчанию **`RECEIVER_HOST=127.0.0.1`** — слушаем только localhost; туннель (bore/ngrok) подключается к локальному порту. Для приёма из LAN задайте `RECEIVER_HOST=0.0.0.0` осознанно. |

## Режим разработки

`RECEIVER_INSECURE_DEV=1` на ПК отключает HMAC и проверку nonce (только для локальных тестов). В проде не используйте.

## Формат запроса (реализует `bot_server.py`)

- Тело: канонический JSON UTF-8 (`sort_keys`, без лишних пробелов).
- Поля: `entries`, `event_ts`, `nonce`.
- Заголовок: `X-Body-Signature: v1=` + HMAC-SHA256(secret, raw_body_bytes).

Подробности реализации: модуль `security.py`, обработчик — `receiver.py`.
