# «Ошибка связи с ПК» — кратко

Полная инструкция: **[WINDOWS_SSH_TUNNEL.md](./WINDOWS_SSH_TUNNEL.md)** (раздел «Устранение неполадок», скрипт `watch_split_tunnel.ps1`, `schtasks`).

Быстрый фикс на Windows:

```powershell
.\scripts\start_split_tunnel.ps1 -Force
```

Если **мигает чёрное окно** раз в несколько минут: это watchdog; в `watch_split_tunnel.ps1` вызов `ssh` без консоли + задача через `run_watch_tunnel_hidden.vbs` — см. [WINDOWS_SSH_TUNNEL.md](./WINDOWS_SSH_TUNNEL.md) (раздел про планировщик).

---

## Что уже чинили (2026-05) — не повторять ошибки

### 1. PuTTY `plink` в `-batch` без ключа хоста

**Симптом:** туннеля нет, в логе plink: *Cannot confirm a host key in batch mode*. Процесс **сразу завершается**, на VPS `curl` на `127.0.0.1:18080` даёт **000**.

**Исправление в коде:** в `start_split_tunnel.ps1` и `watch_split_tunnel.ps1` передаётся **`-hostkey`** в формате PuTTY: `SHA256:` + 43 символа. При **смене host key на сервере** задать **`CASHFLOW_PLINK_HOSTKEY`** (и обновить значение в скрипте/доке при необходимости).

### 2. Ложный флаг `-keepalive` у plink

**Симптом:** скрипт пишет «туннель запущен», но процесса **plink** с `-R …18080…` нет (или он мгновенно падает). У **OpenSSH ssh** есть `ServerAliveInterval`; у **plink** в справке **нет** `-keepalive` — передача этих токенов ломала командную строку / приводила к немедленному выходу.

**Исправление:** для ветки **plink** флаг **не используется**; keep-alive для SSH-ключа по-прежнему в ветке `ssh`.

### 3. `Server disconnected without sending a response` (httpx на VPS)

**Симптом:** не то же самое, что «все попытки соединения провалились»: до ПК достучались, но **ответ HTTP не дошёл** (обрыв на пробросе, плохой keep-alive клиента).

**Исправление в коде:** в **`bot_server.py`** — **`Connection: close`**, `max_keepalive_connections=0`, увеличенный таймаут, до **3** повторов при **`httpx.RequestError`** с **новым nonce** (иначе receiver отклонит повтор по nonce).

**Важно:** после изменений **`bot_server.py`** обязателен **деплой на VPS** (`git pull`, `systemctl restart cashflow-bot-server`), иначе пользователь продолжит видеть старую ошибку.

### 4. Диагностика за 30 секунд

| Проверка | Ожидание |
|----------|----------|
| На ПК: процесс **receiver.py** и **plink**/ssh с **18080** в командной строке | Оба живы |
| На ПК: TCP **127.0.0.1:8080** | Принимает соединение |
| На VPS: `curl -w '%{http_code}' -o /dev/null -X POST http://127.0.0.1:18080/ …` | **403** без подписи — норма |
| `systemctl status cashflow-bot-server` | **active** |

Если **403** есть, а в Telegram всё ещё ошибка — смотреть версию **`bot_server.py`** на сервере (деплой) и логи `journalctl -u cashflow-bot-server`.
