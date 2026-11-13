#!/bin/bash
# zockerbot - Installation auf Linux (MiniPC/VPS)
set -e
cd "$(dirname "$0")"
echo "=== zockerbot Installation ==="
python3 -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet
mkdir -p data logs
chmod +x *.sh
[ -f secret.json ] || { cp secret.json.template secret.json; echo "secret.json angelegt - bitte Bitget-Schluessel und Telegram eintragen."; }
echo ""
echo "Naechste Schritte:"
echo "  1. secret.json ausfuellen (eigenes Bitget-Unterkonto, Positionsmodus 'beidseitig'/Hedge)"
echo "  2. Pruefen ohne Orders:   .venv/bin/python3 live.py --check"
echo "  3. Backtest (optional):   .venv/bin/python3 backtest.py --days 365"
echo "  4. Waechter-Cronjob (crontab -e):"
echo "     */5 * * * * $(pwd)/start.sh"
echo "  5. Log:  tail -f logs/zockerbot.log"
