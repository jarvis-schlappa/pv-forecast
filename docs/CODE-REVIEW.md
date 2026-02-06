# Code-Review: jarvis-schlappa/pv-forecast

Reviewer: Claude | Datum: 06.02.2026 | Version: v0.1.0

Scope: Vollständige Source-Code-Analyse aller Module, Tests & Docs

## Executive Summary

Gesamtnote: 7.5/10 – Ein bemerkenswert reifes Erstrelease mit professioneller Projektstruktur, exzellenter UX und solider Code-Qualität. Das ML-Modell hat klare Verbesserungspotentiale, aber die Software-Engineering-Grundlage ist überdurchschnittlich stark.

## 📊 Bewertungsmatrix

| Kategorie | Note | Gewicht | Kommentar |
|-----------|------|---------|-----------|
| Projektstruktur & Packaging | 9/10 | 15% | Vorbildlich |
| Code-Qualität | 8/10 | 20% | Sauber, konsistent, gut dokumentiert |
| ML-Modell & Features | 5.5/10 | 25% | Solide Basis, aber großer Verbesserungsbedarf |
| Tests | 8/10 | 15% | 158 Tests, gute Coverage, E2E vorhanden |
| UX & Dokumentation | 9/10 | 15% | Herausragend für ein v0.1 |
| Architektur & Erweiterbarkeit | 7/10 | 10% | Saubere Module, aber noch nicht plugin-fähig |

## 🟢 Stärken (was wirklich gut ist)

### 1. Projektstruktur (9/10)

Das Projekt folgt durchgehend Python Best Practices:

- src/-Layout mit pyproject.toml + Hatchling Build-Backend – modern und korrekt
- Optional Dependencies sauber getrennt: [xgb], [tune], [dev], [all]
- Ruff-Konfiguration mit sinnvollem Rule-Set (E, W, F, I, B, UP)
- CI/CD via GitHub Actions für Python 3.9–3.12
- XDG-konforme Pfade: ~/.config/pvforecast/ und ~/.local/share/pvforecast/

4.163 Zeilen Produktivcode, 3.649 Zeilen Tests – ein Test:Code-Ratio von 0.88 ist für ein Solo-Projekt exzellent.

### 2. Code-Qualität (8/10)

- Type Hints konsequent verwendet, inkl. from __future__ import annotations
- Google-Style Docstrings in allen Public Functions mit Args/Returns/Raises
- Dataclasses statt dictionaries für strukturierte Daten (Config, HourlyForecast, Forecast, CheckResult)
- Context Manager für DB-Verbindungen (db.connect())
- Saubere Error-Hierarchie: ValidationError, DependencyError, DataImportError, WeatherAPIError, ModelNotFoundError
- Graceful Degradation bei optionalen Dependencies (XGBoost, Optuna) – mit spezifischen Fehlermeldungen inkl. Installationsanleitung

Besonders positiv: Die XGBoost-Fehlerbehandlung (Zeile 33-52 in model.py) unterscheidet zwischen "nicht installiert", "libomp fehlt" und "unbekannter Fehler" – mit passenden Lösungshinweisen pro Plattform. Das ist herausragend durchdacht.

### 3. UX & Dokumentation (9/10)

- Setup-Wizard mit PLZ-Geocoding – ungewöhnlich poliert für ein CLI-Tool
- pvforecast doctor – ein diagnostisches Health-Check-Tool, das 368 Zeilen umfasst
- Progress-Anzeigen und Timing bei allen langwierigen Operationen
- Metriken-Erklärung als PDF für Nicht-Experten – wirklich durchdacht
- Deutsche Dokumentation für die Zielgruppe (E3DC-Nutzer in DACH)

### 4. Tests (8/10)

- 158 Tests über 7 Test-Module
- E2E-Integration-Tests mit populated_db Fixture (150 Stunden synthetische Daten)
- Edge Cases abgedeckt: leere DB, fehlende Spalten, BOM-CSV, ungültige Daten, Zeitumstellung
- Monkeypatch für Dependency-Tests (XGBoost/Optuna an/aus)
- conftest.py mit wiederverwendbaren Fixtures – sauber getrennt

### 5. Robuste Infrastruktur

- Retry-Logic mit Exponential Backoff + Jitter (Zeile 43-122 in weather.py)
- Wetter-Lücken-Erkennung und automatisches Nachladen
- Abregelungs-Erkennung in E3DC-Daten (curtailed flag)
- Schema-Migration von v1 → v2 (erweiterte Wetter-Features)
- Zeitumstellungs-Handling bei CSV-Import mit ambiguous="NaT"

## 🟡 Verbesserungspotential

### 1. ML-Modell – Feature Engineering (5/10)

Das Feature-Set (Zeile 126-169 in model.py) ist das schwächste Glied des Projekts:

