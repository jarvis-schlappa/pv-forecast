# PV-Forecast: Wetterdaten-Strategie für ML-basierte Ertragsprognose

## Projektkontext

- **Anlage:** 10 kWp Photovoltaik mit E3DC-Inverter, Standort Dülmen (51.43°N, 7.28°E), Münsterland, NRW
- **Ziel:** ML-Modell, das den Zusammenhang zwischen Wetterdaten und tatsächlichem Solarertrag lernt (stündliche Auflösung)
- **Ansatz:** Wetter → Ertrag (OHNE Anlagengeometrie als Input). Das Modell lernt implizit alle standortspezifischen Faktoren aus den historischen Daten
- **Bisheriger Stand:** Open-Meteo als Datenquelle, MAPE von 41.7% auf 30.1% reduziert durch Feature Engineering
- **Problem:** Open-Meteo liefert nach Erfahrung keine besonders guten Vorhersagen

## Benötigte Daten

### Für ML-Training (historisch)

| Parameter | Priorität | Einheit | Hinweis |
|-----------|-----------|---------|---------|
| GHI (Globalstrahlung) | Kritisch | W/m² oder kWh/m² | Wichtigster Einzelparameter |
| DNI (Direktstrahlung) | Hoch | W/m² | Hilft bei Bewölkungsdifferenzierung |
| DHI (Diffusstrahlung) | Hoch | W/m² | GHI = DNI × cos(θ) + DHI |
| Bewölkung | Hoch | % oder Okta | Idealerweise nach Höhenschichten differenziert |
| Temperatur | Mittel | °C | Beeinflusst Modulwirkungsgrad |
| Luftfeuchtigkeit | Mittel | % | Korreliert mit Dunst/Nebel |
| Wind | Niedrig | m/s | Kühlung der Module |
| Sonnenscheindauer | Ergänzend | min oder % | Validierungsparameter |

### Für Vorhersage (Inference)

- Dieselben Parameter als Vorhersagewerte (1–5 Tage voraus)
- Mindestens 3-Stunden-Auflösung, besser stündlich

## Empfohlene Strategie: 3-Schichten-Architektur

### Schicht 1: Historische Trainingsdaten — DWD Open Data (kostenlos)

#### Option A: DUETT Rasterdaten (empfohlen für neuere Daten)

**Was:** Stündliche Globalstrahlung + Sonnenscheindauer als Rasterdaten, kombiniert aus Meteosat-Satellit und 42 DWD-Bodenstationen.

**Vorteile für Dülmen:**
- 1–2 km Auflösung — keine Stationsnähe nötig, exakte Gitterzelle für Dülmen extrahierbar
- Stündliche Aktualisierung
- Mehrstufige Bias-Korrektur (Satellit gegen Bodenmessungen)
- Genauigkeit: mittlere absolute Differenz 21–42 W/m² (je nach Jahreszeit)
- CC BY 4.0 Lizenz, komplett kostenlos

**Daten-URLs:**
- Rasterdaten: https://opendata.dwd.de/climate_environment/CDC/grids_germany/hourly/duett/radiation_global/
  - `/recent/` — stündlich aktualisiert (laufendes Jahr)
  - `/historical/` — Archiv älterer Daten (jährlich aktualisiert)
- Pseudo-Stationsdaten (576 Punkte): https://opendata.dwd.de/climate_environment/CDC/derived_germany/climate/hourly/duett/radiation_global/
- Stationsliste: https://opendata.dwd.de/climate_environment/CDC/grids_germany/hourly/duett/DUETT_ListOfStations.csv

**Format:** NetCDF (.nc), Projektion EPSG-3034 (2 km) bzw. ETRS89_LAEA/EPSG:3035 (1 km seit Nov 2025)

**Python-Zugriff:**
```python
import xarray as xr

# Einzelne Stunde laden
ds = xr.open_dataset("SIS_duett_2km_DE_60min_202501011250_007.nc")

# Wert für Dülmen extrahieren (51.43°N, 7.28°E)
# Koordinaten müssen in die jeweilige Projektion umgerechnet werden
```

**Einschränkung:** DUETT ist ein relativ neues Projekt. Die Historie reicht wahrscheinlich nur ca. 2–3 Jahre zurück. Für längere Zeitreihen → Option B.

