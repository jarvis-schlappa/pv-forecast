# PV-Forecast – Projektstatus

> Letzte Aktualisierung: 2026-02-04 21:25

## 🎯 Aktueller Stand: Phase 2 abgeschlossen ✅

MVP + alle geplanten Verbesserungen implementiert.

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

## 🔓 Offene Issues

| # | Titel | Prio | Phase |
|---|-------|------|-------|
| #20 | README aktualisieren | 🟡 Mittel | 2 |
| #21 | Integration Tests (E2E) | 🟡 Mittel | 2 |
| #22 | Input-Validierung | 🟢 Niedrig | 2 |
| #23 | Automatische tägliche Prognose | 🟢 Niedrig | 3 |
| #24 | Startup-Check für libomp | 🟡 Mittel | 2 |
| #25 | Erweiterte Wetter-Features | 🟡 Mittel | 3 |
| #26 | Feature Engineering | 🟡 Mittel | 3 |
| #27 | Separate Modelle pro Saison | 🟢 Niedrig | 3 |
| #28 | Ensemble RF+XGB | 🟢 Niedrig | 3 |
| #29 | Optuna Tuning | 🟢 Niedrig | 3 |

---

## 📊 Datenstand

| Daten | Anzahl | Zeitraum |
|-------|--------|----------|
| PV-Readings | 61.354 | 2019-2025 |
| Wetter | 62.136 | 2018-2025 |

## 🤖 Modell-Performance

| Modell | MAE | MAPE |
|--------|-----|------|
| RandomForest | 183 W | 45.6% |
| XGBoost | 185 W | 45.6% |

---

## 🧪 Test-Abdeckung

- **65 Unit-Tests** ✅
- Module: data_loader, weather, model, config, db
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
