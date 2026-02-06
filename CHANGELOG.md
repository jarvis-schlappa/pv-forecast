# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Hinzugefügt

- **Optuna Tuning** (`pvforecast tune --method optuna`) – Bayesian Optimization mit Pruning (#29)
- **Feature Engineering** für bessere Prognosen (#80-#83):
  - Zyklische Features (Stunde, Monat, Tag im Jahr)
  - Effective Irradiance, Clear-Sky-Index, Diffuse Fraction
  - Lag-Features (Wetter + Produktion der letzten Stunden)
  - Modultemperatur + Temperatur-Derating
  - peak_kwp Normalisierung (Vorbereitung Multi-Anlagen)

### Geändert

- **Performance verbessert:** MAPE 41.7% → 30.1% (-11.6%)

### Behoben

- CI: fetch_today Tests auf Python 3.11+ (#109)

---

## [0.1.0] - 2026-02-05

Erstes Release von PV-Forecast. 🎉

### Hinzugefügt

#### Kernfunktionen
- **Prognosen** für heute (`pvforecast today`) und kommende Tage (`pvforecast predict`)
- **E3DC CSV-Import** mit automatischer Erkennung und Deduplizierung
- **Wetter-Integration** via Open-Meteo API (kostenlos, kein API-Key nötig)
- **SQLite-Datenbank** für PV- und Wetterdaten

#### Machine Learning
- **RandomForest** Modell (Standard, keine zusätzliche Dependency)
- **XGBoost** Modell (optional, bessere Genauigkeit)
- **Hyperparameter-Tuning** mit RandomizedSearchCV (`pvforecast tune`)
- **Backtesting/Evaluation** (`pvforecast evaluate`)
- Erweiterte Wetter-Features: Wind, Luftfeuchtigkeit, Diffusstrahlung

#### Benutzerfreundlichkeit
- **Interaktiver Setup-Wizard** (`pvforecast setup`) mit Geocoding
- **System-Diagnose** (`pvforecast doctor`) für Healthchecks
- **One-Liner Installation** via curl
- Progress-Anzeigen und Timing für lange Operationen
- Benutzerfreundliche Fehlermeldungen mit Lösungsvorschlägen

#### Dokumentation
- Vollständige CLI-Referenz (`docs/CLI.md`)
- Konfigurationsanleitung (`docs/CONFIG.md`)
- Datenformat-Dokumentation (`docs/DATA.md`)
- ML-Modelle und Tuning (`docs/MODELS.md`)

### Performance

| Modell | MAE | MAPE |
|--------|-----|------|
| XGBoost (tuned) | 144 W | 30.1% |
| RandomForest | ~180 W | ~45% |

*Getestet mit 62.000 Datensätzen (2019-2026), MAPE nur für Stunden >100W.*

---

[0.1.0]: https://github.com/jarvis-schlappa/pv-forecast/releases/tag/v0.1.0
