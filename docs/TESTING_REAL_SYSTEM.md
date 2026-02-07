# Real-System Testkonzept

Vollständige Testmatrix für alle CLI-Befehle und Optionen.

**Testabdeckung:** 20 Kategorien, 70+ Testfälle

| Bereich | Tests |
|---------|-------|
| Funktional (1-12) | Setup, Import, Wetter, Training, Prognosen, Evaluation |
| Robustheit (13-20) | Datenintegrität, Zeitzonen, Parallelität, Limits, Interrupts, Regression, Berechtigungen, Dependencies |

---

## 🔧 Voraussetzungen

```bash
# Frische Test-DB erstellen
export TEST_DB=/tmp/pvforecast-test.db
rm -f $TEST_DB

# Projekt-Verzeichnis
cd ~/projects/pv-forecast
source .venv/bin/activate
```

---

## 📋 Testmatrix

### 1. Setup & Konfiguration

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 1.1 | `pvforecast --db $TEST_DB setup` | Interaktiver Wizard startet |
| 1.2 | `pvforecast config --show` | Zeigt aktuelle Config |
| 1.3 | `pvforecast config --set timezone=Europe/Berlin` | Ändert Timezone |
| 1.4 | `pvforecast --lat 52.0 --lon 8.0 config --show` | CLI-Override funktioniert |

---

### 2. Datenimport

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 2.1 | `pvforecast --db $TEST_DB import ~/e3dc-data/` | CSV-Import erfolgreich |
| 2.2 | `pvforecast --db $TEST_DB import ~/e3dc-data/` | Duplikate erkannt, übersprungen |
| 2.3 | `pvforecast --db $TEST_DB status` | Zeigt importierte Datensätze |

---

### 3. Wetterdaten - Open-Meteo (Default)

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 3.1 | `pvforecast fetch-forecast` | Forecast-Daten abgerufen |
| 3.2 | `pvforecast fetch-forecast --format json` | JSON-Ausgabe |
| 3.3 | `pvforecast fetch-forecast --format csv` | CSV-Ausgabe |

---

### 4. Wetterdaten - MOSMIX

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 4.1 | `pvforecast fetch-forecast --source mosmix` | MOSMIX-Daten abgerufen |
| 4.2 | `pvforecast fetch-forecast --source mosmix --format json` | JSON-Ausgabe |
| 4.3 | `pvforecast today --source mosmix` | Tagesprognose mit MOSMIX |
| 4.4 | `pvforecast predict --source mosmix --days 3` | Mehrtages-Prognose |

---

### 5. Wetterdaten - HOSTRADA

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 5.1 | `pvforecast --db $TEST_DB fetch-historical --source hostrada --start 2024-01-01 --end 2024-01-31 -y` | Download + Import |
| 5.2 | `pvforecast --db $TEST_DB fetch-historical --source hostrada --start 2024-01-01 --end 2024-01-31` | "Bereits vorhanden" |
| 5.3 | `pvforecast --db $TEST_DB fetch-historical --source hostrada --start 2024-01-15 --end 2024-02-15` | Nur Feb laden |
| 5.4 | `pvforecast --db $TEST_DB fetch-historical --source hostrada --start 2024-01-01 --end 2024-01-31 --force -y` | Force-Download |

---

### 6. Training

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 6.1 | `pvforecast --db $TEST_DB train` | RandomForest trainiert |
| 6.2 | `pvforecast --db $TEST_DB train --model xgb` | XGBoost trainiert |
| 6.3 | `pvforecast --db $TEST_DB train --since 2023-01-01` | Nur neuere Daten |
| 6.4 | `pvforecast --db $TEST_DB tune` | RandomizedSearchCV |
| 6.5 | `pvforecast --db $TEST_DB tune --method optuna --trials 10` | Optuna-Tuning |

---

