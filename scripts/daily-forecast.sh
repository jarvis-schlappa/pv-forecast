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

# === Tagesvergleich ins Observation Log ===
log "Writing observation log..."
DATE=$(date +%Y-%m-%d)
NEXT=$(date -v+1d +%Y-%m-%d)
LOG_FILE="/Users/jarvis/projects/pv-forecast/docs/observation-log.md"

# Header anlegen falls Datei nicht existiert
if [ ! -f "$LOG_FILE" ]; then
    cat > "$LOG_FILE" << 'HEADER'
# PV-Forecast Observation Log

Tägliche Dokumentation: Prognose vs. Realität, Modellverhalten, Auffälligkeiten.

---

HEADER
fi

# Tagesertrag aus FHEM holen
YIELD=$(curl -s "http://192.168.40.11:8084/fhem?cmd=get%20sonne%20-%20-%20${DATE}%20${NEXT}%204:sonne&XHR=1" | \
grep -v "^#" | \
awk -F'[_ ]' '
{
  split($2, t, ":")
  ts = t[1]*3600 + t[2]*60 + t[3]
  w = $3
  if (prev_ts > 0 && ts > prev_ts) {
    dt = (ts - prev_ts) / 3600.0
    energy += ((w + prev_w) / 2) * dt
  }
  prev_ts = ts
  prev_w = w
}
END { printf "%.1f", energy/1000 }')

# Prognosen aus DB holen (letzter Forecast vor heute für heute)
FORECASTS=$(python3 -c "
import sqlite3
from datetime import datetime, timezone, timedelta
CET = timezone(timedelta(hours=1))
db = sqlite3.connect('/Users/jarvis/.local/share/pvforecast/data.db')
target_start = int(datetime.strptime('${DATE}', '%Y-%m-%d').replace(tzinfo=CET).timestamp())
target_end = target_start + 86400

# Letzter Forecast pro Quelle (issued vor heute)
for src in ['open-meteo', 'mosmix']:
    row = db.execute('''
        SELECT issued_at, SUM(ghi_wm2)
        FROM forecast_history
        WHERE target_time >= ? AND target_time < ? AND source = ?
        GROUP BY issued_at ORDER BY issued_at DESC LIMIT 1
    ''', (target_start, target_end, src)).fetchone()
    if row:
        ts = datetime.fromtimestamp(row[0], tz=CET).strftime('%H:%M')
        print(f'{src}|{ts}|{row[1]:.0f}')
" 2>/dev/null)

# pvforecast Modell-Prognose (aus Cache falls vorhanden, sonst live)
FORECAST_FILE="/tmp/pv-forecast-today.txt"
if [ -f "$FORECAST_FILE" ] && [ "$(date -r "$FORECAST_FILE" +%Y-%m-%d)" = "$DATE" ]; then
    MODEL_FORECAST=$(cat "$FORECAST_FILE")
else
    MODEL_FORECAST=$(pvforecast today --source open-meteo -q 2>/dev/null | grep -E "Erwarteter Tagesertrag" | grep -oE "[0-9]+\.[0-9]+" | head -1)
fi

# Wetter-Zusammenfassung (Außentemp + Bewölkung aus FHEM)
TEMP=$(curl -s "http://192.168.40.11:8083/fhem?cmd=jsonlist2%20heatronic%20ch_Toutside&XHR=1" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Results'][0]['Readings']['ch_Toutside']['Value'])" 2>/dev/null || echo "?")

# Eintrag schreiben
{
    echo "## ${DATE}"
    echo ""
    echo "- **Ertrag:** ${YIELD} kWh"
    [ -n "$MODEL_FORECAST" ] && echo "- **Modell-Prognose:** ${MODEL_FORECAST} kWh"
    echo "$FORECASTS" | while IFS='|' read -r src ts ghi; do
        [ -n "$src" ] && echo "- **${src}** (${ts}): GHI-Summe ${ghi} W/m²"
    done
    if [ -n "$MODEL_FORECAST" ] && [ "$MODEL_FORECAST" != "0" ]; then
        DEV=$(echo "scale=0; (($YIELD - $MODEL_FORECAST) * 100) / $MODEL_FORECAST" | bc 2>/dev/null)
        echo "- **Abweichung:** ${DEV}%"
    fi
    echo "- **Außentemp:** ${TEMP} °C"
    echo ""
} >> "$LOG_FILE"

log "Observation log updated: ${YIELD} kWh actual"

# Cache morgen's Prognose für PV-Monitoring (um 23:00 = Prognose für morgen)
FORECAST=$(pvforecast predict --days 1 2>/dev/null | grep -E "Erwarteter Tagesertrag" | grep -oE "[0-9]+\.[0-9]+" | head -1)
if [ -n "$FORECAST" ]; then
    echo "$FORECAST" > /tmp/pv-forecast-today.txt
    log "Cached tomorrow forecast: ${FORECAST} kWh"
else
    log "Warning: Could not cache tomorrow forecast"
fi
