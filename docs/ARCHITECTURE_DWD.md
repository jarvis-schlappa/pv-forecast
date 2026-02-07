# Architektur: DWD-Refactoring (Issue #123)

## 1. Source-Abstraktion

Neue Modul-Struktur unter `src/pvforecast/sources/`:

```
src/pvforecast/
├── sources/
│   ├── __init__.py      # WeatherSource Protocol, Factory
│   ├── base.py          # Abstrakte Basisklasse
│   ├── mosmix.py        # MOSMIX Forecast-Source
│   └── hostrada.py      # HOSTRADA Historical-Source
├── weather.py           # → wird zu Compatibility-Layer / Entfernt
└── ...
```

### 1.1 WeatherSource Protocol

```python
# sources/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
import pandas as pd

@dataclass
class WeatherRecord:
    """Einheitliches Wetter-Datenformat."""
    timestamp: int          # Unix timestamp UTC
    ghi_wm2: float         # Globalstrahlung W/m²
    cloud_cover_pct: int   # Bewölkung 0-100%
    temperature_c: float   # Temperatur °C
    wind_speed_ms: float   # Wind m/s
    humidity_pct: int      # Luftfeuchtigkeit 0-100%
    dhi_wm2: float         # Diffusstrahlung (0 wenn nicht verfügbar)
    dni_wm2: float         # Direktnormalstrahlung (0 wenn nicht verfügbar)

class ForecastSource(ABC):
    """Interface für Forecast-Datenquellen."""
    
    @abstractmethod
    def fetch_forecast(self, hours: int = 240) -> pd.DataFrame:
        """Holt Forecast für die nächsten X Stunden."""
        ...
    
    @abstractmethod
    def fetch_today(self, tz: str) -> pd.DataFrame:
        """Holt Daten für heute (Vergangenheit + Forecast)."""
        ...

class HistoricalSource(ABC):
    """Interface für historische Datenquellen."""
    
    @abstractmethod
    def fetch_historical(self, start: date, end: date) -> pd.DataFrame:
        """Holt historische Daten für Zeitraum."""
        ...
```

### 1.2 MOSMIX Source

```python
# sources/mosmix.py
@dataclass
class MOSMIXConfig:
    """MOSMIX-spezifische Konfiguration."""
    station_id: str = "P0051"  # Default: Dülmen
    use_mosmix_l: bool = True  # MOSMIX_L (115 Param) vs MOSMIX_S (40 Param)

class MOSMIXSource(ForecastSource):
    """DWD MOSMIX Forecast-Datenquelle."""
    
    BASE_URL = "https://opendata.dwd.de/weather/local_forecasts/mos/"
    
    # Parameter-Mapping: MOSMIX → internes Format
    PARAM_MAP = {
        "Rad1h": ("ghi_wm2", lambda x: x / 3.6),     # kJ/m² → W/m²
        "TTT": ("temperature_c", lambda x: x - 273.15),  # K → °C
        "Neff": ("cloud_cover_pct", lambda x: int(x)),
        "FF": ("wind_speed_ms", lambda x: x),
        "SunD1": ("sunshine_s", lambda x: x),  # Bonus-Info
    }
    
    def __init__(self, config: MOSMIXConfig | None = None):
        self.config = config or MOSMIXConfig()
    
    def fetch_forecast(self, hours: int = 240) -> pd.DataFrame:
        """Lädt aktuellen MOSMIX-Forecast."""
        kmz_url = self._build_latest_url()
        kml_content = self._download_and_unzip(kmz_url)
        return self._parse_kml(kml_content, hours)
    
    def _parse_kml(self, kml: str, hours: int) -> pd.DataFrame:
        """Parst MOSMIX KML zu DataFrame."""
        # XML Parsing mit lxml oder xml.etree
        # Timestamps aus ForecastTimeSteps
        # Werte aus Forecast-Elementen (space-separated floats)
        ...
```

### 1.3 HOSTRADA Source

```python
# sources/hostrada.py
@dataclass  
class HOSTRADAConfig:
    """HOSTRADA-spezifische Konfiguration."""
    lat: float
    lon: float
    cache_dir: Path | None = None  # Lokaler NetCDF-Cache

class HOSTRADASource(HistoricalSource):
    """DWD HOSTRADA historische Strahlungsdaten."""
    
    BASE_URL = "https://opendata.dwd.de/climate_environment/CDC/derived_germany/climate/hourly/duett/"
    
    def __init__(self, config: HOSTRADAConfig):
        self.config = config
    
    def fetch_historical(self, start: date, end: date) -> pd.DataFrame:
        """Lädt historische Daten für Zeitraum."""
        # 1. NetCDF-Dateien für Zeitraum identifizieren
        # 2. Download (mit Cache)
        # 3. Gridpoint extrahieren (Nearest-Neighbor)
        # 4. Zu DataFrame konvertieren
        ...
    
    def _find_nearest_gridpoint(self, nc_data) -> tuple[int, int]:
        """Findet nächsten Rasterpunkt zu lat/lon."""
        # scipy.spatial.distance oder xarray nearest
        ...
```

## 2. Config-Erweiterung

