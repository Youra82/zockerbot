#!/bin/bash
# Waechter: startet den zockerbot, falls er nicht laeuft (Cron alle 5 min, auch nach Neustart).
cd "$(dirname "$0")"
mkdir -p data logs
PIDFILE=data/bot.pid
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    exit 0
fi
export PYTHONIOENCODING=utf-8
nohup .venv/bin/python3 -u live.py >> logs/stdout.log 2>> logs/stderr.log &
echo $! > "$PIDFILE"
echo "$(date -u '+%Y-%m-%d %H:%M:%S') zockerbot gestartet (PID $!)" >> logs/start.log
