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

## 5. Phase 2: Physikalisches PV-Modell + Residualkorrektur

> **Aufwand:** 1.5–2 Tage · **Erwartetes MAPE:** 18–22%

### ~~5.1 ML-basierte Strahlungskorrektur (MOS-Schicht)~~ — Deprioritisiert

**Status: Auf Eis gelegt (12.02.2026)**

Die Gap-Analyse (Abschnitt 4.1) zeigt nach dem Timestamp-Fix nur noch 1.1% Wetter-Gap.
Das Modell kompensiert Forecast-Fehler bereits über die Wetter-Lag-Features. Eine eigene
MOS-Schicht ist den Aufwand nicht wert (~1 Tag Entwicklung für ~1% Verbesserung).

Die Forecast-Datensammlung (Open-Meteo + MOSMIX → `forecast_history`) läuft weiter.
Falls sich der Gap mit mehr Daten/Jahreszeiten als größer herausstellt, kann die MOS-Schicht
nachträglich implementiert werden. Siehe `docs/FORECAST-ACCURACY.md` für laufende Auswertung.

### 5.2 pvlib PV-System-Modell (3 Arrays) — ✅ Implementiert (PR #185, 12.02.2026)

**Anlagenkonfiguration:**
```yaml
pv_system:
  arrays:
    - name: "Wohnhaus SO"
      azimuth: 140          # Süd-Ost
      tilt: 43
      kwp: 6.08             # 19× Q.Peak DUO-G5 320Wp
    - name: "Wohnhaus NW"
      azimuth: 320          # Nord-West
      tilt: 43
      kwp: 2.56             # 8× Q.Peak DUO-G5 320Wp
    - name: "Gauben SW"
      azimuth: 229          # Süd-West
      tilt: 43
      kwp: 1.28             # 4× Q.Peak DUO-G5 320Wp
```

**Implementierung:**
- POA (Plane of Array) Irradiance pro Array via pvlib Perez-Transpositionsmodell
- Gewichtete Summe nach kWp-Anteil als Feature `poa_total`
- Verhältnis `poa_ratio` = POA/GHI als zusätzliches Feature
- Rückwärtskompatibel: Ohne `pv_system.arrays` → bisheriges Verhalten (poa_total=0)
- pvlib bleibt optional (`[physics]` extra)

**Ergebnis nach Tune (100 Trials):**
- MAPE: 29.0% (unverändert — XGBoost nutzt POA-Features kaum, da GHI+CSI+sun_elevation den Großteil abdecken)
- MAE: 111W, R²: 0.963

**Bewertung:** Die POA-Features sind implementiert und korrekt (Tests bestätigen: SO-Array hat morgens mehr POA als NW-Array). Der eigentliche Mehrwert wird bei der **Residualkorrektur** erwartet, wenn das Modell den theoretischen pvlib-Ertrag mit dem realen vergleichen kann.

### 5.3 Gesamtpipeline Phase 2 (revidiert)

```
Open-Meteo GHI/DHI  →  pvlib Transposition (3 Arrays)  →  POA pro Array
POA + Temperatur     →  pvlib PVSystem                  →  Theor. Ertrag
Theor. Ertrag        →  ML-Residualkorrektur            →  Reale Prognose
```

| Schritt | Methode | Input | Output |
|---------|---------|-------|--------|
| 1. Forecast sammeln | DB | API Response | `forecast_history` |
| ~~2. Strahlungskorrektur~~ | ~~ML (LightGBM)~~ | — | ~~Deprioritisiert~~ |
| 2. Transposition | pvlib (Perez) | GHI/DHI + Solpos | POA pro Array |
| 3. PV-Modell | pvlib (PVSystem) | POA + Temperatur + Wind | Theor. Ertrag |
| 4. Residualkorrektur | ML (LightGBM) | Theor. Ertrag + Solpos | Reale Prognose |

---

## 6. Phase 3: Quantile Regression + optionales Ensemble

> **Aufwand:** 1–2 Tage · **Erwartetes MAPE:** ~20% mit Konfidenzintervallen

### 6.1 Probabilistische Ausgabe (Quantile Regression) — **Priorität**

Statt Punktprognose: *„Morgen 12–18 kWh (80% Konfidenz), erwartet 15 kWh."*

Besonders wertvoll bei bewölkten Tagen (aktuell 46% MAPE), wo eine Punktprognose
irreführend genau wirkt. Die Breite des Konfidenzintervalls signalisiert dem Nutzer
automatisch die Unsicherheit.

```python
model_q10 = LGBMRegressor(objective='quantile', alpha=0.1)
model_q50 = LGBMRegressor(objective='quantile', alpha=0.5)
model_q90 = LGBMRegressor(objective='quantile', alpha=0.9)
```

### ~~6.2 Multi-NWP Ensemble~~ — Deprioritisiert

