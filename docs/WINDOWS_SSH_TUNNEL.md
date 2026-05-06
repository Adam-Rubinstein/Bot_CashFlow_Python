# Windows: обратный SSH-туннель (VPS → ПК) для split-режима

В проде `bot_server.py` на VPS шлёт POST на **`RECEIVER_URL`**. Вариант без bore/ngrok: на **VPS** в `.env` задаётся:

```env
RECEIVER_URL=http://127.0.0.1:18080
```

На сервере `127.0.0.1:18080` слушает **sshd** как часть **обратного SSH** с вашего ПК: трафик пробрасывается на **`receiver.py`** на `127.0.0.1:8080`. Общая схема: [MemoryBank.md](./MemoryBank.md) (раздел «Автоматизированный split»).

## Скрипт `scripts/start_split_tunnel.ps1`

Поднимает в фоне:

1. **`receiver.py`** из venv проекта (`.venv\Scripts\python.exe`). Если venv отсутствует — автоматически ищет `py.exe`-лаунчер или системный `Python313/python.exe` (аналогично TaskManager). При полном отсутствии Python бросает исключение.
2. **`ssh -R 127.0.0.1:18080:127.0.0.1:8080 root@<VPS>`** без отдельного окна (`-WindowStyle Hidden`).

### Параметры

| Параметр | Назначение |
|----------|------------|
| *(по умолчанию)* | **Ensure:** если уже есть процессы `receiver.py` (для этого репозитория) **и** `ssh` с пробросом `18080→8080`, **и** TCP-подключение к `127.0.0.1:8080` успешно — скрипт **ничего не перезапускает**. Иначе выполняется полный цикл: остановить старые процессы и поднять заново. |
| **`-Force`** | Всегда убить старые `receiver`/`ssh` для этого туннеля и поднять снова (ручной полный рестарт). |

Проверка порта **8080** нужна, чтобы не «залипать» в состоянии «процессы есть, а uvicorn не слушает» — в этом случае ensure-режим выполнит рестарт.

### Ручной запуск (PowerShell)

```powershell
cd D:\Desktop\Projects\Bot_CashFlow_Python
.\scripts\start_split_tunnel.ps1
```

Полный перезапуск:

```powershell
.\scripts\start_split_tunnel.ps1 -Force
```

По умолчанию нужен **SSH-ключ к VPS без пароля** (тот же хост: `root@62.60.186.183`). Если ключа нет: задайте **`DEPLOY_SSH_PASSWORD`** в `.env` этого репозитория (или в переменной окружения) и установите **PuTTY**, чтобы в `PATH` был **`plink.exe`** — скрипт поднимет туннель через plink (штатный `ssh.exe` на Windows не принимает пароль неинтерактивно). В **`-batch`** plink не спросит ключ хоста: в скрипте задаётся **`-hostkey`** с отпечатком `SHA256:…` (формат PuTTY 4.19.3). При смене ключа на сервере задайте **`CASHFLOW_PLINK_HOSTKEY`** в окружении. У **plink нет** опции `-keepalive` как у OpenSSH — она не используется. Тот же пароль можно держать в `TaskManager/.env` для Obsidian bridge — там используется **paramiko** (см. `TaskManager/requirements.txt`).

## Автозапуск и watchdog на Windows

Реализация вынесена в соседний репозиторий **TaskManager** (общий автозапуск локальных сервисов на ПК):

- `TaskManager/scripts/windows_autostart/start_local_bot_services.ps1` — при входе в Windows поднимает Obsidian-bridge и вызывает **этот** `start_split_tunnel.ps1`.
- Задача планировщика **`TaskManager-CashFlow-Watchdog`** (каждые **2** минуты) запускает **`WatchdogCashFlow.vbs`** → скрытый PowerShell → `start_split_tunnel.ps1` **без** `-Force` (только ensure: поднять туннель, если упал).

Установка задач: из каталога TaskManager выполнить `install_autostart.ps1` (см. `TaskManager/docs/MemoryBank.md`, раздел про Windows).

Путь к `start_split_tunnel.ps1` в **`WatchdogCashFlow.vbs`** зашит как  
`D:\Desktop\Projects\Bot_CashFlow_Python\scripts\start_split_tunnel.ps1` — при переносе папки проекта отредактируйте `.vbs`.

Ранее использовался автозапуск через `HKCU\...\Run` (`BotCashFlowSplitTunnel`); актуальная схема — **планировщик + watchdog** выше.

## Устранение неполадок

