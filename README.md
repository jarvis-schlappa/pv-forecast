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

### Quick Install (empfohlen)

```bash
curl -sSL https://raw.githubusercontent.com/jarvis-schlappa/pv-forecast/main/install.sh | bash
```

Das Script:
- Prüft Abhängigkeiten (Python 3.9+, git, pip)
- Installiert nach `~/pv-forecast`
- Erstellt einen Wrapper für direkten `pvforecast`-Aufruf
- Startet den interaktiven Setup-Wizard

### Manuelle Installation

```bash
# Repository klonen
git clone https://github.com/jarvis-schlappa/pv-forecast.git
cd pv-forecast

# Virtual Environment
python3 -m venv .venv
source .venv/bin/activate

# Installation
pip install -e .

# Einrichtung
pvforecast setup

# Optional: XGBoost Support (bessere Genauigkeit)
pip install -e ".[xgb]"
```

### Windows

Das Install-Script läuft nicht nativ auf Windows. Nutze WSL:

```powershell
# 1. WSL installieren (PowerShell als Admin)
wsl --install

# 2. Neu starten, dann in WSL-Terminal:
curl -sSL https://raw.githubusercontent.com/jarvis-schlappa/pv-forecast/main/install.sh | bash
```

**Voraussetzungen:** Python 3.9+, git

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
| `pvforecast setup` | **Interaktiver Einrichtungs-Assistent** |
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
| **XGBoost (tuned)** | **111 W** | **30.3%** |
| RandomForest | 168 W | ~46% |

*MAPE nur für Stunden >100W. Mit erweiterten Wetter-Features (Wind, Humidity, DHI).*

## Entwicklung

```bash
# Dev-Dependencies
pip install -e ".[dev]"

# Tests (158 Tests)
pytest

# Linting
ruff check src/
```

## Lizenz

MIT

## Credits

- Wetterdaten: [Open-Meteo](https://open-meteo.com/)
