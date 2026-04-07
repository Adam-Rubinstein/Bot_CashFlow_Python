# Windows: обратный SSH-туннель (VPS → ПК) для split-режима

В проде `bot_server.py` на VPS шлёт POST на **`RECEIVER_URL`**. Вариант без bore/ngrok: на **VPS** в `.env` задаётся:

```env
RECEIVER_URL=http://127.0.0.1:18080
```

На сервере `127.0.0.1:18080` слушает **sshd** как часть **обратного SSH** с вашего ПК: трафик пробрасывается на **`receiver.py`** на `127.0.0.1:8080`. Общая схема: [MemoryBank.md](./MemoryBank.md) (раздел «Автоматизированный split»).

## Скрипт `scripts/start_split_tunnel.ps1`

Поднимает в фоне:

1. **`receiver.py`** из venv проекта (`.venv\Scripts\python.exe`).
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

Требуется **SSH-ключ к VPS без пароля** (тот же хост, что в скрипте: `root@62.60.186.183`).

## Автозапуск и watchdog на Windows

Реализация вынесена в соседний репозиторий **TaskManager** (общий автозапуск локальных сервисов на ПК):

- `TaskManager/scripts/windows_autostart/start_local_bot_services.ps1` — при входе в Windows поднимает Obsidian-bridge и вызывает **этот** `start_split_tunnel.ps1`.
- Задача планировщика **`TaskManager-CashFlow-Watchdog`** (каждые **2** минуты) запускает **`WatchdogCashFlow.vbs`** → скрытый PowerShell → `start_split_tunnel.ps1` **без** `-Force` (только ensure: поднять туннель, если упал).

Установка задач: из каталога TaskManager выполнить `install_autostart.ps1` (см. `TaskManager/docs/MemoryBank.md`, раздел про Windows).

Путь к `start_split_tunnel.ps1` в **`WatchdogCashFlow.vbs`** зашит как  
`D:\Desktop\Projects\Bot_CashFlow_Python\scripts\start_split_tunnel.ps1` — при переносе папки проекта отредактируйте `.vbs`.

Ранее использовался автозапуск через `HKCU\...\Run` (`BotCashFlowSplitTunnel`); актуальная схема — **планировщик + watchdog** выше.

## Устранение неполадок

### В Telegram: «Ошибка связи с ПК: Server disconnected without sending a response»

Источник — `httpx` на VPS: не дошёл ответ от `receiver` при POST на `RECEIVER_URL`.

1. **ПК:** убедиться, что туннель поднят. Проверка вручную: `.\scripts\start_split_tunnel.ps1 -Force`.
2. **VPS:** сервис бота активен: `systemctl status cashflow-bot-server`.
3. **VPS:** до приёмника на ПК есть маршрут через туннель (порт 18080 на localhost):

   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18080/
   ```

   Код **405** для GET к `POST /` — нормально (FastAPI отвечает, что метод не подходит); главное — не `000` / connection refused.

4. Совпадение **`RECEIVER_SECRET`** в `.env` на VPS и в `.env` на ПК для `receiver.py` (и длина ≥ 24 символов).

### Туннель периодически отваливается

Сеть, сон ПК, обрыв SSH — подключите **watchdog** (TaskManager) или ставьте в Планировщик задачу с периодическим вызовом `start_split_tunnel.ps1` без `-Force`.

## См. также

- [deploy/README.md](../deploy/README.md) — `RECEIVER_URL` на VPS, systemd `cashflow-bot-server`.
- [RECEIVER_SECURITY.md](./RECEIVER_SECURITY.md) — HMAC, nonce, защита канала.
- [MemoryBank.md](./MemoryBank.md) — раздел «Автоматизированный split» и журнал.
