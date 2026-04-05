#!/bin/bash
# Однократный деплой на VPS (вызывается с ПК через ssh).
set -eu
REPO="/opt/app/bot-cashflow"
mkdir -p "$REPO"
cd "$REPO"
if [[ ! -d .git ]]; then
  git clone https://github.com/Adam-Rubinstein/Bot_CashFlow_Python.git .
else
  git fetch origin
  git reset --hard origin/master
fi
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
cp -f deploy/cashflow-bot-server.service.example /etc/systemd/system/cashflow-bot-server.service
systemctl daemon-reload
systemctl enable cashflow-bot-server
echo "Bootstrap done. Set .env and restart: systemctl restart cashflow-bot-server"
