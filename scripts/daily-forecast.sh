#!/bin/bash
# Daily forecast archival - runs at 23:00 via cron
# Collects forecast data from multiple sources for Forecast vs Reality analysis

set -e

cd /Users/jarvis/projects/pv-forecast
source .venv/bin/activate

# Log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting daily forecast collection..."

# === Open-Meteo ===
log "Open-Meteo: today"
pvforecast today --source open-meteo >/dev/null 2>&1 || log "Warning: open-meteo today failed"

log "Open-Meteo: predict --days 3"
pvforecast predict --days 3 --source open-meteo >/dev/null 2>&1 || log "Warning: open-meteo predict failed"

# === MOSMIX ===
log "MOSMIX: today"
pvforecast today --source mosmix >/dev/null 2>&1 || log "Warning: mosmix today failed"

log "MOSMIX: predict --days 3"
pvforecast predict --days 3 --source mosmix >/dev/null 2>&1 || log "Warning: mosmix predict failed"

log "Done. Sources: open-meteo, mosmix"

# Cache morgen's Prognose für PV-Monitoring (um 23:00 = Prognose für morgen)
FORECAST=$(pvforecast predict --days 1 2>/dev/null | grep -E "Erwarteter Tagesertrag" | grep -oE "[0-9]+\.[0-9]+" | head -1)
if [ -n "$FORECAST" ]; then
    echo "$FORECAST" > /tmp/pv-forecast-today.txt
    log "Cached tomorrow forecast: ${FORECAST} kWh"
else
    log "Warning: Could not cache tomorrow forecast"
fi
