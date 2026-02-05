"""Interaktiver Setup-Wizard für die Ersteinrichtung.

Führt den Benutzer durch die Konfiguration:
1. Standort (PLZ/Ort → Koordinaten)
2. Anlagenparameter (kWp, Name)
3. Optional: XGBoost Installation
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pvforecast.config import Config, get_config_path
from pvforecast.geocoding import GeocodingError, geocode


@dataclass
class SetupResult:
    """Ergebnis des Setup-Wizards.

    Attributes:
        config: Die erstellte Konfiguration
        config_path: Pfad zur gespeicherten Config-Datei
        xgboost_installed: Ob XGBoost installiert wurde
    """

    config: Config
    config_path: Path
    xgboost_installed: bool


class SetupWizard:
    """Interaktiver Setup-Wizard für pvforecast.

    Führt den Benutzer durch die Ersteinrichtung und erstellt
    eine Config-Datei mit allen notwendigen Parametern.
    """

    def __init__(self, output_func=print, input_func=input):
        """Initialisiert den Wizard.

        Args:
            output_func: Funktion für Ausgaben (default: print)
            input_func: Funktion für Eingaben (default: input)
        """
        self.output = output_func
        self.input = input_func

    def run_interactive(self) -> SetupResult:
        """Führt den interaktiven Setup-Wizard aus.

        Returns:
            SetupResult mit Config und Status
        """
        self._print_header()

        # 1. Standort
        latitude, longitude, location_name = self._prompt_location()

        # 2. Anlage
        peak_kwp, system_name = self._prompt_system(location_name)

        # 3. Config erstellen
        config = Config(
            latitude=latitude,
            longitude=longitude,
            peak_kwp=peak_kwp,
            system_name=system_name,
        )

        # 4. Config speichern
        config_path = get_config_path()
        config.save(config_path)

        # 5. Optional: XGBoost
        xgboost_installed = self._prompt_xgboost()

        self._print_success(config_path)

        return SetupResult(
            config=config,
            config_path=config_path,
            xgboost_installed=xgboost_installed,
        )

    def _print_header(self) -> None:
        """Gibt den Header aus."""
        self.output("")
        self.output("🔆 PV-Forecast Ersteinrichtung")
        self.output("═" * 50)
        self.output("")

    def _print_success(self, config_path: Path) -> None:
        """Gibt die Erfolgsmeldung aus."""
        self.output("")
        self.output("═" * 50)
        self.output("✅ Einrichtung abgeschlossen!")
        self.output("═" * 50)
        self.output("")
        self.output(f"   Config gespeichert: {config_path}")
        self.output("")
        self.output("   Nächste Schritte:")
        self.output("   1. Daten importieren:  pvforecast import <csv-dateien>")
        self.output("   2. Modell trainieren:  pvforecast train")
        self.output("   3. Prognose erstellen: pvforecast today")
        self.output("")

    def _prompt_location(self) -> tuple[float, float, str]:
        """Fragt nach dem Standort.

        Returns:
            Tuple (latitude, longitude, location_name)
        """
        self.output("1️⃣  Standort")
        self.output("")

        while True:
            query = self.input("   Postleitzahl oder Ort: ").strip()

            if not query:
                self.output("   ⚠️  Bitte einen Ort oder PLZ eingeben.")
                continue

            self.output("   Suche...")

            try:
                result = geocode(query)

                if result is None:
                    self.output(f"   ❌ Keine Ergebnisse für '{query}'")
                    self.output("   Versuche eine andere Eingabe (z.B. '48249' oder 'Dülmen')")
                    self.output("")
                    continue

                # Bestätigung
                self.output(
                    f"   → {result.short_name()} "
                    f"({result.latitude:.2f}°N, {result.longitude:.2f}°E)"
                )

                confirm = self.input("   Stimmt das? [J/n]: ").strip().lower()
                if confirm in ("", "j", "ja", "y", "yes"):
                    self.output("   ✓")
                    self.output("")
                    return result.latitude, result.longitude, result.short_name()
                else:
                    self.output("   OK, versuche es erneut.")
                    self.output("")

            except GeocodingError as e:
                self.output(f"   ⚠️  Geocoding-Fehler: {e}")
                self.output("")

                # Fallback: Manuelle Eingabe
                if self._prompt_manual_location_fallback():
                    return self._prompt_manual_location()

    def _prompt_manual_location_fallback(self) -> bool:
        """Fragt ob manuelle Eingabe gewünscht ist."""
        response = self.input("   Koordinaten manuell eingeben? [j/N]: ").strip().lower()
        return response in ("j", "ja", "y", "yes")

    def _prompt_manual_location(self) -> tuple[float, float, str]:
        """Manuelle Koordinaten-Eingabe."""
        self.output("")
        self.output("   Manuelle Eingabe:")

        while True:
            try:
                lat_str = self.input("   Breitengrad (z.B. 51.83): ").strip()
                latitude = float(lat_str)

                if not -90 <= latitude <= 90:
                    self.output("   ⚠️  Breitengrad muss zwischen -90 und 90 liegen.")
                    continue

                lon_str = self.input("   Längengrad (z.B. 7.28): ").strip()
                longitude = float(lon_str)

                if not -180 <= longitude <= 180:
                    self.output("   ⚠️  Längengrad muss zwischen -180 und 180 liegen.")
                    continue

                name = self.input("   Ortsname (optional): ").strip() or "Mein Standort"

                self.output("   ✓")
                self.output("")
                return latitude, longitude, name

            except ValueError:
                self.output("   ⚠️  Bitte eine gültige Zahl eingeben.")

    def _prompt_system(self, default_name: str) -> tuple[float, str]:
        """Fragt nach den Anlagenparametern.

        Args:
            default_name: Vorgeschlagener Anlagenname

        Returns:
            Tuple (peak_kwp, system_name)
        """
        self.output("2️⃣  Anlage")
        self.output("")

        # Peak-Leistung
        while True:
            try:
                kwp_str = self.input("   Peakleistung in kWp: ").strip()
                peak_kwp = float(kwp_str)

                if peak_kwp <= 0:
                    self.output("   ⚠️  Leistung muss größer als 0 sein.")
                    continue

                if peak_kwp > 1000:
                    self.output("   ⚠️  Bist du sicher? Das sind 1 MW!")
                    confirm = self.input("   Fortfahren? [j/N]: ").strip().lower()
                    if confirm not in ("j", "ja", "y", "yes"):
                        continue

                break

            except ValueError:
                self.output("   ⚠️  Bitte eine gültige Zahl eingeben (z.B. 9.92).")

        # Anlagenname
        default_system_name = f"{default_name} PV" if default_name else "Meine PV-Anlage"
        name = self.input(f"   Name (optional) [{default_system_name}]: ").strip()
        system_name = name if name else default_system_name

        self.output("   ✓")
        self.output("")

        return peak_kwp, system_name

    def _prompt_xgboost(self) -> bool:
        """Fragt ob XGBoost installiert werden soll.

        Returns:
            True wenn XGBoost erfolgreich installiert wurde
        """
        self.output("3️⃣  XGBoost (bessere Prognose-Genauigkeit)")
        self.output("")

        # Prüfe ob bereits installiert
        try:
            import xgboost  # noqa: F401

            self.output("   ✓ XGBoost ist bereits installiert")
            self.output("")
            return True
        except ImportError:
            pass

        response = self.input("   XGBoost installieren? [J/n]: ").strip().lower()

        if response in ("n", "no", "nein"):
            self.output(
                "   → Übersprungen (kann später mit 'pip install xgboost' installiert werden)"
            )
            self.output("")
            return False

        self.output("   Installiere XGBoost...")

        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "xgboost"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.output("   ✓ XGBoost installiert")
            self.output("")
            return True

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr[:200] if e.stderr else "Unbekannter Fehler"
            self.output(f"   ⚠️  Installation fehlgeschlagen: {error_msg}")
            self.output("")

            # macOS-spezifischer Hinweis
            if sys.platform == "darwin":
                self.output("   💡 Auf macOS benötigt XGBoost eventuell libomp:")
                self.output("      brew install libomp")
                self.output("")

            self.output("   Du kannst XGBoost später manuell installieren.")
            self.output("")
            return False


def run_setup() -> SetupResult:
    """Convenience-Funktion zum Ausführen des Setup-Wizards.

    Returns:
        SetupResult mit Config und Status
    """
    wizard = SetupWizard()
    return wizard.run_interactive()
