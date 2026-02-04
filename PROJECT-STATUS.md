# PV-Forecast – Projektstatus

> Letzte Aktualisierung: 2026-02-04 18:09

## 🎯 Aktueller Stand: MVP FERTIG ✅

Das CLI-Tool funktioniert und ist einsatzbereit.

### Was funktioniert

| Feature | Status | Befehl |
|---------|--------|--------|
| Prognose heute | ✅ | `pvforecast today` |
| Prognose morgen+ | ✅ | `pvforecast predict` |
| CSV-Import | ✅ | `pvforecast import <csv>` |
| Training | ✅ | `pvforecast train` |
| Status | ✅ | `pvforecast status` |

### Datenstand

| Daten | Anzahl | Zeitraum |
|-------|--------|----------|
| PV-Readings | 61.354 | 2019-01-01 bis 2025-12-31 |
| Wetter | 61.320 | 2018-12-31 bis 2026-01-01 |

### Modell-Performance

| Metrik | Wert | Notiz |
|--------|------|-------|
| **MAE** | **183 W** | ~1.8% von Peak (sehr gut) |
| **MAPE** | **45.6%** | Nur für Stunden >100W berechnet |
| Trainingsdaten | 61.068 | 6 Jahre |

---

## 📂 Projektstruktur

```
~/projects/pv-forecast/
├── SPEC.md              # Vollständige Spezifikation
├── PROJECT-STATUS.md    # Diese Datei
├── README.md            # Dokumentation
├── pyproject.toml       # Python Projekt-Config
├── src/pvforecast/      # Source Code
│   ├── cli.py           # CLI Interface
│   ├── config.py        # Konfiguration
│   ├── db.py            # SQLite Layer
│   ├── data_loader.py   # E3DC CSV Import
│   ├── weather.py       # Open-Meteo Client
│   └── model.py         # ML (RandomForest)
└── tests/               # Pytest Tests
```

### Daten-Speicherorte

```
~/.local/share/pvforecast/
├── data.db              # SQLite mit PV + Wetter
└── model.pkl            # Trainiertes Modell
```

---

## 🔧 Entwicklungsumgebung

```bash
cd ~/projects/pv-forecast
source .venv/bin/activate
```

Python: 3.9.6  
Dependencies: pandas, scikit-learn, httpx

---

## 🚀 Verwendung

### Prognose für heute

```bash
pvforecast today
```

Zeigt den **ganzen heutigen Tag** (vergangene + kommende Stunden) mit:
- Erwarteter Tagesertrag in kWh
- Stundenwerte mit Wetter-Emoji
- Aktuelle Stunde markiert (◄)

### Prognose für morgen + übermorgen

```bash
# Standard: morgen + übermorgen (2 volle Tage)
pvforecast predict

# Mehr Tage
pvforecast predict --days 3

# Als JSON
pvforecast predict --format json
```

### Daten importieren & trainieren

```bash
# Neue CSV importieren
pvforecast import ~/Downloads/E3DC-Export-2026.csv

# Modell neu trainieren
pvforecast train
```

### Status prüfen

```bash
pvforecast status
```

---

## 📋 Offene TODOs

### Priorität 1 (Qualität)
- [ ] **Lücken-Erkennung**: `ensure_weather_history` findet keine Lücken in der Mitte
- [ ] **Retry-Logic**: Bei API-Timeouts automatisch wiederholen

### Priorität 2 (Features)
- [ ] `pvforecast evaluate` implementieren (Backtesting)
- [ ] Config-File Support (optional)

### Priorität 3 (Polish)
- [ ] pytest Tests durchlaufen lassen
- [ ] Git Repository auf GitHub anlegen
- [ ] XGBoost als Alternative zu RandomForest

### Priorität 4 (Später)
- [ ] GUI (Web oder TUI)
- [ ] Automatische tägliche Prognose (Cronjob)
- [ ] Vergleich Prognose vs. Realität

---

## ✅ Erledigte TODOs

- [x] MAPE-Fix: Nur Stunden >100W für Berechnung
- [x] Volle Tage: `--days 2` statt `--hours 48` (morgen + übermorgen)
- [x] `pvforecast today`: Ganzer heutiger Tag mit past_hours API

---

## 📝 Entwicklungshistorie

### 2026-02-04: MVP erstellt
- Fachexperten-Phase: Requirements mit Marcus geklärt
- Architekten-Phase: SPEC.md erstellt, Entscheidungen getroffen
- Entwickler-Phase: Alle Module implementiert
- Wetterdaten für 2019-2025 geladen
- Modell trainiert: MAE 183W, MAPE 45.6%
- **Fixes:** 
  - MAPE-Schwellwert 100W
  - Volle Tage statt 48h
  - `today` Befehl mit past_hours für ganzen Tag

---

*Diese Datei dient als Einstiegspunkt für neue Sessions.*
