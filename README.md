# Bot CashFlow Python

Telegram бот для отслеживания расходов и доходов с автоматическим сохранением в Markdown файлы.

**Репозиторий:** [github.com/Adam-Rubinstein/Bot_CashFlow_Python](https://github.com/Adam-Rubinstein/Bot_CashFlow_Python)

## ⚠️ Warning

**This project is licensed under LGPL v3.0**

This means:

- ✅ You can use, modify, and distribute this code
- ✅ You can use it in commercial projects
- ❌ You must share modifications if you distribute them
- ❌ You cannot make it proprietary

See [LICENSE](LICENSE) for details.

## Документация

- **[docs/MemoryBank.md](docs/MemoryBank.md)** — контекст для разработки и агентов: архитектура, режимы (`bot.py` / `bot_server` + `receiver`), переменные окружения, деплой на VPS, журнал изменений.
- **[deploy/README.md](deploy/README.md)** — установка и обновление `bot_server.py` на VPS (`62.60.186.183`), systemd `cashflow-bot-server`.
- **[docs/TELEGRAM_BLOCKING_AND_PROXY.md](docs/TELEGRAM_BLOCKING_AND_PROXY.md)** — если Telegram / Bot API недоступны с ПК: почему MTProto из приложения не подходит для бота, split-режим (VPS + туннель + `receiver`), SOCKS5/VPN.
- **[docs/RECEIVER_SECURITY.md](docs/RECEIVER_SECURITY.md)** — безопасность туннеля: HMAC, nonce, HTTPS, секрет, localhost.

## Features

- 📝 Send expenses and income via Telegram
- 💾 Auto-save to organized Markdown files
- 📊 Format: `Product; Source; Amount` (example: `Еда; Лента; 1755.5`)
- 📁 Files organized by year and month
- 🔐 Uses environment variables for sensitive data (`.env`)
- 🌐 Optional HTTP/SOCKS proxy for Bot API (useful when `api.telegram.org` is unreachable from your network)

## Installation

1. Clone the repository and open the project folder.
2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Copy the environment template and fill in your values:

   ```bash
   copy .env.example .env
   ```

   - `TELEGRAM_TOKEN` — token from [@BotFather](https://t.me/BotFather).
   - `VAULT_PATH` — absolute path to the folder where Markdown files should be written (e.g. your Obsidian vault or a subfolder).
   - `USER_TIMEZONE` — easiest: fixed offset from UTC, e.g. `UTC+3`, `UTC+5`, `UTC-5`, or with minutes `UTC+03:30`. You can also use an IANA name such as `Europe/Moscow`. Telegram sends message time in UTC; the bot converts it for the daily filename and note title. Use the **same** value on a VPS as on your PC. If unset or invalid, the bot falls back to **`UTC+3`** (MSK offset, no DST).
   - `ALLOWED_USER_IDS` — **optional**. Comma/space/semicolon-separated Telegram user ids allowed to use the bot (e.g. `123456789` or `111,222`). If empty or unset, **any** user can send messages. If set, other users are ignored (no reply).
   - `PROXY_URL` — **optional**. If Telegram is blocked or unstable on your network, set the same kind of proxy you use in Telegram Desktop (SOCKS5 or HTTP), e.g. `socks5://user:pass@host:1080`. Leave empty to connect directly.

4. Run the bot:

   ```bash
   python bot.py
   ```

   **Windows (optional):** copy [bot.example.bat](bot.example.bat) to `bot.bat` and double-click it to start the bot in the background with `pythonw` from `.venv`. `bot.bat` is gitignored so you can keep a local launcher.

5. Run tests (optional):

   ```bash
   pytest
   ```

### Proxy note

The Telegram app’s proxy settings apply only to that app. This Python process uses the network stack of your OS; to route the bot through a proxy you must set `PROXY_URL` in `.env`. For SOCKS5, `httpx[socks]` is included via `requirements.txt`.

### Message date, timezone, and offline backlog

- Each write uses the **Telegram message send time** (UTC from the API), converted with **`USER_TIMEZONE`** — not the server’s local clock, so a VPS and your PC agree on the calendar day when you use the same `USER_TIMEZONE`.
- While the bot is stopped, the Bot API only keeps a **limited** queue of pending updates (on the order of **24 hours**). Older messages are not delivered by the standard bot API; you cannot recover an arbitrary backlog beyond that.

### Split setup: Telegram on a VPS, vault on your PC

If the Telegram bot runs on a server but you want Markdown only on your computer:

1. On the **PC**: set `VAULT_PATH`, `USER_TIMEZONE`, `RECEIVER_SECRET`, `RECEIVER_PORT` (optional), run `python receiver.py` (expose it to the internet, e.g. [bore](https://github.com/ekzhang/bore) tunnel — see `bot.example.bat`).
2. On the **VPS**: set `TELEGRAM_TOKEN`, `RECEIVER_URL` (tunnel URL to the receiver), same `RECEIVER_SECRET`, optional `ALLOWED_USER_IDS`; run `python bot_server.py` (or install via systemd — [deploy/README.md](deploy/README.md)).

Details: [docs/MemoryBank.md](docs/MemoryBank.md).

### Running on a VPS and using Obsidian on your PC

The bot always writes under `VAULT_PATH` on **the machine where `bot.py` runs** (or where `receiver.py` runs in the split setup). It does not push files to another computer by itself.

If you host the bot on a server, set `VAULT_PATH` to an absolute path on that server (Linux example: `/home/you/vault-cashflow`). To get the same Markdown into a local Obsidian vault, use a **separate** sync or shared storage layer, for example:

- **Syncthing** — pair a folder on the VPS with a folder inside your vault on the PC.
- **Git** — commit/push from the server or use the [Obsidian Git](https://github.com/denolehov/obsidian-git) workflow with a remote both sides use.
- **Cloud** (Dropbox, Google Drive, Nextcloud, etc.) — if the vault already lives in synced storage, install the same client on the VPS or point `VAULT_PATH` at a mounted/synced directory.
- **`rsync` over SSH** or cron — workable but less convenient for a constantly edited vault.

Less common: **SMB/NFS** mount so the bot writes to a network path (only if latency and reliability are acceptable).

On a VPS outside networks that block Telegram, you can often **omit `PROXY_URL`**; verify with `curl https://api.telegram.org` on the server. Set **`USER_TIMEZONE`** to the same value as on your PC (e.g. `UTC+3`) so daily filenames match your calendar. Run the bot with **systemd**, **Docker**, or **screen/tmux** as you prefer. Keep `.env` on the server private (file permissions, no commits).

## License

GNU Lesser General Public License v3.0 — see [LICENSE](LICENSE).
