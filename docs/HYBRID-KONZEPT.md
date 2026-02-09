





KONZEPT
Physics-Informed Hybrid-Forecasting
für pvforecast


Projekt: pv-forecast v0.4.2  |  Anlage: 10 kWp, 3 Ausrichtungen, Dülmen
Datum: Februar 2026  |  Aktueller MAPE: 24.9%  |  Ziel: < 20%
Version 2.0 – Angepasst an Implementierungsstand 09.02.2026


1. Executive Summary
Dieses Konzept beschreibt die nächsten Schritte zur Verbesserung von pvforecast. Phase 1 (Feature Engineering) ist bereits implementiert und hat den MAPE von 30.1% auf 24.9% gesenkt. Die verbleibenden Phasen zielen auf die Umstellung von End-to-End-ML auf eine Physics-Informed Hybrid-Pipeline, bei der ML die Wettervorhersage korrigiert und pvlib die PV-Physik berechnet.

Kennzahl
Ist-Stand (v0.4.2)
Ziel
MAPE (trainiert)
24.9%
< 20%
MAE
125W
< 100W
R²
0.97
> 0.98
Historische Daten
HOSTRADA (Messwerte)
Bleibt
Forecast-Quelle
Open-Meteo (ICON/IFS)
Open-Meteo + GFS Ensemble
Physik-Modell
pvlib nur für CSI
pvlib (3 Arrays, Transposition)
ML-Aufgabe
Wetter → Ertrag (End-to-End)
Bias-Korrektur + Residuen
Unsicherheit
Keine (Punktprognose)
Quantile (10/50/90)

2. Ist-Stand der Implementierung
2.1 Bereits implementierte Features (Phase 1 ✓)
Die folgenden Maßnahmen aus dem ursprünglichen Konzept sind in v0.4.2 umgesetzt:

