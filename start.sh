#!/bin/bash
# Waechter: startet den zockerbot, falls er nicht laeuft (fuer Cron alle 5 min, auch nach Neustart des MiniPC).
cd "$(dirname "$0")"
mkdir -p data_dryrun
PIDFILE=data_dryrun/bot.pid
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    exit 0                                   # laeuft bereits
fi
export PATH="$HOME/.local/bin:$PATH"         # Cron kennt ~/.local/bin (Claude Code) sonst nicht
export PYTHONIOENCODING=utf-8
nohup .venv/bin/python3 -u live.py >> data_dryrun/stdout.log 2>> data_dryrun/stderr.log &
echo $! > "$PIDFILE"
echo "$(date -u '+%Y-%m-%d %H:%M:%S') zockerbot gestartet (PID $!)" >> data_dryrun/start.log
