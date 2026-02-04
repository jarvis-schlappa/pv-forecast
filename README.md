# PV-Forecast 🔆

Ertragsprognose für Photovoltaik-Anlagen auf Basis historischer Daten und Wettervorhersagen.

## Features

- 📊 **Prognosen** für heute, morgen und beliebig viele Tage
- 🌤️ **Wetterintegration** via Open-Meteo API (kostenlos)
- 🧠 **ML-basiert** mit RandomForest oder XGBoost
- 🔧 **Hyperparameter-Tuning** für optimale Ergebnisse
- 💾 **E3DC Import** (CSV-Export direkt verwendbar)
- ⚙️ **Konfigurierbar** via CLI oder YAML-Datei

## Installation

```bash
# Repository klonen
git clone https://github.com/jarvis-schlappa/pv-forecast.git
cd pv-forecast

# Virtual Environment
python3 -m venv .venv
source .venv/bin/activate

# Installation
pip install -e .

# Optional: XGBoost Support
pip install -e ".[xgb]"
```

**Voraussetzungen:** Python 3.9+

## Quickstart

```bash
# 1. Historische PV-Daten importieren
pvforecast import ~/Downloads/E3DC-Export-*.csv

# 2. Modell trainieren
pvforecast train

# 3. Prognose erstellen
pvforecast today      # Prognose für heute
pvforecast predict    # Prognose für morgen + übermorgen
```

## Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `pvforecast today` | Prognose für heute |
| `pvforecast predict` | Prognose für morgen + übermorgen |
| `pvforecast import <csv>` | E3DC CSV importieren |
| `pvforecast train` | Modell trainieren |
| `pvforecast tune` | Hyperparameter-Tuning |
| `pvforecast evaluate` | Modell evaluieren |
| `pvforecast status` | Status anzeigen |
| `pvforecast config` | Konfiguration verwalten |

👉 **Alle Befehle mit Optionen:** [docs/CLI.md](docs/CLI.md)

## Beispiel-Output

```
PV-Ertragsprognose für Dülmen PV (9.92 kWp)
Erstellt: 04.02.2026 21:00

════════════════════════════════════════════════════════════
Zusammenfassung
────────────────────────────────────────────────────────────
  05.02.:    12.8 kWh
  06.02.:     8.3 kWh
  ────────────────────
  Gesamt:    21.1 kWh

════════════════════════════════════════════════════════════
Stundenwerte
────────────────────────────────────────────────────────────
  Zeit           Ertrag   Wetter
  ───────────────────────────────────
  05.02. 09:00     318 W   ☁️
  05.02. 10:00    1083 W   ⛅
  05.02. 11:00    1858 W   🌤️
  05.02. 12:00    2352 W   ☀️
  ...
```

## Dokumentation

| Dokument | Inhalt |
|----------|--------|
| [CLI.md](docs/CLI.md) | Alle Befehle mit allen Optionen |
| [CONFIG.md](docs/CONFIG.md) | Konfiguration (CLI & YAML) |
| [MODELS.md](docs/MODELS.md) | ML-Modelle, Training, Tuning |
| [DATA.md](docs/DATA.md) | Datenformat, E3DC Import |

## Performance

| Modell | MAE | MAPE* |
|--------|-----|-------|
| **XGBoost (tuned)** | **117 W** | **29.4%** |
| RandomForest | 183 W | ~45% |

*MAPE nur für Stunden >100W. Mit erweiterten Wetter-Features (Wind, Humidity, DHI).*

## Entwicklung

```bash
# Dev-Dependencies
pip install -e ".[dev]"

# Tests (88 Tests)
pytest

# Linting
ruff check src/
```

## Lizenz

MIT

## Credits

- Wetterdaten: [Open-Meteo](https://open-meteo.com/)
