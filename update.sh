#!/bin/bash
# Sicheres Update: data/ (Zustand, Trades), logs/ und secret.json sind nicht versioniert.
# settings.json wird gesichert und nach dem Update zurueckgespielt (eigene Einstellungen bleiben).
set -e
cd "$(dirname "$0")"
echo "--- Sicheres Update (zockerbot) ---"
cp settings.json settings.json.bak
git fetch origin
git reset --hard origin/main
cp settings.json.bak settings.json && rm settings.json.bak
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
chmod +x *.sh
.venv/bin/pip install -r requirements.txt --quiet
./stop.sh && ./start.sh
echo "Update abgeschlossen, Bot neu gestartet."
