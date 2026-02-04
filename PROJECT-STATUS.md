# PV-Forecast – Projektstatus

> Letzte Aktualisierung: 2026-02-04 22:50

## 🎯 Aktueller Stand: Phase 3 begonnen ✅

MVP + alle geplanten Verbesserungen implementiert.
Erweiterte Wetter-Features (Wind, Humidity, DHI) integriert.

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
| #25 | Erweiterte Wetter-Features | #34 | ✅ |

## 🔓 Offene Issues

| # | Titel | Prio | Phase |
|---|-------|------|-------|
| #22 | Input-Validierung | 🟢 Niedrig | 3 |
| #23 | Automatische tägliche Prognose | 🟢 Niedrig | 3 |
| #24 | Startup-Check für libomp | 🟡 Mittel | 3 |
| #26 | Feature Engineering | 🟡 Mittel | 3 |
| #27 | Separate Modelle pro Saison | 🟢 Niedrig | 3 |
| #28 | Ensemble RF+XGB | 🟢 Niedrig | 3 |
| #29 | Optuna Tuning | 🟢 Niedrig | 3 |
| #30 | RF-Tuning Geschwindigkeit | 🟢 Niedrig | 3 |
| #32 | E2E Tests Refactoring | 🟢 Niedrig | 3 |

---

## 📊 Datenstand

| Daten | Anzahl | Zeitraum |
|-------|--------|----------|
| PV-Readings | 61.354 | 2019-2025 |
| Wetter | 61.392 | 2018-2025 |

### Wetter-Features

| Feature | Beschreibung | Einfluss |
|---------|--------------|----------|
| GHI | Globalstrahlung | Hauptindikator |
| Cloud Cover | Bewölkung | Wolkenabschattung |
| Temperature | Temperatur | Moduleffizienz |
| **Wind Speed** | Windgeschwindigkeit | Modulkühlung |
| **Humidity** | Luftfeuchtigkeit | Dunst-Erkennung |
| **DHI** | Diffusstrahlung | Bewölkungs-Charakter |

## 🤖 Modell-Performance

| Modell | MAE | MAPE | Anmerkung |
|--------|-----|------|-----------|
| XGBoost (tuned) | **117 W** | **29.4%** | ⭐ Empfohlen |
| RandomForest | 183 W | 45.6% | Basis |

*Nach Integration der erweiterten Wetter-Features (Wind, Humidity, DHI) und Tuning.*

---

## 🧪 Test-Abdeckung

- **88 Tests** ✅ (Unit + E2E)
- Module: data_loader, weather, model, config, db, cli
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