### 7. Prognosen

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 7.1 | `pvforecast --db $TEST_DB today` | Tagesprognose (Default: Open-Meteo) |
| 7.2 | `pvforecast --db $TEST_DB today --source mosmix` | Tagesprognose mit MOSMIX |
| 7.3 | `pvforecast --db $TEST_DB today --format json` | JSON-Ausgabe |
| 7.4 | `pvforecast --db $TEST_DB predict --days 1` | 1-Tages-Prognose |
| 7.5 | `pvforecast --db $TEST_DB predict --days 7` | 7-Tages-Prognose |
| 7.6 | `pvforecast --db $TEST_DB predict --days 3 --source mosmix` | MOSMIX Mehrtages |

---

### 8. Evaluation

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 8.1 | `pvforecast --db $TEST_DB evaluate` | Backtesting-Ergebnis |
| 8.2 | `pvforecast --db $TEST_DB evaluate --days 30` | 30-Tage Evaluation |
| 8.3 | `pvforecast --db $TEST_DB evaluate --format json` | JSON-Metriken |

---

### 9. Diagnose & Status

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 9.1 | `pvforecast --db $TEST_DB status` | DB-Statistiken |
| 9.2 | `pvforecast --db $TEST_DB doctor` | Healthcheck bestanden |
| 9.3 | `pvforecast --db $TEST_DB doctor --fix` | Auto-Reparatur |
| 9.4 | `pvforecast --version` | Versionsnummer |

---

### 10. Reset

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 10.1 | `pvforecast --db $TEST_DB reset --model` | Nur Modell gelöscht |
| 10.2 | `pvforecast --db $TEST_DB reset --weather` | Nur Wetterdaten |
| 10.3 | `pvforecast --db $TEST_DB reset --all` | Kompletter Reset |

---

### 11. Edge Cases & Fehlerbehandlung

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 11.1 | `pvforecast --db /nonexistent/path.db status` | Sinnvolle Fehlermeldung |
| 11.2 | `pvforecast predict` (ohne Training) | Hinweis: erst trainieren |
| 11.3 | `pvforecast fetch-historical --source hostrada --start 2030-01-01 --end 2030-01-31` | Zukunft nicht verfügbar |
| 11.4 | `pvforecast fetch-historical --source hostrada --start 2024-01-31 --end 2024-01-01` | Start > End Fehler |
| 11.5 | `pvforecast --lat 999 --lon 999 fetch-forecast` | Ungültige Koordinaten |

---

### 12. Quellen-Vergleich

| Test | Befehl | Erwartung |
|------|--------|-----------|
| 12.1 | Vergleich MOSMIX vs Open-Meteo | Unterschied <30% |

```bash
# Speichere beide Prognosen
pvforecast today --source mosmix --format json > /tmp/mosmix.json
pvforecast today --format json > /tmp/openmeteo.json

# Vergleiche Summen
echo "MOSMIX: $(jq '[.[].predicted_wh] | add' /tmp/mosmix.json) Wh"
echo "Open-Meteo: $(jq '[.[].predicted_wh] | add' /tmp/openmeteo.json) Wh"
```

---

## ✅ Vollständiger Testlauf

```bash
#!/bin/bash
# Automatisierter Testlauf (ohne HOSTRADA-Downloads)

set -e
export TEST_DB=/tmp/pvforecast-fulltest.db
rm -f $TEST_DB

echo "=== 1. Setup ==="
pvforecast --db $TEST_DB config --show

echo "=== 2. Import ==="
pvforecast --db $TEST_DB import ~/e3dc-data/ 2>/dev/null || echo "Keine CSV-Daten"

echo "=== 3. Status ==="
pvforecast --db $TEST_DB status

echo "=== 4. Fetch Forecast (Open-Meteo) ==="
pvforecast fetch-forecast --format json | head -5

echo "=== 5. Fetch Forecast (MOSMIX) ==="
pvforecast fetch-forecast --source mosmix --format json | head -5

echo "=== 6. Train ==="
pvforecast --db $TEST_DB train || echo "Nicht genug Daten"

echo "=== 7. Today ==="
pvforecast --db $TEST_DB today || echo "Kein Modell"

echo "=== 8. Doctor ==="
pvforecast --db $TEST_DB doctor

echo "=== 9. Version ==="
pvforecast --version

echo "=== DONE ==="
```

