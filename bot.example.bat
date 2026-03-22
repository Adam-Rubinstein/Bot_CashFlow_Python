@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo No venv at .venv\Scripts\pythonw.exe
  echo Run: python -m venv .venv
  echo Then: .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

rem Use .venv (system pythonw has no project packages).
rem Do not use start /B — a background job in this console can die when the window closes on exit.
start "" ".venv\Scripts\pythonw.exe" bot.py
exit /b 0
