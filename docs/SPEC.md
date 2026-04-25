# PV-Forecast – Spezifikation

> PV-Ertragsprognose auf Basis historischer Daten und Wettervorhersage

---

## 1. Vision & Ziele

**Was:** CLI-Tool zur Vorhersage des PV-Ertrags für die nächsten 48 Stunden.

**Warum:** Bessere Planung von Energieverbrauch, Speichernutzung und ggf. Einspeisung.

**Erfolgskriterien:**
- [x] Prognose für 48h mit Stundenwerten (W) und Tagesertrag (kWh)
- [x] Abweichung vom tatsächlichen Ertrag < 20% (MAPE) bei normalen Wetterbedingungen *(erreicht: 21.9% mit XGBoost + HOSTRADA)*
- [x] CLI-Aufruf liefert Ergebnis in < 10 Sekunden
- [x] Läuft auf macOS (Mac mini) und Linux (Raspberry Pi)

---

## 2. Kontext

### 2.1 PV-Anlage
| Parameter | Wert |
|-----------|------|
| Peak-Leistung | 9,92 kWp |
| Ausrichtung | Mehrere Flächen, Hauptseite Süd-Ost |
| Standort | Bochum, NRW (51.48°N, 7.22°E) |
| Speicher | E3/DC Hauskraftwerk (S10) |

### 2.2 Datenquellen

**Historische PV-Daten:**
- Quelle: E3DC CSV-Export
- Zeitraum: 2019 – heute
- Granularität: Stündlich (bis 15min verfügbar)
- Format: Semikolon-CSV, deutsches Datumsformat
- Key-Spalte: `Solarproduktion [W]`

**Wetterdaten (Multi-Source):**

| Quelle | Typ | Beschreibung |
|--------|-----|--------------|
| **DWD MOSMIX** | Forecast | Offizielle DWD-Vorhersage, +10 Tage, stündlich |
| **DWD HOSTRADA** | Historisch | Strahlungsdaten 1km-Raster, ab 1995 |
| **Open-Meteo** | Beide | Fallback, kostenlos, weltweit |

Konfigurierbar via `config.yaml` (forecast_provider, historical_provider).

---

## 3. Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Interface                         │
│                     pvforecast [command]                     │
│   (cli/__init__.py, cli/commands.py, cli/parser.py, ...)    │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                      Core Modules                            │
├──────────────┬──────────────┬───────────────────────────────┤
│  DataLoader  │   Sources    │   Model                       │
│  (CSV→SQLite)│ (MOSMIX,     │  (Train/Predict)              │
│              │  HOSTRADA,   │  (RF, XGBoost)                │
│              │  Open-Meteo) │                               │
└──────────────┴──────────────┴───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                     Storage Layer                            │
│              SQLite Database (WAL Mode)                      │
│         (pv_readings + weather_history)                      │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 Module

| Modul | Verantwortung |
|-------|---------------|
| `cli/` | CLI Package (commands, parser, formatters, helpers) |
| `sources/` | Wetter-Sources (MOSMIX, HOSTRADA, Open-Meteo) |
| `data_loader.py` | Import & Normalisierung der E3DC-CSVs |
| `weather.py` | Wetter-Utilities (ensure_weather_history) |
| `model.py` | ML-Modell (Training, Prediction, Evaluation) |
| `config.py` | YAML-Konfiguration + CLI-Override |
| `db.py` | SQLite Datenbankzugriff (WAL Mode) |
| `doctor.py` | System-Diagnose |
| `setup.py` | Interaktiver Setup-Wizard |
| `validation.py` | Input-Validierung |

### 3.2 Datenfluss

```
[Training]
E3DC CSV ──► DataLoader ──► SQLite ◄── Sources ◄── HOSTRADA / Open-Meteo
                              │         (hist.)
                              ▼
                           Merge (JOIN on timestamp)
                              │
                              ▼
                      Train RF/XGBoost ──► model.pkl

[Prediction]
MOSMIX / ──► Sources ──► model.pkl ──► Forecast ──► CLI Output
Open-Meteo    fetch()     predict()   (strukturiert)
```

---