**Achtung Version:** Dateinamen enthalten Versionsnummer (z.B. `_007`). Seit Version 007 (Nov 2024) wurden Schnee-bezogene Fehler bei der Wolkenerkennung korrigiert. Temporale Homogenität der Daten ist nicht garantiert.

#### Option B: HOSTRADA Rasterdaten (für längere Historie)

**Was:** Hochaufgelöster stündlicher Rasterdatensatz für Deutschland.
- **Zeitraum:** seit 1995
- **Auflösung:** 1 km², stündlich
- **Parameter:** Globalstrahlung, Direktstrahlung, langwellige ausgehende Strahlung, plus Temperatur, Feuchte, Druck, Taupunkt, Wolkenbedeckung, Wind
- **Basis:** Projekt TRY (Testreferenzjahre), klimatologischer Referenzdatensatz

**Daten-URL:** https://opendata.dwd.de/climate_environment/CDC/grids_germany/ (Unterverzeichnis hourly)

**Vorteil:** 17+ Jahre stündliche Daten für exakt die 1 km²-Zelle von Dülmen — ideal zum Trainieren eines ML-Modells mit saisonaler Abdeckung.

#### Option C: DWD Stationsdaten (längste Zeitreihen)

**Was:** Stündliche Stationsmessungen der Solarstrahlung (global/diffus) und atmosphärische Gegenstrahlung.
- **Stationen mit Solarstrahlung:** ca. 120 bundesweit
- **Nächste Station zu Dülmen:** voraussichtlich Münster/Osnabrück (~30 km nordöstlich) oder Werl (~50 km südöstlich)
- **Zeitreihen:** teilweise ab 1975, qualitätsgeprüft
- **Parameter:** Diffuse Strahlung, Globalstrahlung, atmosphärische Gegenstrahlung, Sonnenscheindauer (J/cm², Minuten)

**Daten-URL:** https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/solar/
- Stationsliste: `ST_Stundenwerte_Beschreibung_Stationen.txt`
- Daten pro Station als ZIP: `stundenwerte_ST_{station_id}_row.zip`

**Zusätzliche Stationsdaten (für Temperatur, Wind, Feuchte etc.):**
- https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/
- Unterverzeichnisse: `air_temperature/`, `wind/`, `cloud_type/`, `moisture/`, `pressure/`, `sun/`

**Hinweis:** 30 km Abstand im flachen Münsterland ist für Globalstrahlung kein relevanter Fehlerquell. Lokale Bewölkungsunterschiede mitteln sich über Stundenwerte weitgehend aus.

#### Solarstrahlungsraster (monatlich/jährlich, seit 1991)

Für langfristige Analysen und Validierung stehen auch monatliche und jährliche Rasterdaten bereit:
- Globalstrahlung, Diffusstrahlung, Direktstrahlung (1×1 km)
- Aus Satellitendaten + Bodenmessungen abgeleitet
- URL: https://opendata.dwd.de/climate_environment/CDC/grids_germany/ (monthly/annual Unterverzeichnisse)

### Schicht 2: Laufende Vorhersagen — Anbieter-Optionen

#### Option A: Solcast Free-Tier (beste Solar-spezifische Genauigkeit)

- **Genauigkeit:** 25–50% besser als globale Wettermodelle, niedrigste Fehlerrate in EPRI-Trial
- **Vorhersagen:** 5 Min bis 14 Tage, 90 m Auflösung
- **Methodik:** Satellitendaten + ECMWF ERA5 + HRRR + ICON-EU, proprietäres ML-Separationsmodell
- **Parameter:** GHI, DNI, DHI, GTI, Temperatur, Bewölkung, Wind, Luftfeuchtigkeit, Aerosole, PM2.5/PM10, Albedo, Schnee
- **Free-Tier:** "Home PV System" — 10 API-Requests/Tag (persönlich, nicht-kommerziell)
- **Einschränkung Free:** Historische Zeitreihen-Daten NICHT im Free-Tier enthalten
- **Dokumentation:** https://docs.solcast.com.au/
- **Website:** https://solcast.com

#### Option B: Kachelmann/Meteologix (beste lokale Genauigkeit für Deutschland)

