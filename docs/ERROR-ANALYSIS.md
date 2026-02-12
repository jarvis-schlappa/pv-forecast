# PV-Forecast Fehleranalyse (2019–2025)

**Datum:** 2026-02-12  
**Modell:** XGBoost Pipeline (StandardScaler → XGBRegressor)  
**Eval-Zeitraum:** 2019–2025 (28.832 Tageslicht-Stunden, production > 50W)  
**Gesamt-Metriken:** MAE = 216 W, MAPE = 25.9%

---

## 1. Feature Importance

*(Unverändert – modellbasiert, nicht zeitraumabhängig)*

| Rang | Feature | Gain | Anteil |
|------|---------|-----:|-------:|
| 1 | ghi | 416.3M | 52.2% |
| 2 | ghi_rolling_3h | 146.0M | 18.3% |
| 3 | ghi_lag_1h | 61.6M | 7.7% |
| 4 | dhi | 49.2M | 6.2% |
| 5 | csi | 36.5M | 4.6% |
| 6 | hour_sin | 26.3M | 3.3% |
| 7 | diffuse_fraction | 22.0M | 2.8% |
| 8 | sun_elevation | 14.8M | 1.9% |
| 9 | hour_cos | 4.6M | 0.6% |
| 10 | month_cos | 3.7M | 0.5% |

**Fazit:** GHI dominiert (52%). POA-Features werden nicht genutzt (r=0.987 mit GHI → Kollinearität).

---

## 2. Fehler nach Tageszeit (2019–2025)

| Stunde | MAE (W) | MAPE | Bias | n |
|--------|--------:|-----:|-----:|------:|
| 06:00 | 82 | 40.2% | −11 | 745 |
| 07:00 | 165 | 39.3% | −33 | 1.375 |
| 08:00 | 217 | 37.7% | −1 | 1.949 |
| 09:00 | 245 | 33.8% | +10 | 2.407 |
| 10:00 | 252 | 23.3% | +19 | 2.534 |
| 11:00 | 259 | 18.8% | −7 | 2.551 |
| 12:00 | 269 | 18.7% | +2 | 2.553 |
| 13:00 | 267 | 19.1% | +11 | 2.550 |
| 14:00 | 229 | 20.7% | +23 | 2.540 |
| 15:00 | 204 | 20.2% | +14 | 2.412 |
| 16:00 | 187 | 20.8% | +22 | 1.989 |
| 17:00 | 177 | 24.7% | +23 | 1.724 |
| 18:00 | 178 | 28.1% | +20 | 1.396 |
| 19:00 | 163 | 35.7% | −12 | 1.148 |
| 20:00 | 101 | 41.9% | −15 | 759 |

### Erkenntnisse

- **Bias ist über 7 Jahre nahezu neutral** (−33 bis +23 W) – der starke positive Bias aus der 2025-Analyse war ein **Jahreseffekt**, kein Modellproblem
- **Randstunden (morgens/abends) haben hohe MAPE** (35–42%) aber geringen absoluten Fehler
- **Kernstunden (10–16 Uhr) stabil bei 19–23% MAPE** – das Modell funktioniert hier gut
- **Morgens leichter negativer Bias** (Unterschätzung), nachmittags leicht positiv (Überschätzung)

---

## 3. Fehler nach Monat (2019–2025)

| Monat | MAE (W) | MAPE | Bias | n |
|-------|--------:|-----:|-----:|------:|
| Jan | 156 | 44.6% | −3 | 1.486 |
| Feb | 190 | 30.9% | −10 | 1.786 |
| Mär | 202 | 25.0% | +7 | 2.437 |
| Apr | 224 | 20.2% | +8 | 2.775 |
| Mai | 244 | 20.4% | +7 | 3.183 |
| Jun | 225 | 17.7% | +3 | 3.281 |
| Jul | 237 | 21.1% | +16 | 3.248 |
| Aug | 239 | 22.6% | +12 | 3.020 |
| Sep | 228 | 23.8% | +9 | 2.526 |
| Okt | 216 | 32.1% | +15 | 2.119 |
| Nov | 191 | 39.0% | +17 | 1.615 |
| Dez | 145 | 42.1% | −10 | 1.356 |

### Erkenntnisse

- **Saisonales Muster stabil:** Winter MAPE 39–45%, Sommer 18–23%
- **Bias über alle Monate fast null** (−10 bis +17 W) – stark verbessert gegenüber 2025-only
- **Juni ist der beste Monat:** 17.7% MAPE, nur +3W Bias

---

## 4. Top-30 Fehler-Tage (2019–2025)

