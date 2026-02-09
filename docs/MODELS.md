# ML-Modelle

PV-Forecast nutzt Machine Learning um aus historischen Daten und Wettervorhersagen den erwarteten PV-Ertrag zu berechnen.

## Verfügbare Modelle

| Modell | Flag | Dependency | Geschwindigkeit | Genauigkeit |
|--------|------|------------|-----------------|-------------|
| RandomForest | `--model rf` | Keine (sklearn) | ⭐⭐⭐ | ⭐⭐ |
| XGBoost | `--model xgb` | `pvforecast[xgb]` | ⭐⭐ | ⭐⭐⭐ |

### RandomForest (Default)

- ✅ Keine zusätzliche Dependency
- ✅ Robust, wenig Overfitting
- ⚠️ Etwas weniger genau als XGBoost

```bash
pvforecast train --model rf
```

### XGBoost

- ✅ Bessere Genauigkeit
- ✅ Schnelleres Training
- ⚠️ Benötigt zusätzliche Installation

```bash
# Installation
pip install pvforecast[xgb]

# macOS: OpenMP benötigt
brew install libomp

# Training
pvforecast train --model xgb
```

---

## Training

### Basis-Training

```bash
# RandomForest (Standard)
pvforecast train

# XGBoost
pvforecast train --model xgb
```

### Was passiert beim Training?

1. **Daten laden:** PV-Readings + Wetterdaten aus SQLite joinen
2. **Features erstellen:** Stunde, Monat, Sonnenhöhe, Wetter
3. **Split:** 80% Training, 20% Test (zeitbasiert)
4. **Training:** Modell auf Trainingsdaten fitten
5. **Evaluation:** MAPE und MAE auf Testdaten berechnen
6. **Speichern:** Modell + Metriken in `.pkl`

### Features

**Basis-Features:**

| Feature | Beschreibung | Quelle |
|---------|--------------|--------|
| `hour_sin/cos` | Stunde (zyklisch) | Timestamp |
| `month_sin/cos` | Monat (zyklisch) | Timestamp |
| `day_of_year_sin/cos` | Tag im Jahr (zyklisch) | Timestamp |
| `ghi` | Globalstrahlung (W/m²) | Open-Meteo |
| `temperature` | Temperatur (°C) | Open-Meteo |
| `sun_elevation` | Sonnenhöhe (°) | Berechnet |
| `wind_speed` | Windgeschwindigkeit (m/s) | Open-Meteo |
| `humidity` | Relative Luftfeuchtigkeit (%) | Open-Meteo |
| `dhi` | Diffusstrahlung (W/m²) | Open-Meteo |
| `dni` | Direktstrahlung (W/m²) | Open-Meteo |

