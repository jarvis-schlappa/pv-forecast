# pvforecast GUI Mockup

Interaktiver Prototyp für die geplante Web-GUI basierend auf NiceGUI.

📂 **[mockup.html](mockup.html)** – Lokal im Browser öffnen für interaktive Demo

---

## Screenshots

### Dashboard
Übersicht mit Tagesprognose, Wochenvergleich und Systemstatus.

![Dashboard](screenshots/dashboard.png)

### Prognose
Mehrtages-Vorhersage mit Stundenwerten und Wetterdaten.

![Prognose](screenshots/forecast.png)

### Training *(Experten-Modus)*
Modellauswahl, Hyperparameter-Tuning und Training-Logs.

![Training](screenshots/training.png)

### Evaluation *(Experten-Modus)*
Backtesting mit Skill Score und Wetter-Breakdown.

![Evaluation](screenshots/evaluate.png)

### Daten
CSV-Import, Wetterdaten-Abruf und Datenbestand-Übersicht.

![Daten](screenshots/data.png)

### Einstellungen
Anlagenkonfiguration, Wetter-Quellen und Systemcheck.

![Einstellungen](screenshots/settings.png)

---

## Features

- 🌙 **Dark Theme** mit IBM Plex Fonts
- 🔄 **Experten-Modus** Toggle (blendet Training & Evaluation ein/aus)
- 📊 **Plotly-Style Charts** (als Mockup)
- 📱 **Responsive Sidebar**

## Tech Stack (geplant)

- **Backend:** NiceGUI (FastAPI + Vue/Quasar)
- **Charts:** Plotly
- **Styling:** Quasar Components

Siehe auch: [GUI-ANALYSIS.md](../docs/GUI-ANALYSIS.md)
