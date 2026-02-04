# PV-Forecast 🔆

Ertragsprognose für Photovoltaik-Anlagen auf Basis historischer Daten und Wettervorhersagen.

## Features

- 📊 **Tagesprognose** für heute, morgen und übermorgen
- 🌤️ **Wetterintegration** via Open-Meteo API (kostenlos)
- 🧠 **ML-basiert** (RandomForest, trainiert auf deinen echten Daten)
- 💾 **E3DC Import** (CSV-Export direkt verwendbar)
- 🖥️ **Cross-Platform** (macOS, Linux)

## Installation

```bash
# Repository klonen
git clone https://github.com/jarvis-schlappa/pv-forecast.git
cd pv-forecast

# Virtual Environment erstellen
python3 -m venv .venv
source .venv/bin/activate

# Dependencies installieren
pip install -e .
```

## Schnellstart

```bash
# 1. Historische PV-Daten importieren
pvforecast import ~/Downloads/E3DC-Export-*.csv

# 2. Modell trainieren (lädt automatisch Wetterdaten)
pvforecast train

# 3. Prognose erstellen
pvforecast today     # Heute
pvforecast predict   # Morgen + übermorgen
```

## Verwendung

### Prognose für heute

```bash
pvforecast today
```

Zeigt den **ganzen heutigen Tag** (vergangene + kommende Stunden):

```
PV-Prognose für heute (04.02.2026)
Dülmen PV (9.92 kWp)

══════════════════════════════════════════════════
  Erwarteter Tagesertrag:    18.8 kWh
══════════════════════════════════════════════════

  Stundenwerte
  ───────────────────────────────────
  06:00       0 W   ☁️
  09:00     412 W   ☀️
  10:00    1797 W   ☀️
  11:00    2840 W   ☀️
  12:00    3937 W   ☀️
  13:00    3535 W   ☀️
  14:00    3349 W   ☀️
  15:00    1613 W   ☀️
  16:00     949 W   ☀️
  17:00     361 W   ☁️
  18:00       0 W   ☁️ ◄  ← aktuelle Stunde
```

### Prognose für morgen + übermorgen

```bash
# Standard: morgen + übermorgen
pvforecast predict

# Mehr Tage (z.B. 3 Tage ab morgen)
pvforecast predict --days 3

# Als JSON (für Weiterverarbeitung)
pvforecast predict --format json

# Als CSV
pvforecast predict --format csv
```

### Daten importieren

```bash
# Einzelne Datei
pvforecast import E3DC-Export-2024.csv

# Mehrere Dateien
pvforecast import E3DC-Export-*.csv
```

### Status anzeigen

```bash
pvforecast status
```

### Modell trainieren

```bash
# Trainiert auf allen importierten Daten
pvforecast train
```

## Konfiguration

Standardwerte können per CLI überschrieben werden:

```bash
pvforecast --lat 51.83 --lon 7.28 predict
pvforecast --db /path/to/custom.db predict
```

### Defaults

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| `latitude` | 51.83 | Breitengrad (Dülmen) |
| `longitude` | 7.28 | Längengrad |
| `days` | 2 | Prognose-Tage (morgen + übermorgen) |
| `db_path` | `~/.local/share/pvforecast/data.db` | SQLite-Datenbank |
| `model_path` | `~/.local/share/pvforecast/model.pkl` | Trainiertes Modell |

## Datenformat

### E3DC CSV

Das Tool erwartet CSV-Exporte aus dem E3DC Portal:

```csv
"Zeitstempel";"Ladezustand [%]";"Solarproduktion [W]";...
01.01.2024 00:00:00;45;0;...
```

- Semikolon als Trennzeichen
- Deutsches Datumsformat (DD.MM.YYYY HH:MM:SS)
- Zeitzone: Europe/Berlin

## Wie funktioniert's?

1. **Datenimport**: E3DC CSV → SQLite (Timestamps werden zu UTC konvertiert)
2. **Wetterdaten**: Open-Meteo API liefert historische Globalstrahlung, Bewölkung, Temperatur
3. **Training**: RandomForest lernt Zusammenhang Wetter → PV-Ertrag
4. **Prognose**: Wettervorhersage + Modell → erwarteter Ertrag

### ML-Features

| Feature | Beschreibung |
|---------|--------------|
| `hour` | Stunde (0-23) |
| `month` | Monat (saisonale Effekte) |
| `day_of_year` | Tag im Jahr |
| `ghi` | Globalstrahlung (W/m²) |
| `cloud_cover` | Bewölkung (%) |
| `temperature` | Temperatur (°C) |
| `sun_elevation` | Sonnenhöhe (°) |

### Performance

- **MAE**: 183 W (durchschnittlicher Fehler)
- **MAPE**: 45.6% (nur für Stunden >100W)

## Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `pvforecast today` | Prognose für heute (ganzer Tag) |
| `pvforecast predict` | Prognose morgen + übermorgen |
| `pvforecast predict --days N` | Prognose für N Tage ab morgen |
| `pvforecast import <csv>` | CSV-Daten importieren |
| `pvforecast train` | Modell trainieren |
| `pvforecast status` | Status anzeigen |

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

## Credits

- Wetterdaten: [Open-Meteo](https://open-meteo.com/)
- Inspiration: Eigene PV-Anlage optimieren 🌞
