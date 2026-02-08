# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [0.4.2] - 2026-02-08

### Behoben

- **DHI-Schätzung physikalisch korrekt** (#163, #164) – Clearness Index wird jetzt aus GHI/GHI_extraterrestrisch berechnet statt aus Bewölkung approximiert
  - Behebt Train/Inference-Inkonsistenz zwischen MOSMIX und HOSTRADA
  - **MAPE verbessert: 29.3% → 22.3% (−7.0%)**
  - **MAE verbessert: 140W → 107W (−33W)**
  - **Skill Score: +69.4% → +76.7%**
  - Besonders wirksam bei atypischen Wetterbedingungen (Dunst, Cirrus)

### Geändert

- **Breaking:** `estimate_dhi()` Signatur geändert
  - Alt: `estimate_dhi(ghi, cloud_cover_pct, sun_elevation)`
  - Neu: `estimate_dhi(ghi, sun_elevation, timestamp)`
  - Betrifft nur interne API, keine CLI-Änderungen

### Hinweis

Nach Update sollte das Modell neu trainiert werden:
```bash
pvforecast train --model xgb
```

## [0.4.1] - 2026-02-08

### Hinzugefügt

- **GUI Mockup** – Interaktiver HTML/React Prototyp für geplante NiceGUI-Oberfläche
  - 6 Seiten: Dashboard, Prognose, Training, Evaluation, Daten, Einstellungen
  - Dark Theme mit IBM Plex Fonts
  - Screenshots direkt auf GitHub sichtbar (`gui/README.md`)

- **GUI-Framework-Analyse** – Vergleich NiceGUI vs. Streamlit vs. Dash (`docs/GUI-ANALYSIS.md`)

- **Glossar** – Erklärung aller Fachbegriffe und Metriken (`docs/GLOSSARY.md`)

### Behoben

- **Setup: XGBoost nach Installation verfügbar** (#161) – `reload_xgboost()` aktualisiert Import-Cache nach pip-Installation
- **Setup: MAPE-Anzeige korrigiert** (#162) – Wurde doppelt mit 100 multipliziert (2237% statt 22%)
- **Setup: XGBoost-Verfügbarkeit vor Training prüfen** (#160)
- **Setup: HOSTRADA Dateinamen-Parsing** (#158) – Hex-Prefixe werden korrekt ignoriert
- **Setup: Korrekte Argumente an train()** (#154)

### Verbessert

- **Setup: Fortschrittsbalken für HOSTRADA-Import** (#159) – Zeigt Monat und Prozent
- **Setup: HOSTRADA sofort laden** (#157) – Wetterdaten können direkt in DB importiert werden
- **Setup: Wetterdaten vor Training prüfen** (#157) – Bietet Nachladen an wenn keine vorhanden
- **Setup: UX-Verbesserungen** (#149-#152) – Training nach Import, Dependency-Checks

### Dokumentation

- SPEC.md nach `docs/` verschoben
- CLI.md mit `--quiet` Flag aktualisiert
- PROJECT-STATUS.md und METRIKEN-ERKLAERT.pdf entfernt (ersetzt durch GLOSSARY.md)

## [0.4.0] - 2026-02-08

### Hinzugefügt

- **`--quiet` Flag** – Reduzierte Ausgabe für Skripte und Cronjobs (#134, #142, #144)
  - `pvforecast today --quiet` → `12.4 kWh`
  - `pvforecast train --quiet` → `✅ Training: MAPE 30.1%, MAE 144W`
  - Verfügbar für: today, train, tune, import

- **`--since` Filter** – Training/Tuning nur mit Daten ab Jahr X (#76)
  - `pvforecast train --since 2022`
  - `pvforecast tune --since 2023`

- **SQLite WAL Mode** – Bessere Concurrency bei parallelen Zugriffen (#133)

- **MOSMIX Humidity** – Berechnet Luftfeuchtigkeit aus Taupunkt (#146)

### Geändert

- **CLI Refactoring** – `cli.py` (1654 LOC) aufgeteilt in `cli/` Package (#131, #148)
  - `cli/commands.py` – Business-Logik
  - `cli/parser.py` – Argument-Parsing
  - `cli/formatters.py` – Ausgabe-Formatierung
  - `cli/helpers.py` – Source-Helper

- **Open-Meteo Migration** – In Sources-Framework integriert (#147)

- **`load_training_data()` extrahiert** – Bessere Modularität in model.py (#145)

- **Performance:** `itertuples()` statt `iterrows()` (~3x schneller) (#135, #138)

### Behoben

- **Security: SQL Injection** – Parametrisierte Queries für `--since` Filter (#113, #141)
- **`mode=today` mit Produktions-Lags** – Korrekte Prognose für heute (#129, #143)
- **`model_version` in Forecast** – Version wird korrekt übergeben (#128, #140)
- **`cmd_reset` AttributeError** – Robustere Fehlerbehandlung (#127, #139)
- **`degrees()` statt Konstante** – Korrektes Radians-zu-Degrees (#115, #136)
- **`--quiet` nach Subcommand** – Flag-Position flexibel (#144)

### Dokumentation

- **Docs Cleanup** – 8 veraltete Planungsdokumente entfernt (-62%)
- **CLI.md aktualisiert** – `--quiet` und `--since` dokumentiert

---

## [0.3.0] - 2026-02-07

### Hinzugefügt

- **`today --full`** – Zeigt ganzen Tag inkl. vergangener Stunden (#125)
  - Open-Meteo: Volle Unterstützung mit `past_hours`
  - MOSMIX: Info-Meldung (nur Prognosen ab jetzt verfügbar)

- **Lokale HOSTRADA-Dateien** – NetCDF-Dateien aus lokalem Verzeichnis laden
  - `pvforecast setup` fragt nach lokalem Verzeichnis
  - Erkennt bereits heruntergeladene Dateien (kein erneuter Download)

- **Wildcards beim Import** – `pvforecast import ~/Downloads/E3DC*.csv`

- **Automatische Versionierung** – Version aus Git-Tags via hatch-vcs
  - Releases: `v0.3.0` → `0.3.0`
  - Entwicklung: `0.3.1.dev5+g<hash>`

### Behoben

- **KRITISCH: `fetch-historical` speichert jetzt Daten in DB**
  - Bug: Daten wurden geladen und angezeigt, aber nie persistiert
  - Jetzt: Automatischer INSERT OR REPLACE nach Fetch

- **Installer:** Alle interaktiven Prompts lesen von `/dev/tty` (curl|bash kompatibel)
- **Installer:** Bessere Fehlerbehandlung und Validierung

### Geändert

- `fetch-historical` zeigt keine Tabelle mehr (nur DB-Speicherung)
- README: Alle Wetterdatenquellen dokumentiert (MOSMIX, HOSTRADA, Open-Meteo)

---

## [0.2.1] - 2026-02-07

### Behoben

- **HOSTRADA:** `cache_dir` Parameter entfernt (Stream-Processing braucht keinen Cache)
- **HOSTRADA:** Duplikat-Erkennung - bereits geladene Monate werden übersprungen
- **CLI:** `--force` Flag für `fetch-historical` um Duplikat-Check zu umgehen

### Hinzugefügt

- **Testkonzept:** `docs/TESTING_REAL_SYSTEM.md` mit 70+ Testfällen
  - Funktionale Tests für alle CLI-Befehle
  - Robustheitstests (Datenintegrität, Zeitzonen, Parallelität, Interrupts)

---

## [0.2.0] - 2026-02-07

### Hinzugefügt

- **DWD MOSMIX Forecasts** – Offizielle DWD-Vorhersagen als Alternative zu Open-Meteo (#123)
  - `pvforecast predict --source mosmix` / `pvforecast today --source mosmix`
  - `pvforecast fetch-forecast --source mosmix` für Rohdaten-Abruf
  - KML-Parser mit DHI-Schätzung (Erbs-Modell)
  - Konfigurierbare MOSMIX-Station (Standard: P0051/Dülmen)

- **DWD HOSTRADA Historische Daten** – 1km-Rasterdaten für Training (#123)
  - `pvforecast fetch-historical --source hostrada`
  - Stream-Processing: Download → Extract → Delete (kein 63 GB Cache)
  - Fortschrittsanzeige und Download-Warnung mit Bestätigung
  - NetCDF-Parser mit xarray

- **Neue Dependencies:** xarray, netCDF4, scipy (für DWD-Quellen)

### Geändert

- **Performance mit HOSTRADA-Training deutlich besser:**
  
  | Metrik | Open-Meteo | HOSTRADA | Verbesserung |
  |--------|------------|----------|--------------|
  | MAE | 126 W | 105 W | **-17%** |
  | MAPE | 31.3% | 21.9% | **-9.4 PP** |
  | R² | 0.948 | 0.974 | +0.026 |

- Dokumentation erweitert (CLI.md, CONFIG.md, MODELS.md, neue ARCHITECTURE_DWD.md)

### Behoben

- Ruff Lint-Fehler in src/ und tests/

---

## [0.1.1] - 2026-02-06

### Hinzugefügt

- **Optuna Tuning** (`pvforecast tune --method optuna`) – Bayesian Optimization mit Pruning (#29)
- **Feature Engineering** für bessere Prognosen (#80-#83):
  - Zyklische Features (Stunde, Monat, Tag im Jahr)
  - Effective Irradiance, Clear-Sky-Index, Diffuse Fraction
  - Lag-Features (Wetter + Produktion der letzten Stunden)
  - Modultemperatur + Temperatur-Derating
  - peak_kwp Normalisierung (Vorbereitung Multi-Anlagen)

### Geändert

- **Performance verbessert:** MAPE 41.7% → 30.1% (-11.6%)

### Behoben

- CI: fetch_today Tests auf Python 3.11+ (#109)

---

## [0.1.0] - 2026-02-05

Erstes Release von PV-Forecast. 🎉

### Hinzugefügt

#### Kernfunktionen
- **Prognosen** für heute (`pvforecast today`) und kommende Tage (`pvforecast predict`)
- **E3DC CSV-Import** mit automatischer Erkennung und Deduplizierung
- **Wetter-Integration** via Open-Meteo API (kostenlos, kein API-Key nötig)
- **SQLite-Datenbank** für PV- und Wetterdaten

#### Machine Learning
- **RandomForest** Modell (Standard, keine zusätzliche Dependency)
- **XGBoost** Modell (optional, bessere Genauigkeit)
- **Hyperparameter-Tuning** mit RandomizedSearchCV (`pvforecast tune`)
- **Backtesting/Evaluation** (`pvforecast evaluate`)
- Erweiterte Wetter-Features: Wind, Luftfeuchtigkeit, Diffusstrahlung

#### Benutzerfreundlichkeit
- **Interaktiver Setup-Wizard** (`pvforecast setup`) mit Geocoding
- **System-Diagnose** (`pvforecast doctor`) für Healthchecks
- **One-Liner Installation** via curl
- Progress-Anzeigen und Timing für lange Operationen
- Benutzerfreundliche Fehlermeldungen mit Lösungsvorschlägen

#### Dokumentation
- Vollständige CLI-Referenz (`docs/CLI.md`)
- Konfigurationsanleitung (`docs/CONFIG.md`)
- Datenformat-Dokumentation (`docs/DATA.md`)
- ML-Modelle und Tuning (`docs/MODELS.md`)

### Performance

| Modell | MAE | MAPE |
|--------|-----|------|
| XGBoost (tuned) | 144 W | 30.1% |
| RandomForest | ~180 W | ~45% |

*Getestet mit 62.000 Datensätzen (2019-2026), MAPE nur für Stunden >100W.*

---

[0.4.0]: https://github.com/jarvis-schlappa/pv-forecast/releases/tag/v0.4.0
[0.3.0]: https://github.com/jarvis-schlappa/pv-forecast/releases/tag/v0.3.0
[0.2.1]: https://github.com/jarvis-schlappa/pv-forecast/releases/tag/v0.2.1
[0.2.0]: https://github.com/jarvis-schlappa/pv-forecast/releases/tag/v0.2.0
[0.1.1]: https://github.com/jarvis-schlappa/pv-forecast/releases/tag/v0.1.1
[0.1.0]: https://github.com/jarvis-schlappa/pv-forecast/releases/tag/v0.1.0