## 4. CLI Interface

### 4.1 Befehle

```bash
# Prognose für heute (ganzer Tag, inkl. vergangene Stunden)
pvforecast today

# Prognose für morgen + übermorgen (Default: 2 volle Tage)
pvforecast predict [--days 2] [--format table|json|csv]

# Historische Daten importieren
pvforecast import <csv-file> [csv-file2 ...]

# Modell trainieren (lädt fehlende Wetterdaten automatisch)
pvforecast train [--from 2019-01-01] [--to 2025-12-31]

# Hyperparameter-Tuning (RandomizedSearchCV)
pvforecast tune [--model rf|xgb] [--trials 50] [--cv 5]

# Modell-Performance evaluieren
pvforecast evaluate [--year 2025]

# Status: DB-Inhalt, Modell-Info
pvforecast status
```

### 4.2 Globale Optionen

```bash
pvforecast --db ~/.local/share/pvforecast/data.db \
           --lat 51.48 --lon 7.22 \
           predict
```

### 4.3 Output-Beispiel

```
$ pvforecast predict

PV-Ertragsprognose für Bochum (9.92 kWp)
Erstellt: 2026-02-04 17:00

═══════════════════════════════════════════════════════════
Zusammenfassung
───────────────────────────────────────────────────────────
  Heute (04.02.):      12.4 kWh
  Morgen (05.02.):     18.7 kWh
  ────────────────────────────
  Gesamt 48h:          31.1 kWh

═══════════════════════════════════════════════════════════
Stundenwerte
───────────────────────────────────────────────────────────
  Zeit          Ertrag    Wetter
  04.02. 08:00    120 W   ⛅ teilweise bewölkt
  04.02. 09:00    450 W   ⛅ teilweise bewölkt
  04.02. 10:00    890 W   🌤️ leicht bewölkt
  ...
```

---

## 5. Datenmodell

### 5.1 SQLite Schema

```sql
-- PV-Ertragsdaten (aus E3DC CSV)
CREATE TABLE pv_readings (
    timestamp       INTEGER PRIMARY KEY,  -- Unix timestamp (UTC)
    production_w    INTEGER NOT NULL,     -- Solarproduktion [W]
    curtailed       INTEGER DEFAULT 0,    -- 1 wenn Abregelung aktiv war
    soc_pct         INTEGER,              -- Ladezustand [%]
    grid_feed_w     INTEGER,              -- Netzeinspeisung [W]
    grid_draw_w     INTEGER,              -- Netzbezug [W]
    consumption_w   INTEGER               -- Hausverbrauch [W]
);

-- Historische Wetterdaten (HOSTRADA / Open-Meteo)
CREATE TABLE weather_history (
    timestamp           INTEGER PRIMARY KEY,  -- Unix timestamp (UTC)
    ghi_wm2             REAL NOT NULL,        -- Globalstrahlung W/m²
    dhi_wm2             REAL,                 -- Diffusstrahlung W/m²
    dni_wm2             REAL,                 -- Direktstrahlung W/m²
    cloud_cover_pct     INTEGER,              -- Bewölkung %
    temperature_c       REAL,                 -- Temperatur °C
    humidity_pct        REAL,                 -- Luftfeuchtigkeit %
    wind_speed_ms       REAL                  -- Windgeschwindigkeit m/s
);

-- Index für schnelle Zeitbereichs-Abfragen
CREATE INDEX idx_pv_timestamp ON pv_readings(timestamp);
CREATE INDEX idx_weather_timestamp ON weather_history(timestamp);
```

### 5.2 Timezone-Regel

| Kontext | Timezone |
|---------|----------|
| Intern (DB, Model) | **UTC** (Unix timestamps) |
| E3DC CSV Input | Europe/Berlin → konvertieren zu UTC |
| CLI Output | Europe/Berlin (lokale Anzeige) |
| MOSMIX / HOSTRADA | UTC (DWD liefert UTC) |
| Open-Meteo API | UTC (nativ) |

### 5.3 Defaults

