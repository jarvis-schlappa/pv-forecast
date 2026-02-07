# Konzept: DWD-Wetterdaten als einheitliche Datenquelle

## Zusammenfassung

Umstellung der pv-forecast Wetterdaten-Architektur auf ein einheitliches DWD-Ökosystem:

- **MOSMIX** als Forecast-Quelle (ersetzt Open-Meteo)
- **HOSTRADA** als historische Strahlungsdaten (neues Feature)
- **Open-Meteo entfernen** zur Reduzierung von Abhängigkeiten

## Motivation

- Open-Meteo liefert in der Praxis unzuverlässige Vorhersagen
- Proplanta (Issue #122) würde fragiles Web-Scraping erfordern
- MOSMIX ist die Primärquelle, die Proplanta und Open-Meteo selbst nutzen
- Ein einheitliches DWD-Ökosystem reduziert Komplexität und verbessert Datenkonsistenz

## Architektur

```
Historische Daten (Training)           Forecast (Inferenz)
┌─────────────┐                        ┌─────────────┐
│  HOSTRADA   │                        │   MOSMIX    │
│  (DWD CDC)  │                        │   Station   │
│ 1x1km Raster│                        │    P0051    │
│  stündlich  │                        │  (Dülmen)   │
└──────┬──────┘                        └──────┬──────┘
       │                                      │
       │ GHI, DHI, Temperatur                 │ Rad1h, TTT, Neff, FF
       │                                      │
       ▼                                      ▼
┌──────────────────────────────────────────────────┐
│                   ML-Modell                      │
│              (bestehende Pipeline)               │
├──────────────────────────────────────────────────┤
│  + E3DC pv_readings (Ist-Ertrag)                 │
│  + Anlagen-Metadaten (10 kWp, Ausrichtung, etc.) │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
              PV-Ertragsprognose
```

## 1. MOSMIX als Forecast-Quelle

### Stationsdaten

| Parameter | Wert |
|-----------|------|
| Station-ID | P0051 |
| Name | DÜLMEN |
| Koordinaten | 51.83°N, 7.23°E |
| Höhe | 70m ü.NN |
| Typ | Interpolationsstation |

### Relevante MOSMIX-Parameter

| Parameter | Beschreibung | Einheit |
|-----------|--------------|---------|
| Rad1h | Globalstrahlung (Stundensumme) | kJ/m² |
| TTT | Temperatur 2m | K |
| Neff | Effektive Bewölkung | % |
| FF | Windgeschwindigkeit 10m | m/s |
| PPPP | Luftdruck | Pa |
| SunD1 | Sonnenscheindauer letzte Stunde | s |

### Datenquelle

```
MOSMIX_L (empfohlen):
  URL: https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/P0051/kml/
  Format: KMZ (gezipptes KML/XML)
  Update: 4x täglich (03, 09, 15, 21 UTC)
  Horizont: 240h (10 Tage), stündliche Auflösung
  Parameter: ~115
```

### Implementierung

```python
# pvforecast/sources/mosmix.py

class MOSMIXSource:
    """DWD MOSMIX Forecast-Datenquelle."""

    STATION_ID = "P0051"
    BASE_URL = (
        "https://opendata.dwd.de/weather/local_forecasts/mos/"
        "MOSMIX_L/single_stations/{station}/kml/"
    )
    LATEST_PATTERN = "MOSMIX_L_LATEST_{station}.kmz"

    PARAMETERS = ["Rad1h", "TTT", "Neff", "FF", "PPPP", "SunD1"]

    def fetch_forecast(self) -> pd.DataFrame:
        """Aktuellen MOSMIX-Forecast herunterladen und parsen."""
        url = self._build_url()
        kmz_data = self._download(url)
        kml_content = self._unzip_kmz(kmz_data)
        return self._parse_kml(kml_content)

    def _parse_kml(self, kml: str) -> pd.DataFrame:
        """KML/XML parsen und relevante Parameter extrahieren.

        Rad1h ist die integrierte Strahlung der letzten Stunde
        vor dem Forecast-Zeitstempel (laut DWD-Kundenservice).
        Einheit: kJ/m² → Umrechnung in W/m²: Wert / 3.6
        """
        ...
```

### DB-Schema: forecast_cache

```sql
CREATE TABLE mosmix_forecast (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at INTEGER NOT NULL,      -- Unix-Timestamp des Downloads
    issued_at INTEGER NOT NULL,       -- MOSMIX IssueTime
    target_time TEXT NOT NULL,        -- ISO 8601 Forecast-Zeitpunkt
    station_id TEXT NOT NULL DEFAULT 'P0051',
    rad1h_kj REAL,                    -- Globalstrahlung kJ/m²
    ttt_k REAL,                       -- Temperatur in Kelvin
    neff_pct REAL,                    -- Effektive Bewölkung %
    ff_ms REAL,                       -- Windgeschwindigkeit m/s
    pppp_pa REAL,                     -- Luftdruck Pa
    sund1_s REAL,                     -- Sonnenscheindauer s
    UNIQUE(issued_at, target_time, station_id)
);

CREATE INDEX idx_mosmix_target ON mosmix_forecast(target_time);
CREATE INDEX idx_mosmix_fetched ON mosmix_forecast(fetched_at);
```

### Cronjob

```bash
# MOSMIX-Forecast 4x täglich abholen (nach DWD-Update)
15 4,10,16,22 * * * pvforecast fetch-forecast --source mosmix
```

## 2. HOSTRADA als historische Datenquelle

### Überblick

HOSTRADA (HOmogenisierte STRAhlungsDAten) kombiniert interpolierte DWD-Stationsdaten mit CM SAF SARAH-3 Satellitendaten zu einem stündlichen Rasterdatensatz.

| Parameter | Wert |
|-----------|------|
| Auflösung | 1 x 1 km (effektiv ~5x5 km für GHI) |
| Zeitauflösung | Stündlich |
| Format | NetCDF |
| Quelle | DWD CDC Open Data |
| URL | https://opendata.dwd.de/climate_environment/CDC/derived_germany/climate/hourly/duett/ |

### Relevante Parameter

| Parameter | Beschreibung |
|-----------|--------------|
| SIS | Surface Incoming Shortwave (Globalstrahlung) |
| SID | Surface Incoming Direct (Direktstrahlung) |

### Implementierung

```python
# pvforecast/sources/hostrada.py

class HOSTRADASource:
    """DWD HOSTRADA historische Strahlungsdaten."""

    BASE_URL = (
        "https://opendata.dwd.de/climate_environment/CDC/"
        "derived_germany/climate/hourly/duett/"
    )

    # Gitterpunkt nächst an PV-Anlage
    TARGET_LAT = 51.83
    TARGET_LON = 7.23

    def fetch_historical(
        self, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Historische Strahlungsdaten für Gitterpunkt laden."""
        nc_files = self._download_range(start_date, end_date)
        return self._extract_gridpoint(nc_files)

    def _extract_gridpoint(self, nc_files: list) -> pd.DataFrame:
        """Nächsten Gitterpunkt extrahieren.

        Nutzt scipy.spatial oder xarray für
        Nearest-Neighbor-Lookup im NetCDF-Raster.
        """
        ...
```

### Verwendung im ML-Training

```python
# Historische Daten zusammenführen für Training
hostrada_ghi = hostrada.fetch_historical("2023-01-01", "2025-12-31")
e3dc_production = db.get_pv_readings("2023-01-01", "2025-12-31")

# Merge auf Stundenbasis
training_data = pd.merge(
    hostrada_ghi, e3dc_production,
    on="hour", how="inner"
)

# Optional: Archivierte MOSMIX-Forecasts hinzufügen
# → Modell lernt, wie gut MOSMIX-Forecast mit Realität korreliert
mosmix_archive = db.get_archived_forecasts("2023-01-01", "2025-12-31")
training_data = training_data.merge(mosmix_archive, on="hour", how="left")
```

## 3. Open-Meteo entfernen

### Betroffene Dateien (zu prüfen)

- `pvforecast/sources/openmeteo.py` → löschen
- `pvforecast/config.py` → Open-Meteo-Konfiguration entfernen
- `tests/test_openmeteo.py` → löschen
- `requirements.txt` → openmeteo-sdk o.ä. entfernen
- CLI-Commands → `--source openmeteo` Option entfernen
- Dokumentation aktualisieren

### Migrationsstrategie

1. MOSMIX-Source implementieren und testen
2. Parallelbetrieb MOSMIX + Open-Meteo für 2–4 Wochen (optional)
3. Open-Meteo-Code und Abhängigkeiten entfernen
4. Tests und Docs aktualisieren

### Vorteile der Entfernung

- Eine externe Abhängigkeit weniger
- Kein API-Key-Management
- Einheitliches Datenformat (DWD-Ökosystem durchgängig)
- Weniger Fehlerquellen bei Datenabfragen
- Einfacheres Debugging

## 4. CLI-Erweiterungen

```bash
# MOSMIX-Forecast abrufen
pvforecast fetch-forecast --source mosmix

# HOSTRADA-Daten herunterladen
pvforecast fetch-historical --source hostrada --from 2023-01-01 --to 2025-12-31

# Forecast mit MOSMIX-Daten
pvforecast predict --source mosmix

# Forecast-Qualität auswerten
pvforecast evaluate --forecast-source mosmix --actual-source e3dc
```

## 5. Abhängigkeiten

### Neue Abhängigkeiten

```
xarray     # NetCDF-Handling für HOSTRADA
netCDF4    # NetCDF-Dateien lesen
scipy      # Nearest-Neighbor für Gitterpunkt-Extraktion
```

### Entfallende Abhängigkeiten

```
openmeteo-sdk  # oder entsprechendes Open-Meteo-Paket
```

## 6. Implementierungsplan

| Phase | Aufgabe | Aufwand |
|-------|---------|---------|
| 1 | MOSMIX-Source: Download, KML-Parsing, DB-Schema | ~4h |
| 2 | MOSMIX als Feature ins ML-Modell integrieren | ~3h |
| 3 | HOSTRADA-Source: Download, NetCDF-Parsing, Gitterpunkt-Extraktion | ~4h |
| 4 | HOSTRADA als historische Features ins Training | ~2h |
| 5 | Open-Meteo entfernen (Code, Tests, Deps, Docs) | ~2h |
| 6 | CLI-Commands und Cronjob-Dokumentation | ~1h |
| 7 | Tests für MOSMIX + HOSTRADA | ~3h |
| **Gesamt** | | **~19h** |

## 7. Risiken und Mitigationen

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|-------------------|------------|
| DWD ändert KML-Format | Gering (offizieller Standard) | Versionierung im Parser, Schema-Validierung |
| MOSMIX-Station P0051 entfällt | Sehr gering | Fallback auf nächste Station (z.B. Münster 10315) |
| HOSTRADA NetCDF-Struktur ändert sich | Gering | xarray abstrahiert Format-Details |
| DWD Open Data Server nicht erreichbar | Gelegentlich | Retry-Logik, lokaler Cache, Graceful Degradation |
| Rad1h enthält Lücken | Möglich | NaN-Handling, Interpolation oder SunD1 als Fallback |

## Referenzen

- [DWD MOSMIX Dokumentation](https://www.dwd.de/EN/ourservices/met_application_mosmix/met_application_mosmix.html)
- [MOSMIX Stationskatalog](https://www.dwd.de/DE/leistungen/met_verfahren_mosmix/mosmix_stationskatalog.html)
- [MOSMIX Parameter-Beschreibung (PDF)](https://www.dwd.de/DE/leistungen/opendata/help/schluessel_datenformate/kml/mosmix_elemente_pdf.pdf)
- [DWD CDC Open Data](https://opendata.dwd.de/climate_environment/CDC/)
- [HOSTRADA Daten](https://opendata.dwd.de/climate_environment/CDC/derived_germany/climate/hourly/duett/)
- [kilianknoll/DWDForecast](https://github.com/kilianknoll/DWDForecast) – Python-Referenzimplementierung für MOSMIX-Parsing
- [stefae/PVForecast](https://stefae.github.io/PVForecast/README) – PV-Forecast mit DWD-Anbindung
- Issue #50: Alternative Weather Provider
- Issue #121: HOSTRADA
- Issue #122: Proplanta Auto-Kalibrierung (wird durch dieses Konzept ersetzt)

## Relates to

- #50 (Alternative Weather Provider)
- #121 (HOSTRADA)
- #122 (Proplanta – wird durch MOSMIX ersetzt)
