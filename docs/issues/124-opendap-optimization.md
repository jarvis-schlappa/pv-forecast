# Issue #124: HOSTRADA OPeNDAP/Subsetting für effizienteren Datenzugriff

## Problem

Aktuell lädt HOSTRADA komplette Deutschland-Raster herunter:
- **63 GB** für 7 Jahre Daten
- Nutzdaten (1 Gridpunkt Dülmen): **5.7 MB**
- Effizienz: ~0.01%

## Lösung

Server-seitiges Subsetting via:
1. **OPeNDAP/THREDDS** - Standard für wissenschaftliche Daten
2. **WCS (Web Coverage Service)** - OGC Standard
3. **Bright Sky API** - DWD-Wrapper (falls HOSTRADA unterstützt)

## Recherche nötig

- [ ] Hat DWD einen OPeNDAP/THREDDS Server für HOSTRADA?
- [ ] Gibt es WCS-Endpunkte?
- [ ] Alternative: CDC FTP mit Byte-Range Requests?

## Technische Details

**Aktueller Cache-Pfad (nicht löschen!):**
```
/tmp/hostrada_cache/
```
Enthält 63 GB NetCDF-Dateien für 2019-2025.

**Gewünschtes Verhalten:**
```python
# Statt: Lade 150 MB NetCDF, extrahiere 1 Punkt
# Neu:   Lade nur ~1 KB (Zeitreihe für Koordinate)
source.fetch_historical(start, end, lat=51.83, lon=7.28)
```

## Kontext

- Feature Branch: `feature/dwd-architecture-123`
- Issue #123: DWD-Refactoring (MOSMIX + HOSTRADA)
- HOSTRADA liefert +9% bessere MAPE als Open-Meteo
- Test-DB: `/tmp/pv-forecast-hostrada-test.db` (5.7 MB)
- Test-Modell: `/tmp/pv-forecast-hostrada-model.pkl`

## Priorität

Niedrig - Funktionalität ist da, nur ineffizient. 
Für Produktion erstmal MOSMIX-Forecasts nutzen (kein Download-Problem).

---

## Erste Recherche

### DWD Geoservices

Zu prüfen:
- https://www.dwd.de/DE/leistungen/opendata/opendata.html
- https://cdc.dwd.de/portal/ (CDC Portal)
- WCS/WMS Dienste des DWD

### OPeNDAP für NetCDF

xarray unterstützt OPeNDAP direkt:
```python
import xarray as xr
# Wenn OPeNDAP verfügbar:
ds = xr.open_dataset("https://opendap.server/path/to/file.nc")
# Subset on server side:
point = ds.sel(lat=51.83, lon=7.28, method="nearest")
```

### Alternative: Pydap

```python
from pydap.client import open_url
dataset = open_url("https://...")
```

---

## Recherche-Ergebnis (2026-02-07)

### DWD GeoServer (maps.dwd.de)

Hat WCS/WMS/WFS Dienste, aber **HOSTRADA ist NICHT verfügbar**:
- ✅ RADOLAN (Niederschlag)
- ✅ ICON-Modelle (NWP Vorhersagen)
- ✅ UV-Daten
- ✅ Klimareferenzkarten (30-Jahres-Mittel)
- ❌ **HOSTRADA (nicht vorhanden)**

### Mögliche Alternativen

1. **Byte-Range Requests** mit xarray + zarr/kerchunk
   - NetCDF-Dateien unterstützen theoretisch Byte-Range-Zugriffe
   - Aufwändig zu implementieren

2. **Kontakt zum DWD**
   - Anfrage ob OPeNDAP/THREDDS für CDC-Daten geplant ist
   - E-Mail: klima.cdc@dwd.de

3. **Copernicus CDS (ERA5-Land)**
   - Ähnliche Reanalyse-Daten
   - Hat API mit Subsetting
   - Aber: Registrierung nötig, andere Datenquelle

4. **Open-Meteo Historical**
   - Nutzt ERA5 im Hintergrund
   - Hat API mit Punktabfrage
   - Bereits implementiert (aktueller Fallback)

### Empfehlung

Für jetzt: Open-Meteo als Fallback für historische Daten behalten.
HOSTRADA nur für einmaliges Training nutzen (Cache behalten).

Die +9% MAPE-Verbesserung rechtfertigt die 63 GB Download für das initiale Training.
Für laufenden Betrieb reicht MOSMIX (Forecasts) + Open-Meteo (gelegentliche Updates).