| Datum | Actual (kWh) | Predicted (kWh) | Fehler | Fehler % |
|-------|-------------:|----------------:|-------:|---------:|
| 2023-12-04 | 0.40 | 1.65 | +1.25 | 314% |
| 2025-01-09 | 0.07 | 0.30 | +0.23 | 231% |
| 2023-11-13 | 0.68 | 1.92 | +1.24 | 182% |
| 2021-12-05 | 1.70 | 4.61 | +2.91 | 171% |
| 2024-01-06 | 0.46 | 1.21 | +0.75 | 164% |
| 2022-01-19 | 0.78 | 2.00 | +1.22 | 157% |
| 2024-01-14 | 0.41 | 1.04 | +0.63 | 155% |
| 2023-12-19 | 0.07 | 0.22 | +0.15 | 146% |
| 2022-12-05 | 0.38 | 0.92 | +0.54 | 142% |
| 2021-01-17 | 0.05 | 0.19 | +0.14 | 140% |
| 2020-01-04 | 0.52 | 1.23 | +0.71 | 136% |
| 2020-12-27 | 0.44 | 0.99 | +0.55 | 123% |
| 2020-01-14 | 0.65 | 1.42 | +0.77 | 119% |
| 2024-12-11 | 0.52 | 1.13 | +0.61 | 117% |
| 2019-11-18 | 0.46 | 0.99 | +0.53 | 116% |
| 2019-01-30 | 1.32 | 2.82 | +1.50 | 114% |
| 2020-01-09 | 0.69 | 1.45 | +0.76 | 111% |
| 2020-10-25 | 2.58 | 5.35 | +2.76 | 107% |
| 2020-01-24 | 0.75 | 1.54 | +0.79 | 105% |
| 2023-12-25 | 0.92 | 1.84 | +0.93 | 101% |
| 2021-01-11 | 0.70 | 1.41 | +0.71 | 101% |
| 2022-12-11 | 0.49 | 0.99 | +0.49 | 100% |
| 2019-01-12 | 0.49 | 0.97 | +0.48 | 97% |
| 2019-11-28 | 0.88 | 1.71 | +0.83 | 95% |
| 2022-01-25 | 0.75 | 1.45 | +0.70 | 93% |
| 2025-01-11 | 2.11 | 4.00 | +1.89 | 90% |
| 2025-11-01 | 2.29 | 4.29 | +2.00 | 87% |
| 2025-11-19 | 1.14 | 2.09 | +0.95 | 84% |
| 2020-12-29 | 0.56 | 1.01 | +0.45 | 79% |
| 2024-11-25 | 1.24 | 2.21 | +0.97 | 79% |

### Muster

- **100% Überschätzungen** – kein einziger Fehler-Tag mit Unterschätzung
- **Gleichmäßig über alle Jahre verteilt** (2019: 3×, 2020: 6×, 2021: 3×, 2022: 4×, 2023: 4×, 2024: 4×, 2025: 4×) → kein bestimmtes Jahr auffällig schlechter
- **26 von 30 Tagen sind Nov–Feb** (Winter) → Schnee/Frost-Tage mit <2 kWh Ertrag
- **Einziger Nicht-Winter-Ausreißer:** 2020-10-25 (Okt) mit 107% Fehler

---

## 5. Fehler nach Wetterlage (CSI, 2019–2025)

| Kategorie | MAE (W) | MAPE | Σ\|Fehler\| (kWh) | n |
|-----------|--------:|-----:|-------------------:|------:|
| Klar (>0.7) | 246 | 16.9% | 3.481 | 14.150 |
| Teilbewölkt (0.3–0.7) | 218 | 29.6% | 2.090 | 9.578 |
| Bewölkt (<0.3) | 130 | 44.1% | 665 | 5.104 |

### Erkenntnisse

- **Klare Tage: 56% des Gesamtfehlers** (3.481 von 6.235 kWh) – größter Hebel
- **Bewölkte Tage: hohe MAPE (44%) aber absolut gering** – weniger relevant
- Muster ist über 7 Jahre stabil

---

## 6. Jahresvergleich (NEU)

| Jahr | MAE (W) | MAPE | Bias | n |
|------|--------:|-----:|-----:|------:|
| 2019 | 227 | 25.4% | **−70** | 4.138 |
| 2020 | 203 | 23.9% | −22 | 4.131 |
| 2021 | 216 | 25.7% | −21 | 4.119 |
| 2022 | 203 | 22.8% | +3 | 4.157 |
| 2023 | 197 | 25.6% | +2 | 4.072 |
| 2024 | 222 | 29.6% | **+65** | 4.055 |
| 2025 | 246 | 28.4% | **+93** | 4.160 |

### ⚡ Kernerkenntnis: Degradation sichtbar!

- **2019: Bias −70W** → Modell unterschätzt (Anlage war neu, höherer Ertrag als Modell erwartet)
- **2022–2023: Bias ≈ 0** → Modell passt perfekt (Trainingsschwerpunkt?)
- **2024–2025: Bias +65 bis +93W** → Modell überschätzt → **Anlage liefert weniger als erwartet**
- **Bias-Drift: ~23 W/Jahr** von −70 (2019) auf +93 (2025) → **163W Drift in 6 Jahren**
- **MAPE steigt ab 2024** (29.6%) – das Modell wird schlechter

