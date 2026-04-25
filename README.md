# PV-Forecast 🔆

Ertragsprognose für Photovoltaik-Anlagen auf Basis historischer Daten und Wettervorhersagen.

## Funktionen

- 📊 **Prognosen** für heute, morgen und beliebig viele Tage
- 🌤️ **Wetterdaten** aus DWD MOSMIX, HOSTRADA oder Open-Meteo
- 🧠 **ML-basiert** mit RandomForest oder XGBoost
- 🔧 **Hyperparameter-Tuning** für optimale Ergebnisse
- 💾 **E3DC Import** (CSV-Export direkt verwendbar)
- ⚙️ **Konfigurierbar** via CLI oder YAML-Datei

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/jarvis-schlappa/pv-forecast/main/install.sh | bash
```

Nach dem Download startet automatisch der **Setup-Wizard**:

```text
🔆 PV-Forecast Ersteinrichtung
══════════════════════════════════════

1️⃣  Standort
   Postleitzahl oder Ort: 44787
   → Bochum, NRW (51.48°N, 7.22°E) ✓

2️⃣  Anlage
   Peakleistung in kWp: 9.92 ✓

3️⃣  XGBoost installieren? [J/n]: j ✓

✅ Einrichtung abgeschlossen!
```

Fertig! `pvforecast` ist jetzt einsatzbereit.

### Windows

```powershell
# 1. WSL installieren (einmalig, PowerShell als Admin)
wsl --install

# 2. Neu starten, dann in WSL-Terminal:
curl -sSL https://raw.githubusercontent.com/jarvis-schlappa/pv-forecast/main/install.sh | bash
```

<details>
<summary><b>Manuelle Installation</b> (für Entwickler)</summary>

```bash
git clone https://github.com/jarvis-schlappa/pv-forecast.git
cd pv-forecast
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[xgb]"
pvforecast setup
```

</details>

**Voraussetzungen:** Python 3.9+, git

## Schnellstart

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
| `pvforecast doctor` | **System-Diagnose und Healthcheck** |
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

```text
PV-Ertragsprognose für Bochum PV (9.92 kWp)
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
| [SPEC.md](docs/SPEC.md) | Technische Spezifikation & Architektur |
| [**Glossar**](docs/GLOSSARY.md) | Alle Fachbegriffe verständlich erklärt |

## Performance

| Datenquelle | Modell | MAE | MAPE | R² |
|-------------|--------|-----|------|-----|
| **DWD HOSTRADA** | XGBoost | **105 W** | **21.9%** | **0.974** |
| Open-Meteo | XGBoost | 126 W | 30.1% | 0.950 |

*Stand: Februar 2026, XGBoost nach Feature-Engineering*

**Empfehlung:** HOSTRADA für Training (beste Qualität), Open-Meteo für Updates (geringere Latenz).

👉 **Details:** [docs/MODELS.md](docs/MODELS.md) | [docs/CONFIG.md](docs/CONFIG.md#wetterdaten-quellen)

## Entwicklung

```bash
# Dev-Dependencies
pip install -e ".[dev]"

# Tests
pytest

# Linting
ruff check src/
```

## Lizenz

MIT

## Wetterdaten

| Quelle | Typ | Beschreibung |
|--------|-----|--------------|
| **DWD MOSMIX** | Prognose | 10-Tage-Vorhersage, stündlich, offizielle DWD-Daten |
| **DWD HOSTRADA** | Historie | Seit 1995, 1 km Raster, ideal für Training |
| **Open-Meteo** | Beides | Kostenlose API, Fallback, gut für schnelle Updates |

**Empfehlung:**
- Training: HOSTRADA (beste Datenqualität)
- Prognose: MOSMIX (offizielle DWD-Vorhersage) oder Open-Meteo (schneller)
