#!/bin/bash
# Stoppt den zockerbot (der Waechter-Cronjob startet ihn sonst nach spaetestens 5 min wieder).
cd "$(dirname "$0")"
PIDFILE=data_dryrun/bot.pid
if [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "zockerbot gestoppt."
else
    echo "zockerbot lief nicht."
fi
rm -f "$PIDFILE"
