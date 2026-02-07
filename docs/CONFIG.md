# Konfiguration

PV-Forecast kann über CLI-Optionen oder eine YAML-Konfigurationsdatei konfiguriert werden.

## Priorität

1. **CLI-Optionen** (höchste Priorität)
2. **Config-Datei** (`~/.config/pvforecast/config.yaml`)
3. **Defaults** (niedrigste Priorität)

---

## Config-Datei

### Pfad

```text
~/.config/pvforecast/config.yaml
```

### Erstellen

```bash
# Config-Datei mit Defaults erstellen
pvforecast config --init

# Pfad anzeigen
pvforecast config --path

# Aktuelle Config anzeigen
pvforecast config --show
```

### Format

```yaml
# ~/.config/pvforecast/config.yaml

# Standort der PV-Anlage
location:
  latitude: 51.83      # Breitengrad
  longitude: 7.28      # Längengrad

# Anlagen-Daten
system:
  name: "Meine PV-Anlage"   # Name für Anzeige
  peak_kwp: 9.92            # Peak-Leistung in kWp

# Wetterdaten-Quellen
weather:
  forecast_provider: open-meteo   # Für Vorhersagen: mosmix | open-meteo
  historical_provider: open-meteo # Für historische Daten: hostrada | open-meteo
  
  # MOSMIX-Einstellungen (DWD Vorhersage)
  mosmix:
    station: P0051  # Dülmen - siehe Stationsliste unten
  
  # HOSTRADA-Einstellungen (DWD historische Rasterdaten)
  hostrada: {}  # Nutzt automatisch latitude/longitude

# Zeitzone für Ausgabe
timezone: Europe/Berlin

# Pfade (optional, Defaults empfohlen)
paths:
  db: ~/.local/share/pvforecast/data.db
  model: ~/.local/share/pvforecast/model.pkl
```

---

## Alle Parameter

### Standort

| Parameter | CLI | Config | Default | Beschreibung |
|-----------|-----|--------|---------|--------------|
| Breitengrad | `--lat` | `location.latitude` | 51.83 | Breitengrad in Dezimalgrad |
| Längengrad | `--lon` | `location.longitude` | 7.28 | Längengrad in Dezimalgrad |

### System

| Parameter | CLI | Config | Default | Beschreibung |
|-----------|-----|--------|---------|--------------|
| Name | - | `system.name` | "Dülmen PV" | Name für Anzeige |
| Peak-Leistung | - | `system.peak_kwp` | 9.92 | kWp der Anlage |

### Pfade

| Parameter | CLI | Config | Default | Beschreibung |
|-----------|-----|--------|---------|--------------|
| Datenbank | `--db` | `paths.db` | `~/.local/share/pvforecast/data.db` | SQLite-Datenbank |
| Modell | - | `paths.model` | `~/.local/share/pvforecast/model.pkl` | Trainiertes Modell |

### Wetterdaten

| Parameter | CLI | Config | Default | Beschreibung |
|-----------|-----|--------|---------|--------------|
| Forecast-Provider | `--source` | `weather.forecast_provider` | open-meteo | `mosmix` oder `open-meteo` |
| Historical-Provider | `--source` | `weather.historical_provider` | open-meteo | `hostrada` oder `open-meteo` |
| MOSMIX-Station | - | `weather.mosmix.station` | P0051 | MOSMIX-Stationskennung |

### Sonstige

| Parameter | CLI | Config | Default | Beschreibung |
|-----------|-----|--------|---------|--------------|
| Zeitzone | - | `timezone` | Europe/Berlin | Zeitzone für Ausgabe |
| Verbose | `-v` | - | aus | Ausführliche Ausgabe |

---

## Beispiel-Konfigurationen

### Minimal (nur Standort)

```yaml
location:
  latitude: 52.52
  longitude: 13.405
```

### Vollständig

```yaml
location:
  latitude: 52.52
  longitude: 13.405

system:
  name: "Berlin PV"
  peak_kwp: 5.5

timezone: Europe/Berlin

paths:
  db: ~/.local/share/pvforecast/data.db
  model: ~/.local/share/pvforecast/model.pkl
```

### Mehrere Anlagen

Für mehrere Anlagen separate Datenbanken verwenden:

```bash
# Anlage 1
pvforecast --db ~/pv/anlage1.db import anlage1.csv
pvforecast --db ~/pv/anlage1.db --lat 51.83 --lon 7.28 train

# Anlage 2
pvforecast --db ~/pv/anlage2.db import anlage2.csv
pvforecast --db ~/pv/anlage2.db --lat 52.52 --lon 13.41 train
```

---

## Dateipfade

| Datei | Pfad | Beschreibung |
|-------|------|--------------|
| Config | `~/.config/pvforecast/config.yaml` | Konfiguration |
| Datenbank | `~/.local/share/pvforecast/data.db` | PV + Wetterdaten |
| Modell | `~/.local/share/pvforecast/model.pkl` | Trainiertes ML-Modell |

Die Verzeichnisse werden bei Bedarf automatisch erstellt.

---

## Wetterdaten-Quellen

### Übersicht

| Quelle | Typ | Beschreibung | Auflösung |
|--------|-----|--------------|-----------|
| **MOSMIX** | Forecast | DWD Vorhersage für lokale Stationen | Stündlich, 10 Tage |
| **HOSTRADA** | Historical | DWD Rasterdaten Deutschland | 1 km, stündlich, ab 1995 |
| **Open-Meteo** | Beides | API-Service (ERA5/ECMWF) | ~11 km, stündlich |

### MOSMIX-Stationen

MOSMIX-Vorhersagen sind für einzelne Stationen verfügbar. Die Station wird über die Kennung konfiguriert:

```yaml
weather:
  mosmix:
    station: P0051  # Dülmen
```

**Stationsliste:** https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/

**Beispielstationen:**

| Station | Ort |
|---------|-----|
| P0051 | Dülmen |
| 10315 | Berlin-Tegel |
| 10382 | Berlin-Schönefeld |
| 10513 | Hamburg-Fuhlsbüttel |
| 10865 | München-Flughafen |

### HOSTRADA vs Open-Meteo (Performance)

HOSTRADA liefert bessere Trainingsdaten als Open-Meteo:

| Metrik | Open-Meteo | HOSTRADA | Verbesserung |
|--------|------------|----------|--------------|
| **MAE** | 126 W | 105 W | -17% |
| **MAPE** | 31.3% | 21.9% | -9.4 PP |
| **R²** | 0.948 | 0.974 | +0.026 |

**Empfehlung:**
- **Training:** HOSTRADA (einmalig, beste Qualität)
- **Updates:** Open-Meteo (schnell, geringere Latenz)
- **Forecasts:** MOSMIX oder Open-Meteo (beides gut)

### HOSTRADA Download-Warnung

HOSTRADA lädt komplette Deutschland-Raster herunter (~150 MB/Monat/Parameter). Bei 7 Jahren Daten sind das ~50 GB Download für wenige MB Nutzdaten (nur ein Gridpunkt).

Vor dem Download erscheint eine Warnung:

```
⚠️  HOSTRADA lädt komplette Deutschland-Raster herunter.
    Geschätzter Download: ~40.0 GB (7 Jahre × 5 Parameter)
    Extrahierte Daten: wenige MB (nur Gridpunkt 51.85°N, 7.26°E)

Fortfahren? [y/N]: 
```

Mit `--yes` wird diese Bestätigung übersprungen (für Automatisierung).