---

---

## 🔬 Erweiterte Testszenarien

### 13. Datenintegrität

| Test | Szenario | Erwartung |
|------|----------|-----------|
| 13.1 | Korrupte SQLite-DB | Sinnvolle Fehlermeldung, kein Crash |
| 13.2 | Abbruch während CSV-Import (Ctrl+C) | Partielle Daten, kein korrupter Zustand |
| 13.3 | Lücken in PV-Daten (fehlende Stunden) | Training funktioniert, Warnung |
| 13.4 | Doppelte Timestamps in CSV | Deduplizierung oder Fehler |

```bash
# Test 13.1: Korrupte DB
echo "garbage" > /tmp/corrupt.db
pvforecast --db /tmp/corrupt.db status
# Erwartung: "Datenbank beschädigt" o.ä.

# Test 13.3: Lücken prüfen
pvforecast --db $TEST_DB doctor --check-gaps
```

---

### 14. Zeitzone-Edge-Cases

| Test | Szenario | Erwartung |
|------|----------|-----------|
| 14.1 | Prognose über Sommerzeitumstellung (März) | Korrekte Stunden (23h oder 25h Tag) |
| 14.2 | Prognose über Winterzeitumstellung (Oktober) | Korrekte Stunden |
| 14.3 | UTC-Timestamps in DB vs Lokalzeit-Ausgabe | Konsistente Umrechnung |
| 14.4 | Config timezone ändern nach Import | Alte Daten korrekt interpretiert |

```bash
# Test 14.1: Sommerzeitumstellung 2024 (31. März)
pvforecast predict --days 1  # Am 30. März ausführen
# Erwartung: 23 Stunden für den 31. März

# Test 14.3: Timestamp-Check
pvforecast today --format json | jq '.[0].time'
# Erwartung: Lokalzeit, nicht UTC
```

---

### 15. Parallelität & Locking

| Test | Szenario | Erwartung |
|------|----------|-----------|
| 15.1 | Zwei `train` gleichzeitig | DB-Lock, einer wartet oder Fehler |
| 15.2 | `import` während `train` | Saubere Trennung oder Lock |
| 15.3 | `fetch-historical` parallel | Keine doppelten Downloads |

```bash
# Test 15.1: Paralleles Training
pvforecast --db $TEST_DB train &
pvforecast --db $TEST_DB train &
wait
# Erwartung: Beide beenden erfolgreich (SQLite WAL) oder Lock-Fehler
```

---

### 16. Ressourcen-Limits

| Test | Szenario | Erwartung |
|------|----------|-----------|
| 16.1 | Disk voll während HOSTRADA-Download | Cleanup, Fehlermeldung |
| 16.2 | RAM-Limit bei großem Modell | Graceful Degradation oder Hinweis |
| 16.3 | Sehr große CSV (>1 GB, >1M Zeilen) | Fortschrittsanzeige, kein OOM |
| 16.4 | 10 Jahre HOSTRADA (~180 GB Download) | Warnung, Abbruchmöglichkeit |

```bash
# Test 16.3: Große Datei
# Generiere Test-CSV mit 1M Zeilen
python3 -c "
import csv
from datetime import datetime, timedelta
with open('/tmp/large.csv', 'w') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(['Zeitstempel', 'PV-Leistung', 'Hausverbrauch'])
    dt = datetime(2020, 1, 1)
    for i in range(1_000_000):
        w.writerow([dt.strftime('%d.%m.%Y %H:%M:%S'), 1000, 500])
        dt += timedelta(minutes=15)
"
time pvforecast --db /tmp/large-test.db import /tmp/large.csv
```