### В Telegram: «Ошибка связи с ПК: …» (`All connection attempts failed`, `Server disconnected…`)

Источник — `httpx` на VPS: **нет TCP до** `RECEIVER_URL`, **нет ответа** от `receiver`, либо **обрыв до конца HTTP** (текст вроде `Server disconnected without sending a response` — нестабильный канал / keep-alive через SSH). В `bot_server.py` для этого отключено переиспользование TCP к приёмнику и добавлены короткие повторы. Чаще всего при полном отказе **упал обратный SSH** (на VPS `127.0.0.1:18080` не слушает). **Конспект уже исправленных ловушек** (plink `-hostkey`, без ложного `-keepalive`, деплой после правок `bot_server`): [TROUBLESHOOTING_SPLIT.md](./TROUBLESHOOTING_SPLIT.md).

1. **ПК:** поднять туннель заново: `.\scripts\start_split_tunnel.ps1 -Force`.
2. **VPS:** `systemctl status cashflow-bot-server`.
3. **Проверка с VPS** (должен быть код **403** на POST без подписи — приёмник жив):

   ```bash
   curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:18080/ -H "Content-Type: application/json" -d "{}"
   ```

   **`000`** или пусто — туннеля нет, с ПК снова запустить `start_split_tunnel.ps1`.

4. Совпадение **`RECEIVER_SECRET`** в `.env` на VPS и на ПК (≥ 24 символов).

### Watchdog в этом репозитории

Скрипт [scripts/watch_split_tunnel.ps1](../scripts/watch_split_tunnel.ps1): проверяет **локальный** `:8080` и с VPS **POST → 403**; при сбое вызывает `start_split_tunnel.ps1 -Force`.

Планировщик (каждые 5 минут, от пользователя). **Рекомендуется** запуск через VBS — окно не «моргает» даже при старте задачи:

```text
schtasks /Create /F /TN "BotCashFlowTunnelWatch" /TR "wscript.exe //B D:\Desktop\Projects\Bot_CashFlow_Python\scripts\run_watch_tunnel_hidden.vbs" /SC MINUTE /MO 5 /RL LIMITED
```

Если путь к репозиторию содержит пробелы, возьмите `/TR` в кавычки и экранируйте внутренние кавычки под вашу оболочку (в PowerShell удобнее обернуть аргумент в одинарные кавычки целиком).

Скрипт [scripts/run_watch_tunnel_hidden.vbs](../scripts/run_watch_tunnel_hidden.vbs) вызывает PowerShell с `-WindowStyle Hidden` и `WshShell.Run(..., 0, True)` (стиль окна 0 = скрытый, ожидание завершения).

Альтернатива без VBS (если окно всё ещё мелькает — см. ниже):

```text
schtasks /Create /F /TN "BotCashFlowTunnelWatch" /TR "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File D:\Desktop\Projects\Bot_CashFlow_Python\scripts\watch_split_tunnel.ps1" /SC MINUTE /MO 5 /RL LIMITED
```

**«Моргает» консоль раз в 5 минут:** даже при `-WindowStyle Hidden` у задачи дочерний **`ssh.exe`**, вызванный из PowerShell как `& ssh ...`, получает консоль (`conhost`) и на секунду показывается окно. В [scripts/watch_split_tunnel.ps1](../scripts/watch_split_tunnel.ps1) проверка на VPS выполняется через `System.Diagnostics.ProcessStartInfo` с **`CreateNoWindow = $true`** и перенаправлением stdout — без отдельного окна. После обновления скрипта пересоздайте задачу при необходимости; при старом поведении дополнительно используйте строку с **`run_watch_tunnel_hidden.vbs`** выше.

Краткая шпаргалка: [TROUBLESHOOTING_SPLIT.md](./TROUBLESHOOTING_SPLIT.md).

### Туннель периодически отваливается

Сон ПК, сеть, обрыв SSH — используйте **watch** выше или аналог в **TaskManager** (`TaskManager-CashFlow-Watchdog`, см. ниже), либо периодический вызов `start_split_tunnel.ps1` **без** `-Force` (ensure).

## См. также

- [deploy/README.md](../deploy/README.md) — `RECEIVER_URL` на VPS, systemd `cashflow-bot-server`.
- [RECEIVER_SECURITY.md](./RECEIVER_SECURITY.md) — HMAC, nonce, защита канала.
- [MemoryBank.md](./MemoryBank.md) — раздел «Автоматизированный split» и журнал.