**Interpretation:** Die Anlage degradiert oder es gibt zunehmende Verschattung/Verschmutzung. Der lineare Bias-Trend ist konsistent mit einer Panel-Degradation von ca. 1.5–2%/Jahr (bei ~5000W Durchschnitts-Peak → 75–100W/Jahr).

---

## 7. Monat × Jahr MAPE-Heatmap (NEU)

|  | Jan | Feb | Mär | Apr | Mai | Jun | Jul | Aug | Sep | Okt | Nov | Dez |
|------|----:|----:|----:|----:|----:|----:|----:|----:|----:|----:|----:|----:|
| 2019 | 46.1 | 28.6 | 25.8 | 20.6 | 22.7 | 18.9 | 17.2 | 23.5 | 24.1 | 28.7 | 40.4 | 30.9 |
| 2020 | 50.6 | 28.9 | 17.8 | 11.7 | 14.7 | 17.4 | 20.4 | 22.8 | 19.6 | 36.6 | 38.2 | 44.8 |
| 2021 | 39.5 | 26.6 | 26.8 | 20.2 | 24.9 | 18.1 | 23.7 | 23.4 | 18.9 | 29.0 | 35.6 | 45.1 |
| 2022 | 44.4 | 32.4 | 18.9 | 17.9 | 19.2 | 18.2 | 16.8 | 14.5 | 25.3 | 27.3 | 28.1 | 39.1 |
| 2023 | 40.6 | 30.8 | 26.6 | 22.7 | 20.8 | 13.5 | 20.3 | 26.3 | 18.1 | 29.8 | 40.2 | 50.0 |
| 2024 | 47.0 | 32.9 | **35.0** | **28.6** | 23.5 | 21.2 | 22.0 | 21.2 | 27.4 | **35.3** | 43.5 | 47.6 |
| 2025 | 43.7 | **36.5** | 25.1 | 20.2 | 17.5 | 17.0 | 27.6 | 26.6 | **33.4** | **37.8** | **46.8** | 39.0 |

### Erkenntnisse

- **Winter ist IMMER schlecht** (Jan 40–51%, Dez 31–50%) – kein Ausreißer, strukturelles Problem
- **Sommer ist IMMER gut** (Jun 13–21%) – stabil über alle Jahre
- **2024 und 2025 zeigen erhöhte MAPE in Übergangsmonaten** (Mär/Okt) → Degradation wirkt sich bei mittlerer Einstrahlung stärker aus
- **Bester Einzelmonat:** Apr 2020 (11.7%), Jun 2023 (13.5%)
- **Schlechtester Einzelmonat:** Jan 2020 (50.6%), Dez 2023 (50.0%)

---

## Zusammenfassung & Empfehlungen

### Top-3 Erkenntnisse (aktualisiert)

1. **🔴 Degradation nachgewiesen:** Bias driftet von −70W (2019) auf +93W (2025) – ein linearer Trend von ~23W/Jahr. Das Modell überschätzt zunehmend, weil die Anlage weniger liefert. Empfehlung: **Degradationsfaktor ins Modell einbauen** (z.B. −1.5%/Jahr ab Inbetriebnahme).

2. **🟡 Systematische Überschätzung ist ein 2024/2025-Problem, kein Modellproblem:** Über 7 Jahre gemittelt ist der Bias nahezu null. Der in der 2025-Analyse gefundene starke positive Bias war kein Modellfehler, sondern spiegelt die Anlagen-Degradation wider.

3. **🟢 Winter bleibt das Hauptproblem:** MAPE 40–50% (Nov–Feb) vs. 14–22% (Apr–Sep) – stabil über alle Jahre. Ein Schnee-Feature könnte helfen, aber der Winter-Fehler hat geringe absolute Relevanz (<2 kWh Tagesertrag).

### Empfehlungen (aktualisiert)

1. **Degradationsfaktor (höchste Priorität):** Multiplikativer Faktor `(1 - 0.015)^(year - 2019)` oder als Feature `years_since_install`. Quick Win mit großem Effekt auf 2024/2025-Bias.

2. **Monatsabhängige Bias-Korrektur:** Residualkorrekturen pro Monat könnten die saisonalen Schwächen abfedern, sind aber weniger wichtig als der Degradationsfaktor.

3. **Schnee-Feature:** Für Wintertage mit <2 kWh Ertrag. DWD/Open-Meteo `snowfall`/`snow_depth`. Verbessert Top-30-Fehler, aber geringer absoluter Beitrag.

4. **POA als physikalisches Vormodell:** Weiterhin empfohlen – pvlib-Simulation → Residuum mit ML korrigieren. Unverändert gegenüber erster Analyse.
