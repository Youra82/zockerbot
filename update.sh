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
# Neue Einträge aus dem Repo ergänzen (z. B. "echtgeld"), eigene Werte bleiben unverändert
git show origin/main:settings.json > settings.repo.json
python3 - <<'PY'
import json
own = json.load(open("settings.json", encoding="utf-8"))
repo = json.load(open("settings.repo.json", encoding="utf-8"))
neu = [k for k in repo if k not in own]
for k in neu:
    own[k] = repo[k]
if neu:
    json.dump(own, open("settings.json", "w", encoding="utf-8"), indent=4, ensure_ascii=False)
    print("settings.json ergänzt:", ", ".join(neu))
PY
rm -f settings.repo.json
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
chmod +x *.sh
.venv/bin/pip install -r requirements.txt --quiet
./stop.sh && ./start.sh
echo "Update abgeschlossen, Bot neu gestartet."
