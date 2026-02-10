#!/usr/bin/env python3
"""
SFV Ertragsdatenbank Scraper
Lädt regionale Durchschnittserträge für PLZ-Bereiche

Nutzung:
    python3 scrape_ertragsdatenbank.py --region 48 --year 2025
    python3 scrape_ertragsdatenbank.py --all-years  # Alle Jahre scrapen

Cron-Job (monatlich):
    0 3 5 * * cd ~/projects/pv-forecast/scripts && python3 scrape_ertragsdatenbank.py
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime
import argparse
import time
import os

# Konfiguration
DB_PATH = os.path.expanduser('~/projects/pv-forecast/data/regional_benchmarks.db')
DEFAULT_REGION = "48"  # PLZ 48: Coesfeld / Münster
BASE_URL = "https://ertragsdatenbank.de/auswertung/region.html"


def scrape_regional_data(plz_region="48", year=2025, verbose=True):
    """
    Scrapt regionale Durchschnittswerte für PLZ-Bereich
    
    Args:
        plz_region: 2-stelliger PLZ-Bereich (z.B. "48")
        year: Jahr (z.B. 2025)
        verbose: Ausgabe aktivieren
    
    Returns:
        dict mit Monatswerten oder None bei Fehler
    """
    if verbose:
        print(f"[{datetime.now():%H:%M:%S}] Scraping PLZ {plz_region}, Jahr {year}...")
    
    try:
        # Request mit User-Agent (höflich sein!)
        headers = {
            'User-Agent': 'PV-Forecast-Monitor/1.0 (Educational; +https://github.com/jarvis-schlappa)'
        }
        params = {"r": plz_region, "j": str(year), "a": "jahr"}
        
        response = requests.get(BASE_URL, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        # HTML parsen
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Tabelle finden
        table = soup.find('table', class_='table')
        if not table:
            if verbose:
                print(f"⚠️  Keine Tabelle gefunden für PLZ {plz_region}, Jahr {year}")
            return None
        
        # Zeilen durchsuchen
        rows = table.find_all('tr')
        data = {}
        num_plants = None
        
        for row in rows:
            row_text = row.get_text()
            
            # Anzahl Anlagen extrahieren
            if 'Anzahl PV-Anlagen mit Ertrag' in row_text:
                cells = row.find_all('td', class_='text-monospace')
                # Nur Jahreswert (letzter Wert ist oft leer bei laufendem Jahr)
                num_plants = [int(c.text.strip()) for c in cells if c.text.strip().isdigit()]
            
            # Regionale Durchschnittswerte extrahieren
            if 'Regionaler Durch' in row_text and 'Anlagen-Durch' not in row_text:
                cells = row.find_all('td', class_='text-monospace')
                months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                         'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
                
                for i, cell in enumerate(cells):
                    text = cell.text.strip()
                    if text and text.isdigit():
                        if i < len(months):
                            data[months[i]] = int(text)
                        else:
                            data['year_total'] = int(text)
        
        if not data:
            if verbose:
                print(f"⚠️  Keine Daten gefunden für PLZ {plz_region}, Jahr {year}")
            return None
        
        # Metadaten hinzufügen
        data['region'] = plz_region
        data['year'] = year
        data['num_plants'] = num_plants[0] if num_plants else None
        data['scraped_at'] = datetime.now().isoformat()
        
        if verbose:
            total = data.get('year_total', sum(v for k, v in data.items() if k in months))
            print(f"✅ Erfolgreich: {len([k for k in data if k in months])} Monate, "
                  f"Jahresertrag: {total} kWh/kWp, "
                  f"Anlagen: {data['num_plants'] or '?'}")
        
        return data
    
    except requests.RequestException as e:
        if verbose:
            print(f"❌ Fehler beim Abrufen: {e}")
        return None
    except Exception as e:
        if verbose:
            print(f"❌ Fehler beim Parsen: {e}")
        return None


def save_to_db(data):
    """
    Speichert Daten in SQLite-DB
    
    Args:
        data: dict mit Regionaldaten
    """
    if not data:
        return False
    
    # Sicherstellen, dass Verzeichnis existiert
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Tabelle erstellen (falls nicht vorhanden)
    c.execute('''CREATE TABLE IF NOT EXISTS benchmarks (
                    region TEXT,
                    year INTEGER,
                    month TEXT,
                    kwh_per_kwp INTEGER,
                    num_plants INTEGER,
                    scraped_at TIMESTAMP,
                    PRIMARY KEY (region, year, month)
                 )''')
    
    # Daten einfügen/aktualisieren
    months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
              'jul', 'aug', 'sep', 'oct', 'nov', 'dec', 'year_total']
    
    for month in months:
        if month in data:
            c.execute('''INSERT OR REPLACE INTO benchmarks 
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (data['region'], data['year'], month, data[month],
                       data.get('num_plants'), data['scraped_at']))
    
    conn.commit()
    conn.close()
    return True


def scrape_all_years(region=DEFAULT_REGION, start_year=2020, end_year=None):
    """
    Scrapt alle Jahre für eine Region
    
    Args:
        region: PLZ-Region
        start_year: Startjahr
        end_year: Endjahr (default: aktuelles Jahr)
    """
    if end_year is None:
        end_year = datetime.now().year
    
    print(f"\n🚀 Scraping PLZ {region}, Jahre {start_year}-{end_year}...\n")
    
    success_count = 0
    for year in range(start_year, end_year + 1):
        data = scrape_regional_data(region, year)
        if data and save_to_db(data):
            success_count += 1
        
        # Höflich sein: 1 Sekunde Pause zwischen Requests
        if year < end_year:
            time.sleep(1)
    
    print(f"\n✅ Fertig: {success_count}/{end_year - start_year + 1} Jahre erfolgreich gescrapet")


def show_latest_data(region=DEFAULT_REGION):
    """
    Zeigt die neuesten Daten aus der DB
    
    Args:
        region: PLZ-Region
    """
    if not os.path.exists(DB_PATH):
        print(f"❌ Datenbank nicht gefunden: {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Neueste Daten abrufen
    c.execute('''SELECT year, month, kwh_per_kwp, num_plants, scraped_at
                 FROM benchmarks
                 WHERE region = ? AND month != 'year_total'
                 ORDER BY year DESC, 
                          CASE month
                              WHEN 'jan' THEN 1 WHEN 'feb' THEN 2 WHEN 'mar' THEN 3
                              WHEN 'apr' THEN 4 WHEN 'may' THEN 5 WHEN 'jun' THEN 6
                              WHEN 'jul' THEN 7 WHEN 'aug' THEN 8 WHEN 'sep' THEN 9
                              WHEN 'oct' THEN 10 WHEN 'nov' THEN 11 WHEN 'dec' THEN 12
                          END DESC
                 LIMIT 13''', (region,))
    
    rows = c.fetchall()
    
    if not rows:
        print(f"❌ Keine Daten für PLZ {region} in DB")
        conn.close()
        return
    
    print(f"\n📊 Neueste Daten für PLZ {region}:\n")
    print(f"{'Jahr':<6} {'Monat':<5} {'kWh/kWp':<10} {'Anlagen':<10} {'Stand':<20}")
    print("-" * 60)
    
    for row in rows:
        year, month, kwh, plants, scraped = row
        scraped_date = datetime.fromisoformat(scraped).strftime('%Y-%m-%d')
        print(f"{year:<6} {month.upper():<5} {kwh:<10} {plants or '-':<10} {scraped_date:<20}")
    
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='SFV Ertragsdatenbank Scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  %(prog)s --region 48 --year 2025          # Aktuelles Jahr scrapen
  %(prog)s --all-years --start 2020         # Alle Jahre ab 2020
  %(prog)s --show                           # Neueste Daten anzeigen
        """
    )
    
    parser.add_argument('--region', default=DEFAULT_REGION,
                        help=f'PLZ-Region (2-stellig, default: {DEFAULT_REGION})')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Jahr (default: aktuelles Jahr)')
    parser.add_argument('--all-years', action='store_true',
                        help='Alle Jahre scrapen (siehe --start, --end)')
    parser.add_argument('--start', type=int, default=2020,
                        help='Startjahr bei --all-years (default: 2020)')
    parser.add_argument('--end', type=int, default=None,
                        help='Endjahr bei --all-years (default: aktuelles Jahr)')
    parser.add_argument('--show', action='store_true',
                        help='Neueste Daten aus DB anzeigen')
    parser.add_argument('--quiet', action='store_true',
                        help='Keine Ausgabe (nur Errors)')
    
    args = parser.parse_args()
    
    if args.show:
        show_latest_data(args.region)
    elif args.all_years:
        scrape_all_years(args.region, args.start, args.end)
    else:
        data = scrape_regional_data(args.region, args.year, verbose=not args.quiet)
        if data:
            if save_to_db(data):
                if not args.quiet:
                    print(f"💾 Daten gespeichert in: {DB_PATH}")
            else:
                print("❌ Fehler beim Speichern")
                exit(1)
        else:
            exit(1)


if __name__ == '__main__':
    main()