**Aktuelle Features (10 Stück):**
```
hour, month, day_of_year, ghi, cloud_cover, temperature,
sun_elevation, wind_speed, humidity, dhi
```

**Was fehlt und den MAPE von 30% auf ~15-20% senken könnte:**

- **Zyklische Zeit-Features:** hour und month als lineare Integer führen dazu, dass das Modell nicht lernt, dass Stunde 23 und Stunde 0 benachbart sind. Stattdessen sin(2π·hour/24) und cos(2π·hour/24) verwenden – ebenso für month und day_of_year.

- **Clear-Sky-Index (CSI):** Das Verhältnis ghi / ghi_clear_sky ist einer der mächtigsten Prädiktoren für PV-Prognosen. Clear-Sky GHI lässt sich leicht aus Sonnenstand und Extraterrestrial Radiation berechnen (oder direkt von Open-Meteo anfordern). Ein CSI von 0.8 sagt dem Modell "80% des theoretischen Maximums erreicht" – viel informativer als absolute GHI.

- **DNI (Direct Normal Irradiance):** Open-Meteo bietet direct_normal_irradiance – ein wichtiges Feature, das die Unterscheidung zwischen diffuser und direkter Strahlung ermöglicht.

- **Interaktions-Features:** ghi × (1 - cloud_cover/100) als effektive Strahlung, temperature × production (PV-Module verlieren ~0.4%/°C über 25°C)

- **Lag-Features:** Für die today-Prognose: tatsächlicher Ertrag der letzten 1-3 Stunden als Input. Das ist der stärkste Kurzfrist-Prädiktor.

- **Anlagen-spezifische Features:** peak_kwp wird nirgends als Feature verwendet – bei einer 10 kWp-Anlage ist 8000W realistisch, bei 3 kWp nicht.

### 2. Sonnenhöhen-Berechnung (vereinfacht, aber ungenau)

Die eigene Implementierung (Zeile 84-123) ist eine starke Vereinfachung:

```python
solar_time = hour + lon / 15  # Grobe Annäherung
```

Das ignoriert die Equation of Time (bis zu ±16 Minuten Abweichung je nach Jahreszeit) und nutzt 3.14159 statt math.pi. Für ein ML-Feature ist das vermutlich ausreichend, da das Modell die Abweichung lernen kann – aber pvlib.solarposition wäre genauer und ein bereits vorhandener Standard. Die Dependency pvlib ist leichtgewichtig und würde gleichzeitig Clear-Sky-Modelle ermöglichen.

### 3. MAPE-Berechnung und Evaluation

**Gut:** MAPE wird nur für Stunden >100W berechnet (Zeile 333-338) – das vermeidet die bekannte MAPE-Verzerrung bei kleinen Werten.

**Problem:** Es fehlen wichtige Metriken:

- **RMSE** – zeigt, wie groß die Ausreißer sind
- **R²** – wie viel Varianz wird erklärt?
- **Skill Score vs. Persistence-Modell** – DER Benchmark: "Ist das ML-Modell besser als ‚morgen wie heute'?" Ohne diesen Vergleich ist unklar, ob das Modell überhaupt Mehrwert liefert.
- **Aufschlüsselung nach klar/bewölkt** – das Modell könnte bei Sonnenschein exzellent sein und bei Wolken versagen

### 4. Performance-Anti-Patterns

Drei Stellen im Code verwenden iterrows() oder apply() statt vektorisierter Operationen:

```python
# model.py:165 – Sonnenhöhe pro Zeile berechnet
features["sun_elevation"] = df["timestamp"].apply(
    lambda ts: calculate_sun_elevation(int(ts), lat, lon)
)

# data_loader.py:156 – Zeilenweise DB-Insert
for _, row in df.iterrows():
    conn.execute(...)

# weather.py:291 – Zeilenweise Record-Erstellung
for _, row in df.iterrows():
    records.append(...)
```

Bei 62k Datensätzen ist das noch vertretbar, aber numpy-vektorisierte Operationen für die Sonnenhöhe und executemany statt Einzel-Inserts würden die Trainingszeit bei größeren Datenmengen deutlich reduzieren. Der Weather-Bulk-Insert (weather.py:296) nutzt bereits executemany – gut! Aber der data_loader.py Import nicht.

### 5. SQL-Injection-Risiko (niedrig, aber vorhanden)

Drei Stellen nutzen f-Strings für SQL:

```python
query += f" AND p.timestamp >= strftime('%s', '{since_year}-01-01')"
```

since_year kommt aus CLI-Input und ist als int typisiert – das Risiko ist gering, aber es wäre sauberer, parameterisierte Queries zu verwenden:

```python
query += " AND p.timestamp >= strftime('%s', ?)"
params.append(f"{since_year}-01-01")
```

### 6. Pickle für Modell-Serialisierung

pickle.dump/load funktioniert, hat aber bekannte Nachteile:

