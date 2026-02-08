# GUI-Analyse für pvforecast

## Ausgangslage

pvforecast ist ein lokales CLI-Tool mit SQLite-Datenbank, ML-Pipeline und mehreren Wetterdatenquellen. Die GUI soll sowohl Einsteiger (einfache Bedienung, Wizard-Style) als auch Experten (Modelltuning, Dateninspektion, Logs) ansprechen. Das Zielsystem ist primär dein Mac Mini M4 – die GUI läuft lokal und muss nicht im Internet deployed werden.

## Kandidaten-Übersicht

Ich habe die relevanten Frameworks in drei Kategorien analysiert: Web-basierte Data-App-Frameworks, Desktop-GUI-Frameworks und Hybride.

### Kategorie A: Web-basierte Python-Frameworks

| Framework | Architektur | Stärke | Schwäche | GitHub ⭐ |
|-----------|-------------|--------|----------|-----------|
| Streamlit | Script-Reruns, Snowflake-Backed | Schnellster Weg zu einem Dashboard | Reruns bei jeder Interaktion, kaum Layout-Kontrolle | ~40k |
| Dash (Plotly) | Flask + React, Callbacks | Professionelle Dashboards, Enterprise-ready | Steile Lernkurve, HTML/CSS-Kenntnisse nötig | ~22k |
| NiceGUI | FastAPI + Vue/Quasar, WebSocket | Explizit für IoT/SmartHome, kein Rerun | Kleinere Community, weniger Tutorials | ~11k |
| Gradio | HuggingFace-backed | ML-Demos blitzschnell | Zu ML-demo-fokussiert, kaum Dashboard-Features | ~36k |
| Taipy | Pipeline-Engine + React | Szenario-Analyse, Production-Apps | Relativ neu, weniger Battle-tested | ~15k |
| Panel (HoloViz) | Jupyter-kompatibel | Flexibel, Notebook ↔ App | Steile Lernkurve, kleinere Community | ~5k |
| Shiny for Python | Reactive Programming | Bessere Reaktivität als Streamlit | Noch jung im Python-Ökosystem | ~2k |

### Kategorie B: Desktop-GUI-Frameworks

| Framework | Architektur | Stärke | Schwäche |
|-----------|-------------|--------|----------|
| PySide6/PyQt6 | Qt Widgets, nativer Look | Battle-tested, vollständigstes Framework | Verbose, steile Lernkurve, Lizenzthemen bei PyQt |
| Flet | Flutter-Engine, Python-API | Modernes Material-Design, Cross-Platform | Noch jung, kleine Community |
| Tkinter | Built-in, Tcl/Tk | Keine Dependencies | Veraltetes Look & Feel |

### Kategorie C: Hybride / Nische

| Framework | Ansatz | Kommentar |
|-----------|--------|-----------|
| Reflex (ex-Pynecone) | Pure Python → React/NextJS | Noch unreif, Identity-Crisis |
| PyWebView | HTML/CSS/JS in nativem Fenster | Wenn man Web-Skills hat und native App will |
| FastHTML | Von FastAPI-Autoren, kein JS | Vielversprechend aber sehr neu |

## Tiefenanalyse der Top-3 Kandidaten

Basierend auf dem pvforecast-Anforderungsprofil (lokales Tool, SQLite, ML-Pipeline, Einsteiger+Experten, Mac Mini M4) scheiden einige sofort aus: Gradio ist zu ML-Demo-fokussiert, Tkinter zu altbacken, Dash zu enterprise-lastig für ein persönliches Tool. Die drei besten Kandidaten:

### 1. NiceGUI — Der Favorit

**Warum passt es perfekt zu pvforecast?**

NiceGUI wurde buchstäblich für genau diesen Use Case gebaut: lokale Python-Apps für IoT, Smart Home, ML-Tuning und Robotik. Die Firma Zauberzeug aus Deutschland hat es entwickelt, weil ihnen Streamlit zu viel "Magie" beim State-Handling macht.

**Architektur:**
- Backend: FastAPI (Python) — dein gesamter pvforecast-Code bleibt wie er ist
- Frontend: Vue.js + Quasar (automatisch, kein JS nötig)
- Kommunikation: WebSocket (Echtzeit-Updates ohne Rerun)
- Single-Worker: Async-basiert, ein Prozess reicht

**Vorteile für pvforecast:**
- **Kein Rerun-Problem:** Anders als Streamlit wird bei einer Slider-Änderung nur der betroffene Handler aufgerufen — nicht das ganze Script. Kritisch wenn Training Minuten dauert.
- **Direkte SQLite-Integration:** "NiceGUI is designed to just work with normal Python libs including SQLAlchemy, sqlite" — du kannst deine Database-Klasse direkt nutzen.
- **Plotly/Matplotlib-Support:** `ui.plotly()`, `ui.pyplot()` für Charts
- **Data-Binding:** `ui.slider().bind_value()` — UI-Elemente direkt an Python-Variablen binden
- **Docker-ready:** Offizielles Docker-Image, perfekt für deinen Mac Mini als Server
- **Auto-Reload:** Ändere Code, Browser aktualisiert automatisch
- **Async-nativ:** Lang laufende Tasks (Training, HOSTRADA-Download) blockieren nicht die UI

