# Glossar

Erklärung der Fachbegriffe in PV-Forecast – verständlich für Nicht-Experten.

---

## 📊 Metriken & Statistik

### MAE (Mean Absolute Error)
**Mittlerer absoluter Fehler** – durchschnittliche Abweichung der Prognose vom echten Wert, in Watt.

*Beispiel:* MAE = 140 W bedeutet: Die Prognose liegt im Schnitt 140 W daneben.

**Gut wenn:** < 150 W

---

### MAPE (Mean Absolute Percentage Error)
**Mittlerer prozentualer Fehler** – wie stark die Prognose prozentual abweicht.

*Beispiel:* MAPE = 30% bei 1000 W Prognose bedeutet: Der echte Wert liegt typischerweise zwischen 700 W und 1300 W.

**Gut wenn:** < 35%

**Hinweis:** Wird nur für Stunden mit >100 W berechnet (Nacht/Dämmerung verzerrt sonst das Ergebnis).

---

### RMSE (Root Mean Square Error)
**Wurzel des mittleren quadratischen Fehlers** – ähnlich wie MAE, aber größere Fehler werden stärker gewichtet.

*Vereinfacht:* RMSE bestraft große Ausreißer härter als MAE. Wenn RMSE deutlich höher als MAE ist, gibt es gelegentlich größere Fehlprognosen.

---

### R² (Bestimmtheitsmaß)
**Wie gut erklärt das Modell die Schwankungen?**

| R² | Bedeutung |
|----|-----------|
| 1.0 | Perfekt – Modell erklärt alles |
| 0.95 | Sehr gut – 95% der Variation erklärt |
| 0.90 | Gut |
| < 0.80 | Verbesserungsbedarf |

*Beispiel:* R² = 0.95 bedeutet: Das Modell erklärt 95% der Schwankungen in der PV-Produktion. Die restlichen 5% sind Rauschen oder unbekannte Faktoren.

---

### Cross-Validation (CV)
**Kreuzvalidierung** – Methode um zu testen, wie gut das Modell auf *neuen* Daten funktioniert.

Die Daten werden in mehrere Teile geteilt. Das Modell wird auf einem Teil trainiert und auf dem anderen getestet. Das wird mehrfach wiederholt (z.B. 5× bei CV=5).

*Warum wichtig:* Verhindert, dass das Modell nur die Trainingsdaten auswendig lernt.

---

### Overfitting
**Überanpassung** – das Modell lernt die Trainingsdaten *zu gut*, inklusive zufälliger Schwankungen.

*Problem:* Funktioniert perfekt auf alten Daten, aber schlecht auf neuen.

*Gegenmittel:* Cross-Validation, mehr Daten, einfachere Modelle.

---

### Train/Test Split
Die Daten werden aufgeteilt:
- **Training (80%):** Modell lernt Muster
- **Test (20%):** Prüfung auf ungesehenen Daten

Bei PV-Forecast wird zeitbasiert gesplittet (ältere Daten zum Training, neuere zum Testen).

---

## 🤖 Machine Learning

### Feature
**Eingabewert** für das ML-Modell – alles was zur Vorhersage genutzt wird.

*Beispiele:* Uhrzeit, Monat, Sonnenhöhe, Bewölkung, Temperatur, Globalstrahlung.

---

### Feature Engineering
**Merkmale ableiten** – aus Rohdaten neue, aussagekräftige Features berechnen.

*Beispiel:* Aus GHI und Bewölkung wird `effective_irradiance` berechnet: GHI × (1 - Bewölkung/100)

---

### Lag-Features
**Verzögerte Werte** – Werte von vor X Stunden als zusätzliche Features.

*Beispiel:* `ghi_lag_1h` = Globalstrahlung vor einer Stunde. Hilft dem Modell, Trends zu erkennen.

---

### RandomForest
**Zufallswald** – ML-Algorithmus der viele Entscheidungsbäume kombiniert.

✅ Robust, wenig Overfitting  
✅ Keine zusätzliche Installation  
⚠️ Etwas weniger genau als XGBoost

---

### XGBoost
**Extreme Gradient Boosting** – fortgeschrittener ML-Algorithmus.

✅ Beste Genauigkeit  
✅ Schnelles Training  
⚠️ Benötigt zusätzliche Installation (`pip install pvforecast[xgb]`)

