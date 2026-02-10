#!/bin/bash
# Battery Health Tracking - E3DC Batterie-Degradation
# Läuft monatlich am 1. um 12:00 via OpenClaw Cron
#
# Liest DCB-Modulinfo via e3dcset und loggt:
# - SOH (State of Health) pro Modul
# - Volle/verbleibende/Design Kapazität
# - Ladezyklen
# - Strom, Spannung, Statusflags
#
# Output: CSV-Datei + iMessage bei Auffälligkeiten

set -e

E3DC="sudo /Users/jarvis/projects/e3dcset/e3dcset-query.sh"
CSV_FILE="/Users/jarvis/projects/pv-forecast/data/battery-health.csv"
DATE=$(date +%Y-%m-%d)

# CSV-Header anlegen falls Datei nicht existiert
if [ ! -f "$CSV_FILE" ]; then
    mkdir -p "$(dirname "$CSV_FILE")"
    echo "date,dcb,soh_pct,full_capacity_wh,design_capacity_wh,remaining_capacity_wh,cycles,voltage_v,current_a,status_flags,warning_flags,alarm_flags,error_flags" > "$CSV_FILE"
fi

# Modulinfo holen und parsen
MODULE_DATA=$($E3DC -m 0 2>/dev/null)

if [ -z "$MODULE_DATA" ]; then
    echo "FEHLER: E3DC nicht erreichbar"
    exit 1
fi

# Gesamtwerte (oberste Ebene)
TOTAL_SOH=$(echo "$MODULE_DATA" | grep -A1 "^State of Health" | tail -1 | tr -d ' ')
TOTAL_CYCLES=$(echo "$MODULE_DATA" | grep -A1 "^Anzahl Ladezyklen" | tail -1 | tr -d ' ')

# Pro DCB-Zellblock parsen
ALERT=""
DCB_COUNT=$(echo "$MODULE_DATA" | grep -c "^Zellblock #")

for i in $(seq 0 $((DCB_COUNT - 1))); do
    # Block für diesen DCB extrahieren
    if [ $i -eq $((DCB_COUNT - 1)) ]; then
        BLOCK=$(echo "$MODULE_DATA" | sed -n "/^Zellblock #${i}$/,\$p")
    else
        BLOCK=$(echo "$MODULE_DATA" | sed -n "/^Zellblock #${i}$/,/^Zellblock #$((i+1))$/p" | sed '$d')
    fi

    SOH=$(echo "$BLOCK" | grep -A1 "Module State of Health" | tail -1 | tr -d ' ')
    FULL_CAP=$(echo "$BLOCK" | grep -A1 "Volle Ladekapazität" | tail -1 | tr -d ' ')
    DESIGN_CAP=$(echo "$BLOCK" | grep -A1 "Design-Kapazität" | tail -1 | tr -d ' ')
    REMAIN_CAP=$(echo "$BLOCK" | grep -A1 "Verbleibende Kapazität" | tail -1 | tr -d ' ')
    CYCLES=$(echo "$BLOCK" | grep -A1 "^Ladezyklen" | tail -1 | tr -d ' ')
    VOLTAGE=$(echo "$BLOCK" | grep -A1 "^Spannung (V)$" | tail -1 | tr -d ' ')
    CURRENT=$(echo "$BLOCK" | grep -A1 "^Strom (A)$" | tail -1 | tr -d ' ')
    STATUS=$(echo "$BLOCK" | grep -A1 "Status Flags" | tail -1 | tr -d ' ')
    WARNING=$(echo "$BLOCK" | grep -A1 "Warning Flags" | tail -1 | tr -d ' ')
    ALARM=$(echo "$BLOCK" | grep -A1 "Alarm Flags" | tail -1 | tr -d ' ')
    ERROR=$(echo "$BLOCK" | grep -A1 "Error Flags" | tail -1 | tr -d ' ')

    # In CSV schreiben
    echo "${DATE},${i},${SOH},${FULL_CAP},${DESIGN_CAP},${REMAIN_CAP},${CYCLES},${VOLTAGE},${CURRENT},${STATUS},${WARNING},${ALARM},${ERROR}" >> "$CSV_FILE"

    # Degradation prüfen: full_capacity / design_capacity
    if [ -n "$FULL_CAP" ] && [ -n "$DESIGN_CAP" ]; then
        REAL_SOH=$(echo "scale=1; $FULL_CAP / $DESIGN_CAP * 100" | bc 2>/dev/null)
        if [ -n "$REAL_SOH" ] && [ "$(echo "$REAL_SOH < 90" | bc)" -eq 1 ]; then
            ALERT="${ALERT}⚠️ DCB#${i}: SOH ${REAL_SOH}% (${FULL_CAP}/${DESIGN_CAP} Wh)\n"
        fi
    fi

    # Warning/Alarm/Error Flags prüfen
    if [ "$WARNING" != "0" ] || [ "$ALARM" != "0" ] || [ "$ERROR" != "0" ]; then
        ALERT="${ALERT}🚨 DCB#${i}: Flags! Warning=${WARNING} Alarm=${ALARM} Error=${ERROR}\n"
    fi
done

# Zusammenfassung ausgeben
echo "Batterie-Health Log: ${DATE}"
echo "  Module: ${DCB_COUNT}"
echo "  Gesamt-SOH: ${TOTAL_SOH}%"
echo "  Zyklen: ${TOTAL_CYCLES}"
echo "  CSV: ${CSV_FILE}"

if [ -n "$ALERT" ]; then
    echo ""
    echo "ALERTS:"
    echo -e "$ALERT"
    # Alert-Text für iMessage
    echo "ALERT:$(echo -e "$ALERT")"
else
    echo "  Status: Alles OK ✅"
fi
