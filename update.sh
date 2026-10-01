#!/bin/bash
# Sicheres Update: data_dryrun/ (Kontostand, Gedaechtnis) und secret.json sind nicht versioniert
# und werden von 'git reset --hard' nicht angefasst. settings.json wird gesichert und zurueckgespielt.
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
