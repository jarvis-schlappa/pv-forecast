# PV-Forecast – Projektstatus

> Letzte Aktualisierung: 2026-02-05 17:55

## 🎯 Aktueller Stand: Phase 2 abgeschlossen ✅

MVP + alle geplanten Verbesserungen implementiert.
CLI-Output optimiert (Progress, Timing, weniger Verbose).

---

## ✅ Erledigte Issues

| # | Titel | PR | Status |
|---|-------|-----|--------|
| #1 | Lücken-Erkennung | #7 | ✅ |
| #2 | Retry-Logic | #8 | ✅ |
| #3 | evaluate (Backtesting) | #15 | ✅ |
| #4 | Config-File (YAML) | #9 | ✅ |
| #5 | Tests vervollständigen | #16 | ✅ |
| #6 | XGBoost | #19 | ✅ |
| #10 | Config-Validierung | #13 | ✅ |
| #11 | Bulk Insert Performance | #14 | ✅ |
| #12 | Retry 429 + Jitter | #17 | ✅ |
| #18 | Hyperparameter-Tuning | #30 | ✅ |
| #20 | Dokumentation (docs/) | #33 | ✅ |
| #21 | E2E Integration Tests | #31 | ✅ |
| #22 | Input-Validierung | #41 | ✅ |
| #24 | libomp Startup-Check | #42 | ✅ |
| #25 | Erweiterte Wetter-Features | #34 | ✅ |
| #32 | E2E Tests Refactoring | #40 | ✅ |
| #43 | CLI-Koordinaten-Validierung | #44 | ✅ |
| #45 | CLI Output Cleanup | #48 | ✅ |
| #46 | Progress-Anzeige | #49 | ✅ |
| #47 | Timing bei Operationen | #49 | ✅ |

## 🔓 Offene Issues

| # | Titel | Prio | Beschreibung |
|---|-------|------|--------------|
| #23 | Automatische tägliche Prognose | 🟢 Niedrig | Cron-Integration |
| #26 | Feature Engineering | 🟡 Mittel | Weitere ML-Features |
| #27 | Separate Modelle pro Saison | 🟢 Niedrig | Sommer/Winter-Split |
| #28 | Ensemble RF+XGB | 🟢 Niedrig | Modell-Kombination |
| #29 | Optuna Tuning | 🟢 Niedrig | Besseres Hyperparameter-Tuning |
| #36-39 | Home Assistant Integration | 🟡 Mittel | HA-Sensor |
| #50 | Alternative Weather Provider | 🟡 Mittel | Solcast, Forecast.Solar |
| #51 | Dokumentation aktualisieren | 🟢 Niedrig | Post-Phase-2 Cleanup |

---

## 📊 Datenstand

| Daten | Anzahl | Zeitraum |
|-------|--------|----------|
| PV-Readings | 62.212 | 2019-2026 |
| Wetter | 62.256 | 2018-2026 |

### Wetter-Features

| Feature | Beschreibung | Einfluss |
|---------|--------------|----------|
| GHI | Globalstrahlung | Hauptindikator |
| Cloud Cover | Bewölkung | Wolkenabschattung |
| Temperature | Temperatur | Moduleffizienz |
| Wind Speed | Windgeschwindigkeit | Modulkühlung |
| Humidity | Luftfeuchtigkeit | Dunst-Erkennung |
| DHI | Diffusstrahlung | Bewölkungs-Charakter |

## 🤖 Modell-Performance

| Modell | MAE | MAPE | Anmerkung |
|--------|-----|------|-----------|
| XGBoost (tuned) | **111 W** | **30.3%** | ⭐ Empfohlen |
| RandomForest | 168 W | 46.0% | Basis |

*MAPE nur für Stunden >100W. Mit erweiterten Wetter-Features.*

---

## 🧪 Test-Abdeckung

- **158 Tests** ✅ (Unit + E2E)
- Module: validation, data_loader, weather, model, config, db, cli
- CI: GitHub Actions (Python 3.9-3.12)

---

## 🚀 Befehle

```bash
cd ~/projects/pv-forecast && source .venv/bin/activate

# Prognose
pvforecast today              # heute (ganzer Tag)
pvforecast predict            # morgen + übermorgen
pvforecast predict --days 3   # 3 Tage

# Training
pvforecast train              # RandomForest (default)
pvforecast train --model xgb  # XGBoost

# Hyperparameter-Tuning
pvforecast tune               # XGBoost Tuning (default)
pvforecast tune --model rf    # RandomForest Tuning
pvforecast tune --trials 100  # Mehr Iterationen

# Verwaltung
pvforecast status             # DB-Status
pvforecast import <csv>       # E3DC CSV importieren
pvforecast evaluate           # Modell evaluieren

# Konfiguration
pvforecast config --show      # Config anzeigen
pvforecast config --init      # Config-Datei erstellen
```

### Beispiel-Output (neu mit Progress + Timing)

```
[1/3] E3DC-Export-2024.csv: 8782 neue Datensätze
[2/3] E3DC-Export-2025.csv: 8758 neue Datensätze
[3/3] E3DC-Export-2026.csv: 858 neue Datensätze
✅ Import abgeschlossen in 1s: 18398 neue Datensätze

🌤️  Lade historische Wetterdaten...
   62256 neue Wetterdatensätze geladen in 1m 8s

✅ Training abgeschlossen in 2s!
✅ Tuning abgeschlossen in 4m 23s!
```

---

## 📂 Dateien

```
~/.config/pvforecast/config.yaml    # Konfiguration
~/.local/share/pvforecast/data.db   # Datenbank
~/.local/share/pvforecast/model.pkl # Trainiertes Modell
```

---

## 🔗 Links

- **GitHub:** https://github.com/jarvis-schlappa/pv-forecast
- **CI:** GitHub Actions (Python 3.9-3.12)
- **Issues:** https://github.com/jarvis-schlappa/pv-forecast/issues