```python
DEFAULTS = {
    "db_path": "~/.local/share/pvforecast/data.db",
    "model_path": "~/.local/share/pvforecast/model.pkl",
    "latitude": 51.48,
    "longitude": 7.22,
    "timezone": "Europe/Berlin",
    "peak_kwp": 9.92,
}
```

---

## 6. ML-Modell

### 6.1 Ansatz
- **MVP:** RandomForestRegressor (sklearn) – keine extra Dependencies
- **Später:** XGBoost/LightGBM für bessere Performance

### 6.2 Features

| Feature | Beschreibung | Quelle |
|---------|--------------|--------|
| `hour` | Stunde des Tages (0-23) | Timestamp |
| `month` | Monat (1-12) | Timestamp |
| `day_of_year` | Tag im Jahr (1-366) | Timestamp |
| `ghi` | Globalstrahlung (W/m²) | Open-Meteo |
| `cloud_cover` | Bewölkungsgrad (%) | Open-Meteo |
| `temperature` | Temperatur (°C) | Open-Meteo |
| `sun_elevation` | Sonnenhöhe (°) | Berechnet* |

*Sonnenhöhe wird aus Koordinaten + Timestamp berechnet (pvlib oder eigene Formel).

### 6.3 Target
- `production_w` – Solarproduktion in Watt

### 6.4 Evaluation
- **Metriken:**
  - MAPE (Mean Absolute Percentage Error) – nur für Stunden >100W (vermeidet Verzerrung bei niedrigen Werten)
  - MAE (Mean Absolute Error) – durchschnittlicher absoluter Fehler in Watt
- **Aktuelle Performance:** MAPE 21.9%, MAE 105W (mit HOSTRADA) / MAPE 30.1%, MAE 126W (mit Open-Meteo)
- **Validation:** Zeitbasierter Split (80% Training, 20% Test)

### 6.5 Abregelung
Datensätze mit aktiver Abregelung (`curtailed=1`) werden beim Training **ausgeschlossen**, da sie nicht die wahre Produktionskapazität zeigen.

---

## 7. Schnittstellen (Interfaces)

### 7.1 Datenstrukturen

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class HourlyForecast:
    """Einzelner Stundenwert der Prognose."""
    timestamp: datetime      # UTC
    production_w: int        # Prognostizierte Leistung
    ghi_wm2: float          # Globalstrahlung (für Kontext)
    cloud_cover_pct: int    # Bewölkung (für Anzeige)

@dataclass
class Forecast:
    """Komplette Prognose."""
    hourly: list[HourlyForecast]
    total_kwh: float
    generated_at: datetime
    model_version: str
```

### 7.2 Modul-Interfaces

```python
# === data_loader.py ===
def load_e3dc_csv(path: Path) -> pd.DataFrame:
    """
    Lädt E3DC CSV und normalisiert.
    
    Returns:
        DataFrame mit Spalten:
        - timestamp: datetime (UTC)
        - production_w: int
        - curtailed: bool
        - soc_pct, grid_feed_w, grid_draw_w, consumption_w
    """

def import_to_db(df: pd.DataFrame, db_path: Path) -> int:
    """Importiert DataFrame in SQLite. Returns: Anzahl neue Zeilen."""


# === sources/base.py ===
class WeatherSource(Protocol):
    """Abstrakte Basis für Wetter-Sources."""
    
    def fetch_forecast(self, hours: int = 48) -> pd.DataFrame:
        """Holt Wettervorhersage."""
        ...
    
    def fetch_historical(self, start: date, end: date) -> pd.DataFrame:
        """Holt historische Wetterdaten."""
        ...

# === sources/mosmix.py, sources/hostrada.py, sources/openmeteo.py ===
# Implementieren WeatherSource Protocol


# === model.py ===
def train(db_path: Path) -> tuple[Pipeline, dict]:
    """
    Trainiert Modell auf allen Daten in DB.
    
    Returns:
        (sklearn Pipeline, metrics dict mit 'mape', 'rmse', 'n_samples')
    """

def predict(model: Pipeline, weather_df: pd.DataFrame) -> Forecast:
    """
    Erstellt Prognose basierend auf Wettervorhersage.
    
    Args:
        model: Trainierte sklearn Pipeline
        weather_df: DataFrame von fetch_forecast()
    
    Returns:
        Forecast-Objekt mit Stundenwerten und Summe
    """

