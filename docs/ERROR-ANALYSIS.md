# PV-Forecast Fehleranalyse

**Datum:** 2026-02-12  
**Modell:** XGBoost Pipeline (StandardScaler → XGBRegressor)  
**Eval-Zeitraum:** 2025 (4.863 Tageslicht-Stunden)  
**Gesamt-Metriken:** MAE = 214 W, MAPE = 28.5% (bei Actual > 50W)

---

## 1. Feature Importance

Das Modell wird dominiert von Einstrahlungs-Features. GHI allein macht 52% der Gain-Importance aus:

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

### POA-Features: Nicht im trainierten Modell!

Die Features `poa_total` und `poa_ratio` werden von `prepare_features()` korrekt berechnet (23 Features), aber das **aktuell gespeicherte Modell wurde mit nur 23 Features trainiert, die POA bereits enthalten**. Allerdings zeigt die Feature-Importance-Analyse, dass **keine POA-Features vom Modell genutzt werden** (importance = 0 für `poa_total`, nicht in gain scores).

**Ursache:** Die Korrelation zwischen `ghi` und `poa_total` beträgt **r = 0.987** – fast perfekte Kollinearität. XGBoost splittet praktisch nie auf `poa_total`, weil `ghi` bereits den gleichen Informationsgehalt liefert. `poa_ratio` (r = 0.22 mit GHI) hat zwar unabhängige Information, wird aber ebenfalls nicht genutzt.

**Fazit:** POA-Features bringen in der aktuellen Architektur keinen Mehrwert, weil das Modell GHI bevorzugt und POA stark mit GHI korreliert.

---

## 2. Fehler nach Tageszeit

| Stunde | MAE (W) | MAPE | Bias | n |
|--------|--------:|-----:|-----:|--:|
| 05:00 | 161 | 35.0% | -38 | 209 |
| 06:00 | 208 | 36.7% | +46 | 274 |
| 07:00 | 225 | 41.0% | +100 | 354 |
| 08:00 | 304 | 38.2% | +107 | 365 |
| 09:00 | 269 | 25.7% | +86 | 365 |
| 10:00 | 304 | 18.6% | +136 | 365 |
| 11:00 | 333 | 18.0% | +142 | 365 |
| 12:00 | 301 | 20.1% | +167 | 365 |
| 13:00 | 247 | 21.9% | +107 | 365 |
| 14:00 | 203 | 22.9% | +109 | 365 |
| 15:00 | 165 | 32.7% | +105 | 351 |
| 16:00 | 151 | 28.6% | +69 | 270 |
| 17:00 | 142 | 39.6% | +16 | 217 |
| 18:00 | 79 | 41.1% | -6 | 165 |

### Erkenntnisse

- **Systematischer positiver Bias über den gesamten Tag** (+16 bis +167 W) → Das Modell überschätzt konsistent
- **Höchster absoluter Fehler mittags** (11:00: 333W MAE), aber niedrigste MAPE (18%) wegen hoher Absolutwerte
- **Höchste MAPE morgens (7-8h) und abends (17-18h)** – genau die Stunden, wo die 3 Arrays (SO/NW/SW) unterschiedlich beleuchtet werden
- **Morgen-Bias ist besonders auffällig:** 07:00 hat +100W Bias, 08:00 +107W → Modell überschätzt den Morgenertrag

---

## 3. Fehler nach Monat

| Monat | MAE (W) | MAPE | Bias | n |
|-------|--------:|-----:|-----:|--:|
| Jan | 135 | 43.9% | +23 | 276 |
| Feb | 173 | 37.3% | +51 | 306 |
| Mär | 206 | 25.0% | +74 | 392 |
| Apr | 221 | 20.2% | +110 | 445 |
| Mai | 244 | 17.4% | +94 | 523 |
| Jun | 199 | 17.2% | +107 | 546 |
| Jul | 255 | 27.6% | +80 | 554 |
| Aug | 256 | 26.7% | +133 | 504 |
| Sep | 281 | 33.4% | +110 | 410 |
| Okt | 166 | 37.5% | +45 | 348 |
| Nov | 183 | 47.1% | +84 | 292 |
| Dez | 150 | 38.9% | +20 | 267 |

### Erkenntnisse

- **Winter (Nov-Feb) hat die höchste MAPE** (38-47%), Sommer (Mai-Jun) die niedrigste (17%)
- **September ist ein Ausreißer:** MAPE 33.4% und höchster MAE (281W) trotz noch guter Einstrahlung
- **Durchgehend positiver Bias** in allen Monaten → systematische Überschätzung
- **August-Bias (+133W) ist der höchste** – möglicherweise Degradation oder Verschmutzung?