> **Hinweis:** `cloud_cover` wird absichtlich NICHT als Feature verwendet (#168).
> Forecast-APIs liefern oft inkonsistente Daten (100% Bewölkung bei hoher GHI).
> Die Strahlungsfeatures (GHI, DNI, CSI) sind bessere Indikatoren.

**Abgeleitete Features (ab v0.1.0):**

| Feature | Beschreibung | Berechnung |
|---------|--------------|------------|
| `csi` | Clear-Sky-Index | GHI / Clear-Sky-GHI (pvlib) |
| `diffuse_fraction` | Diffus-Anteil | DHI / (GHI + 1) |
| `t_module` | Modultemperatur | NOCT-basiert |
| `efficiency_factor` | Temperatur-Derating | 1 - 0.004 × (t_module - 25) |
| `peak_kwp` | Anlagenleistung | Konfiguration |

**Lag-Features:**

| Feature | Beschreibung |
|---------|--------------|
| `ghi_lag_1h/3h` | GHI vor 1/3 Stunden |
| `ghi_rolling_3h` | GHI Mittel letzte 3h |

> **Hinweis:** `production_lag_*` Features wurden entfernt (#170).
> Sie waren im Predict-Modus immer 0 und führten zu massiver Unterschätzung.

---

## Hyperparameter-Tuning

Für bessere Ergebnisse können die Modell-Parameter optimiert werden.

### Tuning-Methoden

| Methode | Flag | Strategie | Besonderheit |
|---------|------|-----------|--------------|
| **RandomizedSearchCV** | `--method random` | Zufällig | Standard, schnell |
| **Optuna** | `--method optuna` | Bayesian | Lernt, Pruning |

### Ausführen

```bash
# XGBoost Tuning mit RandomizedSearchCV (Standard)
pvforecast tune

# Optuna mit Bayesian Optimization (empfohlen für beste Ergebnisse)
pvforecast tune --method optuna

# Optuna mit Timeout (max 10 Minuten)
pvforecast tune --method optuna --trials 100 --timeout 600

# RandomForest Tuning
pvforecast tune --model rf

# Mehr Iterationen für bessere Ergebnisse
pvforecast tune --trials 100 --cv 10
```

### Installation (für Optuna)

```bash
pip install pvforecast[tune]
# oder: pip install optuna
```

### Parameter

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--model` | `rf` oder `xgb` | `xgb` |
| `--method` | `random` oder `optuna` | `random` |
| `--trials` | Anzahl Trials/Kombinationen | 50 |
| `--cv` | Cross-Validation Splits | 5 |
| `--timeout` | Max. Sekunden (nur Optuna) | - |

### Optuna vs RandomizedSearchCV

| Aspekt | RandomizedSearchCV | Optuna |
|--------|-------------------|--------|
| **Suchstrategie** | Zufällig | Bayesian (lernt aus Trials) |
| **Pruning** | Nein | Ja (bricht schlechte Trials ab) |
| **Effizienz** | Alle Trials vollständig | 30-50% Trials gepruned |
| **Konvergenz** | Zufallsabhängig | Gerichtet |
| **Dependency** | Inkludiert (sklearn) | `optuna>=3.0` |

**Empfehlung:** 
- **Schnelle Tests:** `--method random` (Standard)
- **Beste Ergebnisse:** `--method optuna`

### Suchraum

**XGBoost:**

| Parameter | Bereich |
|-----------|---------|
| `n_estimators` | 100-500 |
| `max_depth` | 4-12 |
| `learning_rate` | 0.01-0.3 |
| `min_child_weight` | 1-10 |
| `subsample` | 0.6-1.0 |
| `colsample_bytree` | 0.6-1.0 |

**RandomForest:**

| Parameter | Bereich |
|-----------|---------|
| `n_estimators` | 100-500 |
| `max_depth` | 5-24 |
| `min_samples_split` | 2-20 |
| `min_samples_leaf` | 1-15 |

### Dauer

**RandomizedSearchCV:**

| Modell | 50 Trials | 100 Trials |
|--------|-----------|------------|
| XGBoost | ~30 Sek | ~1 Min |
| RandomForest | ~10-15 Min | ~20-30 Min |

**Optuna:**

| Modell | 50 Trials | 100 Trials |
|--------|-----------|------------|
| XGBoost | ~2 Min | ~4 Min |
| RandomForest | ~5-10 Min | ~10-20 Min |

*Hinweis: Optuna braucht pro Trial länger, aber Pruning spart 30-50% der Trials.*

---

## Evaluation

### Backtesting

```bash
# Alle Daten
pvforecast evaluate

# Nur 2024
pvforecast evaluate --year 2024
```

### Metriken

| Metrik | Beschreibung | Gut wenn |
|--------|--------------|----------|
| **MAE** | Mean Absolute Error (Watt) | < 150 W |
| **MAPE** | Mean Absolute Percentage Error | < 35% |

**Hinweis:** MAPE wird nur für Stunden >100W berechnet (vermeidet Verzerrung bei Nacht/Dämmerung).

### Aktuelle Performance

*Mit Feature-Engineering (Issues #80-#83) und DWD-Integration (#123):*

| Datenquelle | Modell | MAE | MAPE | R² |
|-------------|--------|-----|------|-----|
| **DWD HOSTRADA** | XGBoost | **105 W** | **21.9%** | **0.974** |
| Open-Meteo | XGBoost | 126 W | 30.1% | 0.950 |
| Open-Meteo | RandomForest | ~180 W | ~45% | ~0.90 |

**Empfehlung:** HOSTRADA für Training (beste Qualität, 1 km Raster), Open-Meteo für Updates.

*Stand: 2026-02-07, 62k Datensätze (2019-2026)*

### Feature-Engineering Fortschritt

| Issue | Feature | MAPE-Verbesserung |
|-------|---------|-------------------|
| #80 | Zyklische Features | -0.2% |
| #83 | peak_kwp Normalisierung | Basis für Multi-Anlagen |
| #82 | **Lag-Features (Wetter)** | **-10%** |
| #81 | CSI, DNI, Modultemperatur | -1.4% |
| #168 | cloud_cover, effective_irradiance entfernt | -0.8% |
| #170 | production_lag entfernt (Forecast-Fix) | +X% (Backtest), Forecast funktioniert |

**Hinweis:** Backtest-MAPE kann durch #170 steigen, aber Forecasts sind jetzt korrekt.

---

## Tipps für bessere Ergebnisse

### Mehr Daten

Je mehr historische Daten, desto besser:
- Mindestens 1 Jahr für saisonale Effekte
- Idealerweise 3+ Jahre

### Datenqualität

- Abregelungsdaten werden automatisch ausgeschlossen (`curtailed=1`) – siehe [DATA.md](DATA.md#was-passiert-beim-import)
- Negative Werte werden ignoriert
- Fehlende Wetterdaten werden automatisch nachgeladen

### Tuning

1. Erst mit Defaults trainieren
2. Performance prüfen (`pvforecast evaluate`)
3. Bei Bedarf tunen (`pvforecast tune`)
4. Ggf. mehr Trials

### Modellwahl

- **Wenig Zeit:** RandomForest (keine Tuning nötig)
- **Beste Genauigkeit:** XGBoost + Tuning
