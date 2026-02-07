# DWD-Refactoring: Implementierungs-Status

> **Issue:** [#123 - Refactor: Einheitliche DWD-Architektur](https://github.com/jarvis-schlappa/pv-forecast/issues/123)
> **Branch:** `feature/dwd-architecture-123`
> **Letztes Update:** 2026-02-07 17:15

## Übersicht

Umstellung von Open-Meteo auf DWD-native Datenquellen:
- **MOSMIX** für Forecasts (ersetzt Open-Meteo Forecast API)
- **HOSTRADA** für historische Daten (ersetzt Open-Meteo Archive API)

## Workflow

```
Fachexperte → Architekt → Entwickler → Tester → Security → Real-Test → Merge
    ✅           ✅          🔄          ⏳         ⏳          ⏳        ⏳
```

**Legende:** ✅ Abgeschlossen | 🔄 In Arbeit | ⏳ Ausstehend

## Phasen-Status

### ✅ Phase 1: Fachexperten-Analyse (abgeschlossen)

**Ergebnisse:**
- MOSMIX Station P0051 (Dülmen) verfügbar und geeignet
- KML-Format analysiert und verstanden
- HOSTRADA NetCDF-Struktur identifiziert
- Parameter-Mapping definiert:

| Open-Meteo | MOSMIX | HOSTRADA | Umrechnung |
|------------|--------|----------|------------|
| `shortwave_radiation` | `Rad1h` | SIS | MOSMIX: kJ/m² → W/m² (/3.6) |
| `temperature_2m` | `TTT` | - | K → °C (-273.15) |
| `cloud_cover` | `Neff` | - | % |
| `wind_speed_10m` | `FF` | - | m/s |
| `diffuse_radiation` | - | SID | Nur HOSTRADA |

**DHI/DNI:**
- Werden im Modell genutzt, aber mit Fallback auf 0.0
- MOSMIX liefert kein DHI → bleibt 0.0 für Forecasts
- HOSTRADA liefert SID (diffuse) → kann genutzt werden
- **Entscheidung:** DHI-Schätzung als separates Issue (low priority)

**Datenzeitraum:**
- E3DC-Daten: 2019-01-01 bis heute
- HOSTRADA-Import ab 2019-01-01

### ✅ Phase 2: Architektur-Design (abgeschlossen)

**Dokument:** [ARCHITECTURE_DWD.md](./ARCHITECTURE_DWD.md)

**Kernentscheidungen:**
1. Source-Abstraktion mit `ForecastSource` / `HistoricalSource` Interfaces
2. MOSMIX-Station konfigurierbar via `config.yaml`
3. MOSMIX-Forecasts werden gecacht (für Analyse)
4. HOSTRADA monatsweise laden (einfacher, besseres Caching)
5. Neue Dependencies: `xarray`, `netCDF4`, `scipy`

**Neue Struktur:**
```
src/pvforecast/sources/
├── __init__.py
├── base.py       # Interfaces
├── mosmix.py     # Forecast
└── hostrada.py   # Historical
```

### ⏳ Phase 3: Entwicklung (in Arbeit)

| Task | Status | Datei |
|------|--------|-------|
| Source Interfaces | ✅ | `sources/base.py` |
| MOSMIX KML-Parser | ✅ | `sources/mosmix.py` |
| DHI-Schätzung (Erbs-Modell) | ✅ | `sources/mosmix.py` |
| Config-Erweiterung | ✅ | `config.py` |
| CLI MOSMIX Integration | ✅ | `cli.py` (`fetch-forecast --source mosmix`) |
| DB-Schema (mosmix_forecast) | ⏳ | `db.py` |
| HOSTRADA Integration | ⚠️ BLOCKED | Daten erst ab 2024-04 verfügbar! |
| Hybrid-Strategie | 🔄 | Open-Meteo für Historie, MOSMIX für Forecast |
| Open-Meteo entfernen | ⏳ | `weather.py` |

### ⏳ Phase 4: Tests

| Test | Status |
|------|--------|
| Unit: MOSMIX Parser | ⏳ |
| Unit: HOSTRADA Parser | ⏳ |
| Unit: Config | ⏳ |
| E2E: fetch-forecast --source mosmix | ⏳ |
| E2E: fetch-historical --source hostrada | ⏳ |
| E2E: predict mit MOSMIX | ⏳ |

### ⏳ Phase 5: Security Review

- [ ] API-Zugriffe validieren (keine Credentials nötig, Open Data)
- [ ] Datenvalidierung bei KML/NetCDF-Parsing
- [ ] Error-Handling bei korrupten Dateien

### ⏳ Phase 6: Real-System Test

- [ ] MOSMIX-Forecast auf echtem System testen
- [ ] Vergleich MOSMIX vs Open-Meteo Forecasts
- [ ] HOSTRADA-Import für historische Daten
- [ ] Model-Training mit HOSTRADA-Daten

## Bekannte Risiken

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|-------------------|------------|
| KML-Format ändert sich | Gering | Schema-Validierung, Parser versionieren |
| Station P0051 entfällt | Sehr gering | Config-Option, Fallback-Station |
| NetCDF-Files sehr groß | Mittel | Lokaler Cache, Chunk-Loading |
| DWD-Server nicht erreichbar | Gelegentlich | Retry-Logik, Graceful Degradation |

## Nächste Schritte

1. [ ] `sources/base.py` - Interfaces implementieren
2. [ ] `sources/mosmix.py` - KML-Parser
3. [ ] Config erweitern für `weather.forecast.mosmix.station_id`
4. [ ] Tests schreiben

## Zeitschätzung

| Phase | Geschätzt | Tatsächlich |
|-------|-----------|-------------|
| Fachexperte | 2h | 1h ✅ |
| Architekt | 2h | 1h ✅ |
| Entwickler | 12h | - |
| Tester | 3h | - |
| Security | 1h | - |
| Real-Test | 2h | - |
| **Gesamt** | **~22h** | - |

---

*Dieses Dokument wird während der Implementierung aktualisiert.*