**Code-Beispiel (wie pvforecast aussehen könnte):**

```python
from nicegui import ui
from pvforecast.db import Database
from pvforecast.model import load_model, predict

db = Database(config.db_path)

with ui.tabs() as tabs:
    ui.tab('Dashboard', icon='solar_power')
    ui.tab('Prognose', icon='trending_up')
    ui.tab('Training', icon='model_training')
    ui.tab('Daten', icon='database')

with ui.tab_panels(tabs):
    with ui.tab_panel('Dashboard'):
        # Heutige Prognose als Karte
        with ui.card():
            ui.label('Heutige Prognose').classes('text-h5')
            chart = ui.plotly({...})  # Plotly-Chart

        # Anlagenstatus
        with ui.card():
            pv_count = db.get_pv_count()
            ui.label(f'{pv_count:,} PV-Datensätze')

    with ui.tab_panel('Training'):
        model_type = ui.toggle(['RandomForest', 'XGBoost'])
        since_year = ui.number('Ab Jahr', value=2023)
        ui.button('Training starten', on_click=start_training)
        log = ui.log(max_lines=100)  # Live-Log-Output

ui.run(port=8080)
```

**Nachteile:**
- Kleinere Community als Streamlit (~11k vs ~40k Stars)
- Weniger fertige "Copy-Paste"-Beispiele online
- Für Charts kein eingebautes Charting wie Streamlit — man nutzt Plotly/Matplotlib explizit

**Aufwand-Schätzung:** ~2-3 Wochenenden für ein solides Dashboard

### 2. Streamlit — Der Schnellste

**Warum erwägenswert?**

Streamlit hat die mit Abstand größte Community, tausende Beispiele, und du hast in 30 Minuten ein funktionierendes Dashboard. Für einen "MVP in einem Nachmittag" unschlagbar.

**Architektur:**
- Bei jeder Interaktion wird das gesamte Script von oben nach unten neu ausgeführt
- State-Management über `st.session_state`
- Server-side Rendering, Browser zeigt nur an

**Vorteile:**
- **Extremste Einfachheit:** 10 Zeilen Code = funktionierendes Dashboard
- **Eingebaute Komponenten:** `st.line_chart()`, `st.dataframe()`, `st.metric()` — alles mit einem Aufruf
- **Riesige Community:** StackOverflow-Antworten für fast jedes Problem
- **Streamlit Components:** Erweiterbar durch Community-Widgets (z.B. streamlit-plotly-events)

**Code-Beispiel:**

```python
import streamlit as st
from pvforecast.db import Database

st.title('☀️ PV Forecast Dashboard')

# Sidebar für Einstellungen
with st.sidebar:
    model_type = st.selectbox('Modell', ['RandomForest', 'XGBoost'])
    since_year = st.slider('Daten ab', 2020, 2025, 2023)

# Hauptbereich
col1, col2, col3 = st.columns(3)
col1.metric('Heute', '12.4 kWh', '+2.1')
col2.metric('MAPE', '28.3%', '-1.8%')
col3.metric('Datensätze', '14,231')

st.line_chart(forecast_df)
```

**Nachteile für pvforecast:**
- **Script-Rerun-Problem:** Jeder Klick → Script startet neu. Ein Training-Button würde alles neu laden. Workaround: `st.session_state` + `@st.cache_data`, aber das wird bei komplexer App schnell unübersichtlich.
- **Kein echtes Event-Handling:** Du kannst nicht "bei Klick auf Punkt im Chart tue X" — Streamlit ist unidirektional.
- **Begrenzte Layout-Kontrolle:** Sidebar + Columns + Tabs, mehr geht kaum.
- **Keine Hintergrund-Tasks:** Kein nativer Weg, ein Training im Hintergrund laufen zu lassen und den Fortschritt zu zeigen.
- **Nicht für "App"-Feeling:** Streamlit fühlt sich immer wie ein Report an, nie wie eine Anwendung.

**Aufwand-Schätzung:** ~1 Wochenende für Basis-Dashboard, aber bei Experten-Features (Training-UI, Live-Logs) stößt man schnell an Grenzen.

### 3. Dash (Plotly) — Der Professionelle

**Warum erwägenswert?**

Dash ist der Enterprise-Standard für Python-Dashboards. Wenn die GUI irgendwann auch anderen E3DC-Besitzern zur Verfügung stehen soll, ist Dash die sicherste Wahl.

**Architektur:**
- Flask-basiert mit React.js-Frontend
- Callback-System: `@app.callback(Output, Input)` — explizite Reaktivität
- Plotly-Charts sind erstklassig integriert

