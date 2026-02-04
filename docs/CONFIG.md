# Konfiguration

PV-Forecast kann über CLI-Optionen oder eine YAML-Konfigurationsdatei konfiguriert werden.

## Priorität

1. **CLI-Optionen** (höchste Priorität)
2. **Config-Datei** (`~/.config/pvforecast/config.yaml`)
3. **Defaults** (niedrigste Priorität)

---

## Config-Datei

### Pfad

```
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
