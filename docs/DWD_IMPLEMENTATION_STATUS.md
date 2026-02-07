# DWD-Refactoring: Implementierungs-Status

> **Issue:** [#123 - Refactor: Einheitliche DWD-Architektur](https://github.com/jarvis-schlappa/pv-forecast/issues/123)
> **Branch:** `feature/dwd-architecture-123`
> **Status:** ✅ **Fertig - bereit für PR**
> **Letztes Update:** 2026-02-07 19:15

## Übersicht

Umstellung von Open-Meteo auf DWD-native Datenquellen:
- **MOSMIX** für Forecasts (ergänzt Open-Meteo Forecast API)
- **HOSTRADA** für historische Daten (ergänzt Open-Meteo Archive API)

## Workflow

```
Fachexperte → Architekt → Entwickler → Tester → Security → Real-Test → Merge
    ✅           ✅          ✅          ✅         ✅          ✅        ⏳
```

**Legende:** ✅ Abgeschlossen | ⏳ Ausstehend (nur PR-Merge)

---

## Modell-Performance: HOSTRADA vs Open-Meteo

Real-System Test mit 60.648 Wetterdatensätzen (2019-2025):

| Metrik | Open-Meteo | HOSTRADA | Verbesserung |
|--------|------------|----------|--------------|
| **MAE** | 126 W | 105 W | **-17%** |
| **MAPE** | 31.3% | 21.9% | **-9.4 PP** |
| **RMSE** | 275 W | 228 W | **-17%** |
| **R²** | 0.948 | 0.974 | **+0.026** |

**Fazit:** HOSTRADA liefert signifikant bessere Trainingsdaten durch höhere räumliche Auflösung (1 km Raster) und konsistentere Messwerte.

---

## Neue CLI-Parameter

### `--source` Flag

Verfügbar für: `predict`, `today`, `fetch-forecast`, `fetch-historical`

```bash
# Forecasts
pvforecast predict --source mosmix --days 3
pvforecast today --source mosmix
pvforecast fetch-forecast --source mosmix

# Historische Daten
pvforecast fetch-historical --source hostrada --start 2020-01-01 --end 2024-12-31
```

**Werte:**
- `mosmix` - DWD MOSMIX (Forecasts)
- `open-meteo` - Open-Meteo API (Forecasts + Historical)
- `hostrada` - DWD HOSTRADA (Historical)

### `--yes` / `-y` Flag

Überspringt die Bestätigung bei HOSTRADA-Downloads (für Automatisierung):

```bash
pvforecast fetch-historical --source hostrada --start 2020-01-01 --end 2024-12-31 --yes
```

---

## HOSTRADA Download-Warnung

Bei HOSTRADA erscheint vor dem Download eine Warnung:

```
⚠️  HOSTRADA lädt komplette Deutschland-Raster herunter.
    Geschätzter Download: ~40.0 GB (7 Jahre × 5 Parameter)
    Extrahierte Daten: wenige MB (nur Gridpunkt 51.85°N, 7.26°E)

    Für regelmäßige Updates empfehlen wir Open-Meteo.
    HOSTRADA eignet sich für einmaliges Training mit historischen Daten.

Fortfahren? [y/N]: 
```

---

## Stream-Processing (kein Cache)

HOSTRADA verwendet Download-Extract-Delete Workflow:

```
1. Download NetCDF → Temp-Datei (~150 MB)
2. xarray extrahiert Gridpunkt → DB
3. Temp-Datei wird sofort gelöscht
4. Nächste Datei...
```

**Ergebnis:**
| Vorher | Nachher |
|--------|---------|
| 63 GB persistenter Cache | 0 GB |
| ~150 MB temp während Download | ✅ |

Fortschrittsanzeige:
```
Fetching HOSTRADA [████████████████░░░░░░░░░░░░░░]  53% (223/420)
```

---

## Konfiguration

Neue Optionen in `~/.config/pvforecast/config.yaml`:

```yaml
weather:
  # Forecast-Provider (default: open-meteo)
  forecast_provider: mosmix  # oder: open-meteo
  
  # Historical-Provider (default: open-meteo)
  historical_provider: hostrada  # oder: open-meteo
  
  # MOSMIX-Einstellungen
  mosmix:
    station: P0051  # Dülmen (default)
    # Andere Stationen: https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/
  
  # HOSTRADA-Einstellungen
  hostrada:
    # Keine spezifischen Einstellungen nötig
    # Nutzt automatisch latitude/longitude aus der Hauptconfig
```

---

## Parameter-Mapping

| Metrik | Open-Meteo | MOSMIX | HOSTRADA | Einheit |
|--------|------------|--------|----------|---------|
| GHI | `shortwave_radiation` | `Rad1h` | `rsds` | W/m² |
| Temperatur | `temperature_2m` | `TTT` | `tas` | °C |
| Bewölkung | `cloud_cover` | `Neff` | `clt` | % |
| Wind | `wind_speed_10m` | `FF` | `sfcWind` | m/s |
| Feuchte | `relative_humidity_2m` | - | `hurs` | % |
| DHI | `diffuse_radiation` | *geschätzt* | *geschätzt* | W/m² |

**DHI-Schätzung:** Erbs-Modell basierend auf GHI und Sonnenstand.

---

## Datenverfügbarkeit

| Quelle | Zeitraum | Auflösung | Latenz |
|--------|----------|-----------|--------|
| **MOSMIX** | +10 Tage | Stündlich | Echtzeit |
| **HOSTRADA** | 1995 - heute | Stündlich, 1 km | ~2 Monate |
| **Open-Meteo** | 1940 - heute | Stündlich | ~5 Tage |

---

## Test-Ergebnisse

- **Unit Tests:** 16 neue Tests für MOSMIX/HOSTRADA
- **Alle Tests:** 264 passed, 2 skipped
- **CI:** Grün (Python 3.9-3.12)

---

## Bekannte Einschränkungen

1. **HOSTRADA Latenz:** Daten ~2 Monate verzögert (für Reanalyse-Qualität)
2. **MOSMIX DHI:** Muss geschätzt werden (Erbs-Modell)
3. **Download-Größe:** HOSTRADA lädt volle Raster (~150 MB/Monat)

---

## Follow-Up Issues

- **#124:** [OPeNDAP-Optimierung](https://github.com/jarvis-schlappa/pv-forecast/issues/124) - Server-seitiges Subsetting für effizientere Downloads (niedrige Priorität)

---

*Dieses Dokument wird nach dem Merge archiviert.*