**Vorteile:**
- **Plotly-native:** Beste Chart-Integration aller Frameworks
- **Production-ready:** Multi-User, Authentication, Caching
- **Maximale Kontrolle:** HTML-Layouts, CSS-Styling, Custom Components
- **Background Callbacks:** `@dash.callback(..., background=True)` für langlaufende Tasks

**Nachteile für pvforecast:**
- **Verbose:** Einfache Dinge brauchen viel Code (HTML-Layouting, Callback-Definitionen)
- **Web-Dev-Wissen nötig:** HTML/CSS-Grundlagen quasi Pflicht
- **Overkill:** Für ein lokales Single-User-Tool zu viel Overhead
- **Nicht "pythonisch":** `html.Div([html.H1("Title"), dcc.Graph(...)])` fühlt sich mehr nach React als nach Python an

**Aufwand-Schätzung:** ~3-4 Wochenenden, deutlich mehr Boilerplate

## Empfehlung

### 🏆 NiceGUI ist der klare Sieger für pvforecast

**Die Entscheidungsmatrix:**

| Kriterium | NiceGUI | Streamlit | Dash |
|-----------|---------|-----------|------|
| Lokales Single-User-Tool | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Integration mit bestehender Codebasis | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Einsteiger-Freundlichkeit der GUI | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Experten-Features (Training, Logs) | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Hintergrund-Tasks (Training, Download) | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| Lernkurve für Entwickler | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Community / Dokumentation | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Smart Home / Home Assistant Nähe | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Mac Mini als lokaler Server | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

**Die ausschlaggebenden Gründe:**

1. **Kein Rerun-Problem:** Ein Training dauert Minuten — Streamlit würde bei jedem UI-Klick alles neu laden. NiceGUI hat echtes Event-Handling.

2. **Async ist ein Muss:** HOSTRADA-Downloads, MOSMIX-Fetches, ML-Training — alles braucht Hintergrund-Tasks mit Fortschrittsanzeige. NiceGUI ist async-native.

3. **Du nutzt schon FastAPI-Konzepte:** NiceGUI baut auf FastAPI — wenn du eigene API-Endpoints brauchst (z.B. für Home Assistant), geht das direkt.

4. **Smart-Home-DNA:** NiceGUI kommt aus dem IoT/Robotics-Bereich. Das Paradigma (lokaler Server, Echtzeit-Updates, Hardware-Steuerung) passt exakt zu einem PV-Monitoring-Tool auf dem Mac Mini.

5. **Einsteiger vs. Experten lösbar:** Tab-Layout mit "Dashboard" (simpel) und "Experte" (Training, Modellvergleich, Rohdaten) — NiceGUI's Quasar-Components (Tabs, Expansion Panels, Stepper) machen das elegant.

## Vorgeschlagene UI-Architektur

```
pvforecast/
├── gui/
│   ├── __init__.py           # ui.run() Entry Point
│   ├── app.py                # Haupt-App: Tabs, Navigation
│   ├── pages/
│   │   ├── dashboard.py      # Tagesübersicht, aktuelle Prognose
│   │   ├── forecast.py       # Mehrtages-Prognose mit Chart
│   │   ├── history.py        # Historische Daten, Monatsvergleich
│   │   ├── training.py       # Modell trainieren/tunen (Experten)
│   │   ├── data.py           # CSV-Import, DB-Status, Datenqualität
│   │   └── settings.py       # Config-Editor, Setup-Wizard
│   └── components/
│       ├── forecast_chart.py # Plotly-Chart für Prognosen
│       ├── metric_card.py    # Kennzahl-Karte (kWh, MAPE, etc.)
│       └── weather_table.py  # Wetter-Tabelle mit Emojis
```

### Seiten-Konzept

**Einsteiger sieht:**
- **Dashboard:** "Heute werden ca. 14.2 kWh erzeugt ☀️" + Chart
- **Prognose:** Nächste 2 Tage als einfache Übersicht
- **Einstellungen:** Guided Setup wie im CLI

**Experte sieht (zusätzlich):**
- **Training:** Modelltyp, Hyperparameter, Live-Metriken, Feature Importance
- **Daten:** DB-Explorer, Lücken-Analyse, PV/Wetter-Overlap
- **Evaluation:** Backtesting-Ergebnisse, Monats-Breakdown, Skill Score

Umschaltbar über einen simplen Toggle "Einfach / Experte" in der Navigation.

## Alternativer Weg: Streamlit für schnellen Prototyp

Falls du erstmal schnell etwas Sichtbares haben willst, um das UI-Konzept zu testen, könnte Streamlit als Prototyp dienen: An einem Nachmittag ein Grundgerüst bauen, Screenshots machen, Features priorisieren — und dann die finale Version in NiceGUI implementieren.

## Abhängigkeiten

```toml
# pyproject.toml
[project.optional-dependencies]
gui = ["nicegui>=2.0", "plotly>=5.0"]
```

So bleibt die GUI optional und die CLI funktioniert weiterhin ohne UI-Dependencies.
