"""Diagnose-Tool für pvforecast Installation.

Prüft alle Komponenten und gibt einen Statusbericht aus.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime

from pvforecast import __version__
from pvforecast.config import get_config_path, load_config


@dataclass
class CheckResult:
    """Ergebnis eines Diagnose-Checks.

    Attributes:
        name: Name des Checks
        status: "ok", "warning", oder "error"
        message: Beschreibung des Ergebnisses
        detail: Optionale Details
    """

    name: str
    status: str  # "ok", "warning", "error"
    message: str
    detail: str | None = None


class Doctor:
    """Diagnose-Tool für pvforecast.

    Prüft Installation, Konfiguration, Datenbank und Modell.
    """

    def __init__(self, output_func=print):
        """Initialisiert den Doctor.

        Args:
            output_func: Funktion für Ausgaben (default: print)
        """
        self.output = output_func
        self.results: list[CheckResult] = []

    def run(self) -> int:
        """Führt alle Diagnose-Checks aus.

        Returns:
            0 wenn alles OK, 1 bei Warnungen, 2 bei Fehlern
        """
        self._print_header()

        # Checks durchführen
        self._check_python()
        self._check_pvforecast()
        self._check_config()
        self._check_database()
        self._check_model()
        self._check_xgboost()
        self._check_network()

        self._print_results()
        return self._get_exit_code()

    def _print_header(self) -> None:
        """Gibt den Header aus."""
        self.output("")
        self.output("🔍 PV-Forecast Systemcheck")
        self.output("═" * 50)
        self.output("")

    def _add_result(self, result: CheckResult) -> None:
        """Fügt ein Check-Ergebnis hinzu."""
        self.results.append(result)

    def _check_python(self) -> None:
        """Prüft Python-Version."""
        version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        # Python 3.9+ ist Mindestanforderung (pyproject.toml)
        self._add_result(
            CheckResult(
                name="Python",
                status="ok",
                message=version,
            )
        )

    def _check_pvforecast(self) -> None:
        """Prüft pvforecast Installation."""
        self._add_result(
            CheckResult(
                name="pvforecast",
                status="ok",
                message=__version__,
            )
        )

    def _check_config(self) -> None:
        """Prüft Konfiguration."""
        config_path = get_config_path()

        if not config_path.exists():
            self._add_result(
                CheckResult(
                    name="Config",
                    status="warning",
                    message="Nicht vorhanden",
                    detail="Erstelle mit: pvforecast setup",
                )
            )
            return

        try:
            config = load_config()
            self._add_result(
                CheckResult(
                    name="Config",
                    status="ok",
                    message=str(config_path),
                )
            )

            # Standort-Info
            self._add_result(
                CheckResult(
                    name="Standort",
                    status="ok",
                    message=f"{config.system_name} ({config.peak_kwp} kWp)",
                    detail=f"{config.latitude:.2f}°N, {config.longitude:.2f}°E",
                )
            )
        except Exception as e:
            self._add_result(
                CheckResult(
                    name="Config",
                    status="error",
                    message=f"Fehler beim Laden: {e}",
                )
            )

    def _check_database(self) -> None:
        """Prüft Datenbank."""
        try:
            config = load_config()
            db_path = config.db_path

            if not db_path.exists():
                self._add_result(
                    CheckResult(
                        name="Datenbank",
                        status="warning",
                        message="Nicht vorhanden",
                        detail="Importiere Daten mit: pvforecast import <csv>",
                    )
                )
                return

            from pvforecast.db import Database

            db = Database(db_path)

            pv_count = db.get_pv_count()
            weather_count = db.get_weather_count()

            if pv_count == 0:
                self._add_result(
                    CheckResult(
                        name="Datenbank",
                        status="warning",
                        message="Keine PV-Daten",
                        detail="Importiere mit: pvforecast import <csv>",
                    )
                )
            else:
                pv_start, pv_end = db.get_pv_date_range()
                start_date = (
                    datetime.fromtimestamp(pv_start).strftime("%Y-%m-%d") if pv_start else "?"
                )
                end_date = datetime.fromtimestamp(pv_end).strftime("%Y-%m-%d") if pv_end else "?"

                self._add_result(
                    CheckResult(
                        name="Datenbank",
                        status="ok",
                        message=f"{pv_count:,} PV / {weather_count:,} Wetter",
                        detail=f"Zeitraum: {start_date} bis {end_date}",
                    )
                )

        except Exception as e:
            self._add_result(
                CheckResult(
                    name="Datenbank",
                    status="error",
                    message=f"Fehler: {e}",
                )
            )

    def _check_model(self) -> None:
        """Prüft trainiertes Modell."""
        try:
            config = load_config()
            model_path = config.model_path

            if not model_path.exists():
                self._add_result(
                    CheckResult(
                        name="Modell",
                        status="warning",
                        message="Nicht vorhanden",
                        detail="Trainiere mit: pvforecast train",
                    )
                )
                return

            from pvforecast.model import load_model

            _, metrics = load_model(model_path)

            if metrics:
                mae = metrics.get("mae", "?")
                mape = metrics.get("mape", "?")
                model_type = metrics.get("model_type", "unknown")

                # Qualitätsbewertung
                if isinstance(mae, (int, float)) and mae < 150:
                    status = "ok"
                elif isinstance(mae, (int, float)) and mae < 250:
                    status = "warning"
                else:
                    status = "ok"  # Trotzdem OK, nur nicht optimal

                msg = (
                    f"{model_type} (MAE: {mae:.0f}W)"
                    if isinstance(mae, (int, float))
                    else model_type
                )
                detail = f"MAPE: {mape:.1f}%" if isinstance(mape, (int, float)) else None
                self._add_result(
                    CheckResult(
                        name="Modell",
                        status=status,
                        message=msg,
                        detail=detail,
                    )
                )
            else:
                self._add_result(
                    CheckResult(
                        name="Modell",
                        status="ok",
                        message="Vorhanden (keine Metriken)",
                    )
                )

        except Exception as e:
            self._add_result(
                CheckResult(
                    name="Modell",
                    status="error",
                    message=f"Fehler: {e}",
                )
            )

    def _check_xgboost(self) -> None:
        """Prüft XGBoost Installation."""
        try:
            import xgboost

            version = xgboost.__version__
            self._add_result(
                CheckResult(
                    name="XGBoost",
                    status="ok",
                    message=version,
                )
            )
        except ImportError:
            self._add_result(
                CheckResult(
                    name="XGBoost",
                    status="warning",
                    message="Nicht installiert (optional)",
                    detail="pip install xgboost",
                )
            )

        # macOS: libomp check
        if sys.platform == "darwin":
            self._check_libomp()

    def _check_libomp(self) -> None:
        """Prüft libomp auf macOS."""
        import subprocess

        try:
            # Prüfe ob libomp via Homebrew installiert ist
            result = subprocess.run(
                ["brew", "list", "libomp"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self._add_result(
                    CheckResult(
                        name="libomp",
                        status="ok",
                        message="Installiert (Homebrew)",
                    )
                )
            else:
                # Nur Warnung wenn XGBoost installiert ist
                try:
                    import xgboost  # noqa: F401

                    self._add_result(
                        CheckResult(
                            name="libomp",
                            status="warning",
                            message="Nicht gefunden",
                            detail="brew install libomp (für XGBoost-Performance)",
                        )
                    )
                except ImportError:
                    pass  # Keine Warnung wenn XGBoost nicht da ist

        except FileNotFoundError:
            # Homebrew nicht installiert
            pass

    def _check_network(self) -> None:
        """Prüft Netzwerk-Konnektivität zu Wetter-APIs."""
        import httpx

        # Check Open-Meteo
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(
                    "https://api.open-meteo.com/v1/forecast?latitude=0&longitude=0"
                )
                if response.status_code == 200:
                    self._add_result(
                        CheckResult(
                            name="Open-Meteo",
                            status="ok",
                            message="API erreichbar",
                        )
                    )
                else:
                    self._add_result(
                        CheckResult(
                            name="Open-Meteo",
                            status="warning",
                            message=f"HTTP {response.status_code}",
                        )
                    )
        except httpx.RequestError as e:
            self._add_result(
                CheckResult(
                    name="Open-Meteo",
                    status="warning",
                    message="Nicht erreichbar",
                    detail=str(e)[:50],
                )
            )

        # Check DWD (MOSMIX) - only if configured
        try:
            config = load_config()
            if config.weather.forecast_provider == "mosmix":
                self._check_dwd_mosmix()
        except Exception:
            pass  # Config not available, skip DWD check

    def _check_dwd_mosmix(self) -> None:
        """Prüft DWD MOSMIX Erreichbarkeit."""
        import httpx

        try:
            with httpx.Client(timeout=10) as client:
                # Check if DWD OpenData is reachable
                response = client.head(
                    "https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_S/"
                )
                if response.status_code in (200, 301, 302):
                    self._add_result(
                        CheckResult(
                            name="DWD MOSMIX",
                            status="ok",
                            message="OpenData erreichbar",
                        )
                    )
                else:
                    self._add_result(
                        CheckResult(
                            name="DWD MOSMIX",
                            status="warning",
                            message=f"HTTP {response.status_code}",
                        )
                    )
        except httpx.RequestError as e:
            self._add_result(
                CheckResult(
                    name="DWD MOSMIX",
                    status="warning",
                    message="Nicht erreichbar",
                    detail=str(e)[:50],
                )
            )

    def _print_results(self) -> None:
        """Gibt die Ergebnisse aus."""
        for result in self.results:
            icon = {"ok": "✓", "warning": "⚠", "error": "✗"}[result.status]
            self.output(f" {icon} {result.name}: {result.message}")
            if result.detail:
                self.output(f"   └─ {result.detail}")

        self.output("")

        # Zusammenfassung
        errors = sum(1 for r in self.results if r.status == "error")
        warnings = sum(1 for r in self.results if r.status == "warning")

        if errors > 0:
            self.output(f"❌ {errors} Fehler gefunden")
        elif warnings > 0:
            self.output(f"⚠️  {warnings} Warnungen")
        else:
            self.output("✅ Alles OK!")

        self.output("")

    def _get_exit_code(self) -> int:
        """Ermittelt den Exit-Code."""
        if any(r.status == "error" for r in self.results):
            return 2
        if any(r.status == "warning" for r in self.results):
            return 1
        return 0


def run_doctor() -> int:
    """Convenience-Funktion zum Ausführen des Doctors.

    Returns:
        Exit-Code (0=OK, 1=Warnungen, 2=Fehler)
    """
    doctor = Doctor()
    return doctor.run()
