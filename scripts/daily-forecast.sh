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

# Tagesertrag direkt vom E3DC (via RSCP)
E3DC="sudo /Users/jarvis/projects/e3dcset/e3dcset-query.sh"
YIELD=$($E3DC -H day 2>/dev/null | grep "PV-Produktion" | grep -oE "[0-9]+\.[0-9]+" | head -1)
YIELD=${YIELD:-0.0}

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

# === E3DC Stundenwerte in pvforecast DB importieren ===
log "Importing E3DC hourly data into DB..."
$E3DC -H day --raw 2>/dev/null | python3 -c "
import sys, csv, sqlite3
from datetime import datetime, timezone, timedelta

CET = timezone(timedelta(hours=1))
db = sqlite3.connect('/Users/jarvis/.local/share/pvforecast/data.db')

reader = csv.reader(sys.stdin)
next(reader)  # header

hourly = {}
for row in reader:
    dt = datetime.strptime(row[0], '%Y-%m-%d %H:%M').replace(tzinfo=CET)
    hour = dt.replace(minute=0, second=0)
    if hour not in hourly:
        hourly[hour] = {'pv': [], 'cons': [], 'grid_in': [], 'grid_out': []}
    hourly[hour]['pv'].append(float(row[1]))
    hourly[hour]['cons'].append(float(row[6]))
    hourly[hour]['grid_in'].append(float(row[4]))
    hourly[hour]['grid_out'].append(float(row[5]))

inserted = 0
for hour_dt in sorted(hourly.keys()):
    h = hourly[hour_dt]
    if len(h['pv']) < 4:
        continue  # unvollständige Stunde
    ts = int(hour_dt.timestamp())
    # E3DC raw = W Durchschnitt pro 15-Min, DB = Wh pro Stunde
    pv = int(sum(h['pv']) * 0.25)
    cons = int(sum(h['cons']) * 0.25)
    feed = int(sum(h['grid_in']) * 0.25)
    draw = int(sum(h['grid_out']) * 0.25)
    db.execute(
        'INSERT OR IGNORE INTO pv_readings (timestamp, production_w, consumption_w, grid_feed_w, grid_draw_w, soc_pct, curtailed) VALUES (?, ?, ?, ?, ?, NULL, 0)',
        (ts, pv, cons, feed, draw))
    inserted += db.total_changes and 1 or 0

db.commit()
print(f'{inserted} Stunden importiert')
" 2>&1 | while read line; do log "DB: $line"; done

# Cache morgen's Prognose für PV-Monitoring (um 23:00 = Prognose für morgen)
FORECAST=$(pvforecast predict --days 1 2>/dev/null | grep -E "Erwarteter Tagesertrag" | grep -oE "[0-9]+\.[0-9]+" | head -1)
if [ -n "$FORECAST" ]; then
    echo "$FORECAST" > /tmp/pv-forecast-today.txt
    log "Cached tomorrow forecast: ${FORECAST} kWh"
else
    log "Warning: Could not cache tomorrow forecast"
fi