Feature
Status
Code-Referenz
Zyklische Zeitfeatures (sin/cos)
✅ Implementiert
model.py: encode_cyclic()
pvlib Clear-Sky-Index (CSI)
✅ Implementiert
model.py: Location.get_clearsky()
Diffuse Fraction (DHI/GHI)
✅ Implementiert
model.py: diffuse_fraction
DNI (Direct Normal Irradiance)
✅ Implementiert
model.py: dni_wm2
Modultemperatur (NOCT)
✅ Implementiert
model.py: t_module
Temperatur-Derating
✅ Implementiert
model.py: efficiency_factor
Wetter-Lags (1h, 3h, rolling)
✅ Implementiert
model.py: ghi_lag_1h etc.
DHI physikalisch korrekt (#163)
✅ Implementiert
v0.4.2: Clearness Index
Cloud Cover entfernt (#168)
✅ Bewusst entfernt
Inkonsistent mit GHI
Production Lags entfernt (#170)
✅ Bewusst entfernt
Train/Predict-Mismatch

2.2 Aktuelle Architektur
Training:   HOSTRADA (Messwerte)  →  prepare_features()  →  XGBoost  →  Modell
Forecast:   Open-Meteo (ICON/IFS) →  prepare_features()  →  Modell   →  Ertrag

Bekanntes Problem: Train/Predict-Gap. Das Modell trainiert auf HOSTRADA-Messwerten (Ground Truth GHI), prognostiziert aber mit Open-Meteo-Vorhersagewerten. Die systematischen Fehler der Wettervorhersage hat das Modell nie gesehen. Dies erklärt einen Teil der Backtesting-Diskrepanz (MAPE trainiert: 24.9% vs. Backtesting 2026: 109%, wobei letzteres durch Schnee auf den Modulen im Januar zusätzlich verzerrt ist).

2.3 Aktuelle Datenquellen
Komponente
Quelle
Speicherung
Historische Wetterdaten
DWD HOSTRADA (Rasterdaten)
weather_history Tabelle
Forecast-Daten
Open-Meteo (Default = ICON/IFS)
Direkt in Pipeline (nicht persistiert)
PV-Ertragsdaten
E3DC CSV Export
pv_readings Tabelle

Hinweis: Die DB hat keine Source-Kennung – weather_history enthält HOSTRADA-Daten, unterscheidet aber nicht nach Herkunft. Für Phase 3 (Ensemble) wird eine Erweiterung nötig.

3. Grundprinzip: Warum Hybrid?
Die gesamte Unsicherheit der PV-Prognose stammt aus der Wolkenvorhersage. Der bisherige End-to-End-Ansatz zwingt das ML-Modell, sowohl Wetterfehler als auch PV-Physik zu lernen. Die Hybrid-Pipeline trennt diese Aufgaben: ML korrigiert dort wo Physik versagt (Wettervorhersage-Bias), Physik berechnet dort wo sie exakt ist (Strahlungstransport, Modulverhalten).

Bisheriger Ansatz (aktuell)
Open-Meteo GHI  →  prepare_features()  →  XGBoost  →  Ertrag (Watt)

Neuer Ansatz (Hybrid-Pipeline)
Open-Meteo GHI  →  ML-Bias-Korrektur    →  korrigierte GHI
korrigierte GHI →  pvlib (3 Arrays)      →  theoretischer Ertrag
theor. Ertrag   →  ML-Residualkorrektur  →  reale Prognose

Die Residualkorrektur lernt implizit Verschattung durch umliegende Bebauung sowie Wechselrichter-Verluste, ohne dass diese explizit modelliert werden.

4. Vorab-Validierung (vor Implementierung)
Bevor die Architektur umgebaut wird, können folgende Tests mit den vorhandenen Daten die Erfolgsaussichten quantifizieren:

4.1 Obergrenze des Verbesserungspotenzials
Schlüsseltest: Backtesting mit HOSTRADA-Daten statt Open-Meteo als Forecast-Input. Hierfür die historischen HOSTRADA-Messwerte aus der DB als „perfekte Wettervorhersage“ verwenden und den MAPE messen. Dieser Wert zeigt die theoretische Untergrenze – alles zwischen diesem Wert und 24.9% ist durch bessere Strahlungsvorhersage erreichbar.

# Pseudo-Code: Backtesting mit perfekter Strahlung
X_test = prepare_features(hostrada_data, ...)  # Messwerte statt Forecast
y_pred = model.predict(X_test)
mape_perfect = calculate_mape(y_real, y_pred)
# Erwartet: 10-15% → Potenzial von ~10-15% Verbesserung

4.2 MOSMIX-Bias-Analyse
Vorhandene MOSMIX-Vorhersagen (sofern in der DB) gegen HOSTRADA-Messwerte plotten. Systematische Muster (z.B. „MOSMIX überschätzt morgens im Winter“) bestätigen, dass die MOS-Schicht greifen wird. Wenn der Fehler rein zufällig ist, bringt ML-Korrektur wenig.

4.3 Open-Meteo Bias-Analyse
Da Open-Meteo die aktuelle Forecast-Quelle ist: Open-Meteo-Vorhersagen für vergangene Tage (via past_days Parameter) abrufen und gegen HOSTRADA-Messwerte vergleichen. Der MAE und die Fehlerstruktur der Strahlungsvorhersage zeigen direkt, wie viel die MOS-Korrektur bringen kann.

4.4 NWP-Unabhängigkeit prüfen
Einige Wochen GFS-Daten von Open-Meteo holen und die Fehlerkorrelation mit den Standard-Open-Meteo-Daten berechnen. Korrelation < 0.7 → Ensemble lohnt sich. Korrelation > 0.9 → GFS bringt wenig, Solcast wäre besser.

Test
Aufwand
Was er zeigt
Priorität
Backtesting mit HOSTRADA
1-2 Stunden
Obergrenze des Potenzials
⭐ Höchste
Open-Meteo Bias-Analyse
2-3 Stunden
MOS-Schicht-Potenzial
Hoch
NWP-Fehlerkorrelation
Halber Tag
Ensemble-Mehrwert
Mittel

5. Phase 2: MOS-Schicht + physikalisches PV-Modell
Aufwand: 2–3 Tage  ·  Erwartetes MAPE: 18–22%  ·  Adressiert den Train/Predict-Gap

Phase 2 ist der kritischste nächste Schritt, da sie direkt das Kernproblem adressiert: Das Modell trainiert auf Messwerten, muss aber auf Vorhersagewerten prognostizieren.

5.1 ML-basierte Strahlungskorrektur (MOS-Schicht)
Ein separates, leichtes ML-Modell lernt den systematischen Bias der Open-Meteo-Strahlungsvorhersage. Dafür werden Paare von Open-Meteo-Vorhersagen und HOSTRADA-Messwerten für dieselben Zeitpunkte benötigt.

Datensammlung (Voraussetzung)
Aktuell werden Open-Meteo-Forecasts nicht persistiert. Für die MOS-Schicht müssen Forecast-Daten mindestens 2–3 Monate gesammelt werden, bevor das MOS-Modell trainiert werden kann. Dafür ist eine DB-Erweiterung nötig:

-- Neue Tabelle für Forecast-Daten
CREATE TABLE forecast_history (
    timestamp       INTEGER,
    source          TEXT,           -- 'open-meteo', 'gfs', 'mosmix'
    issued_at       INTEGER,        -- Wann wurde der Forecast erstellt?
    ghi_wm2         REAL,
    cloud_cover_pct INTEGER,
    temperature_c   REAL,
    dhi_wm2         REAL,
    dni_wm2         REAL,
    PRIMARY KEY (timestamp, source, issued_at)
);

Trainings-Setup
# Features: Open-Meteo Vorhersage + Kontext
X = df[['openmeteo_ghi', 'openmeteo_cloud', 'clearsky_ghi',
        'hour_sin', 'hour_cos', 'doy_sin', 'doy_cos']]
 
# Target: HOSTRADA-Messung (Ground Truth)
y = df['hostrada_ghi']
 
# Leichtes Modell – Bias-Korrektur ist einfacher als End-to-End
mos_model = LGBMRegressor(n_estimators=100, max_depth=4)

5.2 pvlib PV-System-Modell (3 Arrays)
pvlib wird von der reinen CSI-Berechnung zum vollständigen PV-Modell ausgebaut. Die drei Ausrichtungen werden als separate Arrays mit eigener Transpositionsberechnung konfiguriert. Benötigte Angaben: Azimut, Neigung und kWp pro Ausrichtung (einmalig in config.yaml).

Konfigurationserweiterung
pv_system:                         # NEU
  arrays:
    - name: "Ausrichtung 1"
      azimuth: ???               # Grad, 180 = Süd
      tilt: ???                  # Grad Neigung
      kwp: ???
    - name: "Ausrichtung 2"
      azimuth: ???
      tilt: ???
      kwp: ???
    - name: "Ausrichtung 3"
      azimuth: ???
      tilt: ???
      kwp: ???
  temperature_coefficient: -0.37  # %/°C (Default kristallines Si)
  mounting: rack                  # Aufdach mit Hinterlüftung

pvlib berechnet pro Array die POA-Strahlung (Perez-Modell), Modultemperatur und theoretischen Ertrag. Das Ergebnis ist der unverschattete theoretische Ertrag.

5.3 ML-Residualkorrektur (Verschattung + Verluste)
Ein zweites ML-Modell lernt die systematische Abweichung zwischen pvlib-Berechnung und realem Ertrag:
	•	Verschattung durch umliegende Bebauung (sonnenstandsabhängig, saisonal)
	•	Wechselrichter-Verluste (Teillast, Clipping durch E3DC)
	•	Leitungsverluste, Degradation, Verschmutzung, Schnee

Da Verschattung deterministisch vom Sonnenstand abhängt, reicht ein volles Jahr Trainingsdaten (vorhanden). Kein 3D-Modell oder Horizontprofil nötig.

5.4 Gesamtpipeline Phase 2
Schritt
Methode
Input
Output
1. Forecast sammeln
DB (neu)
Open-Meteo API Response
forecast_history Tabelle
2. Strahlungskorrektur
ML (LightGBM)
Open-Meteo GHI + Kontext
Korrigierte GHI/DHI
3. Transposition
pvlib (Perez)
Korr. GHI/DHI + Solpos
POA pro Array
4. PV-Modell
pvlib (PVSystem)
POA + Temperatur + Wind
Theor. Ertrag
5. Residualkorrektur
ML (LightGBM)
Theor. Ertrag + Solpos
Reale Prognose

Vorteil: Fehlerquelle sofort lokalisierbar – Wetter (Schritt 2) vs. Anlage (Schritt 5). Ersetzt das aktuelle prepare_features() → XGBoost → Ertrag.

6. Phase 3: Multi-NWP Ensemble + Unsicherheit
Aufwand: 3–5 Tage  ·  Erwartetes MAPE: 15–20%  ·  Professionelles Niveau

6.1 Datenquellen-Unabhängigkeit
Die aktuelle Forecast-Quelle Open-Meteo liefert im Default ICON/IFS-Daten. MOSMIX basiert ebenfalls auf ICON + IFS – ein Ensemble aus beiden hätte daher nur geringe Fehler-Dekorrelation. Für ein echtes Ensemble braucht es ein unabhängiges Basismodell.

Quelle
Basismodell
Unabhängigkeit
Kosten
Open-Meteo (aktuell)
ICON + IFS
– (Referenz)
0 €
MOSMIX
ICON + IFS (MOS)
Gering – gleiche Basis!
0 €
Open-Meteo GFS
GFS (NOAA)
Hoch – anderes Modell
0 €
Solcast
Satellit + NWP
Sehr hoch – andere Methodik
~20 €/Mon.

6.2 Empfehlung: Open-Meteo (Default) + Open-Meteo (GFS)
Open-Meteo wird zusätzlich mit dem GFS-Modell (NOAA) abgefragt. GFS ist ein komplett unabhängiges Modell. Da der bestehende Open-Meteo-Source-Code bereits existiert, ist der Aufwand minimal:

# Bestehend (ICON/IFS):
https://api.open-meteo.com/v1/forecast?...
 
# Zusatz (unabhängiges Modell):
https://api.open-meteo.com/v1/gfs?...
# Alternativ: &models=gfs_seamless

6.3 Ensemble-Features
features['ghi_spread']       = abs(openmeteo_ghi - gfs_ghi)
features['ghi_mean']         = (openmeteo_ghi + gfs_ghi) / 2
features['cloud_agreement']  = 1 - abs(openmeteo_cloud - gfs_cloud) / 100

Der Spread ist ein wertvoller Unsicherheitsindikator: Übereinstimmung = konfident, Divergenz = unsichere Wetterlage.

6.4 Probabilistische Ausgabe (Quantile Regression)
Statt Punktprognose: „Morgen 12–18 kWh (80% Konfidenz), erwartet 15 kWh.“

model_q10 = LGBMRegressor(objective='quantile', alpha=0.1)
model_q50 = LGBMRegressor(objective='quantile', alpha=0.5)
model_q90 = LGBMRegressor(objective='quantile', alpha=0.9)

Wertvoll für Batteriesteuerung und Eigenverbrauchsoptimierung in Home Assistant.

6.5 Optionales Premium-Upgrade: Solcast
Solcast nutzt Satellitenbilder statt NWP – höchste Fehler-Dekorrelation. Besonders für Nowcasting (0–6h) überlegen. Kosten: ~20 €/Monat.

7. Verschattungsbehandlung
7.1 Ansatz: Implizites ML-Lernen
Die Verschattung durch umliegende Bebauung wird nicht explizit modelliert. Die ML-Residualkorrektur (Phase 2, Schritt 5) lernt die Muster aus den Trainingsdaten. Dies funktioniert, weil Verschattung deterministisch ist: gleicher Sonnenstand = gleicher Schatten. Das Modell lernt z.B.: „Bei Elevation < 15° und Azimut 120–150° liegt der Ertrag 30% unter dem pvlib-Wert.“

Voraussetzung: Min. 1 Jahr Trainingsdaten (vorhanden).
Vorteil: Kein Konfigurationsaufwand. Passt sich bei Bebauungsänderungen nach Neutraining automatisch an.

Ansatz
Aufwand
Genauigkeit
Empfehlung
Implizites ML-Lernen
Keiner
Gut (≥1 Jahr Daten)
✅ Empfohlen
Horizontprofil (pvlib)
Hoch (3x Profil)
Etwas besser
Nur bei Bedarf
3D-Simulation (PVsyst)
Sehr hoch
Am besten
Overkill

8. Umsetzungs-Roadmap

Phase
Maßnahme
Aufwand
MAPE-Ziel
Status
1a
pvlib + Clear-Sky-Index
–
–
✅ Erledigt (v0.4.2)
1b
Zyklische Zeitfeatures
–
–
✅ Erledigt
1c
Diffuse Fraction, DNI, Modultemp.
–
–
✅ Erledigt
1d
Wetter-Lags (1h, 3h, rolling)
–
24.9%
✅ Erledigt
V
Vorab-Validierung (Kap. 4)
0.5–1 Tag
–
⭐ Empfohlen vor Phase 2
2a
Forecast-Daten persistieren (DB)
0.5 Tage
–
Offen – Voraussetzung!
2b
MOS-Schicht (Strahlungskorrektur)
1 Tag
–
Offen (nach 2–3 Mon. Daten)
2c
pvlib PV-System (3 Arrays)
0.5 Tage
–
Offen
2d
ML-Residualkorrektur
0.5 Tage
18–22%
Offen
3a
Open-Meteo GFS als 2. Quelle
0.5 Tage
–
Offen
3b
Ensemble-Features
0.5 Tage
–
Offen
3c
Quantile Regression
1 Tag
15–20%
Offen
Opt.
Solcast Integration
1 Tag
< 15%?
Offen

Kritischer Pfad: Phase 2a (Forecast persistieren) sofort starten, da die MOS-Schicht 2–3 Monate gesammelte Forecast-Daten benötigt. Je früher das Logging beginnt, desto früher kann Phase 2b trainiert werden.

Restaufwand: ca. 5–8 Arbeitstage für Phase 2 + 3 (Phase 1 ist abgeschlossen).

9. Technische Voraussetzungen
9.1 Neue Dependencies
Paket
Zweck
Status
pvlib
Sonnenstand, Clear-Sky (aktuell nur CSI)
✅ Bereits installiert
pvlib (erweitert)
Transposition, PVSystem, Temperaturmodell
Nutzung ausbauen
lightgbm
MOS + Residualkorrektur + Quantile
Neu (schneller als XGBoost)

9.2 DB-Schema-Erweiterung
Neue Tabelle forecast_history für persistierte Forecast-Daten mit Source-Kennung. Ermöglicht sowohl die MOS-Schicht (Phase 2) als auch das Multi-Source-Ensemble (Phase 3).

9.3 Config-Erweiterung
Neuer Abschnitt pv_system mit Array-Definitionen (Azimut, Neigung, kWp pro Ausrichtung). Platzhalter-Werte müssen mit den realen Anlagendaten gefüllt werden.

10. Risiken und Mitigationen

Risiko
Eintritt
Impact
Mitigation
Zu wenig Forecast-Daten für MOS
Sicher (initial)
Hoch
Logging sofort starten; 2-3 Monate sammeln
Train/Predict-Gap bleibt nach MOS
Gering
Hoch
Vorab-Validierung (Kap. 4) quantifiziert Potenzial
pvlib-Parameter ungenau
Mittel
Mittel
ML-Residualkorrektur gleicht aus
GFS für NW-Deutschland ungenau
Mittel
Mittel
Ensemble-Gewichtung lernt optimal
Overfitting MOS-Schicht
Mittel
Mittel
max_depth=4, TimeSeriesSplit
Schnee-Events nicht vorhersagbar
Sicher (Winter)
Gering
Anomalie-Detektion, nicht ML-Lösung

11. Erfolgskriterien

Kriterium
Messung
Aktuell
Ziel
MAPE gesamt
Testset, temporal split
24.9%
< 20%
MAPE klare Tage
CSI > 0.8
~10% (gesch.)
< 10%
MAPE bewölkte Tage
CSI < 0.4
Hoch
< 30%
Backtesting MAPE
Reale Forecasts vs. Ertrag
109% (Jan, Schnee)
< 25%
MAE
Testset
125W
< 100W
Konfidenzintervall
80%-Intervall Kalibrierung
–
±5%
Laufzeit
Fetch + Predict
OK
< 30 Sekunden

12. Zusammenfassung
Phase 1 ist abgeschlossen und hat den MAPE von 30.1% auf 24.9% gesenkt. Die verbleibende Lücke zum Ziel (< 20%) wird primär durch den Train/Predict-Gap verursacht: Das Modell trainiert auf HOSTRADA-Messwerten, prognostiziert aber mit Open-Meteo-Vorhersagewerten.

	•	Sofort: Vorab-Validierung durchführen (Kap. 4) und Forecast-Daten-Logging starten (Phase 2a).
	•	Phase 2 (Kern): MOS-Schicht korrigiert Open-Meteo-Bias, pvlib berechnet PV-Physik für 3 Arrays, ML lernt Verschattung. Adressiert direkt den Train/Predict-Gap.
	•	Phase 3 (Feinschliff): Open-Meteo + GFS (nicht MOSMIX!) als echtes Ensemble mit Quantile Regression.

Restaufwand: 5–8 Arbeitstage. Realistisches MAPE-Ziel: 15–20%, mit < 10% an klaren Tagen.