- Eigenes SuperHD 1×1 km Modell + alle nationalen Wettermodelle (ECMWF, ICON, UKMO)
- MOS-Vorhersagen: Model Output Statistics optimiert für spezifische Standorte
- Wolkenschicht-Differenzierung: Hohe, mittelhohe und tiefe Wolken separat (wertvoll für ML)
- Sonnenscheindauer und Globalstrahlung als Messwerte/Vorhersagen
- **API-Zugang:** Im Plus-Abo enthalten (Hobby/Smart-Home-API-Paket)
- **Pricing:** Plus-Abo 6,99 €/Monat bzw. 69,90 €/Jahr
- **API-Doku:** https://api.kachelmannwetter.com/v02/_doc.html
- **Endpoints:** /current, /forecast, Stationsdaten, JSON-Format, REST-API
- **Einschränkung:** Historische Strahlungsdaten per API unklar → direkte Anfrage bei Meteologix empfohlen
- **Business-API:** https://www.business.meteologix.com/en/api

#### Option C: Visual Crossing (bestes Preis-Leistung-Verhältnis)

- **Solar-Parameter:** DNI, Diffuse, GHI, GTI seit 2012 (stündlich)
- **Vorhersage:** 15 Tage
- **Free-Tier:** 1000 Records/Tag (sehr großzügig)
- **Vorteil:** Ein API-Endpunkt für Historie + Forecast im gleichen Format
- **Pricing:** $0.0001 pro Record nach Free-Tier
- **Einschränkung:** Erweiterte Solar-Energy-Elemente nur in höheren Preisstufen
- **Dokumentation:** https://www.visualcrossing.com/weather-api/

#### Option D: Proplanta (kostenlos, Deutschland-fokussiert)

- Globalstrahlung in kWh/m² als Tagesprognose für 5 Tage
- 3-Stunden-Auflösung in den Wetterprognosen
- 7.500 Orte in Deutschland abgedeckt
- Kostenlos und frei zugänglich
- **Bewährt:** In der PV- und Smart-Home-Community vielfach für Akkusteuerung genutzt
- **Kein REST-API** — nur HTML-Scraping (es gibt fertige Parser für FHEM, ioBroker, HomeMatic)
- **Bezahlte API:** Existiert, nicht öffentlich dokumentiert → Anfrage bei Proplanta direkt
- **Solarwetter-Seite:** https://www.proplanta.de/solar-wetter/solarwetter.html
- **Profi-Wetter:** https://www.proplanta.de/wetter/deutschland/

#### Option E: Open-Meteo DWD ICON (kostenlos, Open Source)

- 15-Min-Daten für direkte und diffuse Solarstrahlung in Zentraleuropa (ICON-D2)
- **Satellite Radiation API:** Bündelt Satellitendaten verschiedener geostationärer Satelliten
- Komplett kostenlos und Open Source
- DWD nutzt seit März 2023 sichtbares Licht aus Satellitenbeobachtungen in Datenassimilation
- **Dokumentation:** https://open-meteo.com/en/docs/dwd-api
- **Satellite API:** https://open-meteo.com/en/docs/satellite-radiation-api

### Schicht 3: Ground Truth — E3DC-Ertragsdaten

Die tatsächlichen Ertragsdaten der eigenen E3DC-Anlage sind die Ground Truth für das ML-Training:
- Stündliche (oder höhere) Auflösung der tatsächlichen Erzeugung in kWh
- Direkt aus dem E3DC-System abrufbar
- Diese Daten werden mit den Wetterdaten gepaart: `(Wetter_Stunde_t) → (Ertrag_Stunde_t)`

## Empfohlene Implementierungs-Reihenfolge

### Phase 1: Historisches Training aufbauen

1. **DWD HOSTRADA-Daten laden (1995–2012, stündlich, 1 km²)**
   - Globalstrahlung + Temperatur + Wind + Bewölkung für die Gitterzelle Dülmen
   - Format: NetCDF, lesen mit xarray
   - Alternativ: DWD Stationsdaten Münster als Backup

2. **DWD DUETT-Daten laden (seit ~2022, stündlich, 1–2 km)**
   - Für die neuere Periode mit besserer Methodik

3. **Lücke zwischen HOSTRADA (bis 2012) und DUETT (ab ~2022)** mit DWD-Stationsdaten oder monatlichen Rastern überbrücken

