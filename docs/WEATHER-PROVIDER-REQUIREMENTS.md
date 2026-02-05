# Weather Provider Requirements

*Fachexperten-Analyse für Issue #50*

## 1. Ist-Zustand

### Aktueller Code (`weather.py`)

```
Funktionen:
├── fetch_historical(lat, lon, start, end) → DataFrame
├── fetch_forecast(lat, lon, hours) → DataFrame
├── save_weather_to_db(df, db) → int
├── find_weather_gaps(db, start_ts, end_ts) → list
└── ensure_weather_history(db, lat, lon, start_ts, end_ts) → int
```

### Aktuelles Datenmodell

| Feld | Typ | Beschreibung | Quelle |
|------|-----|--------------|--------|
| `timestamp` | int | Unix timestamp (UTC) | alle |
| `ghi_wm2` | float | Globalstrahlung W/m² | Open-Meteo |
| `dhi_wm2` | float | Diffusstrahlung W/m² | Open-Meteo |
| `cloud_cover_pct` | int | Bewölkung % | Open-Meteo |
| `temperature_c` | float | Temperatur °C | Open-Meteo |
| `wind_speed_ms` | float | Wind m/s | Open-Meteo |
| `humidity_pct` | int | Luftfeuchtigkeit % | Open-Meteo |

### Nutzung im Code

- **cli.py**: `fetch_forecast()`, `ensure_weather_history()`
- **model.py**: Liest aus `weather_history` Tabelle
- **doctor.py**: Prüft Open-Meteo Erreichbarkeit

---

## 2. Provider-Analyse

### 2.1 Open-Meteo (aktuell)

| Eigenschaft | Wert |
|-------------|------|
| **Kosten** | Kostenlos |
| **API Key** | Nicht benötigt |
| **GHI MAPE** | ~20-25% |
| **Historisch** | ✅ Ja (Archive API) |
| **Forecast** | ✅ Ja (bis 16 Tage) |
| **Rate Limit** | 10.000 Requests/Tag |

**Liefert:** GHI, DHI, Temperatur, Bewölkung, Wind, Luftfeuchtigkeit

### 2.2 Solcast

| Eigenschaft | Wert |
|-------------|------|
| **Kosten** | Ab $19/Monat |
| **API Key** | ✅ Benötigt |
| **GHI MAPE** | ~10-11% (DNV validiert) |
| **Historisch** | ✅ Ja |
| **Forecast** | ✅ Ja (bis 14 Tage) |
| **Rate Limit** | Je nach Plan |

**Liefert:** GHI, DNI, DHI, Temperatur, Cloud Opacity, etc.

### 2.3 Forecast.Solar

| Eigenschaft | Wert |
|-------------|------|
| **Kosten** | Free Tier + Paid |
| **API Key** | Optional (mehr Features mit Key) |
| **Historisch** | ❌ Nein |
| **Forecast** | ✅ Ja (bis 4-7 Tage) |
| **Rate Limit** | 12 Requests/Stunde (Free) |

**⚠️ WICHTIG:** Liefert **direkt PV-Output (Watt)**, nicht Strahlungsdaten!

**Benötigt zusätzlich:**
- Panel-Neigung (declination)
- Panel-Azimuth
- kWp

---

## 3. Architektur-Entscheidung

### ⚠️ Fundamentaler Unterschied

```
┌─────────────────────────────────────────────────────────────┐
│ WETTER-BASIERT (Open-Meteo, Solcast)                        │
│                                                             │
│   API → Strahlungsdaten → ML-Modell → PV-Prognose          │
│                              ▲                              │
│                              │                              │
│                    (unser trainiertes Modell)               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PV-BASIERT (Forecast.Solar)                                 │
│                                                             │
│   API → PV-Prognose (fertig)                               │
│                                                             │
│   (ML-Modell wird umgangen/ersetzt!)                       │
└─────────────────────────────────────────────────────────────┘
```

### Frage an Stakeholder

**Option A:** Nur Wetter-Provider (GHI/DHI liefern)
- Unser ML-Modell bleibt zentral
- Bessere Wetterdaten → bessere Prognose
- Konsistente Architektur

**Option B:** Auch PV-Provider (direkte Prognose)
- Forecast.Solar umgeht unser Modell komplett
- Könnte als "Vergleichs-Benchmark" dienen
- Andere Architektur (kein Training nötig)

