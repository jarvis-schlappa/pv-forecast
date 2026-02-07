# CLI-Referenz

Vollständige Dokumentation aller `pvforecast`-Befehle.

## Befehlsübersicht

| Befehl | Beschreibung |
|--------|--------------|
| [`setup`](#pvforecast-setup) | Interaktiver Einrichtungs-Assistent |
| [`doctor`](#pvforecast-doctor) | System-Diagnose und Healthcheck |
| [`today`](#pvforecast-today) | Prognose für heute |
| [`predict`](#pvforecast-predict) | Prognose für kommende Tage |
| [`fetch-forecast`](#pvforecast-fetch-forecast) | Wettervorhersage abrufen |
| [`fetch-historical`](#pvforecast-fetch-historical) | Historische Wetterdaten abrufen |
| [`import`](#pvforecast-import) | E3DC CSV importieren |
| [`train`](#pvforecast-train) | Modell trainieren |
| [`tune`](#pvforecast-tune) | Hyperparameter-Tuning |
| [`evaluate`](#pvforecast-evaluate) | Modell evaluieren |
| [`status`](#pvforecast-status) | Status anzeigen |
| [`config`](#pvforecast-config) | Konfiguration verwalten |

---

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

```text
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

```text
🔍 PV-Forecast Systemcheck
══════════════════════════════════════════════════

 ✓ Python: 3.11.4
 ✓ pvforecast: 0.1.0
 ✓ Config: ~/.config/pvforecast/config.yaml
 ✓ Standort: Dülmen PV (9.92 kWp)
   └─ 51.85°N, 7.26°E
 ✓ Datenbank: 62,212 PV / 62,256 Wetter
   └─ Zeitraum: 2019-01-01 bis 2026-02-06
 ✓ Modell: xgb (MAE: 144W)
   └─ MAPE: 30.1%
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
pvforecast today [OPTIONEN]
```

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--source SOURCE` | Wetterdaten-Quelle: `mosmix`, `open-meteo` | aus Config |

**Beispiele:**

```bash
# Standard (aus Config)
pvforecast today

# Mit DWD MOSMIX
pvforecast today --source mosmix

# Mit Open-Meteo
pvforecast today --source open-meteo
```

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
| `--source SOURCE` | Wetterdaten-Quelle: `mosmix`, `open-meteo` | aus Config |

**Beispiele:**

```bash
# Standard: morgen + übermorgen
pvforecast predict

# 5 Tage Prognose
pvforecast predict --days 5

# Mit DWD MOSMIX (Station Dülmen)
pvforecast predict --source mosmix --days 3

# Als JSON (für Weiterverarbeitung)
pvforecast predict --format json

# Als CSV
pvforecast predict --format csv > forecast.csv
```

**Datenquellen:**

| Quelle | Beschreibung | Horizont |
|--------|--------------|----------|
| `mosmix` | DWD MOSMIX (Station P0051 Dülmen) | +10 Tage |
| `open-meteo` | Open-Meteo API | +16 Tage |

---

### `pvforecast fetch-forecast`

Ruft Wettervorhersage-Daten ab und zeigt sie an (ohne Prognose).

```bash
pvforecast fetch-forecast [OPTIONEN]
```

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--source SOURCE` | Datenquelle: `mosmix`, `open-meteo` | aus Config |
| `--hours N` | Anzahl Stunden | 48 |
| `--format FORMAT` | Ausgabeformat: `table`, `json`, `csv` | `table` |

**Beispiele:**

```bash
# MOSMIX Vorhersage anzeigen
pvforecast fetch-forecast --source mosmix

# 72 Stunden als JSON
pvforecast fetch-forecast --source mosmix --hours 72 --format json
```

---

### `pvforecast fetch-historical`

Ruft historische Wetterdaten ab (für Training oder Analyse).

```bash
pvforecast fetch-historical [OPTIONEN]
```

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--source SOURCE` | Datenquelle: `hostrada`, `open-meteo` | aus Config |
| `--start YYYY-MM-DD` | Startdatum | 7 Tage vor Ende |
| `--end YYYY-MM-DD` | Enddatum | ~2 Monate vor heute |
| `--format FORMAT` | Ausgabeformat: `table`, `json`, `csv` | `table` |
| `-y, --yes` | Bestätigung überspringen | aus |

**Beispiele:**

```bash
# HOSTRADA für 2024
pvforecast fetch-historical --source hostrada --start 2024-01-01 --end 2024-12-31

# Ohne Bestätigung (für Automatisierung)
pvforecast fetch-historical --source hostrada --start 2020-01-01 --end 2024-12-31 --yes

# Als CSV exportieren
pvforecast fetch-historical --source hostrada --start 2024-01-01 --end 2024-12-31 --format csv > weather.csv
```

**Datenquellen:**

| Quelle | Beschreibung | Zeitraum | Auflösung |
|--------|--------------|----------|-----------|
| `hostrada` | DWD HOSTRADA (Rasterdaten) | 1995 - heute | 1 km, stündlich |
| `open-meteo` | Open-Meteo Historical | 1940 - heute | ~11 km, stündlich |

**⚠️ HOSTRADA Warnung:**

Bei HOSTRADA erscheint vor dem Download eine Warnung wegen der Datenmenge:

```
⚠️  HOSTRADA lädt komplette Deutschland-Raster herunter.
    Geschätzter Download: ~40.0 GB (7 Jahre × 5 Parameter)
    Extrahierte Daten: wenige MB (nur Gridpunkt 51.85°N, 7.26°E)

    Für regelmäßige Updates empfehlen wir Open-Meteo.
    HOSTRADA eignet sich für einmaliges Training mit historischen Daten.

Fortfahren? [y/N]: 
```

Mit `--yes` wird diese Bestätigung übersprungen.

**Performance-Vergleich:**

HOSTRADA liefert bessere Trainingsdaten als Open-Meteo:

| Metrik | Open-Meteo | HOSTRADA | Verbesserung |
|--------|------------|----------|--------------|
| MAE | 126 W | 105 W | -17% |
| MAPE | 31.3% | 21.9% | -9.4 PP |
| R² | 0.948 | 0.974 | +0.026 |

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

```text
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

Hyperparameter-Tuning mit RandomizedSearchCV oder Optuna.

```bash
pvforecast tune [OPTIONEN]
```

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--model MODEL` | Modell-Typ: `rf` oder `xgb` | `xgb` |
| `--method METHOD` | Tuning-Methode: `random` oder `optuna` | `random` |
| `--trials N` | Anzahl der Trials/Iterationen | 50 |
| `--cv N` | Anzahl der Cross-Validation Splits | 5 |
| `--timeout SECS` | Maximale Laufzeit in Sekunden (nur Optuna) | - |

#### Tuning-Methoden

**RandomizedSearchCV** (`--method random`, Default):
- Zufällige Suche im Parameter-Raum
- Schnell, einfach, gut für erste Experimente
- Alle Trials werden vollständig ausgeführt

**Optuna** (`--method optuna`):
- Bayesian Optimization (lernt aus vorherigen Trials)
- Pruning: Bricht aussichtslose Trials früh ab
- Bessere Konvergenz bei gleicher Trial-Anzahl
- Benötigt: `pip install pvforecast[tune]`

**Beispiele:**

```bash
# Standard: RandomizedSearchCV mit XGBoost
pvforecast tune

# Optuna mit Bayesian Optimization
pvforecast tune --method optuna

# Optuna mit Timeout (max 10 Minuten)
pvforecast tune --method optuna --trials 100 --timeout 600

# RandomForest Tuning
pvforecast tune --model rf

# Schneller Test
pvforecast tune --trials 10 --cv 3
```

**Ausgabe (Optuna):**

```text
🔧 Hyperparameter-Tuning für XGBoost
   Methode: Optuna
   Trials: 50
   CV-Splits: 5

⏳ Das kann einige Minuten dauern...

==================================================
✅ Tuning abgeschlossen in 1m 54s!
==================================================

📊 Performance:
   MAPE: 45.9%
   MAE:  169 W
   CV-Score (MAE): 199 W

📈 Optuna-Statistiken:
   Trials abgeschlossen: 24
   Trials gepruned: 26

🎯 Beste Parameter:
   n_estimators: 355
   max_depth: 7
   learning_rate: 0.0176
   min_child_weight: 4
   subsample: 0.7903
   colsample_bytree: 0.9033

💾 Modell gespeichert: ~/.local/share/pvforecast/model.pkl
```

#### Vergleich der Methoden

| Kriterium | RandomizedSearchCV | Optuna |
|-----------|-------------------|--------|
| Strategie | Zufällig | Bayesian (lernt) |
| Pruning | Nein | Ja |
| Typische Zeitersparnis | - | 30-50% |
| Installation | Inkludiert | `pip install pvforecast[tune]` |
| Empfohlen für | Schnelle Tests | Beste Ergebnisse |

**Dauer (50 Trials, 62k Datensätze):**
- RandomizedSearchCV: ~30 Sekunden
- Optuna: ~2 Minuten (aber 50% Trials gepruned)

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

```text
PV-Forecast Status
========================================

📍 Standort:
   Dülmen PV
   51.83°N, 7.28°E
   9.92 kWp

📊 Datenbank:
   PV-Datensätze: 62,212
   Wetterdaten:   62,256
   Zeitraum:      2019-01-01 bis 2026-02-06

🧠 Modell:
   Typ:     XGBoost
   MAPE:    30.1%
   MAE:     144 W
   Erstellt: 2026-02-06
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