4. **E3DC-Ertragsdaten korrelieren**
   - Überlappungszeitraum zwischen Wetterdaten und Ertragsdaten identifizieren

5. **Feature-Engineering:** GHI, DNI, DHI, Temperatur, Bewölkung, Tageszeit, Monat, Sonnenstand

### Phase 2: Vorhersage-Pipeline aufbauen

1. **Vorhersage-Quelle wählen und anbinden:**
   - **Budget-Option:** Solcast Free (10 Calls/Tag) + Open-Meteo als Fallback
   - **Qualitäts-Option:** Kachelmann Plus (69,90 €/Jahr) für beste lokale Genauigkeit
   - **Pragmatische Option:** Proplanta scrapen (kostenlos, bewährt, aber fragil)

2. **Einheitliches Datenformat definieren:**
   - Alle Quellen auf gemeinsames Schema mappen (Zeitstempel UTC, W/m² für Strahlung, °C etc.)
   - Gleiche Feature-Struktur wie beim Training

### Phase 3: Modell optimieren

1. **A/B-Test verschiedener Vorhersage-Quellen:**
   - Parallel mehrere Quellen abfragen
   - MAPE pro Quelle messen
   - Ggf. Ensemble aus mehreren Quellen

## Weitere Anbieter (Referenz)

### Tier 2: Gute Alternativen

| Anbieter | Stärke | Historic | Forecast | Preis | Doku |
|----------|--------|----------|----------|-------|------|
| Weatherbit | ML-Bias-Korrektur (50% weniger Fehler) | 20+ Jahre (ab Pro, $35/Mo) | 15 Tage | Free-Plan ohne Historie | https://www.weatherbit.io/api |
| OpenWeatherMap Solar | ECMWF ERA5 + CAMS | Ab 1979 | 15 Tage | Separate Subscription | https://openweathermap.org/api/solar-irradiance |
| Tomorrow.io | 60+ Data Layers, solarGHI, solarDNI | - | 7 Tage+14 Tage | Free-Tier | https://docs.tomorrow.io/reference/solar |
| Bright Sky | JSON-API für DWD Open Data | Begrenzt | MOSMIX | Kostenlos (CC BY 4.0) | https://brightsky.dev/ |

### Tier 3: Enterprise / Spezial

| Anbieter | Stärke | Hinweis |
|----------|--------|---------|
| Meteomatics (CH) | 1800+ Parameter, 90 m Downscaling, Millisekunden-Antwortzeiten | 14 Tage Trial, danach Enterprise-Pricing |
| Meteotest/SolarWebServices (CH) | 30+ Jahre Solar-Expertise, CloudMove (Wolkenbewegungsanalyse) | Anfrage erforderlich |
| Steadysun | Multi-Modell (20+ Wettermodelle + 5 Satelliten) | 4-Wochen-Trial |
| Solargis | NWP + Satelliten, Nowcast bis Medium-term | Enterprise-fokussiert |

## Technische Hinweise

### NetCDF-Zugriff (DWD-Daten)

```python
import xarray as xr
import numpy as np

# DUETT Rasterdaten laden
ds = xr.open_dataset("SIS_duett_2km_DE_60min_YYYYMMDDHHM_007.nc")

# Für Koordinaten-Umrechnung (EPSG:3034 → Lat/Lon)
from pyproj import Transformer
transformer = Transformer.from_crs("EPSG:4326", "EPSG:3034", always_xy=True)
x_duelmen, y_duelmen = transformer.transform(7.28, 51.43)

# Nächsten Gitterpunkt finden
ghi = ds['SIS'].sel(x=x_duelmen, y=y_duelmen, method='nearest')
```

### DWD Stationsdaten (CSV in ZIP)

```python
import pandas as pd
import zipfile
import io

# Station herunterladen und entpacken
with zipfile.ZipFile("stundenwerte_ST_XXXXX_row.zip") as z:
    for name in z.namelist():
        if name.startswith("produkt_"):
            df = pd.read_csv(z.open(name), sep=";", skipinitialspace=True)
            break

# Spalten: STATIONS_ID, MESS_DATUM, QN_592, ATMO_STRAHL, FD_STRAHL, FG_STRAHL, SD_STRAHL
# FG_STRAHL = Globalstrahlung in J/cm²
# Umrechnung: 1 J/cm² = 2.778 Wh/m² (für Stundenwerte)
df['GHI_Wh_m2'] = df['FG_STRAHL'] * 2.778
```

