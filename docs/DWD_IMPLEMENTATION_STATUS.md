# DWD-Refactoring: Implementierungs-Status

> **Issue:** [#123 - Refactor: Einheitliche DWD-Architektur](https://github.com/jarvis-schlappa/pv-forecast/issues/123)
> **Branch:** `feature/dwd-architecture-123`
> **Letztes Update:** 2026-02-07 17:25

## Übersicht

Umstellung von Open-Meteo auf DWD-native Datenquellen:
- **MOSMIX** für Forecasts (ersetzt Open-Meteo Forecast API)
- **HOSTRADA** für historische Daten (ersetzt Open-Meteo Archive API)

## Workflow

```
Fachexperte → Architekt → Entwickler → Tester → Security → Real-Test → Merge
    ✅           ✅          ✅          ⏳         ⏳          ⏳        ⏳
```

**Legende:** ✅ Abgeschlossen | 🔄 In Arbeit | ⏳ Ausstehend

## Phasen-Status

### ✅ Phase 1: Fachexperten-Analyse (abgeschlossen)

**Ergebnisse:**
- MOSMIX Station P0051 (Dülmen) verfügbar und geeignet
- KML-Format analysiert und verstanden
- HOSTRADA NetCDF-Struktur identifiziert (Grids, 1km Auflösung)
- Parameter-Mapping definiert:

| Open-Meteo | MOSMIX | HOSTRADA | Einheit |
|------------|--------|----------|---------|
| `shortwave_radiation` | `Rad1h` | `rsds` | W/m² |
| `temperature_2m` | `TTT` | `tas` | °C |
| `cloud_cover` | `Neff` | `clt` | % |
| `wind_speed_10m` | `FF` | `sfcWind` | m/s |
| `relative_humidity` | - | `hurs` | % |

**DHI-Schätzung:**
- MOSMIX und HOSTRADA liefern kein direktes DHI
- Implementiert: Erbs-Modell für DHI-Schätzung aus GHI

**Datenzeitraum:**
- **HOSTRADA:** 1995-01 bis ~2 Monate vor heute (Raster-Daten)
- **MOSMIX:** Echtzeit-Forecasts (10 Tage voraus)

### ✅ Phase 2: Architektur-Design (abgeschlossen)

**Dokument:** [ARCHITECTURE_DWD.md](./ARCHITECTURE_DWD.md)

**Kernentscheidungen:**
1. Source-Abstraktion mit `ForecastSource` / `HistoricalSource` Interfaces
2. MOSMIX-Station konfigurierbar via `config.yaml`
3. HOSTRADA mit lokaler Cache-Directory für NetCDF-Dateien
4. HOSTRADA monatsweise laden (besseres Caching)
5. Dependencies: `xarray`, `netCDF4`, `scipy`

**Struktur:**
```
src/pvforecast/sources/
├── __init__.py     ✅
├── base.py         ✅ Interfaces
├── mosmix.py       ✅ Forecast (KML-Parser)
└── hostrada.py     ✅ Historical (NetCDF-Parser)
```

### ✅ Phase 3: Entwicklung (abgeschlossen)

| Task | Status | Datei |
|------|--------|-------|
| Source Interfaces | ✅ | `sources/base.py` |
| MOSMIX KML-Parser | ✅ | `sources/mosmix.py` |
| DHI-Schätzung (Erbs-Modell) | ✅ | `sources/mosmix.py`, `sources/hostrada.py` |
| Config-Erweiterung | ✅ | `config.py` |
| CLI MOSMIX Integration | ✅ | `pvforecast fetch-forecast --source mosmix` |
| HOSTRADA NetCDF-Parser | ✅ | `sources/hostrada.py` |
| CLI HOSTRADA Integration | ✅ | `pvforecast fetch-historical --source hostrada` |
| DB-Schema (mosmix_forecast) | ⏳ | Für Caching-Feature (optional) |
| Open-Meteo entfernen | ⏳ | `weather.py` (als Fallback behalten) |

**HOSTRADA Parameter:**
- `radiation_downwelling` → GHI (rsds)
- `air_temperature_mean` → Temperatur (tas)
- `cloud_cover` → Bewölkung (clt, Oktas → %)
- `humidity_relative` → Luftfeuchtigkeit (hurs)
- `wind_speed` → Wind (sfcWind)

### ⏳ Phase 4: Tests

| Test | Status |
|------|--------|
| Unit: MOSMIX Parser | ⏳ |
| Unit: HOSTRADA Parser | ⏳ |
| Unit: Config | ⏳ |
| E2E: fetch-forecast --source mosmix | ✅ Manual |
| E2E: fetch-historical --source hostrada | ✅ Manual |
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
| NetCDF-Files sehr groß (~120-215 MB/Monat) | Mittel | Lokaler Cache, Chunk-Loading |
| DWD-Server nicht erreichbar | Gelegentlich | Retry-Logik, Graceful Degradation |

## Nächste Schritte

1. [x] ~~Config-Erweiterung für MOSMIX~~
2. [x] ~~CLI fetch-forecast~~
3. [x] ~~HOSTRADA Parser~~
4. [x] ~~CLI fetch-historical~~
5. [ ] Unit Tests schreiben
6. [ ] Default auf DWD-Quellen umstellen
7. [ ] PR erstellen & CI prüfen

## Zeitschätzung

| Phase | Geschätzt | Tatsächlich |
|-------|-----------|-------------|
| Fachexperte | 2h | 1h ✅ |
| Architekt | 2h | 1h ✅ |
| Entwickler | 12h | ~4h ✅ |
| Tester | 3h | - |
| Security | 1h | - |
| Real-Test | 2h | - |
| **Gesamt** | **~22h** | ~6h (bisher) |

---

*Dieses Dokument wird während der Implementierung aktualisiert.*
