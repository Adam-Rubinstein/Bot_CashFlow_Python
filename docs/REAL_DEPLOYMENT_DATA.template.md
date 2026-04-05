# REAL DEPLOYMENT DATA — шаблон

Скопируйте в `REAL_DEPLOYMENT_DATA.local.md` (файл в `.gitignore`) и подставьте значения. Секрет для `RECEIVER_SECRET` сгенерируйте, например:

`python -c "import secrets; print(secrets.token_urlsafe(48))"`

## Split-режим (bot_server на VPS, receiver на ПК)

| Где | Переменная | Описание |
|-----|------------|----------|
| ПК | `RECEIVER_SECRET` | Общий с VPS, ≥24 символов |
| VPS | `RECEIVER_SECRET` | Тот же, что на ПК |
| VPS | `RECEIVER_URL` | URL туннеля до приёмника (лучше HTTPS) |

Подробности: [RECEIVER_SECURITY.md](./RECEIVER_SECURITY.md), [deploy/README.md](../deploy/README.md).
