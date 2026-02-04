# Datenformat & Import

## Unterstützte Formate

Aktuell wird das E3DC CSV-Format unterstützt. Weitere Formate können bei Bedarf ergänzt werden.

---

## E3DC CSV-Import

### Export erstellen

1. E3DC Portal öffnen (https://my.e3dc.com)
2. **Statistik** → **Export** wählen
3. Zeitraum auswählen
4. CSV herunterladen

### Dateiformat

```csv
"Zeitstempel";"Ladezustand [%]";"Solarproduktion [W]";"Batterie Laden [W]";"Batterie Entladen [W]";"Netzeinspeisung [W]";"Netzbezug [W]";"Hausverbrauch [W]";"Abregelungsgrenze [W]"
01.01.2024 00:00:00;45;0;0;200;0;100;300;5000
01.01.2024 01:00:00;43;0;0;150;0;80;230;5000
...
```

| Eigenschaft | Wert |
|-------------|------|
| Trennzeichen | Semikolon (`;`) |
| Dezimaltrennzeichen | Komma (`,`) in deutschen Exports |
| Datumsformat | `DD.MM.YYYY HH:MM:SS` |
| Zeitzone | Europe/Berlin (lokal) |
| Encoding | UTF-8 |

### Wichtige Spalten

| Spalte | Beschreibung | Verwendet für |
|--------|--------------|---------------|
| `Zeitstempel` | Datum und Uhrzeit | Timestamp |
| `Solarproduktion [W]` | PV-Erzeugung in Watt | Training & Evaluation |
| `Abregelungsgrenze [W]` | Max. erlaubte Einspeisung | Abregelungs-Erkennung |
| `Ladezustand [%]` | Batterie-SoC | Optional |

### Import

```bash
# Einzelne Datei
pvforecast import E3DC-Export-2024.csv

# Mehrere Dateien (Wildcards)
pvforecast import E3DC-Export-*.csv

# Absoluter Pfad
pvforecast import ~/Downloads/E3DC-Export-2024-01.csv

# Mehrere Jahre
pvforecast import \
  ~/Downloads/E3DC-2022.csv \
  ~/Downloads/E3DC-2023.csv \
  ~/Downloads/E3DC-2024.csv
```

### Was passiert beim Import?

1. **Parsing:** CSV lesen, Spalten erkennen
2. **Konvertierung:** Deutsches Datumsformat → UTC Unix Timestamp
3. **Abregelung:** Wenn `Solarproduktion >= Abregelungsgrenze * 0.95` → `curtailed=1`
4. **Deduplizierung:** Existierende Timestamps werden übersprungen
5. **Speichern:** In SQLite-Datenbank

---

## Datenbank

### Schema

```sql
-- PV-Ertragsdaten
CREATE TABLE pv_readings (
    timestamp       INTEGER PRIMARY KEY,  -- Unix timestamp (UTC)
    production_w    INTEGER NOT NULL,     -- Solarproduktion [W]
    curtailed       INTEGER DEFAULT 0,    -- 1 wenn abgeregelt
    soc_pct         INTEGER,              -- Ladezustand [%]
    grid_feed_w     INTEGER,              -- Netzeinspeisung [W]
    grid_draw_w     INTEGER,              -- Netzbezug [W]
    consumption_w   INTEGER               -- Hausverbrauch [W]
);

-- Wetterdaten (von Open-Meteo)
CREATE TABLE weather_history (
    timestamp           INTEGER PRIMARY KEY,
    ghi_wm2             REAL NOT NULL,    -- Globalstrahlung W/m²
    cloud_cover_pct     INTEGER,          -- Bewölkung %
    temperature_c       REAL              -- Temperatur °C
);
```

### Pfad

```
~/.local/share/pvforecast/data.db
```

### Direkt abfragen

```bash
# SQLite CLI
sqlite3 ~/.local/share/pvforecast/data.db

# Beispiel-Queries
sqlite> SELECT COUNT(*) FROM pv_readings;
sqlite> SELECT date(timestamp, 'unixepoch') as day, 
               SUM(production_w)/1000.0 as kwh 
        FROM pv_readings 
        GROUP BY day 
        ORDER BY day DESC 
        LIMIT 10;
```

---

## Wetterdaten

Wetterdaten werden automatisch von [Open-Meteo](https://open-meteo.com/) geladen:

- **Historisch:** Archive API (ERA5-Reanalyse)
- **Vorhersage:** Forecast API (bis 16 Tage)

### Geladene Parameter

| Parameter | API-Name | Beschreibung |
|-----------|----------|--------------|
| GHI | `shortwave_radiation` | Globalstrahlung (W/m²) |
| Bewölkung | `cloud_cover` | Bewölkungsgrad (%) |
| Temperatur | `temperature_2m` | Temperatur in 2m Höhe (°C) |

### Automatisches Laden

Beim Training werden fehlende historische Wetterdaten automatisch nachgeladen:

```
🌤️  Lade historische Wetterdaten...
   1.234 neue Wetterdatensätze geladen
```

---

## Timezones

| Kontext | Timezone |
|---------|----------|
| E3DC CSV | Europe/Berlin (lokal) |
| Datenbank (intern) | **UTC** |
| Open-Meteo API | UTC |
| CLI-Ausgabe | Europe/Berlin (konfigurierbar) |

Alle Timestamps werden intern als Unix-Timestamps (Sekunden seit 1970-01-01 UTC) gespeichert.

---

## Troubleshooting

### "Keine Daten importiert"

```bash
# Datei prüfen
head -5 export.csv

# Encoding prüfen (sollte UTF-8 sein)
file export.csv
```

### "Falsches Datumsformat"

Das erwartete Format ist `DD.MM.YYYY HH:MM:SS`:
- ✅ `01.06.2024 12:00:00`
- ❌ `2024-06-01 12:00:00`
- ❌ `06/01/2024 12:00:00`

### "Duplikate werden übersprungen"

Normal! Bereits importierte Timestamps werden nicht erneut importiert. Das ermöglicht inkrementelle Imports.

### Daten zurücksetzen

```bash
# Datenbank löschen
rm ~/.local/share/pvforecast/data.db

# Modell löschen
rm ~/.local/share/pvforecast/model.pkl

# Neu importieren
pvforecast import *.csv
pvforecast train
```
