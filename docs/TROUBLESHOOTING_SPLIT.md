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

**Исправление в коде:** в **`bot_server.py`** — **`Connection: close`**, `max_keepalive_connections=0`, увеличенный таймаут, до **8** повторов при **`httpx.RequestError`** (паузы **2, 4, 8, 16, 32, 64, 128 с**, новый **nonce** на каждую попытку). Ошибка в Telegram только после всех попыток.

**Важно:** после изменений **`bot_server.py`** обязателен **деплой на VPS** (`git pull`, `systemctl restart cashflow-bot-server`), иначе пользователь продолжит видеть старую ошибку.

### 3a. `400 Bad Request` для `http://127.0.0.1:18080/`

**Симптом:** в Telegram «Ошибка связи с ПК: Client error '400 Bad Request'…». Туннель и HMAC **в порядке** (иначе был бы 403 или `All connection attempts failed`): приёмник **отклонил** тело/перезапись дневного `.md`.

**Типичная причина:** в уже существующей строке дня сумма с nbsp / невидимыми символами (например `14\xa0521,5\u202c`) — старый `float(...)` в `build_table` падал → 400 на **любую** новую запись за этот день.

**Исправление:** в **`receiver.py`** (и `bot.py`) — `_parse_amount_str`; после правки перезапустить приёмник (`start_split_tunnel.ps1 -Force`). Смотреть лог receiver: `Некорректное тело запроса: …`.

### 3b. `All connection attempts failed` при живом боте в Telegram

**Симптом:** бот отвечает (значит **VPS и `bot_server` живы**), но пишет `All connection attempts failed` — на VPS нет TCP к `127.0.0.1:18080` (обратный туннель с ПК мёртв).

**Частая причина (2026-09):** с ПК **не открывается TCP на `VPS:22`** (fail2ban / firewall провайдера / бан IP после частых plink). Интернет при этом работает (`8.8.8.8:443` OK), а `84.22.149.170:22` — timeout. Старый guardian при этом каждые 20 с делал `-Force` и **усиливал бан**.

**Что сделано в скриптах:** `Get-SplitTunnelHealth` различает `Healthy` / `VpsUnreachable` / `TunnelBroken`; при `VpsUnreachable` **не** вызывается `-Force` (backoff до 5 мин). У plink keepalive через сессию PuTTY `BotCashFlowReverse` (`PingInterval=30`). Лог: `logs/split_tunnel_guardian.log`.

**Что сделать вручную, если `VpsUnreachable`:**
1. Панель VPS / `fail2ban-client set sshd unbanip <ваш_IP>` / security group — разрешить SSH с текущего IP.
2. На ПК: `.\scripts\start_split_tunnel.ps1 -Force`, затем probe 403 с VPS.
3. Включить задачу **`BotCashFlowTunnelWatch`**, если она Disabled: `schtasks /Change /TN BotCashFlowTunnelWatch /ENABLE`.

### 4. Диагностика за 30 секунд

| Проверка | Ожидание |
|----------|----------|
| На ПК: процесс **receiver.py** и **plink**/ssh с **18080** в командной строке | Оба живы |
| На ПК: TCP **127.0.0.1:8080** | Принимает соединение |
| На VPS: `curl -w '%{http_code}' -o /dev/null -X POST http://127.0.0.1:18080/ …` | **403** без подписи — норма |
| `systemctl status cashflow-bot-server` | **active** |

Если **403** есть, а в Telegram всё ещё ошибка — смотреть версию **`bot_server.py`** на сервере (деплой) и логи `journalctl -u cashflow-bot-server`.

### 5. Если процесс watchdog убивают вручную

В этом репозитории есть постоянный guardian `scripts/keep_split_tunnel_alive.ps1`, запускаемый скрыто через `scripts/run_keep_split_tunnel_hidden.vbs` и задачу `BotCashFlowTunnelGuardian`. Он использует timeout-safe health probe и снова поднимает `start_split_tunnel.ps1 -Force`, если reverse SSH или локальный `receiver` перестал отвечать.