---

### 17. Interrupt-Handling (Ctrl+C)

| Test | Szenario | Erwartung |
|------|----------|-----------|
| 17.1 | Ctrl+C während HOSTRADA-Download | Temp-Dateien gelöscht, sauberer Exit |
| 17.2 | Ctrl+C während Training | Kein korruptes Modell, alter Stand bleibt |
| 17.3 | Ctrl+C während CSV-Import | Partielle Daten OK, nächster Import fortsetzbar |

```bash
# Test 17.1: Download abbrechen
pvforecast fetch-historical --source hostrada --start 2020-01-01 --end 2020-12-31 -y
# Ctrl+C nach einigen Sekunden
ls /tmp/*.nc  # Sollte leer sein (Cleanup)
```

---

### 18. Regressionstests

| Test | Szenario | Erwartung |
|------|----------|-----------|
| 18.1 | Modell-Performance nach Code-Update | MAPE nicht signifikant schlechter |
| 18.2 | Prognose-Summe reproduzierbar | Gleiche Eingabe → gleiche Ausgabe |
| 18.3 | Alte Config mit neuer Version | Migration oder Warnung |

```bash
# Test 18.1: Performance-Baseline
pvforecast evaluate --format json > /tmp/baseline.json
# Nach Code-Änderung:
pvforecast evaluate --format json > /tmp/after.json
jq -s '.[0].mape as $b | .[1].mape as $a | 
  if ($a - $b) > 5 then "REGRESSION: MAPE +\($a - $b)%" else "OK" end' \
  /tmp/baseline.json /tmp/after.json
```

---

### 19. Berechtigungen

| Test | Szenario | Erwartung |
|------|----------|-----------|
| 19.1 | Keine Schreibrechte auf DB-Pfad | Klare Fehlermeldung |
| 19.2 | Keine Schreibrechte auf Config-Dir | Fallback oder Fehler |
| 19.3 | Read-only DB (chmod 444) | Nur Lesebefehle funktionieren |

```bash
# Test 19.1: Kein Schreibzugriff
chmod 444 $TEST_DB
pvforecast --db $TEST_DB import ~/e3dc-data/
# Erwartung: "Keine Schreibberechtigung" o.ä.
chmod 644 $TEST_DB

# Test 19.3: Read-only
chmod 444 $TEST_DB
pvforecast --db $TEST_DB status  # Sollte funktionieren
pvforecast --db $TEST_DB train   # Sollte fehlschlagen
chmod 644 $TEST_DB
```

---

### 20. Dependency-Fehler

| Test | Szenario | Erwartung |
|------|----------|-----------|
| 20.1 | xarray nicht installiert → HOSTRADA | Klarer Hinweis: `pip install pvforecast[all]` |
| 20.2 | xgboost nicht installiert → `--model xgb` | Klarer Hinweis: `pip install pvforecast[xgb]` |
| 20.3 | optuna nicht installiert → `tune --method optuna` | Klarer Hinweis |
| 20.4 | pvlib nicht installiert → Physics-Features | Fallback oder Hinweis |

```bash
# Test 20.2: XGBoost fehlt
pip uninstall xgboost -y 2>/dev/null
pvforecast train --model xgb
# Erwartung: "XGBoost nicht installiert. Installiere mit: pip install pvforecast[xgb]"
pip install xgboost
```

---

## 🐛 Bekannte Einschränkungen

1. **Keine Quellen-Unterscheidung in DB:** weather_history speichert nicht, ob Daten von Open-Meteo oder HOSTRADA stammen.

2. **Monats-Granularität:** HOSTRADA Skip-Check prüft nur Monat-Existenz, nicht Vollständigkeit.

3. **HOSTRADA ~2 Monate behind:** Aktuelle Monate nicht verfügbar.

4. **Kein Offline-Modus:** Alle Wetter-Befehle brauchen Internet.