- **Sicherheitsrisiko:** Pickle kann beliebigen Code ausführen
- **Versionsfragilität:** Modelle können nach sklearn-Updates unlesbar werden
- **Keine Metadaten-Inspektion ohne Laden**

Alternative: joblib (sklearn-Standard) oder skops für sichere Serialisierung. Für ein lokales CLI-Tool ist Pickle vertretbar, aber für eine spätere HA-Integration problematisch.

## 🔴 Fehlende Features für den Praxis-Einsatz

### 1. Keine Home-Assistant-Integration

Für deinen Use Case (10 kWp + Batterie + HA) ist dies der größte Blocker. Kein REST-API-Modus, kein MQTT, kein HA-Sensor. Die offenen Issues #36-39 adressieren das.

### 2. Kein automatischer Cron-Betrieb

Kein systemd-Service, kein Cron-Setup, kein --daemon-Modus.

### 3. Keine Konfidenzintervalle

Das Modell liefert nur Punktprognosen ("morgen 15 kWh"), aber keine Unsicherheitsschätzung ("morgen 12-18 kWh mit 80% Wahrscheinlichkeit"). XGBoost kann mit quantile Objective leicht Quantil-Regression liefern.

### 4. Kein Online-Learning

Modell muss manuell nachtrainiert werden. Kein Feedback-Loop "Prognose vs. Realität".

## 🏗️ Architektur-Bewertung

### Positiv

- Klare Modul-Trennung (6 Module mit jeweils einem Verantwortungsbereich)
- DB als zentrale Datenschicht mit JOIN-basiertem Feature-Merge
- Config-System mit YAML + CLI-Override
- Saubere Datenfluss-Trennung: Import → DB → Train → Model → Predict

### Verbesserungswürdig

- cli.py ist mit 1034 Zeilen zu groß – Output-Formatierung, Command-Handler und Argumentparsing sollten getrennt werden
- Kein Plugin-System für alternative Wetter-Provider (nur Open-Meteo hardcoded)
- Kein abstrakes Datenimport-Interface – nur E3DC CSV wird unterstützt

## Detaillierte Code-Metriken

| Modul | Zeilen | Verantwortung | Bewertung |
|-------|--------|---------------|-----------|
| cli.py | 1.034 | CLI + Formatting | Zu groß, aufteilen |
| model.py | 878 | ML Train/Predict/Tune | Kernstück, Feature Engineering zu dünn |
| doctor.py | 368 | Diagnostik | Exzellent, überraschend durchdacht |
| weather.py | 447 | Open-Meteo Client | Robust, Retry+Gap-Filling |
| validation.py | 312 | Input-Validierung | Sauber, umfassend |
| data_loader.py | 194 | E3DC CSV Import | Kompakt, korrekt |
| config.py | 194 | YAML Config | Sauber, validiert |
| db.py | 143 | SQLite Layer | Minimal aber ausreichend |
| setup.py | ~300 | Setup Wizard | Poliert |
| geocoding.py | ~250 | PLZ → Koordinaten | Clever gelöst |

## Empfehlung: Top-5 Verbesserungen nach Impact

| # | Maßnahme | Geschätzter Impact auf MAPE | Aufwand |
|---|----------|----------------------------|---------|
| 1 | Zyklische Zeit-Features (sin/cos) | -3-5% | 🟢 30 Min |
| 2 | Clear-Sky-Index als Feature | -5-8% | 🟡 2-3 Std |
| 3 | Lag-Features für Today-Prognose | -3-5% (nur today) | 🟡 2-3 Std |
| 4 | DNI + weitere Open-Meteo Params | -2-3% | 🟢 1 Std |
| 5 | LightGBM statt XGBoost | -1-2% + schneller | 🟢 30 Min |

Kumuliert könnten diese 5 Maßnahmen den MAPE von ~30% auf ~15-20% senken – und damit das Erfolgskriterium aus der SPEC.md (<20%) erreichen.

## Fazit

pv-forecast ist ein **außergewöhnlich gut strukturiertes und dokumentiertes Solo-Projekt**, das als Software-Engineering-Leistung beeindruckt. Die Projektorganisation (SPEC, Changelog, PROJECT-STATUS, Issues, CI) ist professioneller als bei vielen Team-Projekten.

Die ML-Performance hat klaren Verbesserungsbedarf, aber die Code-Architektur bietet eine solide Basis dafür. Die fünf genannten Feature-Engineering-Maßnahmen wären mit vertretbarem Aufwand (1-2 Tage) umsetzbar und könnten die Genauigkeit signifikant verbessern.

Für den Einsatz in deinem Setup (10 kWp, Batterie, HA) fehlt aktuell die HA-Integration und die Prognosegenauigkeit für automatisierte Steuerung. Als Forschungs- und Lernprojekt ist es aber eine hervorragende Ausgangsbasis.
