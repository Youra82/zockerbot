#!/bin/bash
# zockerbot - Installation auf Linux (MiniPC)
set -e
cd "$(dirname "$0")"
echo "=== zockerbot Installation ==="
python3 -m venv .venv
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet
mkdir -p data_dryrun
chmod +x *.sh

if command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]; then
    echo "Claude Code gefunden."
else
    echo "WARNUNG: Claude Code fehlt. Installieren mit:"
    echo "    curl -fsSL https://claude.ai/install.sh | bash"
    echo "und danach EINMAL 'claude' starten und mit dem Claude-Abo anmelden."
fi

echo ""
echo "Naechste Schritte:"
echo "  1. Test ohne KI (kostenlos):   .venv/bin/python3 live.py --mock"
echo "  2. Auftrag an die KI ansehen:  .venv/bin/python3 live.py --prompt"
echo "  3. Waechter-Cronjob eintragen (crontab -e):"
echo "     */5 * * * * $(pwd)/start.sh"
echo "  4. Status:  tail -f data_dryrun/zockerbot.log"