```yaml
# ~/.config/pvforecast/config.yaml
location:
  latitude: 51.83
  longitude: 7.28
  timezone: Europe/Berlin

system:
  peak_kwp: 9.92
  name: Dülmen PV

data:
  db_path: ~/.local/share/pvforecast/data.db
  model_path: ~/.local/share/pvforecast/model.pkl

# NEU: Weather Sources
weather:
  forecast:
    provider: mosmix           # mosmix | open-meteo (deprecated)
    mosmix:
      station_id: P0051        # Konfigurierbar!
      use_mosmix_l: true
  
  historical:
    provider: hostrada         # hostrada | open-meteo (deprecated)
    hostrada:
      cache_dir: ~/.cache/pvforecast/hostrada
```

## 3. DB-Schema Erweiterung

### 3.1 Neue Tabelle: mosmix_forecast (Cache)

```sql
-- Cached MOSMIX-Forecasts für Analyse/Debugging
CREATE TABLE IF NOT EXISTS mosmix_forecast (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at INTEGER NOT NULL,      -- Unix timestamp Download
    issued_at INTEGER NOT NULL,       -- MOSMIX IssueTime
    target_time INTEGER NOT NULL,     -- Forecast-Zeitpunkt (Unix)
    station_id TEXT NOT NULL,
    
    -- Rohdaten (MOSMIX-Einheiten)
    rad1h_kj REAL,                    -- kJ/m²
    ttt_k REAL,                       -- Kelvin
    neff_pct REAL,                    -- %
    ff_ms REAL,                       -- m/s
    sund1_s REAL,                     -- Sekunden
    
    UNIQUE(issued_at, target_time, station_id)
);

CREATE INDEX IF NOT EXISTS idx_mosmix_target ON mosmix_forecast(target_time);
CREATE INDEX IF NOT EXISTS idx_mosmix_station ON mosmix_forecast(station_id);
```

### 3.2 weather_history bleibt gleich

Die bestehende `weather_history` Tabelle bleibt das einheitliche Format.
HOSTRADA-Daten werden beim Import konvertiert.

## 4. CLI-Änderungen

```bash
# Neuer Source-Parameter
pvforecast fetch-forecast --source mosmix      # NEU
pvforecast fetch-forecast --source open-meteo  # Legacy (deprecated)

pvforecast fetch-historical --source hostrada --from 2019-01-01
pvforecast fetch-historical --source open-meteo --from 2019-01-01  # Legacy

# Predict nutzt automatisch konfigurierte Source
pvforecast predict --days 3
pvforecast today

# Config zeigen (inkl. neuer Weather-Config)
pvforecast config --show
```

## 5. Migration: Open-Meteo Entfernung

### Phase 1: Parallelbetrieb (optional, 2-4 Wochen)
- MOSMIX implementieren
- Beide Sources parallel betreiben
- Forecasts vergleichen

### Phase 2: Umstellung
- Default auf MOSMIX/HOSTRADA
- Open-Meteo als `--source open-meteo` noch verfügbar

### Phase 3: Entfernung
- `weather.py` löschen (oder zu Compatibility-Layer umbauen)
- Tests anpassen
- Docs aktualisieren

## 6. Neue Dependencies

```toml
# pyproject.toml
dependencies = [
    # Bestehend...
    
    # NEU für HOSTRADA
    "xarray>=2024.1.0",
    "netCDF4>=1.6.0",
    "scipy>=1.11.0",  # Für Nearest-Neighbor
]
```

## 7. Implementierungs-Reihenfolge

| Phase | Task | Aufwand | Abhängigkeiten |
|-------|------|---------|----------------|
| 1 | `sources/base.py` - Interfaces | 1h | - |
| 2 | `sources/mosmix.py` - KML-Parsing | 3h | Phase 1 |
| 3 | Config-Erweiterung (YAML) | 1h | - |
| 4 | DB-Schema (mosmix_forecast) | 0.5h | - |
| 5 | CLI-Integration MOSMIX | 1h | Phase 2, 3, 4 |
| 6 | `sources/hostrada.py` - NetCDF | 3h | Phase 1 |
| 7 | CLI-Integration HOSTRADA | 1h | Phase 6 |
| 8 | Tests (Unit + E2E) | 3h | Phase 5, 7 |
| 9 | Open-Meteo entfernen | 2h | Phase 8 |
| 10 | Docs aktualisieren | 1h | Phase 9 |
| **Gesamt** | | **~17h** | |

## 8. Risiken & Mitigationen

| Risiko | Mitigation |
|--------|------------|
| KML-Format ändert sich | Schema-Version prüfen, Parser versionieren |
| Station P0051 nicht verfügbar | Graceful error, Config-Option für andere Station |
| NetCDF-Files sehr groß | Chunk-weise laden, lokaler Cache |
| HOSTRADA-Server langsam | Retry-Logik, Background-Download |

## 9. Design-Entscheidungen

| Frage | Entscheidung | Begründung |
|-------|--------------|------------|
| MOSMIX Caching | ✅ Ja, alte Forecasts speichern | Ermöglicht Forecast-Analyse und Debugging |
| HOSTRADA Granularität | ✅ Monatsweise laden | Einfacher, weniger Requests, besseres Caching |
| DHI-Schätzung | ⏳ Später (separates Issue) | Modell funktioniert ohne (Fallback 0.0), Feature-Engineering-Optimierung |

## 10. Referenzen

- Issue: https://github.com/jarvis-schlappa/pv-forecast/issues/123
- DWD MOSMIX: https://www.dwd.de/DE/leistungen/met_verfahren_mosmix/met_verfahren_mosmix.html
- DWD HOSTRADA: https://opendata.dwd.de/climate_environment/CDC/derived_germany/climate/hourly/duett/
