# CLI-Referenz

Vollständige Dokumentation aller `pvforecast`-Befehle.

## Globale Optionen

Diese Optionen gelten für alle Befehle:

```bash
pvforecast [GLOBALE OPTIONEN] <befehl> [BEFEHL-OPTIONEN]
```

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--db PATH` | Pfad zur SQLite-Datenbank | `~/.local/share/pvforecast/data.db` |
| `--lat FLOAT` | Breitengrad | aus Config |
| `--lon FLOAT` | Längengrad | aus Config |
| `-v, --verbose` | Ausführliche Ausgabe (inkl. HTTP-Requests, Debug-Logs) | aus |
| `--version` | Version anzeigen | - |
| `-h, --help` | Hilfe anzeigen | - |

---

## Befehle

### `pvforecast setup`

Interaktiver Einrichtungs-Assistent für die Erstkonfiguration.

```bash
pvforecast setup [OPTIONEN]
```

| Option | Beschreibung |
|--------|--------------|
| `--force` | Überschreibt existierende Konfiguration |

**Ablauf:**

```
🔆 PV-Forecast Ersteinrichtung
══════════════════════════════════════════════════

1️⃣  Standort
   Postleitzahl oder Ort: 48249
   Suche...
   → Dülmen, Nordrhein-Westfalen (51.85°N, 7.26°E)
   Stimmt das? [J/n]: j
   ✓

2️⃣  Anlage
   Peakleistung in kWp: 9.92
   Name (optional) [Dülmen PV]: 
   ✓

3️⃣  XGBoost (bessere Prognose-Genauigkeit)
   XGBoost installieren? [J/n]: j
   Installiere XGBoost...
   ✓ XGBoost installiert

══════════════════════════════════════════════════
✅ Einrichtung abgeschlossen!
══════════════════════════════════════════════════

   Config gespeichert: ~/.config/pvforecast/config.yaml

   Nächste Schritte:
   1. Daten importieren:  pvforecast import <csv-dateien>
   2. Modell trainieren:  pvforecast train
   3. Prognose erstellen: pvforecast today
```

**Features:**
- Automatische Standort-Ermittlung via PLZ oder Ortsname (Geocoding)
- Validierung aller Eingaben
- Optional: XGBoost-Installation (mit macOS libomp-Hinweis)

---

### `pvforecast doctor`

System-Diagnose und Healthcheck.

```bash
pvforecast doctor
```

**Keine Optionen.**

**Ausgabe:**

```
🔍 PV-Forecast Systemcheck
══════════════════════════════════════════════════

 ✓ Python: 3.11.4
 ✓ pvforecast: 0.1.0
 ✓ Config: ~/.config/pvforecast/config.yaml
 ✓ Standort: Dülmen PV (9.92 kWp)
   └─ 51.85°N, 7.26°E
 ✓ Datenbank: 62,212 PV / 62,256 Wetter
   └─ Zeitraum: 2019-01-01 bis 2026-02-05
 ✓ Modell: xgb (MAE: 111W)
   └─ MAPE: 30.3%
 ✓ XGBoost: 2.1.4
 ✓ libomp: Installiert (Homebrew)
 ✓ Netzwerk: Open-Meteo API erreichbar

✅ Alles OK!
```

**Checks:**
- Python-Version
- pvforecast-Version
- Config-Datei (Existenz & Validität)
- Standort-Einstellungen
- Datenbank (PV/Wetter-Datensätze, Zeitraum)
- Modell (Typ, MAE, MAPE)
- XGBoost-Installation
- libomp (nur macOS)
- Netzwerk-Konnektivität (Open-Meteo API)

**Exit-Codes:**
- `0`: Alles OK
- `1`: Warnungen vorhanden
- `2`: Fehler vorhanden

---

### `pvforecast today`

Prognose für den heutigen Tag (vergangene + kommende Stunden).

```bash
pvforecast today
```

**Keine zusätzlichen Optionen.**

---

### `pvforecast predict`

Prognose für kommende Tage (ab morgen).

```bash
pvforecast predict [OPTIONEN]
```

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--days N` | Anzahl Tage ab morgen | 2 |
| `--format FORMAT` | Ausgabeformat: `table`, `json`, `csv` | `table` |

**Beispiele:**

```bash
# Standard: morgen + übermorgen
pvforecast predict

# 5 Tage Prognose
pvforecast predict --days 5

# Als JSON (für Weiterverarbeitung)
pvforecast predict --format json

# Als CSV
pvforecast predict --format csv > forecast.csv
```

---

### `pvforecast import`

Importiert PV-Daten aus E3DC CSV-Exporten.

```bash
pvforecast import <DATEIEN>
```

| Argument | Beschreibung |
|----------|--------------|
| `DATEIEN` | Eine oder mehrere CSV-Dateien |

**Beispiele:**

