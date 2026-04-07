# Деплой Bot CashFlow (`bot_server.py` на VPS)

Речь о режиме **split**: процесс на сервере только опрашивает Telegram и шлёт записи на `RECEIVER_URL` (приёмник `receiver.py` на ПК за туннелем). Файлы `.md` на VPS **не создаются**.

## Production VPS

- **IP:** `62.60.186.183`
- **SSH:** `ssh root@62.60.186.183`
- **Код на сервере:** `/opt/app/bot-cashflow`
- **Сервис:** `cashflow-bot-server`
- **Перезапуск после правок:** `systemctl restart cashflow-bot-server`
- **Логи:** `journalctl -u cashflow-bot-server -f`

На том же хосте могут быть другие каталоги под `/opt/app` и отдельные сервисы — не смешивайте рабочие каталоги и `.env`.

---

## Рекомендованный flow

Папка приложения: `/opt/app/bot-cashflow`, unit systemd: `cashflow-bot-server`.

1. Подключение:

```bash
ssh root@62.60.186.183
```

2. Установка:

```bash
apt update && apt install -y python3 python3-venv python3-pip git
mkdir -p /opt/app/bot-cashflow
cd /opt/app/bot-cashflow
git clone https://github.com/Adam-Rubinstein/Bot_CashFlow_Python.git .
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Создайте `/opt/app/bot-cashflow/.env` (без `VAULT_PATH` — vault только на ПК):

```env
TELEGRAM_TOKEN=<токен от @BotFather>
# Предпочтительно HTTPS туннеля (ngrok, cloudflared и т.д.); см. docs/RECEIVER_SECURITY.md
RECEIVER_URL=https://xxxx.ngrok-free.app
# Тот же секрет, что на ПК в receiver; не короче 24 символов
RECEIVER_SECRET=<сгенерируйте: python -c "import secrets; print(secrets.token_urlsafe(32))">
# ALLOWED_USER_IDS=123456789
# PROXY_URL=socks5://user:pass@host:1080
```

`USER_TIMEZONE` задаётся на **ПК** в `receiver.py`, не в этом `.env`.

Канал до приёмника защищён HMAC по телу запроса и nonce — см. [docs/RECEIVER_SECURITY.md](../docs/RECEIVER_SECURITY.md).

4. Сервис:

```bash
cp deploy/cashflow-bot-server.service.example /etc/systemd/system/cashflow-bot-server.service
systemctl daemon-reload
systemctl enable --now cashflow-bot-server
```

5. Проверка:

```bash
systemctl status cashflow-bot-server
journalctl -u cashflow-bot-server -f
```

## Обновление

```bash
cd /opt/app/bot-cashflow
git pull
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart cashflow-bot-server
```

## Обратный SSH с ПК (без публичного URL / bore)

Если `receiver.py` крутится на **вашем ПК** (Windows), а на VPS нужен доступ к `127.0.0.1` на стороне сервера, используйте в `.env` на VPS:

```env
RECEIVER_URL=http://127.0.0.1:18080
```

На ПК поднимается обратный туннель `ssh -R …` и процесс `receiver` — см. **[docs/WINDOWS_SSH_TUNNEL.md](../docs/WINDOWS_SSH_TUNNEL.md)** (`start_split_tunnel.ps1`, ensure/`-Force`, автозапуск через репозиторий TaskManager).

## Безопасность

- Не коммитьте `.env` и токены.
- Публичный IP прод-сервера указан выше для операций; при смене хоста обновите `deploy/README.md` и `docs/MemoryBank.md`.
- Полный чеклист: [docs/RECEIVER_SECURITY.md](../docs/RECEIVER_SECURITY.md) — HTTPS туннель, секрет ≥24 символов, `ALLOWED_USER_IDS`.
- Long polling; webhook в коде не настроен.
