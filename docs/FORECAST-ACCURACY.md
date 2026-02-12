# Forecast Accuracy Report

*Automatisch generiert. Neuester Stand oben.*

---

## 2026-02-12 — Forecast-Qualität (GHI: Prognose vs. HOSTRADA-Ist)

**Datenbasis:** Forecasts seit 09.02.2026 (Sammlung via daily-forecast.sh, 23:00 Uhr)

### Gesamt

| Metrik | Open-Meteo | MOSMIX (DWD) |
|--------|-----------|--------------|
| Datenpunkte | 1,191 | 402 |
| MAE GHI | 19.2 W/m² | 17.4 W/m² |
| MAPE (GHI>50) | 59.7% | 50.1% |
| Bias | -7.4 W/m² | -12.0 W/m² |
| Ø Forecast GHI | 32.1 W/m² | 21.6 W/m² |
| Ø Actual GHI | 39.5 W/m² | 33.6 W/m² |

### Bewölkung

| Metrik | Open-Meteo | MOSMIX |
|--------|-----------|--------|
| MAE Cloud Cover | 12.5% | 6.8% |
| Bias | +1.3% | -1.7% |

### Nach Vorhersage-Horizont

| Horizont | Open-Meteo MAE | Open-Meteo MAPE | MOSMIX MAE | MOSMIX MAPE |
|----------|---------------|-----------------|------------|-------------|
| 0-6h | 28.4 | 67% | 23.0 | 61% |
| 6-12h | 18.4 | 62% | 14.6 | 44% |
| 12-24h | 35.3 | 111% | 21.2 | 61% |
| 24-48h | 21.4 | 76% | 14.3 | 42% |
| 48-72h | 0.0 | — | 0.1 | — |

### Einschätzung

- **MOSMIX (DWD) schlägt Open-Meteo** bei GHI und Bewölkung deutlich
- Beide Quellen **unterschätzen** die tatsächliche Strahlung (negativer Bias)
- MOSMIX besonders stark auf 24-48h Horizont
- **Einschränkung:** Nur wenige Tage Winterdaten — Aussagekraft steigt mit der Zeit

### Methodik

- **Vergleichsbasis:** HOSTRADA (DWD-Messdaten) als Ground Truth
- **MAPE:** Nur Stunden mit GHI > 50 W/m² (Tageslichtstunden)
- **Horizont:** Differenz issued_at → target_time
- **Timestamp-Konvention:** Alle Quellen auf Intervallanfang normalisiert (PRs #178, #179, #183)