---

### Hyperparameter
**Einstellungen** die *vor* dem Training festgelegt werden (nicht vom Modell gelernt).

*Beispiele:* Anzahl der Bäume (`n_estimators`), maximale Tiefe (`max_depth`), Lernrate (`learning_rate`).

---

### Hyperparameter-Tuning
**Optimierung** der Hyperparameter durch systematisches Ausprobieren.

Methoden:
- **RandomizedSearchCV:** Zufällig ausprobieren
- **Optuna (Bayesian):** Lernt aus vorherigen Versuchen → effizienter

---

### Trial
**Versuch** beim Tuning – eine Kombination von Hyperparametern wird getestet.

*Beispiel:* 50 Trials = 50 verschiedene Einstellungen werden ausprobiert.

---

### Pruning
**Frühzeitiges Abbrechen** von aussichtslosen Trials beim Tuning.

*Vorteil:* Spart Zeit, weil schlechte Kombinationen nicht vollständig durchgerechnet werden.

---

## 🌤️ Wetter & Strahlung

### GHI (Global Horizontal Irradiance)
**Globalstrahlung** – gesamte Sonnenstrahlung auf eine horizontale Fläche (in W/m²).

Besteht aus:
- Direkter Sonnenstrahlung (Schatten-werfend)
- Diffuser Strahlung (vom Himmel gestreut)

*Wichtigster Faktor für PV-Ertrag!*

---

### DHI (Diffuse Horizontal Irradiance)
**Diffusstrahlung** – der Anteil der Strahlung, der vom Himmel gestreut wird (nicht direkt von der Sonne).

*Bei bewölktem Himmel:* DHI ist hoch (viel gestreutes Licht)  
*Bei klarem Himmel:* DHI ist niedrig (meist Direktstrahlung)

---

### DNI (Direct Normal Irradiance)
**Direktstrahlung** – Strahlung direkt von der Sonne, senkrecht zur Einstrahlung gemessen.

*Wichtig für:* Nachführsysteme und konzentrierende Solartechnik.

---

### Clear-Sky-Index (CSI)
**Klarhimmel-Index** – Verhältnis von gemessener zu theoretisch möglicher Strahlung.

| CSI | Bedeutung |
|-----|-----------|
| 1.0 | Klarer Himmel (100% des Möglichen) |
| 0.5 | Stark bewölkt (50% des Möglichen) |
| >1.0 | Möglich bei Wolkenrändern (Reflexion) |

---

### Sonnenhöhe (Solar Elevation)
**Winkel der Sonne über dem Horizont** in Grad.

- 0° = Sonnenauf-/untergang
- 90° = Sonne steht senkrecht (nur in Tropen)
- Deutschland Sommer Mittag: ~60°
- Deutschland Winter Mittag: ~15°

---

### Modultemperatur
**Temperatur der PV-Module** – beeinflusst den Wirkungsgrad.

*Faustregel:* Pro °C über 25°C sinkt die Leistung um ~0.4%.

Wird geschätzt aus Umgebungstemperatur, Strahlung und Wind (NOCT-Modell).

---

### NOCT (Nominal Operating Cell Temperature)
**Nenn-Betriebstemperatur** – Referenzwert für die Modultemperatur unter Standardbedingungen (800 W/m², 20°C Umgebung, Wind 1 m/s).

Typisch: 45°C. Wird verwendet um die reale Modultemperatur zu schätzen.

---

## 🌐 Datenquellen (DWD)

### DWD
**Deutscher Wetterdienst** – offizielle Wetterbehörde Deutschlands. Stellt kostenlose Wetterdaten bereit.

---

### MOSMIX
**Model Output Statistics MIX** – 10-Tage-Wettervorhersage des DWD.

- Stündliche Auflösung
- Stationsbasiert (nächste Wetterstation)
- Offizielle Vorhersagedaten

*Verwendung:* Prognose für kommende Tage.

---

### HOSTRADA
**Hourly Surface Radiation** – historische Strahlungsdaten des DWD.

- Seit 1995 verfügbar
- 1 km Rasterauflösung (sehr genau!)
- Basiert auf Satellitenmessungen

*Verwendung:* Training (beste Datenqualität für historische Wetterdaten).

⚠️ **Achtung:** Lädt komplette Deutschland-Raster herunter (~40 GB für mehrere Jahre).