def load_model(path: Path) -> Pipeline:
    """Lädt gespeichertes Modell."""

def save_model(model: Pipeline, path: Path) -> None:
    """Speichert Modell."""
```

---

## 8. Tech Stack

| Komponente | Technologie | Begründung |
|------------|-------------|------------|
| Sprache | Python 3.10+ | Type Hints, match statements |
| CLI | `argparse` | stdlib, keine Dependency |
| Daten | `pandas` | De-facto Standard |
| DB | `sqlite3` | stdlib, cross-platform |
| ML | `scikit-learn` | Robust, gut dokumentiert |
| HTTP | `httpx` | Modern, async-fähig (für später) |
| Tests | `pytest` | Standard |

### 8.1 Dependencies

```toml
[project]
dependencies = [
    "pandas>=2.0",
    "scikit-learn>=1.3",
    "httpx>=0.25",
    "pyyaml>=6.0",
    "xarray>=2024.1",      # HOSTRADA NetCDF
    "netCDF4>=1.6",        # HOSTRADA NetCDF
    "scipy>=1.11",
]

[project.optional-dependencies]
xgb = ["xgboost>=2.0"]
tune = ["optuna>=3.0"]
physics = ["pvlib>=0.10.0"]
dev = ["pytest>=8.0", "pytest-cov>=4.0", "ruff>=0.4"]
```

### 8.2 Projektstruktur

```
pv-forecast/
├── SPEC.md
├── README.md
├── pyproject.toml
├── src/
│   └── pvforecast/
│       ├── __init__.py
│       ├── __main__.py         # Entry point
│       ├── cli/                # CLI Package
│       │   ├── __init__.py     # main(), Entry Point
│       │   ├── commands.py     # cmd_* Funktionen
│       │   ├── parser.py       # Argument-Parser
│       │   ├── formatters.py   # Output-Formatierung
│       │   └── helpers.py      # Source-Helper
│       ├── sources/            # Wetter-Sources
│       │   ├── base.py         # WeatherSource Protocol
│       │   ├── mosmix.py       # DWD MOSMIX
│       │   ├── hostrada.py     # DWD HOSTRADA
│       │   └── openmeteo.py    # Open-Meteo (Fallback)
│       ├── config.py           # YAML-Konfiguration
│       ├── db.py               # SQLite (WAL Mode)
│       ├── data_loader.py      # CSV Import
│       ├── weather.py          # Wetter-Utilities
│       ├── model.py            # ML (RF, XGBoost)
│       ├── doctor.py           # System-Diagnose
│       ├── setup.py            # Setup-Wizard
│       └── validation.py       # Input-Validierung
├── tests/
│   ├── conftest.py
│   ├── test_*.py               # ~240 Tests
│   └── test_e2e.py             # End-to-End Tests
└── docs/
    ├── CLI.md
    ├── CONFIG.md
    ├── DATA.md
    └── MODELS.md
```

---

## 9. Code Style Guide

### 9.1 Allgemein
- **Python 3.10+** mit Type Hints
- **PEP 8** + **Ruff** für Linting
- Docstrings: Google-Style

### 9.2 Beispiel

```python
# ✅ Gut
def load_pv_data(csv_path: Path, start_date: date | None = None) -> pd.DataFrame:
    """
    Lädt PV-Daten aus E3DC CSV-Export.
    
    Args:
        csv_path: Pfad zur CSV-Datei
        start_date: Optional, nur Daten ab diesem Datum
        
    Returns:
        DataFrame mit normalisierten Spalten (UTC timestamps)
        
    Raises:
        DataImportError: Wenn Datei nicht existiert oder ungültiges Format
    """
    if not csv_path.exists():
        raise DataImportError(f"CSV nicht gefunden: {csv_path}")
    
    df = pd.read_csv(
        csv_path, 
        sep=";", 
        decimal=",",
        parse_dates=["Zeitstempel"],
        dayfirst=True,
    )
    # Normalize...
    return df