**Empfehlung:** Option A für Phase 1, Option B optional später

---

## 4. Anforderungen

### 4.1 Funktionale Anforderungen

| ID | Anforderung | Priorität |
|----|-------------|-----------|
| F1 | Provider-Abstraktion (Interface/Protocol) | Must |
| F2 | Open-Meteo refactoren auf Interface | Must |
| F3 | Mindestens 1 alternativer Provider | Must |
| F4 | Config: Provider-Auswahl | Must |
| F5 | Config: API Keys sicher speichern | Must |
| F6 | Fallback bei Provider-Fehler | Should |
| F7 | CLI: Provider wechseln | Should |
| F8 | Historische Daten bei Provider-Wechsel behalten | Must |

### 4.2 Nicht-funktionale Anforderungen

| ID | Anforderung | Priorität |
|----|-------------|-----------|
| N1 | Keine Breaking Changes für bestehende User | Must |
| N2 | Open-Meteo bleibt Default (kostenlos) | Must |
| N3 | API Keys nicht im Klartext loggen | Must |
| N4 | Tests für jeden Provider | Must |
| N5 | Dokumentation aktualisieren | Must |

### 4.3 Datenmodell-Kompatibilität

Alle Wetter-Provider müssen folgendes Minimum liefern:

```python
@dataclass
class WeatherData:
    timestamp: int      # Unix timestamp UTC
    ghi_wm2: float      # Globalstrahlung (PFLICHT)
    cloud_cover_pct: int | None
    temperature_c: float | None
    # Optional (für erweiterte Features):
    dhi_wm2: float | None
    wind_speed_ms: float | None
    humidity_pct: int | None
```

**Mapping-Notizen:**
- Solcast `ghi` → `ghi_wm2`
- Solcast `cloud_opacity` → `cloud_cover_pct` (Umrechnung nötig?)
- Solcast `air_temp` → `temperature_c`

---

## 5. Edge Cases & Risiken

### 5.1 Edge Cases

| Case | Handling |
|------|----------|
| API Key ungültig/abgelaufen | Klare Fehlermeldung, Fallback auf Open-Meteo? |
| Rate Limit erreicht | Retry mit Backoff, Warnung an User |
| Provider temporär down | Retry, dann Fehlermeldung |
| Historische Daten von anderem Provider | Behalten, nur neue Daten vom neuen Provider |
| Provider liefert weniger Felder | None/Defaults für fehlende Felder |

### 5.2 Risiken

| Risiko | Mitigation |
|--------|------------|
| API-Änderungen bei Providern | Versionierung, Tests gegen echte API |
| Kosten bei Paid Providern | Dokumentation, Warnung bei Config |
| Unterschiedliche Datenqualität | Dokumentieren, User entscheidet |

---

## 6. Vorgeschlagene Implementierungs-Reihenfolge

### Phase 1: Abstraktion (Pflicht)
1. `WeatherProvider` Protocol definieren
2. `OpenMeteoProvider` Klasse erstellen (bestehender Code)
3. Tests anpassen
4. Config-Schema erweitern

### Phase 2: Solcast (Empfohlen)
1. `SolcastProvider` implementieren
2. API Key Handling
3. Feld-Mapping
4. Tests + Doku

### Phase 3: Forecast.Solar (Optional)
- **Nur sinnvoll** als Benchmark/Vergleich
- Erfordert Architektur-Entscheidung (umgeht ML-Modell)

---

## 7. Offene Fragen

1. **Provider-Wechsel:** Was passiert mit historischen Daten in der DB?
   - Vorschlag: Behalten, neue Daten vom neuen Provider

2. **Forecast.Solar:** Wollen wir das überhaupt?
   - Liefert PV-Output direkt, nicht Wetterdaten
   - Würde unser ML-Modell ersetzen, nicht ergänzen

3. **Fallback-Strategie:** Bei Paid-Provider-Fehler auf Open-Meteo fallen?
   - Pro: Robuster
   - Con: Inkonsistente Datenqualität

4. **API Key Speicherung:** Config-File vs. Environment Variable?
   - Empfehlung: Beides unterstützen, Env-Var hat Vorrang

---

*Erstellt: 2026-02-05 | Autor: Fachexperte*
*Nächster Schritt: Architekten-Review*
