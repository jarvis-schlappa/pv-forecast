# SFV Ertragsdatenbank Scraper

Automatisiertes Scraping von regionalen PV-Ertragsdaten für Benchmark-Analysen.

## Quick Start

```bash
# Aktuelles Jahr scrapen
cd ~/projects/pv-forecast/scripts
python3 scrape_ertragsdatenbank.py

# Spezifisches Jahr
python3 scrape_ertragsdatenbank.py --year 2024

# Alle Jahre ab 2020
python3 scrape_ertragsdatenbank.py --all-years --start 2020

# Neueste Daten anzeigen
python3 scrape_ertragsdatenbank.py --show
```

## Installation

Dependencies:
```bash
pip3 install --user requests beautifulsoup4
```

## Cron-Job (monatlich)

```bash
# Crontab bearbeiten
crontab -e

# Zeile hinzufügen (jeden 5. des Monats um 3:00 Uhr)
0 3 5 * * cd ~/projects/pv-forecast/scripts && python3 scrape_ertragsdatenbank.py >> ~/projects/pv-forecast/logs/scraper.log 2>&1
```

## Datenbank

Daten werden gespeichert in:
```
~/projects/pv-forecast/data/regional_benchmarks.db
```

Schema:
```sql
CREATE TABLE benchmarks (
    region TEXT,        -- PLZ-Bereich (z.B. "48")
    year INTEGER,       -- Jahr (z.B. 2025)
    month TEXT,         -- Monat (jan, feb, ..., year_total)
    kwh_per_kwp INTEGER,-- Durchschnittsertrag (kWh/kWp)
    num_plants INTEGER, -- Anzahl Anlagen
    scraped_at TIMESTAMP,
    PRIMARY KEY (region, year, month)
);
```

## Abfrage-Beispiele

```python
import sqlite3

conn = sqlite3.connect('~/projects/pv-forecast/data/regional_benchmarks.db')
c = conn.cursor()

# Jahresertrag 2025 für PLZ 48
c.execute("SELECT kwh_per_kwp FROM benchmarks WHERE region='48' AND year=2025 AND month='year_total'")
print(c.fetchone()[0])  # → 918

# Alle Monate 2025
c.execute("""
    SELECT month, kwh_per_kwp 
    FROM benchmarks 
    WHERE region='48' AND year=2025 AND month != 'year_total'
    ORDER BY CASE month
        WHEN 'jan' THEN 1 WHEN 'feb' THEN 2 WHEN 'mar' THEN 3
        WHEN 'apr' THEN 4 WHEN 'may' THEN 5 WHEN 'jun' THEN 6
        WHEN 'jul' THEN 7 WHEN 'aug' THEN 8 WHEN 'sep' THEN 9
        WHEN 'oct' THEN 10 WHEN 'nov' THEN 11 WHEN 'dec' THEN 12
    END
""")
for month, kwh in c.fetchall():
    print(f"{month.upper()}: {kwh} kWh/kWp")

conn.close()
```

## Performance-Vergleich

```python
# Eigenen Ertrag berechnen (Beispiel: Januar 2025)
own_kwh = 180  # kWh (aus FHEM)
plant_kwp = 9.92
own_kwh_per_kwp = own_kwh / plant_kwp  # → 18.1

# Regionaler Durchschnitt
regional_kwh_per_kwp = 18  # aus DB

# Performance-Ratio
performance = (own_kwh_per_kwp / regional_kwh_per_kwp) * 100
print(f"Performance: {performance:.1f}%")  # → 100.6%
```

## Respektvolle Nutzung

⚠️ **Wichtig:** Die SFV Ertragsdatenbank ist ein ehrenamtliches Projekt!

- **1 Request pro Scraping-Lauf** (nicht pro Monat!)
- **1 Sekunde Pause** zwischen Requests (bei --all-years)
- **User-Agent** gesetzt (identifiziert uns)
- **Monatlich scrapen**, nicht täglich!

## Troubleshooting

**Fehler: "No module named 'bs4'"**
```bash
pip3 install --user beautifulsoup4
```

**Fehler: "No module named 'requests'"**
```bash
pip3 install --user requests
```

**Warnung: "NotOpenSSLWarning"**
→ Harmlos, kann ignoriert werden (macOS-System-Python)

## Links

- SFV Ertragsdatenbank: https://ertragsdatenbank.de
- Dokumentation: ~/clawd/memory/ertragsdatenbank-analyse.md