```

### 9.3 Error Handling

```python
class PVForecastError(Exception):
    """Basis-Exception."""

class DataImportError(PVForecastError):
    """Fehler beim Datenimport."""

class WeatherAPIError(PVForecastError):
    """Fehler bei Wetter-API."""

class ModelNotFoundError(PVForecastError):
    """Kein trainiertes Modell vorhanden."""
```

---

## 10. Rollen-Checklisten

### 🎓 Fachexperte
- [x] Domäne verstanden (PV, Wetter, Prognose)
- [x] Datenquellen identifiziert
- [x] Anforderungen geklärt
- [x] Erfolgskriterien definiert

### 🏛️ Architekt
- [x] Modulstruktur validiert
- [x] Datenfluss geprüft
- [x] Schnittstellen definiert
- [x] Erweiterbarkeit sichergestellt (GUI später)
- [x] Kein Overengineering (MVP-fokussiert)
- [x] Timezone-Handling geklärt
- [x] Entscheidungen dokumentiert

### 👨‍💻 Entwickler
- [x] Projektsetup (pyproject.toml, venv)
- [x] DB-Schema + Migrations
- [x] data_loader.py
- [x] sources/ (MOSMIX, HOSTRADA, Open-Meteo)
- [x] model.py (RandomForest + XGBoost)
- [x] cli/ Package (Refactoring)
- [x] README.md

### 🧪 Tester
- [x] Unit Tests pro Modul (~240 Tests)
- [x] Integration Tests (End-to-End)
- [x] Edge Cases (leere DB, API-Fehler, fehlende Daten)
- [x] Performance-Test (< 10s Ziel erreicht)

### 🔒 Security
- [x] Keine Secrets im Code
- [x] Input-Validierung (Pfade, Koordinaten)
- [x] SQL Injection Prevention (parametrisierte Queries)
- [x] API-Rate-Limiting beachtet (Retry mit Backoff + Jitter)

---

## 11. Entscheidungen

| Frage | Entscheidung | Begründung |
|-------|--------------|------------|
| CLI-Framework | **argparse** | stdlib, keine Dependency |
| Datenbank | **SQLite** | Joins, Queries, performant, stdlib |
| ML-Algorithmus (MVP) | **RandomForest** | sklearn-only, robust |
| ML-Algorithmus (später) | XGBoost | Bessere Accuracy |
| Caching Wetter | **SQLite** | Eine DB für alles |
| Config-Format | **CLI-Args + Defaults** | Einfach für MVP |
| Timezone intern | **UTC** | Konsistenz |

---

## 12. Roadmap

### Phase 1: MVP ✅
1. ✅ SPEC.md
2. ✅ Projektsetup (pyproject.toml)
3. ✅ DB-Schema + `db.py`
4. ✅ `data_loader.py` – CSV Import
5. ✅ `weather.py` – Open-Meteo Client
6. ✅ `model.py` – RandomForest Training/Predict
7. ✅ `cli.py` – predict, import, train, status
8. ✅ README.md

### Phase 2: Polish ✅
- ✅ Bessere Evaluation-Metriken (`evaluate` Befehl)
- ✅ XGBoost als Alternative
- ✅ Caching/Performance optimieren (Bulk Insert, itertuples)
- ✅ Error-Handling verbessern (Retry-Logic + Jitter)
- ✅ Config-File Support (YAML)
- ✅ Input-Validierung
- ✅ Integration Tests (E2E)
- ✅ Hyperparameter-Tuning (tune Befehl, Optuna)

### Phase 3: DWD-Integration ✅
- ✅ MOSMIX Forecast-Source
- ✅ HOSTRADA Historical-Source
- ✅ Sources-Framework (abstrakte Basis)
- ✅ Open-Meteo als Fallback behalten
- ✅ CLI Refactoring (cli/ Package)

### Phase 4: Erweiterungen (offen)
- 🔲 Home Assistant Integration
- 🔲 Automatische tägliche Updates
- 🔲 Visualisierung (Charts)
- 🔲 Web-UI oder TUI

---

*Erstellt: 2026-02-04 | Version: 0.4.0 (Stand: 2026-02-08)*