---

### Open-Meteo
**Kostenlose Wetter-API** – Alternative zu DWD.

- Historische Daten (ERA5-Reanalyse)
- Vorhersagen bis 16 Tage
- Einfacher Zugriff, geringere Latenz

*Verwendung:* Fallback, schnelle Updates, wenn HOSTRADA zu aufwändig.

---

### ERA5
**ECMWF Reanalysis v5** – globaler historischer Wetterdatensatz.

Kombiniert Beobachtungen mit Wettermodellen zu einem konsistenten Datensatz. Auflösung ~31 km, stündlich, ab 1940.

*Open-Meteo nutzt ERA5 für historische Daten.*

---

## ☀️ Photovoltaik

### kWp (Kilowatt Peak)
**Nennleistung** einer PV-Anlage unter Standardbedingungen (1000 W/m², 25°C Modultemperatur).

*Beispiel:* 9.92 kWp = Anlage kann maximal ~10 kW produzieren (bei perfekten Bedingungen).

---

### Ertrag (kWh)
**Produzierte Energie** – Leistung über Zeit.

*Beispiel:* 2000 W für 5 Stunden = 10 kWh

---

### Abregelung (Curtailment)
**Erzwungene Leistungsreduzierung** – wenn die Anlage weniger produziert als möglich wäre.

*Gründe:*
- 70%-Regelung (max. 70% der Nennleistung ins Netz)
- Netzüberlastung
- Wechselrichter-Limits

*Bei PV-Forecast:* Abgeregelte Stunden werden beim Training ausgeschlossen (würden das Modell verfälschen).

---

### E3DC
**Hersteller von Hauskraftwerken** (PV-Speichersysteme).

PV-Forecast kann E3DC CSV-Exporte direkt importieren.

---

### SoC (State of Charge)
**Ladezustand** des Batteriespeichers in Prozent.

- 100% = Batterie voll
- 0% = Batterie leer

---

## 🔧 Technik

### API (Application Programming Interface)
**Schnittstelle** um Daten automatisiert abzurufen.

*Beispiel:* Open-Meteo API liefert Wetterdaten als strukturierte Antwort auf Anfragen.

---

### CLI (Command Line Interface)
**Kommandozeile** – Text-basierte Bedienung im Terminal.

*Beispiel:* `pvforecast predict --days 5`

---

### CSV (Comma-Separated Values)
**Textdatei mit Tabellendaten** – Werte durch Trennzeichen (z.B. `;`) getrennt.

Standard-Exportformat von E3DC und vielen anderen Systemen.

---

### SQLite
**Einfache Datenbank** in einer einzelnen Datei.

PV-Forecast speichert alle Daten in `~/.local/share/pvforecast/data.db`.

---

### UTC (Coordinated Universal Time)
**Koordinierte Weltzeit** – Zeitzone ohne Sommer-/Winterzeit.

Deutschland = UTC+1 (Winter) bzw. UTC+2 (Sommer).

*Intern speichert PV-Forecast alles in UTC.*

---

### Unix Timestamp
**Sekunden seit 1. Januar 1970 00:00 UTC** – universelles Zeitformat.

*Beispiel:* 1707350400 = 8. Februar 2024, 00:00 UTC

---

### Geocoding
**Ortssuche** – Umwandlung von PLZ oder Ortsname in Koordinaten (Lat/Lon).

*Beispiel:* "48249" → Dülmen, 51.85°N, 7.26°E

---

## 📈 Vergleichswerte

Was bedeuten die Metriken in der Praxis?

| Qualität | MAPE | MAE (bei 10 kWp) | Bedeutung |
|----------|------|------------------|-----------|
| Exzellent | <20% | <120 W | Sehr genaue Prognose |
| Gut | 20-30% | 120-180 W | Zuverlässig planbar |
| Akzeptabel | 30-40% | 180-240 W | Grobe Orientierung |
| Schlecht | >40% | >240 W | Wenig aussagekräftig |

**Aktuelle Performance von PV-Forecast:**
- Mit DWD HOSTRADA: MAPE ~22%, MAE ~105 W → **Exzellent**
- Mit Open-Meteo: MAPE ~30%, MAE ~126 W → **Gut**

---

*Letzte Aktualisierung: Februar 2026*
