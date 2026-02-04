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

| Feature | Beschreibung | Quelle |
|---------|--------------|--------|
| `hour` | Stunde (0-23) | Timestamp |
| `month` | Monat (1-12) | Timestamp |
| `day_of_year` | Tag im Jahr | Timestamp |
| `ghi` | Globalstrahlung (W/m²) | Open-Meteo |
| `cloud_cover` | Bewölkung (%) | Open-Meteo |
| `temperature` | Temperatur (°C) | Open-Meteo |
| `sun_elevation` | Sonnenhöhe (°) | Berechnet |

---

## Hyperparameter-Tuning

Für bessere Ergebnisse können die Modell-Parameter optimiert werden.

### Ausführen

```bash
# XGBoost Tuning (empfohlen)
pvforecast tune

# RandomForest Tuning (dauert länger)
pvforecast tune --model rf

# Mehr Iterationen für bessere Ergebnisse
pvforecast tune --trials 100 --cv 10
```

### Parameter

| Option | Beschreibung | Default |
|--------|--------------|---------|
| `--model` | `rf` oder `xgb` | `xgb` |
| `--trials` | Anzahl Kombinationen | 50 |
| `--cv` | Cross-Validation Splits | 5 |

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

| Modell | 50 Trials | 100 Trials |
|--------|-----------|------------|
| XGBoost | ~2-5 Min | ~5-10 Min |
| RandomForest | ~10-15 Min | ~20-30 Min |

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
| **MAE** | Mean Absolute Error (Watt) | < 200 W |
| **MAPE** | Mean Absolute Percentage Error | < 30% |

**Hinweis:** MAPE wird nur für Stunden >100W berechnet (vermeidet Verzerrung bei Nacht/Dämmerung).

### Aktuelle Performance

| Modell | MAE | MAPE |
|--------|-----|------|
| RandomForest (default) | 183 W | 45.6% |
| XGBoost (default) | 185 W | 45.6% |
| XGBoost (tuned) | 176 W | 43.4% |

---

## Tipps für bessere Ergebnisse

### Mehr Daten

Je mehr historische Daten, desto besser:
- Mindestens 1 Jahr für saisonale Effekte
- Idealerweise 3+ Jahre

### Datenqualität

- Abregelungsdaten werden automatisch ausgeschlossen (`curtailed=1`)
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