```bash
# Einzelne Datei
pvforecast import E3DC-Export-2024.csv

# Mehrere Dateien
pvforecast import E3DC-Export-*.csv

# Mit absolutem Pfad
pvforecast import ~/Downloads/E3DC-Export-2024-01.csv
```

**Ausgabe (mit Progress und Timing):**

```
[1/3] E3DC-Export-2024.csv: 8782 neue Datensätze
[2/3] E3DC-Export-2025.csv: 8758 neue Datensätze
[3/3] E3DC-Export-2026.csv: 858 neue Datensätze
✅ Import abgeschlossen in 1s: 18398 neue Datensätze
   Datenbank: ~/.local/share/pvforecast/data.db
   Gesamt in DB: 62212 PV-Datensätze
```

---

### `pvforecast train`

Trainiert das ML-Modell auf den importierten Daten.

```bash
pvforecast train [OPTIONEN]
```

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--model MODEL` | Modell-Typ: `rf` (RandomForest) oder `xgb` (XGBoost) | `rf` |

**Beispiele:**

```bash
# RandomForest (Standard, keine zusätzliche Dependency)
pvforecast train

# XGBoost (benötigt: pip install pvforecast[xgb])
pvforecast train --model xgb
```

**Hinweis:** Beim Training werden automatisch fehlende historische Wetterdaten von Open-Meteo geladen.

---

### `pvforecast tune`

Hyperparameter-Tuning mit RandomizedSearchCV.

```bash
pvforecast tune [OPTIONEN]
```

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--model MODEL` | Modell-Typ: `rf` oder `xgb` | `xgb` |
| `--trials N` | Anzahl der Kombinationen | 50 |
| `--cv N` | Anzahl der Cross-Validation Splits | 5 |

**Beispiele:**

```bash
# XGBoost Tuning (Standard)
pvforecast tune

# RandomForest Tuning (dauert länger!)
pvforecast tune --model rf

# Mehr Iterationen für bessere Ergebnisse
pvforecast tune --trials 100

# Schneller Test
pvforecast tune --trials 10 --cv 3
```

**Ausgabe (mit Timing):**

```
🔧 Hyperparameter-Tuning für XGBoost
   Iterationen: 50
   CV-Splits: 5

⏳ Das kann einige Minuten dauern...

==================================================
✅ Tuning abgeschlossen in 4m 23s!
==================================================

📊 Performance:
   MAPE: 30.3%
   MAE:  111 W
   CV-Score (MAE): 201 W

🎯 Beste Parameter:
   colsample_bytree: 0.8782
   learning_rate: 0.0504
   max_depth: 10
   min_child_weight: 4
   n_estimators: 112
   subsample: 0.6308

💾 Modell gespeichert: ~/.local/share/pvforecast/model.pkl
```

**Dauer:**
- XGBoost: ~2-5 Minuten (50 Trials)
- RandomForest: ~10-15 Minuten (50 Trials)

---

### `pvforecast evaluate`

Evaluiert die Modell-Performance mit Backtesting.

```bash
pvforecast evaluate [OPTIONEN]
```

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--year JAHR` | Nur Daten aus diesem Jahr evaluieren | alle |

**Beispiele:**

```bash
# Evaluation auf allen Daten
pvforecast evaluate

# Nur 2024 evaluieren
pvforecast evaluate --year 2024
```

---

### `pvforecast status`

Zeigt Status der Datenbank und des Modells.

```bash
pvforecast status
```

**Ausgabe:**

```
PV-Forecast Status
========================================

📍 Standort:
   Dülmen PV
   51.83°N, 7.28°E
   9.92 kWp

📊 Datenbank:
   PV-Datensätze: 62,212
   Wetterdaten:   62,256
   Zeitraum:      2019-01-01 bis 2026-02-05

🧠 Modell:
   Typ:     XGBoost
   MAPE:    30.3%
   MAE:     111 W
   Erstellt: 2026-02-05 17:30
```

---

### `pvforecast config`

Konfiguration verwalten.

```bash
pvforecast config [OPTIONEN]
```

| Option | Beschreibung |
|--------|--------------|
| `--show` | Aktuelle Konfiguration anzeigen |
| `--init` | Config-Datei mit Defaults erstellen |
| `--path` | Pfad zur Config-Datei anzeigen |

**Beispiele:**

```bash
# Config anzeigen
pvforecast config --show

# Config-Datei erstellen
pvforecast config --init

# Pfad anzeigen
pvforecast config --path
# → ~/.config/pvforecast/config.yaml
```

---

## Kombinierte Beispiele

```bash
# Kompletter Workflow
pvforecast import ~/Downloads/E3DC-*.csv
pvforecast train --model xgb
pvforecast tune --trials 100
pvforecast predict --days 7 --format json > week.json

# Mit eigener Datenbank
pvforecast --db /tmp/test.db import data.csv
pvforecast --db /tmp/test.db train
pvforecast --db /tmp/test.db predict

# Für anderen Standort
pvforecast --lat 52.52 --lon 13.405 predict
```
