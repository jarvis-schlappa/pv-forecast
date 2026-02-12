# Physics-Informed Hybrid-Forecasting für pvforecast

> **Projekt:** pv-forecast v0.5.0 | **Anlage:** 10 kWp, 3 Ausrichtungen, Dülmen  
> **Datum:** Februar 2026 | **Aktueller MAPE:** 25.3% (eval) / 29.0% (train) | **Ziel:** < 20%  
> **Version:** 2.1 – Aktualisiert nach Timestamp-Fix (12.02.2026)

---

## 1. Executive Summary

Dieses Konzept beschreibt die nächsten Schritte zur Verbesserung von pvforecast. Phase 1 (Feature Engineering) ist implementiert, der Timestamp-Fix (PRs #178, #179, #183) hat alle Datenquellen auf Intervallanfang normalisiert. Aktueller Stand: MAPE 25.3% (eval 2025).

| Kennzahl | Ist-Stand (12.02.2026) | Ziel |
|----------|----------------------|------|
| MAPE (eval 2025) | 25.3% | < 20% |
| MAPE (train) | 29.0% | — |
| MAE | 122W (eval) / 112W (train) | < 100W |
| R² | 0.968 (eval) / 0.963 (train) | > 0.98 |
| Historische Daten | HOSTRADA (Messwerte) | Bleibt |
| Forecast-Quelle | Open-Meteo (ICON/IFS) | Open-Meteo + GFS Ensemble |
| Physik-Modell | pvlib nur für CSI | pvlib (3 Arrays, Transposition) |
| ML-Aufgabe | Wetter → Ertrag (End-to-End) | Bias-Korrektur + Residuen |
| Unsicherheit | Keine (Punktprognose) | Quantile (10/50/90) |

---

## 2. Ist-Stand der Implementierung

### 2.1 Bereits implementierte Features (Phase 1 ✓)

| Feature | Status | Code-Referenz |
|---------|--------|---------------|
| Zyklische Zeitfeatures (sin/cos) | ✅ Implementiert | `model.py: encode_cyclic()` |
| pvlib Clear-Sky-Index (CSI) | ✅ Implementiert | `model.py: Location.get_clearsky()` |
| Diffuse Fraction (DHI/GHI) | ✅ Implementiert | `model.py: diffuse_fraction` |
| DNI (Direct Normal Irradiance) | ✅ Implementiert | `model.py: dni_wm2` |
| Modultemperatur (NOCT) | ✅ Implementiert | `model.py: t_module` |
| Temperatur-Derating | ✅ Implementiert | `model.py: efficiency_factor` |
| Wetter-Lags (1h, 3h, rolling) | ✅ Implementiert | `model.py: ghi_lag_1h` etc. |
| DHI physikalisch korrekt (#163) | ✅ Implementiert | v0.4.2: Clearness Index |
| Cloud Cover entfernt (#168) | ✅ Bewusst entfernt | Inkonsistent mit GHI |
| Production Lags entfernt (#170) | ✅ Bewusst entfernt | Train/Predict-Mismatch |

### 2.2 Aktuelle Architektur

```
Training:   HOSTRADA (Messwerte)  →  prepare_features()  →  XGBoost  →  Modell
Forecast:   Open-Meteo (ICON/IFS) →  prepare_features()  →  Modell   →  Ertrag
```

**Bekanntes Problem: Train/Predict-Gap.** Das Modell trainiert auf HOSTRADA-Messwerten (Ground Truth GHI), prognostiziert aber mit Open-Meteo-Vorhersagewerten. Die systematischen Fehler der Wettervorhersage hat das Modell nie gesehen.

### 2.3 Aktuelle Datenquellen

| Komponente | Quelle | Speicherung |
|------------|--------|-------------|
| Historische Wetterdaten | DWD HOSTRADA (Rasterdaten) | `weather_history` Tabelle |
| Forecast-Daten | Open-Meteo + MOSMIX | `forecast_history` Tabelle ✅ |
| PV-Ertragsdaten | E3DC CSV Export | `pv_readings` Tabelle |

---

## 3. Grundprinzip: Warum Hybrid?

Die gesamte Unsicherheit der PV-Prognose stammt aus der **Wolkenvorhersage**. Der bisherige End-to-End-Ansatz zwingt das ML-Modell, sowohl Wetterfehler als auch PV-Physik zu lernen.

**Bisheriger Ansatz (aktuell):**
```
Open-Meteo GHI  →  prepare_features()  →  XGBoost  →  Ertrag (Watt)
```

**Neuer Ansatz (Hybrid-Pipeline):**
```
Open-Meteo GHI  →  ML-Bias-Korrektur    →  korrigierte GHI
korrigierte GHI →  pvlib (3 Arrays)      →  theoretischer Ertrag
theor. Ertrag   →  ML-Residualkorrektur  →  reale Prognose
```

Die Residualkorrektur lernt implizit Verschattung durch umliegende Bebauung sowie Wechselrichter-Verluste.

---

## 4. Vorab-Validierung

### 4.1 Obergrenze des Verbesserungspotenzials ✅

**Status: Aktualisiert am 12.02.2026 (nach Timestamp-Fix)**

Backtesting 2025 mit HOSTRADA-Daten statt Open-Meteo als Forecast-Input:

| Metrik | Mit Forecast | Mit HOSTRADA (perfekt) | Gap |
|--------|--------------|------------------------|-----|
| MAPE | 25.3% | 24.2% | **1.1%** |
| MAE | 122W | 121W | 1W |
| R² | 0.968 | 0.969 | 0.001 |

*Zum Vergleich – vor Timestamp-Fix (09.02.2026): 29.4% → 23.3%, Gap 6.1%*

**Interpretation:** Der Wetter-Gap ist nach dem Timestamp-Fix von 6.1% auf nur noch **1.1%** geschrumpft. Das bedeutet:
- Das Modell kompensiert Forecast-Fehler bereits sehr gut durch die Feature-Lags
- Die **MOS-Schicht (Phase 2b) hat deutlich weniger Potenzial** als ursprünglich angenommen (~1% statt ~6%)
- Die verbleibenden ~24% MAPE sind primär **Modell-Limits** (Verschattung, Schnee, Wechselrichter-Verluste, etc.)
- **Größtes Verbesserungspotenzial liegt jetzt bei pvlib (3 Arrays, Transposition) und Residualkorrektur**, nicht bei Wetterkorrektur

### 4.2 Weitere Tests (ausstehend)

| Test | Aufwand | Was er zeigt | Status |
|------|---------|--------------|--------|
| Backtesting mit HOSTRADA | 1-2h | Obergrenze des Potenzials | ✅ Erledigt |
| Open-Meteo Bias-Analyse | 2-3h | MOS-Schicht-Potenzial | ⏳ Nach Datensammlung |
| NWP-Fehlerkorrelation | 0.5 Tage | Ensemble-Mehrwert | ⏳ Offen |

---

## 5. Phase 2: MOS-Schicht + physikalisches PV-Modell

> **Aufwand:** 2–3 Tage · **Erwartetes MAPE:** 18–22%

### 5.1 ML-basierte Strahlungskorrektur (MOS-Schicht)

**Datensammlung (Voraussetzung) ✅**

```sql
-- Neue Tabelle (implementiert in v0.5.0)
CREATE TABLE forecast_history (
    id              INTEGER PRIMARY KEY,
    issued_at       INTEGER NOT NULL,     -- Wann der Forecast erstellt wurde
    target_time     INTEGER NOT NULL,     -- Für welchen Zeitpunkt
    source          TEXT NOT NULL,        -- 'open-meteo', 'mosmix'
    ghi_wm2         REAL,
    cloud_cover_pct INTEGER,
    temperature_c   REAL,
    ...
);
```

**Trainings-Setup (nach 2-3 Monaten Datensammlung):**
```python
# Features: Open-Meteo Vorhersage + Kontext
X = df[['openmeteo_ghi', 'openmeteo_cloud', 'clearsky_ghi',
        'hour_sin', 'hour_cos', 'doy_sin', 'doy_cos']]

# Target: HOSTRADA-Messung (Ground Truth)
y = df['hostrada_ghi']

# Leichtes Modell
mos_model = LGBMRegressor(n_estimators=100, max_depth=4)
```

### 5.2 pvlib PV-System-Modell (3 Arrays)

**Konfigurationserweiterung (TODO):**
```yaml
pv_system:
  arrays:
    - name: "Ausrichtung 1"
      azimuth: ???          # Grad, 180 = Süd
      tilt: ???             # Grad Neigung
      kwp: ???
    - name: "Ausrichtung 2"
      azimuth: ???
      tilt: ???
      kwp: ???
    - name: "Ausrichtung 3"
      azimuth: ???
      tilt: ???
      kwp: ???
  temperature_coefficient: -0.37  # %/°C
  mounting: rack
```

### 5.3 Gesamtpipeline Phase 2

| Schritt | Methode | Input | Output |
|---------|---------|-------|--------|
| 1. Forecast sammeln | DB | API Response | `forecast_history` |
| 2. Strahlungskorrektur | ML (LightGBM) | Open-Meteo GHI + Kontext | Korrigierte GHI/DHI |
| 3. Transposition | pvlib (Perez) | Korr. GHI/DHI + Solpos | POA pro Array |
| 4. PV-Modell | pvlib (PVSystem) | POA + Temperatur + Wind | Theor. Ertrag |
| 5. Residualkorrektur | ML (LightGBM) | Theor. Ertrag + Solpos | Reale Prognose |

---

## 6. Phase 3: Multi-NWP Ensemble + Unsicherheit

> **Aufwand:** 3–5 Tage · **Erwartetes MAPE:** 15–20%

### 6.1 Datenquellen-Unabhängigkeit

| Quelle | Basismodell | Unabhängigkeit | Kosten |
|--------|-------------|----------------|--------|
| Open-Meteo (aktuell) | ICON + IFS | – (Referenz) | 0 € |
| MOSMIX | ICON + IFS (MOS) | Gering – gleiche Basis! | 0 € |
| Open-Meteo GFS | GFS (NOAA) | **Hoch** – anderes Modell | 0 € |
| Solcast | Satellit + NWP | Sehr hoch | ~20 €/Mon. |

**Empfehlung:** Open-Meteo (Default) + Open-Meteo (GFS) als echtes Ensemble.

### 6.2 Ensemble-Features

```python
features['ghi_spread']      = abs(openmeteo_ghi - gfs_ghi)
features['ghi_mean']        = (openmeteo_ghi + gfs_ghi) / 2
features['cloud_agreement'] = 1 - abs(openmeteo_cloud - gfs_cloud) / 100
```

### 6.3 Probabilistische Ausgabe (Quantile Regression)

Statt Punktprognose: *„Morgen 12–18 kWh (80% Konfidenz), erwartet 15 kWh."*

```python
model_q10 = LGBMRegressor(objective='quantile', alpha=0.1)
model_q50 = LGBMRegressor(objective='quantile', alpha=0.5)
model_q90 = LGBMRegressor(objective='quantile', alpha=0.9)
```

---

## 7. Umsetzungs-Roadmap

| Phase | Maßnahme | Aufwand | MAPE-Ziel | Status |
|-------|----------|---------|-----------|--------|
| 1a | pvlib + Clear-Sky-Index | – | – | ✅ Erledigt |
| 1b | Zyklische Zeitfeatures | – | – | ✅ Erledigt |
| 1c | Diffuse Fraction, DNI, Modultemp. | – | – | ✅ Erledigt |
| 1d | Wetter-Lags (1h, 3h, rolling) | – | 24.9% | ✅ Erledigt |
| V | Vorab-Validierung | 0.5 Tage | – | ✅ Erledigt |
| **2a** | **Forecast-Daten persistieren** | 0.5 Tage | – | ✅ **Erledigt (09.02.2026)** |
| 2b | MOS-Schicht (Strahlungskorrektur) | 1 Tag | – | ⏳ Nach 2-3 Mon. Daten |
| 2c | pvlib PV-System (3 Arrays) | 0.5 Tage | – | ⏳ Offen |
| 2d | ML-Residualkorrektur | 0.5 Tage | 18–22% | ⏳ Offen |
| 3a | Open-Meteo GFS als 2. Quelle | 0.5 Tage | – | ⏳ Offen |
| 3b | Ensemble-Features | 0.5 Tage | – | ⏳ Offen |
| 3c | Quantile Regression | 1 Tag | 15–20% | ⏳ Offen |

**Kritischer Pfad:** Forecast-Daten werden jetzt gesammelt (Phase 2a ✅). In 2-3 Monaten kann die MOS-Schicht trainiert werden.

---

## 8. Erfolgskriterien

| Kriterium | Messung | Aktuell | Ziel |
|-----------|---------|---------|------|
| MAPE gesamt | Eval 2025 | 25.3% | < 20% |
| MAPE klare Tage | CSI > 0.7 | 18.7% | < 10% |
| MAPE bewölkte Tage | CSI < 0.3 | 46.0% | < 30% |
| MAE | Eval 2025 | 122W | < 100W |
| Konfidenzintervall | 80%-Intervall | – | ±5% |
| Laufzeit | Fetch + Predict | OK | < 30s |

---

## 9. Zusammenfassung

**Phase 1 ist abgeschlossen** (MAPE aktuell 25.3% eval). Nach dem Timestamp-Fix (PRs #178, #179, #183) ist der Wetter-Gap auf 1.1% geschrumpft — die MOS-Schicht hat weniger Potenzial als erwartet. Größtes Potenzial liegt bei pvlib (3 Arrays) und Residualkorrektur.

**Nächste Schritte:**
1. ✅ Forecast-Daten-Logging läuft (Open-Meteo + MOSMIX)
2. ⏳ 2-3 Monate Daten sammeln
3. ⏳ MOS-Schicht trainieren
4. ⏳ pvlib mit 3 Arrays konfigurieren (braucht Anlagen-Daten)
5. ⏳ Residualkorrektur für Verschattung

**Restaufwand:** 5–8 Arbeitstage für Phase 2 + 3.  
**Realistisches MAPE-Ziel:** 15–20%, mit < 10% an klaren Tagen.