Der Wetter-Gap von 1.1% zeigt, dass das Modell Forecast-Fehler bereits gut kompensiert.
Ein zweites NWP-Modell (z.B. GFS) bringt voraussichtlich wenig Mehrwert.

Die Forecast-Datensammlung (Open-Meteo + MOSMIX) läuft trotzdem weiter.
Falls sich nach mehreren Monaten zeigt, dass der Gap saisonal größer wird
(z.B. im Sommer bei Gewitterlagen), kann das Ensemble nachträglich ergänzt werden.

| Quelle | Basismodell | Unabhängigkeit | Kosten | Status |
|--------|-------------|----------------|--------|--------|
| Open-Meteo (aktuell) | ICON + IFS | – (Referenz) | 0 € | ✅ Aktiv |
| MOSMIX | ICON + IFS (MOS) | Gering | 0 € | ✅ Daten werden gesammelt |
| Open-Meteo GFS | GFS (NOAA) | **Hoch** | 0 € | ⏸️ Optional |
| Solcast | Satellit + NWP | Sehr hoch | ~20 €/Mon. | ❌ Nicht geplant |

---

## 7. Umsetzungs-Roadmap (revidiert 12.02.2026)

### Abgeschlossen

| Phase | Maßnahme | MAPE | Status |
|-------|----------|------|--------|
| 1a | pvlib + Clear-Sky-Index | – | ✅ |
| 1b | Zyklische Zeitfeatures | – | ✅ |
| 1c | Diffuse Fraction, DNI, Modultemp. | – | ✅ |
| 1d | Wetter-Lags (1h, 3h, rolling) | – | ✅ |
| V | Vorab-Validierung + Gap-Analyse | – | ✅ |
| 2a | Forecast-Daten persistieren | – | ✅ |
| T | Timestamp-Fix (PRs #178, #179, #183) | 25.3% | ✅ |
| 2b | pvlib 3 Arrays / POA-Features (PR #185) | 29.0% | ✅ |

### Nächste Schritte (priorisiert)

| Prio | Maßnahme | Aufwand | Impact | Status |
|------|----------|---------|--------|--------|
| 🔴 1 | **ML-Residualkorrektur** (theor. Ertrag vs. real) | 0.5–1 Tag | MAPE -2–3% | ⏳ Offen |
| 🟡 2 | **Quantile Regression** (Unsicherheitsbänder) | 1 Tag | Bessere UX | ⏳ Offen |

### Deprioritisiert

| Maßnahme | Grund | Status |
|----------|-------|--------|
| MOS-Schicht (Strahlungskorrektur) | Wetter-Gap nur 1.1% | ⏸️ Auf Eis |
| Multi-NWP Ensemble (GFS) | Geringer Mehrwert bei 1.1% Gap | ⏸️ Optional |

**Kritischer Pfad:** Residualkorrektur benötigt die jetzt vorhandenen POA-Features als Input.

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

**Phase 1 + Timestamp-Fix sind abgeschlossen** (MAPE 25.3% eval). Der Wetter-Gap ist auf 1.1% geschrumpft – das Modell kompensiert Forecast-Fehler bereits durch Lag-Features. Die MOS-Schicht und das NWP-Ensemble sind daher deprioritisiert.

**Strategie-Shift:** Statt Wetterkorrektur liegt der Fokus jetzt auf **physikalischer Modellierung** (pvlib 3 Arrays) und **Residualkorrektur** (Verschattung, WR-Verluste). Das sind die verbleibenden ~24% MAPE.

**Nächste Schritte:**
1. ✅ **pvlib 3 Arrays** implementiert (PR #185) — POA-Features verfügbar, MAPE noch unverändert (29.0%)
2. ⏳ **Residualkorrektur** implementieren (theor. pvlib-Ertrag vs. realer Ertrag → Verschattung, WR-Verluste lernen)
3. ⏳ **Quantile Regression** für Unsicherheitsbänder (besonders bei bewölkten Tagen mit 46% MAPE)
4. 📊 Forecast-Datensammlung läuft weiter (Open-Meteo + MOSMIX → `FORECAST-ACCURACY.md`)

**Erkenntnis pvlib 3 Arrays:** Die POA-Features allein verbessern das End-to-End-XGBoost-Modell nicht,
weil GHI + CSI + sun_elevation den Großteil der Information bereits liefern. Der Mehrwert entsteht erst
bei der Residualkorrektur, wenn der theoretische pvlib-Ertrag als Baseline dient und das ML-Modell nur
noch die Abweichung (Verschattung, Schnee, WR-Verluste) lernen muss.

**Restaufwand:** 1.5–2 Arbeitstage für verbleibende Schritte.  
**Realistisches MAPE-Ziel:** 18–22%, mit < 10% an klaren Tagen.  
**Langfristig (mit Residual + Quantile):** 15–20%.
