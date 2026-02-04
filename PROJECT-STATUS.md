# PV-Forecast – Projektstatus

> Letzte Aktualisierung: 2026-02-04 20:20

## 🎯 Aktueller Stand: MVP + Verbesserungen ✅

Das CLI-Tool funktioniert und wird aktiv verbessert.

---

## 🔄 Entwicklungs-Workflow

**⚠️ Vor jedem Commit: Architekten-Review!**

```
1. Issue auswählen
2. Branch erstellen (fix/... oder feature/...)
3. Code implementieren
4. 🏗️ ARCHITEKTEN-REVIEW (vor Commit!)
5. Tests schreiben/laufen lassen
6. Commit + Push
7. PR erstellen
8. CI abwarten
9. Merge + Cleanup
```

---

## ✅ Erledigte Issues

| # | Titel | PR |
|---|-------|-----|
| #1 | Lücken-Erkennung | #7 ✅ |
| #2 | Retry-Logic | #8 ✅ |
| #4 | Config-File (YAML) | #9 ✅ |

## 🔓 Offene Issues

| # | Titel | Prio |
|---|-------|------|
| #10 | Config-Validierung | 🔴 Hoch |
| #11 | Bulk Insert Performance | 🔴 Hoch |
| #3 | evaluate (Backtesting) | 🟡 Mittel |
| #5 | Tests vervollständigen | 🟡 Mittel |
| #6 | XGBoost | 🟢 Niedrig |
| #12 | Retry 429 + Jitter | 🟢 Niedrig |

---

## 📊 Datenstand

| Daten | Anzahl | Zeitraum |
|-------|--------|----------|
| PV-Readings | 61.354 | 2019-2025 |
| Wetter | 61.320 | 2018-2025 |

## 🤖 Modell-Performance

| Metrik | Wert |
|--------|------|
| **MAE** | 183 W |
| **MAPE** | 45.6% |

---

## 🚀 Befehle

```bash
cd ~/projects/pv-forecast && source .venv/bin/activate

pvforecast today              # Prognose heute
pvforecast predict            # morgen + übermorgen
pvforecast predict --days 3   # 3 Tage
pvforecast status             # DB-Status
pvforecast train              # Modell trainieren
pvforecast import <csv>       # E3DC CSV importieren
pvforecast config --show      # Config anzeigen
pvforecast config --init      # Config-Datei erstellen
```

---

## 📂 Struktur

```
~/.config/pvforecast/config.yaml    # Konfiguration
~/.local/share/pvforecast/data.db   # Datenbank
~/.local/share/pvforecast/model.pkl # Trainiertes Modell
```

---

## 🔗 Links

- **GitHub:** https://github.com/jarvis-schlappa/pv-forecast
- **CI:** GitHub Actions (Python 3.9-3.12)
