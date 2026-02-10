# Batterie-Degradation Tracking

Monatliches Monitoring der E3DC-Batteriemodule (DCB-Zellblöcke) zur Erkennung von Kapazitätsverlust und Anomalien.

## Übersicht

Das E3DC S10 Hauskraftwerk enthält 4 DCB-Zellblöcke (ATL3_3, Hersteller ATL). Die Batterien wurden Anfang 2026 ausgetauscht und haben daher eine sehr kurze Laufzeit.

**Baseline (10.02.2026):**

| DCB | SOH | Kapazität (voll) | Kapazität (Design) | Zyklen |
|-----|-----|-------------------|---------------------|--------|
| #0  | 100% | 59.20 Wh | 64.00 Wh | 37 |
| #1  | 100% | 59.00 Wh | 64.00 Wh | 37 |
| #2  | 100% | 59.60 Wh | 64.00 Wh | 40 |
| #3  | 100% | 61.00 Wh | 64.00 Wh | 40 |

**Gesamt:** 4 × 64 Wh = 256 Wh Design-Kapazität (pro DCB-Ebene)

## Wie es funktioniert

### Datenquelle

Direkte RSCP-Abfrage des E3DC via `e3dcset -m 0`:
- Verbindung über lokales Netzwerk (192.168.40.x)
- Kein Cloud/Internet nötig
- Liest alle 4 DCB-Module in einem Request

### Was gemessen wird

| Metrik | Beschreibung | Einheit |
|--------|-------------|---------|
| `soh_pct` | State of Health (E3DC-intern) | % |
| `full_capacity_wh` | Aktuelle volle Ladekapazität | Wh |
| `design_capacity_wh` | Ursprüngliche Design-Kapazität | Wh |
| `remaining_capacity_wh` | Aktuell verbleibende Kapazität | Wh |
| `cycles` | Anzahl vollständiger Ladezyklen | Anzahl |
| `voltage_v` | Modulspannung | V |
| `current_a` | Modulstrom | A |
| `status/warning/alarm/error_flags` | Statusflags | Integer |

### Echte vs. angezeigte SOH

Die E3DC zeigt SOH immer als `100%` an, solange die Batterie "gesund" ist. Die **echte Degradation** zeigt sich in:

```
Echte SOH = full_capacity_wh / design_capacity_wh × 100
```

Beispiel: Wenn `full_capacity_wh` von 64.00 auf 57.60 fällt, ist die echte SOH 90%, auch wenn E3DC noch 100% anzeigt.

### Alert-Schwellen

| Bedingung | Alert |
|-----------|-------|
| `full_capacity / design_capacity < 90%` | ⚠️ Degradation Warning |
| `warning_flags ≠ 0` | 🚨 Warning Flag |
| `alarm_flags ≠ 0` | 🚨 Alarm Flag |
| `error_flags ≠ 0` | 🚨 Error Flag |

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `scripts/battery-health.sh` | Mess-Script (läuft monatlich) |
| `data/battery-health.csv` | Historische Messwerte |
| `docs/BATTERY-HEALTH.md` | Diese Dokumentation |

## Zeitplan

- **Wann:** 1. des Monats, 12:00 Uhr (Europe/Berlin)
- **Wie:** OpenClaw Cron-Job → isolated Session
- **Output:** iMessage an Marcus mit SOH + Zyklen
- **Alert:** Sofortige Benachrichtigung bei Auffälligkeiten

## CSV-Format

```csv
date,dcb,soh_pct,full_capacity_wh,design_capacity_wh,remaining_capacity_wh,cycles,voltage_v,current_a,status_flags,warning_flags,alarm_flags,error_flags
2026-02-10,0,100.00,59.20,64.00,13.30,37,53.40,12.90,224,0,0,0
```

## Manuelle Abfrage

```bash
# Einmal-Messung
/Users/jarvis/projects/pv-forecast/scripts/battery-health.sh

# Rohdaten vom E3DC
sudo /Users/jarvis/projects/e3dcset/e3dcset-query.sh -m 0

# CSV anzeigen
cat /Users/jarvis/projects/pv-forecast/data/battery-health.csv | column -t -s,
```

## Erwartete Degradation

Lithium-Batterien verlieren typischerweise:
- **1-3% pro Jahr** bei normaler Nutzung
- Beschleunigt durch: hohe Temperaturen, viele Zyklen, dauerhaft hoher/niedriger SOC
- ATL-Zellen (NMC): ~80% SOH nach 4.000-6.000 Zyklen (Herstellerangabe)

Bei aktuell ~40 Zyklen in ~6 Monaten → ~80 Zyklen/Jahr → die Batterien sollten Jahrzehnte halten.
