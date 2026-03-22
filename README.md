# Bot CashFlow Python

Telegram бот для отслеживания расходов и доходов с автоматическим сохранением в Markdown файлы.

## ⚠️ Warning

**This project is licensed under LGPL v3.0**

This means:

- ✅ You can use, modify, and distribute this code
- ✅ You can use it in commercial projects
- ❌ You must share modifications if you distribute them
- ❌ You cannot make it proprietary

See [LICENSE](LICENSE) for details.

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
   - `PROXY_URL` — **optional**. If Telegram is blocked or unstable on your network, set the same kind of proxy you use in Telegram Desktop (SOCKS5 or HTTP), e.g. `socks5://user:pass@host:1080`. Leave empty to connect directly.

4. Run the bot:

   ```bash
   python bot.py
   ```

   **Windows (optional):** copy [bot.example.bat](bot.example.bat) to `bot.bat` and double-click it to start the bot in the background with `pythonw` from `.venv`. `bot.bat` is gitignored so you can keep a local launcher.

### Proxy note

The Telegram app’s proxy settings apply only to that app. This Python process uses the network stack of your OS; to route the bot through a proxy you must set `PROXY_URL` in `.env`. For SOCKS5, `httpx[socks]` is included via `requirements.txt`.

## License

GNU Lesser General Public License v3.0 — see [LICENSE](LICENSE).
