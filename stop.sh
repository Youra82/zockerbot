#!/bin/bash
# Stoppt den zockerbot (der Waechter-Cronjob startet ihn sonst nach spaetestens 5 min wieder).
# Offene Positionen und ihre TP-Orders bleiben auf Bitget bestehen.
cd "$(dirname "$0")"
PIDFILE=data/bot.pid
if [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "zockerbot gestoppt."
else
    echo "zockerbot lief nicht."
fi
rm -f "$PIDFILE"