---

## 4. Top-20 Fehler-Tage

| Datum | Actual (kWh) | Predicted (kWh) | Fehler | Fehler % |
|-------|-------------:|----------------:|-------:|---------:|
| 2025-01-09 | 0.15 | 1.34 | +1.19 | 799% |
| 2025-01-05 | 0.17 | 1.03 | +0.85 | 487% |
| 2025-11-19 | 1.20 | 2.36 | +1.16 | 97% |
| 2025-01-11 | 2.13 | 4.10 | +1.96 | 92% |
| 2025-11-01 | 2.35 | 4.41 | +2.07 | 88% |
| 2025-01-02 | 5.04 | 8.02 | +2.98 | 59% |
| 2025-12-27 | 5.52 | 8.68 | +3.17 | 57% |
| 2025-11-28 | 0.94 | 1.47 | +0.53 | 56% |
| 2025-11-25 | 1.36 | 2.09 | +0.73 | 53% |
| 2025-11-23 | 6.81 | 10.26 | +3.45 | 51% |

### Muster

- **Alle 20 schlechtesten Tage sind Überschätzungen** (positiver Fehler)
- **Konzentration auf Winter-Monate:** 7× Januar, 5× November, 3× Dezember, 2× Februar
- **Schnee/Frost-Verdacht:** Jan 5, 9, 11 mit sehr niedrigem Ertrag (< 2 kWh) aber signifikanter Prediction
- **Keine Sommertage** in der Liste → Sommermodell funktioniert deutlich besser

---

## 5. Fehler nach Wetterlage (CSI)

| Kategorie | MAE (W) | MAPE | Σ\|Fehler\| (kWh) | n |
|-----------|--------:|-----:|-------------------:|--:|
| Klar (>0.7) | 288 | 21.5% | 614.8 | 2133 |
| Teilbewölkt (0.3-0.7) | 223 | 30.3% | 319.1 | 1431 |
| Bewölkt (<0.3) | 83 | 47.8% | 108.3 | 1299 |

### Erkenntnisse

- **Klare Tage verursachen 59% des Gesamtfehlers** (615 kWh von 1042 kWh)
- Bei klarem Himmel: niedrige MAPE (21.5%) aber hoher absoluter Fehler (288W MAE)
- Bei bewölktem Himmel: hohe MAPE (47.8%) aber geringer absoluter Beitrag
- **Der größte Hebel liegt bei klaren Tagen** – hier stimmt die GHI→Ertrag-Umrechnung nicht

---

## Zusammenfassung & Empfehlungen

### Top-3 Erkenntnisse

1. **Systematische Überschätzung:** Das Modell hat einen durchgängig positiven Bias (+80-170W mittags). Es überschätzt den Ertrag in jeder Stunde, jedem Monat und jeder Wetterlage. Das deutet auf ein grundsätzliches Skalierungsproblem hin (z.B. Degradation, Verschattung, WR-Verluste nicht abgebildet).

2. **POA-Features wirkungslos:** `poa_total` korreliert mit r=0.987 mit GHI. XGBoost nutzt sie nicht. Die 3-Array-POA-Features bringen in der aktuellen flachen Architektur keinen Mehrwert.

3. **Winter ist das Hauptproblem:** MAPE 38-47% (Nov-Feb) vs 17% (Mai-Jun). Die 20 schlechtesten Tage sind alle im Winter. Schneebedeckung und Niedrigertragstage werden systematisch überschätzt.

### Empfehlungen

1. **Bias-Korrektur als Quick Win:** Ein einfacher multiplikativer Skalierungsfaktor (z.B. 0.85) oder monatsabhängige Korrektur könnte den systematischen Bias sofort reduzieren. → Residualkorrektur-Ansatz ist der richtige nächste Schritt.

2. **Schnee-Feature:** Binary Snow-Flag oder Schneehöhe als Feature könnte Wintertage deutlich verbessern. DWD/Open-Meteo liefern `snowfall` und `snow_depth`.

3. **POA anders nutzen:** Statt als XGBoost-Feature → POA als physikalisches Vormodell verwenden (pvlib-Simulation → Residuum mit ML korrigieren). So wird die Array-Geometrie physikalisch korrekt abgebildet, nicht statistisch.