### Proplanta Scraping (Beispiel-Ansatz)

```python
import requests
from bs4 import BeautifulSoup

# URL-Schema für Profi-Wetter
url = "https://www.proplanta.de/Wetter/profi-wetter.php?SITEID=60&PLZ=48249&STADT=Duelmen"
# Alternativ Agrarwetter:
url = "https://www.proplanta.de/Agrar-Wetter/Duelmen-AgrarWetter.html"

# HTML parsen und Globalstrahlung extrahieren
# Siehe existierende Parser: FHEM (59_PROPLANTA.pm), ioBroker-Adapter
# Globalstrahlung wird als "GS" im HTML markiert
```

### Solcast Free-Tier API

```python
import requests

API_KEY = "your_key"
lat, lon = 51.43, 7.28

# Forecast
resp = requests.get(
    "https://api.solcast.com.au/world_radiation/forecasts",
    params={"latitude": lat, "longitude": lon, "output_parameters": "ghi,dni,dhi,air_temp",
            "format": "json", "api_key": API_KEY}
)
```

## Wichtige Parameter-Referenz

| Abkürzung | Bedeutung | Einheit | Relevanz für PV |
|-----------|-----------|---------|-----------------|
| GHI | Global Horizontal Irradiance | W/m² | Gesamte Einstrahlung auf horizontale Fläche |
| DNI | Direct Normal Irradiance | W/m² | Direkte Sonnenstrahlung senkrecht zum Strahl |
| DHI | Diffuse Horizontal Irradiance | W/m² | Gestreute Strahlung (Wolken, Atmosphäre) |
| GTI | Global Tilted Irradiance | W/m² | Einstrahlung auf geneigte Modulfläche |
| SIS | Surface Incoming Shortwave | W/m² | DWD-Bezeichnung für Globalstrahlung |
| FG_STRAHL | Globalstrahlung (DWD-Stationen) | J/cm² | Stundensumme, Umrechnung: ×2.778 = Wh/m² |
| FD_STRAHL | Diffusstrahlung (DWD-Stationen) | J/cm² | Stundensumme |

## Kostenübersicht

| Komponente | Kosten | Hinweis |
|------------|--------|---------|
| DWD DUETT/HOSTRADA/Stationen | 0 € | CC BY 4.0 |
| DWD Solarstrahlungsraster | 0 € | CC BY 4.0 |
| Solcast Free-Tier | 0 € | 10 Calls/Tag, nur Vorhersagen |
| Open-Meteo | 0 € | Open Source |
| Proplanta | 0 € | Scraping, kein offizielles API |
| Bright Sky | 0 € | CC BY 4.0 |
| Kachelmann Plus | 69,90 €/Jahr | Beste lokale Vorhersage-Qualität |
| Visual Crossing | 0 € (1000 Rec/Tag) | Danach $0.0001/Record |

**Minimal-Budget:** 0 € (DWD + Solcast Free + Open-Meteo)
**Optimal-Budget:** 69,90 €/Jahr (+ Kachelmann für Vorhersagen)

## Nächste Schritte

- [ ] DWD DUETT-Daten für Dülmen herunterladen und Zeitraum/Verfügbarkeit prüfen
- [ ] DWD HOSTRADA-Daten lokalisieren und für Dülmen extrahieren
- [ ] Nächste DWD-Solarstation zu Dülmen identifizieren (Stationsliste prüfen)
- [ ] E3DC-Ertragsdaten-Export für Überlappungszeitraum vorbereiten
- [ ] Solcast Free-Tier Account erstellen und Test-Abfrage durchführen
- [ ] Bei Kachelmann/Meteologix nach historischen Daten im Hobby-API-Paket fragen
- [ ] Bei Proplanta nach bezahltem API-Service fragen
- [ ] Feature-Engineering-Pipeline aufbauen (einheitliches Schema für alle Quellen)
- [ ] Baseline-Modell mit DWD-Daten + E3DC-Ertrag trainieren
- [ ] Vorhersage-Quellen vergleichen (MAPE pro Quelle)
