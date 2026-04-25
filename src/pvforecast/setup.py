"""Interaktiver Setup-Wizard für die Ersteinrichtung.

Führt den Benutzer durch die Konfiguration:
1. Erkennung existierender Installation
2. Standort (PLZ/Ort → Koordinaten)
3. Anlagenparameter (kWp, Name)
4. Wetterdaten-Quelle
5. Modell-Auswahl und Tuning
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pvforecast.config import Config, WeatherConfig, get_config_path
from pvforecast.geocoding import GeocodingError, geocode
from pvforecast.model import reload_xgboost


@dataclass
class SetupResult:
    """Ergebnis des Setup-Wizards.

    Attributes:
        config: Die erstellte Konfiguration
        config_path: Pfad zur gespeicherten Config-Datei
        xgboost_installed: Ob XGBoost installiert wurde
        model_type: Gewähltes Modell (rf oder xgb)
        weather_source: Gewählte Wetterdaten-Quelle
        run_tuning: Ob Tuning durchgeführt werden soll
    """

    config: Config
    config_path: Path
    xgboost_installed: bool = False
    model_type: str = "rf"
    weather_source: str = "open-meteo"
    run_tuning: bool = False
    existing_db_records: int = 0


class SetupWizard:
    """Interaktiver Setup-Wizard für pvforecast.

    Führt den Benutzer durch die Ersteinrichtung und erstellt
    eine Config-Datei mit allen notwendigen Parametern.

    Features:
    - Erkennung existierender Installation (Config, DB, Modell)
    - Hilfetexte für alle Parameter
    - Modell-Auswahl mit Vor-/Nachteilen
    - Wetterdaten-Quelle Auswahl
    - Optionales Tuning
    """

    def __init__(self, output_func=print, input_func=input):
        """Initialisiert den Wizard.

        Args:
            output_func: Funktion für Ausgaben (default: print)
            input_func: Funktion für Eingaben (default: input)
        """
        self.output = output_func
        self.input = input_func
        self._existing_db_records = 0
        self._existing_config = None
        self._run_training_after_import = False
        self._training_completed = False
        self._latitude: float | None = None
        self._longitude: float | None = None
        self._existing_weather_records = 0

    def run_interactive(self) -> SetupResult:
        """Führt den interaktiven Setup-Wizard aus.

        Returns:
            SetupResult mit Config und Status
        """
        self._print_header()

        # 0. Existierende Installation prüfen
        self._check_existing_installation()

        # 1. Standort
        latitude, longitude, location_name = self._prompt_location()

        # 2. Anlage
        peak_kwp, system_name = self._prompt_system(location_name)

        # 3. Wetterdaten-Quellen
        forecast_source, historical_source, hostrada_local_dir = self._prompt_weather_source()

        # 4. Modell-Auswahl
        model_type, xgboost_installed = self._prompt_model()

        # 5. Tuning
        run_tuning = self._prompt_tuning(model_type)

        # Config erstellen
        from pvforecast.config import HOSTRADAConfig

        hostrada_config = HOSTRADAConfig(local_dir=hostrada_local_dir)
        weather_config = WeatherConfig(
            forecast_provider=forecast_source,
            historical_provider=historical_source,
            hostrada=hostrada_config,
        )

        config = Config(
            latitude=latitude,
            longitude=longitude,
            peak_kwp=peak_kwp,
            system_name=system_name,
            weather=weather_config,
        )

        # Config speichern
        config_path = get_config_path()
        config.save(config_path)

        # 6. Daten importieren
        imported_count = self._prompt_import(config)

        # Issue #149: Training nach Import durchführen wenn gewünscht
        if self._run_training_after_import:
            self._execute_training(model_type, config)

        self._print_success(config_path, model_type, run_tuning, imported_count)

        return SetupResult(
            config=config,
            config_path=config_path,
            xgboost_installed=xgboost_installed,
            model_type=model_type,
            weather_source=forecast_source,
            run_tuning=run_tuning,
            existing_db_records=self._existing_db_records,
        )

    def _print_header(self) -> None:
        """Gibt den Header aus."""
        self.output("")
        self.output("🔆 PV-Forecast Ersteinrichtung")
        self.output("═" * 50)
        self.output("")

    def _check_existing_installation(self) -> None:
        """Prüft auf existierende Installation und informiert den Benutzer."""
        from pvforecast.config import _default_db_path, _default_model_path

        config_path = get_config_path()
        db_path = _default_db_path()
        model_path = _default_model_path()

        found_items = []

        # Config prüfen
        if config_path.exists():
            try:
                self._existing_config = Config.load(config_path)
                found_items.append(f"Config: {self._existing_config.system_name}")
            except Exception:
                found_items.append("Config: vorhanden (nicht lesbar)")

        # DB prüfen
        if db_path.exists():
            try:
                from pvforecast.db import Database

                db = Database(db_path)
                self._existing_db_records = db.get_pv_count()
                self._existing_weather_records = db.get_weather_count()
                db_info = (
                    f"{self._existing_db_records:,} PV + {self._existing_weather_records:,} Wetter"
                )
                found_items.append(f"Datenbank: {db_info}")
            except Exception:
                found_items.append("Datenbank: vorhanden")

        # Modell prüfen
        if model_path.exists():
            try:
                from pvforecast.model import load_model

                model_data = load_model(model_path)
                mtype, mape = model_data.model_type, model_data.mape
                found_items.append(f"Modell: {mtype}, ~{mape:.0f}% Abweichung")
            except Exception:
                found_items.append("Modell: vorhanden")

        if found_items:
            self.output("ℹ️  Existierende Installation gefunden:")
            for item in found_items:
                self.output(f"   • {item}")
            self.output("")
            self.output("   Die Daten bleiben erhalten. Nur die Config wird aktualisiert.")
            self.output("")

    def _prompt_location(self) -> tuple[float, float, str]:
        """Fragt nach dem Standort."""
        self.output("1️⃣  Standort")
        self.output("")
        self.output("   ℹ️  Der Standort wird für die Wettervorhersage benötigt.")
        self.output("      Gib deine Postleitzahl oder deinen Ort ein.")
        self.output("")

        # Vorschlag aus existierender Config
        default_hint = ""
        if self._existing_config:
            lat, lon = self._existing_config.latitude, self._existing_config.longitude
            default_hint = f" [{lat:.2f}, {lon:.2f}]"

        while True:
            query = self.input(f"   Postleitzahl oder Ort{default_hint}: ").strip()

            # Enter bei existierender Config = übernehmen
            if not query and self._existing_config:
                self.output("   ✓ Übernehme existierenden Standort")
                self.output("")
                self._latitude = self._existing_config.latitude
                self._longitude = self._existing_config.longitude
                return (
                    self._latitude,
                    self._longitude,
                    self._existing_config.system_name.replace(" PV", ""),
                )

            if not query:
                self.output("   ⚠️  Bitte einen Ort oder PLZ eingeben.")
                continue

            self.output("   Suche...")

            try:
                result = geocode(query)

                if result is None:
                    self.output(f"   ❌ Keine Ergebnisse für '{query}'")
                    self.output("   Versuche eine andere Eingabe (z.B. '44787' oder 'Bochum')")
                    self.output("")
                    continue

                self.output(
                    f"   → {result.short_name()} "
                    f"({result.latitude:.2f}°N, {result.longitude:.2f}°E)"
                )

                confirm = self.input("   Stimmt das? [J/n]: ").strip().lower()
                if confirm in ("", "j", "ja", "y", "yes"):
                    self.output("   ✓")
                    self.output("")
                    self._latitude = result.latitude
                    self._longitude = result.longitude
                    return result.latitude, result.longitude, result.short_name()
                else:
                    self.output("   OK, versuche es erneut.")
                    self.output("")

            except GeocodingError as e:
                self.output(f"   ⚠️  Geocoding-Fehler: {e}")
                self.output("")

                if self._prompt_manual_location_fallback():
                    return self._prompt_manual_location()
                # User declined manual entry, continue loop to retry

    def _prompt_manual_location_fallback(self) -> bool:
        """Fragt ob manuelle Eingabe gewünscht ist."""
        response = self.input("   Koordinaten manuell eingeben? [j/N]: ").strip().lower()
        return response in ("j", "ja", "y", "yes")

    def _prompt_manual_location(self) -> tuple[float, float, str]:
        """Manuelle Koordinaten-Eingabe."""
        self.output("")
        self.output("   Manuelle Eingabe:")
        self.output("   ℹ️  Koordinaten findest du z.B. auf Google Maps (Rechtsklick → Koordinaten)")
        self.output("")

        while True:
            try:
                lat_str = self.input("   Breitengrad (z.B. 51.48): ").strip()
                latitude = float(lat_str)

                if not -90 <= latitude <= 90:
                    self.output("   ⚠️  Breitengrad muss zwischen -90 und 90 liegen.")
                    continue

                lon_str = self.input("   Längengrad (z.B. 7.22): ").strip()
                longitude = float(lon_str)

                if not -180 <= longitude <= 180:
                    self.output("   ⚠️  Längengrad muss zwischen -180 und 180 liegen.")
                    continue

                name = self.input("   Ortsname (optional): ").strip() or "Mein Standort"

                self.output("   ✓")
                self.output("")
                self._latitude = latitude
                self._longitude = longitude
                return latitude, longitude, name

            except ValueError:
                self.output("   ⚠️  Bitte eine gültige Zahl eingeben.")

    def _prompt_system(self, default_name: str) -> tuple[float, str]:
        """Fragt nach den Anlagenparametern."""
        self.output("2️⃣  PV-Anlage")
        self.output("")
        self.output("   ℹ️  Die Peakleistung (kWp) findest du:")
        self.output("      • Auf dem Typenschild deines Wechselrichters")
        self.output("      • Im Anlagenpass oder Kaufvertrag")
        self.output("      • Typische Werte: 5-15 kWp für Einfamilienhäuser")
        self.output("")

        # Default aus existierender Config
        default_kwp = ""
        if self._existing_config:
            default_kwp = f" [{self._existing_config.peak_kwp}]"

        while True:
            try:
                kwp_str = self.input(f"   Peakleistung in kWp{default_kwp}: ").strip()

                # Enter bei existierender Config = übernehmen
                if not kwp_str and self._existing_config:
                    peak_kwp = self._existing_config.peak_kwp
                else:
                    peak_kwp = float(kwp_str)

                if peak_kwp <= 0:
                    self.output("   ⚠️  Leistung muss größer als 0 sein.")
                    continue

                if peak_kwp > 100:
                    self.output(f"   ⚠️  {peak_kwp} kWp ist ungewöhnlich hoch für eine Hausanlage.")
                    confirm = self.input("   Stimmt der Wert? [j/N]: ").strip().lower()
                    if confirm not in ("j", "ja", "y", "yes"):
                        continue

                break

            except ValueError:
                self.output("   ⚠️  Bitte eine gültige Zahl eingeben (z.B. 9.92).")

        # Anlagenname
        default_system_name = f"{default_name} PV" if default_name else "Meine PV-Anlage"
        if self._existing_config:
            default_system_name = self._existing_config.system_name

        name = self.input(f"   Name (optional) [{default_system_name}]: ").strip()
        system_name = name if name else default_system_name

        self.output("   ✓")
        self.output("")

        return peak_kwp, system_name

    def _prompt_weather_source(self) -> tuple[str, str]:
        """Fragt nach der Wetterdaten-Quelle.

        Returns:
            Tuple (forecast_source, historical_source)
        """
        self.output("3️⃣  Wetterdaten-Quellen")
        self.output("")

        # Forecast-Quelle
        self.output("   A) Vorhersagen (für Prognosen)")
        self.output("")
        self.output("   [1] Open-Meteo (Standard)")
        self.output("       ✓ Kostenlos, weltweit verfügbar")
        self.output("")
        self.output("   [2] DWD MOSMIX (Deutschland)")
        self.output("       ✓ Offizielle DWD-Daten, oft genauer")
        self.output("")

        while True:
            choice = self.input("   Auswahl [1]: ").strip()
            if choice in ("", "1"):
                forecast_source = "open-meteo"
                self.output("   ✓ Open-Meteo für Vorhersagen")
                break
            elif choice == "2":
                forecast_source = "mosmix"
                self.output("   ✓ MOSMIX für Vorhersagen")
                break
            else:
                self.output("   ⚠️  Bitte 1 oder 2 eingeben.")

        self.output("")

        # Historical-Quelle
        self.output("   B) Historische Daten (für Training)")
        self.output("")
        self.output("   [1] Open-Meteo (Standard)")
        self.output("       ✓ Schnell, keine großen Downloads")
        self.output("       ○ Typische Abweichung: ~30%")
        self.output("")
        self.output("   [2] DWD HOSTRADA (Deutschland, empfohlen)")
        self.output("       ✓ Typische Abweichung: nur ~22%")
        self.output("       ⚠ Download: ~750 MB/Monat (5 Jahre ≈ 45 GB)")
        self.output("       ✓ Speicher: nur wenige MB (Stream-Processing)")
        self.output("       ⏱ Dauer: ~30 Min bei 50 Mbit/s (5 Jahre)")
        self.output("       → Einmalig, lohnt sich für bessere Prognosen!")
        self.output("")

        while True:
            choice = self.input("   Auswahl [1]: ").strip()
            if choice in ("", "1"):
                historical_source = "open-meteo"
                self.output("   ✓ Open-Meteo für Training")
                break
            elif choice == "2":
                historical_source = "hostrada"
                self.output("   ✓ HOSTRADA für Training (bessere Genauigkeit)")
                break
            else:
                self.output("   ⚠️  Bitte 1 oder 2 eingeben.")

        self.output("")

        # Bei HOSTRADA: Nach lokalem Verzeichnis fragen
        hostrada_local_dir = None
        if historical_source == "hostrada":
            hostrada_local_dir = self._prompt_hostrada_path()

        return forecast_source, historical_source, hostrada_local_dir

    def _prompt_hostrada_path(self) -> str | None:
        """Fragt nach lokalem HOSTRADA-Verzeichnis."""
        self.output("   Hast du bereits HOSTRADA-Dateien heruntergeladen?")
        self.output("   (NetCDF-Dateien von einem früheren Download)")
        self.output("")

        response = self.input("   Lokales Verzeichnis angeben? [j/N]: ").strip().lower()

        if response not in ("j", "ja", "y", "yes"):
            self.output("   → Dateien werden bei Bedarf heruntergeladen")
            self.output("")
            return None

        self.output("")
        self.output("   💡 Standard auf diesem Mac: /Users/Shared/hostrada")
        self.output("")

        while True:
            path_str = self.input("   Pfad [/Users/Shared/hostrada]: ").strip()

            if not path_str:
                path_str = "/Users/Shared/hostrada"

            # Expandiere ~
            path_str = path_str.strip("'\"")
            local_path = Path(path_str).expanduser()

            if not local_path.exists():
                self.output(f"   ⚠️  Verzeichnis existiert nicht: {local_path}")
                create = self.input("   Erstellen? [j/N]: ").strip().lower()
                if create in ("j", "ja", "y", "yes"):
                    try:
                        local_path.mkdir(parents=True, exist_ok=True)
                        self.output(f"   ✓ Erstellt: {local_path}")
                    except Exception as e:
                        self.output(f"   ❌ Fehler: {e}")
                        continue
                else:
                    continue

            # Prüfe ob NetCDF-Dateien vorhanden
            nc_files = list(local_path.glob("*.nc"))
            if nc_files:
                self.output(f"   ✓ {len(nc_files)} NetCDF-Dateien gefunden")

                # Issue #155: Anbieten, die Dateien sofort zu laden
                if self._latitude is not None and self._longitude is not None:
                    self.output("")
                    response = self.input(
                        "   Wetterdaten jetzt in Datenbank laden? [J/n]: "
                    ).strip().lower()
                    if response not in ("n", "nein", "no"):
                        loaded = self._load_hostrada_to_db(str(local_path))
                        if loaded > 0:
                            self._existing_weather_records = loaded
            else:
                self.output("   ℹ️  Noch keine Dateien vorhanden (werden bei Bedarf geladen)")

            self.output("")
            return str(local_path)

    def _load_hostrada_to_db(self, local_dir: str) -> int:
        """Lädt HOSTRADA-Daten aus lokalem Verzeichnis in die Datenbank.

        Args:
            local_dir: Pfad zum Verzeichnis mit NetCDF-Dateien

        Returns:
            Anzahl geladener Datensätze
        """
        from datetime import date, timedelta

        from pvforecast.config import _default_db_path
        from pvforecast.db import Database
        from pvforecast.sources.hostrada import HOSTRADASource

        self.output("")
        self.output("   Lade Wetterdaten...")

        # Fortschrittsanzeige als Closure
        last_month_shown = [0, 0]  # [year, month] - mutable für Closure

        def progress_callback(current: int, total: int, year: int, month: int):
            """Callback für Fortschrittsanzeige."""
            pct = (current * 100) // total
            bar_len = 20
            filled = (current * bar_len) // total
            bar = "█" * filled + "░" * (bar_len - filled)

            # Zeige Monat nur wenn er sich ändert
            month_str = ""
            if (year, month) != tuple(last_month_shown):
                month_str = f" → {year}-{month:02d}"
                last_month_shown[0], last_month_shown[1] = year, month

            # \r für Überschreiben der Zeile
            import sys

            sys.stdout.write(f"\r   [{bar}] {pct:3d}% ({current}/{total}){month_str}    ")
            sys.stdout.flush()

        try:
            # HOSTRADA Source initialisieren mit Progress-Callback
            source = HOSTRADASource(
                latitude=self._latitude,
                longitude=self._longitude,
                local_dir=local_dir,
                show_progress=False,
                progress_callback=progress_callback,
            )

            # Verfügbaren Datumsbereich ermitteln
            local_path = Path(local_dir)
            nc_files = sorted(local_path.glob("*.nc"))

            if not nc_files:
                self.output("   ⚠️  Keine NetCDF-Dateien gefunden")
                return 0

            # Extrahiere Jahreszahlen aus Dateinamen
            # Format: *_gn_YYYYMMDDHH-YYYYMMDDHH.nc
            import re

            years_months = set()
            # HOSTRADA-Pattern: *_gn_YYYYMMDDHH-YYYYMMDDHH.nc
            hostrada_pattern = r"_gn_(\d{4})(\d{2})\d{2}\d{2}-(\d{4})(\d{2})\d{2}\d{2}\.nc$"
            for f in nc_files:
                match = re.search(hostrada_pattern, f.name)
                if match:
                    start_year, start_month = int(match.group(1)), int(match.group(2))
                    end_year, end_month = int(match.group(3)), int(match.group(4))
                    # Validierung
                    if 1 <= start_month <= 12 and 1995 <= start_year <= 2100:
                        years_months.add((start_year, start_month))
                    if 1 <= end_month <= 12 and 1995 <= end_year <= 2100:
                        years_months.add((end_year, end_month))

            if not years_months:
                self.output("   ⚠️  Konnte Datumsbereich nicht ermitteln")
                return 0

            sorted_ym = sorted(years_months)
            first_year, first_month = sorted_ym[0]
            last_year, last_month = sorted_ym[-1]

            start_date = date(first_year, first_month, 1)
            # Letzter Tag des letzten Monats
            if last_month == 12:
                end_date = date(last_year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(last_year, last_month + 1, 1) - timedelta(days=1)

            self.output(f"   Zeitraum: {start_date} bis {end_date}")

            # Daten laden mit Fortschrittsanzeige
            weather_df = source.fetch_historical(start_date, end_date)

            # Neue Zeile nach Fortschrittsbalken
            import sys

            sys.stdout.write("\n")
            sys.stdout.flush()

            if len(weather_df) == 0:
                self.output("   ⚠️  Keine Wetterdaten geladen")
                return 0

            # In DB speichern (nutze bestehende Funktion)
            from pvforecast.weather import save_weather_to_db

            db_path = _default_db_path()
            db = Database(db_path)
            loaded = save_weather_to_db(weather_df, db)

            self.output(f"   ✓ {loaded:,} Wetterdatensätze geladen")
            return loaded

        except Exception as e:
            self.output(f"   ❌ Fehler beim Laden: {e}")
            return 0

    def _fetch_weather_for_training(self, config: Config) -> int:
        """Lädt Wetterdaten für das Training.

        Wird aufgerufen wenn vor dem Training keine Wetterdaten vorhanden sind.

        Args:
            config: Die aktuelle Konfiguration

        Returns:
            Anzahl geladener Datensätze
        """
        from datetime import date, timedelta

        from pvforecast.db import Database
        from pvforecast.weather import fetch_historical, save_weather_to_db

        response = self.input("   Wetterdaten jetzt laden? [J/n]: ").strip().lower()
        if response in ("n", "nein", "no"):
            return 0

        self.output("")
        self.output("   Lade Wetterdaten von Open-Meteo...")

        try:
            db = Database(config.db_path)

            # Lade PV-Daten Zeitraum um passende Wetterdaten zu ermitteln
            pv_range = db.get_pv_date_range()
            if pv_range is None:
                self.output("   ⚠️  Keine PV-Daten vorhanden")
                return 0

            start_ts, end_ts = pv_range
            start_date = date.fromtimestamp(start_ts)
            end_date = date.fromtimestamp(end_ts)

            self.output(f"   Zeitraum: {start_date} bis {end_date}")

            # Wetterdaten laden (in Chunks von max 1 Jahr)
            total_loaded = 0
            current = start_date
            max_chunk_days = 365

            while current <= end_date:
                chunk_end = min(current + timedelta(days=max_chunk_days), end_date)
                self.output(f"   → Lade {current} bis {chunk_end}...")

                try:
                    weather_df = fetch_historical(
                        lat=config.latitude,
                        lon=config.longitude,
                        start=current,
                        end=chunk_end,
                    )
                    loaded = save_weather_to_db(weather_df, db)
                    total_loaded += loaded
                except Exception as e:
                    self.output(f"   ⚠️  Fehler: {e}")

                current = chunk_end + timedelta(days=1)

            if total_loaded > 0:
                self.output(f"   ✓ {total_loaded:,} Wetterdatensätze geladen")
                self._existing_weather_records = total_loaded

            return total_loaded

        except Exception as e:
            self.output(f"   ❌ Fehler beim Laden: {e}")
            return 0

    def _prompt_model(self) -> tuple[str, bool]:
        """Fragt nach dem Prognose-Modell.

        Returns:
            Tuple (model_type, xgboost_installed)
        """
        self.output("4️⃣  Prognose-Modell")
        self.output("")
        self.output("   Welches ML-Modell soll verwendet werden?")
        self.output("")
        self.output("   [1] RandomForest (Standard)")
        self.output("       ✓ Keine zusätzliche Installation nötig")
        self.output("       ✓ Schnelles Training")
        self.output("       ○ Typische Abweichung: ~30%")
        self.output("")
        self.output("   [2] XGBoost (Empfohlen)")
        self.output("       ✓ Typische Abweichung: nur ~22%")
        self.output("       ✓ State-of-the-Art für Zeitreihen")
        self.output("       ○ Benötigt zusätzliche Installation (~50 MB)")
        self.output("")

        # Prüfe ob XGBoost bereits installiert
        xgboost_available = False
        try:
            import xgboost  # noqa: F401

            xgboost_available = True
            self.output("   ℹ️  XGBoost ist bereits installiert")
            self.output("")
        except ImportError:
            pass

        while True:
            default = "2" if xgboost_available else "1"
            choice = self.input(f"   Auswahl [{default}]: ").strip()

            if not choice:
                choice = default

            if choice == "1":
                self.output("   ✓ RandomForest")
                self.output("")
                return "rf", xgboost_available
            elif choice == "2":
                if xgboost_available:
                    self.output("   ✓ XGBoost")
                    self.output("")
                    return "xgb", True
                else:
                    # XGBoost installieren
                    xgboost_installed = self._install_xgboost()
                    if xgboost_installed:
                        return "xgb", True
                    else:
                        self.output("   → Fallback auf RandomForest")
                        return "rf", False
            else:
                self.output("   ⚠️  Bitte 1 oder 2 eingeben.")

    def _check_libomp_macos(self) -> bool:
        """Prüft ob libomp auf macOS installiert ist und bietet Installation an.

        Returns:
            True wenn libomp verfügbar oder installiert wurde, False sonst.
        """
        if sys.platform != "darwin":
            return True

        # Prüfe beide möglichen Pfade (Apple Silicon und Intel)
        libomp_paths = [
            Path("/opt/homebrew/lib/libomp.dylib"),  # Apple Silicon
            Path("/usr/local/lib/libomp.dylib"),  # Intel
        ]

        if any(p.exists() for p in libomp_paths):
            return True

        self.output("")
        self.output("   ⚠️  XGBoost benötigt libomp (OpenMP)")
        self.output("")

        # Prüfe ob Homebrew verfügbar
        try:
            subprocess.run(
                ["brew", "--version"],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.output("   ❌ Homebrew nicht gefunden.")
            self.output("   💡 Installiere libomp manuell:")
            self.output("      brew install libomp")
            self.output("")
            return False

        response = self.input("   Mit Homebrew installieren? [J/n]: ").strip().lower()
        if response in ("n", "nein", "no"):
            self.output("   → libomp nicht installiert")
            self.output("")
            return False

        self.output("   Installiere libomp...")
        try:
            subprocess.run(
                ["brew", "install", "libomp"],
                check=True,
                capture_output=True,
            )
            self.output("   ✓ libomp installiert")
            return True
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr[:100] if e.stderr else "Unbekannter Fehler"
            self.output(f"   ❌ Installation fehlgeschlagen: {error_msg}")
            return False

    def _install_xgboost(self) -> bool:
        """Installiert XGBoost."""
        # Issue #151: libomp-Check auf macOS vor XGBoost
        if not self._check_libomp_macos():
            self.output("   → XGBoost-Installation übersprungen (libomp fehlt)")
            self.output("")
            return False

        self.output("")
        self.output("   Installiere XGBoost...")

        try:
            # Use version constraint from pyproject.toml
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "xgboost>=2.0"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.output("   ✓ XGBoost installiert")

            # Wichtig: XGBoost im laufenden Prozess verfügbar machen
            # Der normale Import-Cache verhindert sonst, dass das neu
            # installierte Paket erkannt wird
            if not reload_xgboost():
                self.output("   ⚠️  XGBoost installiert, aber Import fehlgeschlagen")
                self.output("   💡 Starte pvforecast neu für Training")
                self.output("")
                return False

            self.output("")
            return True

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr[:200] if e.stderr else "Unbekannter Fehler"
            self.output(f"   ⚠️  Installation fehlgeschlagen: {error_msg}")
            self.output("")

            if sys.platform == "darwin":
                self.output("   💡 Auf macOS benötigt XGBoost eventuell libomp:")
                self.output("      brew install libomp")
                self.output("")

            return False

    def _install_optuna(self) -> bool:
        """Installiert Optuna für besseres Hyperparameter-Tuning.

        Returns:
            True wenn Optuna installiert wurde, False sonst.
        """
        self.output("")
        self.output("   Installiere Optuna...")

        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "optuna>=3.0"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.output("   ✓ Optuna installiert")
            return True
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr[:100] if e.stderr else "Unbekannter Fehler"
            self.output(f"   ⚠️  Installation fehlgeschlagen: {error_msg}")
            return False

    def _prompt_tuning(self, model_type: str) -> bool:
        """Fragt ob Hyperparameter-Tuning durchgeführt werden soll."""
        # Nur fragen wenn genug Daten vorhanden
        if self._existing_db_records < 1000:
            return False

        self.output("5️⃣  Hyperparameter-Tuning")
        self.output("")
        self.output("   ℹ️  Tuning optimiert das Modell für deine Anlage.")
        self.output("      Das verbessert die Genauigkeit um ~5-10%.")
        self.output("")
        self.output(f"      Du hast {self._existing_db_records:,} Datensätze - genug für Tuning!")
        self.output("")
        self.output("   Optionen:")
        self.output("   [1] Kein Tuning (schnell, Standard-Parameter)")
        self.output("   [2] Schnelles Tuning (~2 Min, 20 Versuche)")
        self.output("   [3] Gründliches Tuning (~10 Min, 100 Versuche)")
        self.output("")

        # Prüfe ob Optuna verfügbar
        optuna_available = False
        try:
            import optuna  # noqa: F401

            optuna_available = True
        except ImportError:
            pass

        if optuna_available:
            self.output("   ℹ️  Optuna ist installiert - Bayesian Optimization verfügbar")
        else:
            self.output("   ℹ️  Für besseres Tuning: pip install optuna")
        self.output("")

        while True:
            choice = self.input("   Auswahl [1]: ").strip()

            if choice in ("", "1"):
                self.output("   ✓ Kein Tuning")
                self.output("")
                return False
            elif choice in ("2", "3"):
                # Issue #152: Optuna bei Tuning-Auswahl installieren
                if not optuna_available:
                    self.output("")
                    self.output("   ℹ️  Optuna ermöglicht besseres Tuning (Bayesian Optimization)")
                    response = self.input("   Optuna installieren? [J/n]: ").strip().lower()
                    if response not in ("n", "nein", "no"):
                        if self._install_optuna():
                            optuna_available = True
                    self.output("")

                self.output("   ✓ Tuning wird nach dem Training durchgeführt")
                self.output("")
                # Speichere Tuning-Einstellung für später
                self._tuning_trials = 20 if choice == "2" else 100
                return True
            else:
                self.output("   ⚠️  Bitte 1, 2 oder 3 eingeben.")

    def _prompt_import(self, config: Config) -> int:
        """Fragt nach CSV-Dateien zum Importieren.

        Returns:
            Anzahl importierter Datensätze
        """
        # Überspringe wenn schon Daten vorhanden
        if self._existing_db_records > 0:
            return 0

        self.output("6️⃣  Daten importieren")
        self.output("")
        self.output("   ℹ️  Unterstützte Formate:")
        self.output("      • E3DC Portal Export (CSV)")
        self.output("      • CSV mit Spalten: Zeitstempel, PV-Leistung")
        self.output("")

        response = self.input("   Hast du CSV-Dateien zum Importieren? [j/N]: ").strip().lower()

        if response not in ("j", "ja", "y", "yes"):
            self.output("   → Übersprungen")
            self.output("")
            return 0

        self.output("")
        self.output("   Gib den Pfad ein (Ordner oder Datei):")
        self.output("   💡 Tipp: Ziehe den Ordner ins Terminal für den Pfad")
        self.output("")

        while True:
            path_str = self.input("   Pfad: ").strip()

            if not path_str:
                self.output("   → Übersprungen")
                self.output("")
                return 0

            # Entferne Anführungszeichen (von Drag&Drop)
            path_str = path_str.strip("'\"")

            # Expandiere ~ und Wildcards
            import glob as glob_module

            expanded_path = str(Path(path_str).expanduser())

            # Prüfe ob Wildcards vorhanden
            if "*" in expanded_path or "?" in expanded_path:
                # Glob-Expansion für Wildcards
                matched_paths = glob_module.glob(expanded_path)
                if not matched_paths:
                    self.output(f"   ⚠️  Keine Dateien gefunden für: {path_str}")
                    continue
                files = [Path(p) for p in matched_paths if p.endswith((".csv", ".CSV"))]
                if not files:
                    self.output(f"   ⚠️  Keine CSV-Dateien gefunden für: {path_str}")
                    continue
            else:
                import_path = Path(expanded_path)
                if not import_path.exists():
                    self.output(f"   ⚠️  Pfad existiert nicht: {import_path}")
                    continue

                if import_path.is_file():
                    files = [import_path]
                else:
                    files = list(import_path.glob("*.csv")) + list(import_path.glob("*.CSV"))

            # Import durchführen
            try:
                from pvforecast.data_loader import import_csv_files
                from pvforecast.db import Database

                db = Database(config.db_path)

                if not files:
                    self.output(f"   ⚠️  Keine CSV-Dateien gefunden in: {import_path}")
                    continue

                self.output(f"   Importiere {len(files)} Datei(en)...")

                total_imported = 0
                for csv_file in files:
                    try:
                        count = import_csv_files([csv_file], db)
                        total_imported += count
                    except Exception as e:
                        self.output(f"   ⚠️  {csv_file.name}: {e}")

                if total_imported > 0:
                    self.output(f"   ✓ {total_imported:,} Datensätze importiert")
                    self._existing_db_records = total_imported

                    # Issue #149: Training nach Import anbieten
                    self.output("")
                    response = self.input("   Jetzt Modell trainieren? [J/n]: ").strip().lower()
                    if response not in ("n", "nein", "no"):
                        self._run_training_after_import = True
                    else:
                        self._run_training_after_import = False
                else:
                    self.output("   ⚠️  Keine neuen Datensätze (evtl. Duplikate)")

                self.output("")
                return total_imported

            except Exception as e:
                self.output(f"   ❌ Import fehlgeschlagen: {e}")
                self.output("")
                return 0

    def _execute_training(self, model_type: str, config: Config) -> bool:
        """Führt das Training nach dem Import durch.

        Args:
            model_type: Modelltyp (rf oder xgb)
            config: Die aktuelle Konfiguration

        Returns:
            True wenn Training erfolgreich, False sonst.
        """
        self.output("")
        self.output("🔄 Training wird gestartet...")
        self.output("")

        try:
            from pvforecast.config import _default_model_path
            from pvforecast.db import Database
            from pvforecast.model import save_model, train

            db = Database(config.db_path)
            model_path = _default_model_path()

            # Issue #156: Vor Training prüfen ob Wetterdaten vorhanden sind
            weather_count = db.get_weather_count()
            if weather_count == 0:
                self.output("   ⚠️  Keine Wetterdaten vorhanden!")
                self.output("   Training benötigt historische Wetterdaten.")
                self.output("")

                # Anbieten Wetterdaten zu laden
                loaded = self._fetch_weather_for_training(config)
                if loaded == 0:
                    self.output("   ❌ Training abgebrochen (keine Wetterdaten)")
                    self.output("")
                    self._training_completed = False
                    return False

            # Prüfe ob gewähltes Modell verfügbar ist
            if model_type == "xgb":
                try:
                    import xgboost  # noqa: F401
                except ImportError:
                    self.output("   ⚠️  XGBoost ist nicht installiert!")
                    self.output("")
                    response = self.input("   Jetzt installieren? [J/n]: ").strip().lower()
                    if response not in ("n", "nein", "no"):
                        if self._install_xgboost():
                            self.output("")
                        else:
                            self.output("   → Fallback auf RandomForest")
                            self.output("")
                            model_type = "rf"
                    else:
                        self.output("   → Fallback auf RandomForest")
                        self.output("")
                        model_type = "rf"

            # Training durchführen
            model, metrics = train(
                db=db,
                lat=config.latitude,
                lon=config.longitude,
                model_type=model_type,
                peak_kwp=config.peak_kwp,
            )

            # Modell speichern
            save_model(model, model_path, metrics)

            # MAPE ist bereits in Prozent (z.B. 22.4 für 22.4%)
            mape = metrics.get("mape", 0) if metrics else 0
            self.output(f"   ✓ Modell trainiert: {model_type}")
            self.output(f"   ✓ Genauigkeit: ~{mape:.0f}% Abweichung (MAPE)")
            self.output("")
            self._training_completed = True
            return True

        except Exception as e:
            self.output(f"   ❌ Training fehlgeschlagen: {e}")
            self.output("")
            self._training_completed = False
            return False

    def _show_test_forecast(self, config: Config) -> None:
        """Zeigt eine Test-Prognose am Ende des Setups.

        Args:
            config: Die aktuelle Konfiguration
        """
        try:
            from datetime import datetime

            from pvforecast.config import _default_model_path
            from pvforecast.model import load_model, predict
            from pvforecast.weather import fetch_forecast

            model_path = _default_model_path()
            if not model_path.exists():
                return

            self.output("")
            self.output("🎉 Test-Prognose für heute:")
            self.output("")

            # Wetterdaten holen
            weather_df = fetch_forecast(
                latitude=config.latitude,
                longitude=config.longitude,
                provider=config.weather.forecast_provider,
            )

            # Modell laden
            model, metrics = load_model(model_path)

            # Prognose erstellen
            predictions_df = predict(
                model=model,
                weather_df=weather_df,
                peak_kwp=config.peak_kwp,
            )

            # Nur Tageslicht-Stunden zeigen (9-17 Uhr, max 5 Zeilen)
            now = datetime.now()
            today_mask = predictions_df.index.date == now.date()
            hour_mask = (predictions_df.index.hour >= 9) & (predictions_df.index.hour <= 17)
            day_predictions = predictions_df[today_mask & hour_mask]

            if day_predictions.empty:
                self.output("   (Keine Prognose für heute verfügbar)")
                return

            self.output("    Zeit    Ertrag  Wetter")
            self.output("   ─────────────────────────")

            # Zeige max 5 Stunden
            for idx, row in day_predictions.head(5).iterrows():
                hour = idx.strftime("%H:%M")
                power_kw = row["predicted_power"] / 1000

                # Wetter-Emoji basierend auf cloud_cover
                emoji = "  "
                if "cloud_cover" in row:
                    cc = row["cloud_cover"]
                    if cc < 20:
                        emoji = "☀️"
                    elif cc < 50:
                        emoji = "⛅"
                    else:
                        emoji = "☁️"

                self.output(f"   {hour}   {power_kw:5.1f} kW  {emoji}")

            # Tagesertrag berechnen
            today_total = predictions_df[today_mask]["predicted_power"].sum() / 1000
            self.output("")
            self.output(f"   Tagesertrag: ~{today_total:.1f} kWh")

        except Exception as e:
            # Bei Fehlern still ignorieren - Test-Prognose ist optional
            self.output(f"   (Prognose nicht verfügbar: {e})")

    def _print_success(
        self, config_path: Path, model_type: str, run_tuning: bool, imported_count: int = 0
    ) -> None:
        """Gibt die Erfolgsmeldung und nächste Schritte aus."""
        self.output("")
        self.output("═" * 50)
        self.output("✅ Einrichtung abgeschlossen!")
        self.output("═" * 50)
        self.output("")
        self.output(f"   Config gespeichert: {config_path}")

        # Issue #150: Test-Prognose zeigen wenn Training abgeschlossen
        if self._training_completed:
            # Config wird benötigt für Test-Prognose, holen wir aus dem Pfad
            try:
                config = Config.load(config_path)
                self._show_test_forecast(config)
            except Exception:
                pass  # Still ignorieren wenn es nicht klappt

        self.output("")
        self.output("   Nächste Schritte:")
        self.output("")

        step = 1

        # Datenimport nur wenn keine Daten vorhanden und nicht gerade importiert
        if self._existing_db_records == 0 and imported_count == 0:
            self.output(f"   {step}. Daten importieren:")
            self.output("      pvforecast import ~/Downloads/*.csv")
            self.output("")
            step += 1
        elif self._existing_db_records > 0 or imported_count > 0:
            total = self._existing_db_records or imported_count
            self.output(f"   ✓ {total:,} Datensätze vorhanden")
            self.output("")

        # Training - nur anzeigen wenn noch nicht durchgeführt
        if not self._training_completed:
            model_flag = f" --model {model_type}" if model_type == "xgb" else ""
            self.output(f"   {step}. Modell trainieren:")
            self.output(f"      pvforecast train{model_flag}")
            step += 1
        else:
            self.output("   ✓ Modell trainiert")
            self.output("")

        # Tuning
        if run_tuning:
            trials = getattr(self, "_tuning_trials", 20)
            self.output("")
            self.output(f"   {step}. Tuning durchführen:")
            self.output(f"      pvforecast tune --trials {trials}")
            step += 1

        # Prognose
        self.output("")
        self.output(f"   {step}. Prognose erstellen:")
        self.output("      pvforecast today")
        self.output("")


def run_setup() -> SetupResult:
    """Convenience-Funktion zum Ausführen des Setup-Wizards.

    Returns:
        SetupResult mit Config und Status
    """
    wizard = SetupWizard()
    return wizard.run_interactive()
