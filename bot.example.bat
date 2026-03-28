@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo No venv at .venv\Scripts\pythonw.exe
  echo Run: python -m venv .venv
  echo Then: .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

rem Запускаем bore в фоне (свёрнутое окно)
start /min "bore-tunnel" cmd /c "D:\Desktop\bore.exe local 8080 --to bore.pub"

rem Ждём 2 секунды пока bore подключится
timeout /t 2 /nobreak >nul

rem Запускаем receiver в фоне
start "" ".venv\Scripts\pythonw.exe" receiver.py

exit /b 0
