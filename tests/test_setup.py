"""Tests für das Setup-Modul."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from pvforecast.geocoding import GeoResult
from pvforecast.setup import SetupResult, SetupWizard


class TestSetupWizard:
    """Tests für die SetupWizard Klasse."""

    def test_wizard_creation(self):
        """Test: Wizard kann erstellt werden."""
        wizard = SetupWizard()
        assert wizard.output == print
        assert wizard.input == input

    def test_wizard_custom_io(self):
        """Test: Wizard mit custom I/O Funktionen."""
        mock_output = MagicMock()
        mock_input = MagicMock()
        wizard = SetupWizard(output_func=mock_output, input_func=mock_input)
        assert wizard.output == mock_output
        assert wizard.input == mock_input


class TestPromptLocation:
    """Tests für _prompt_location."""

    @patch("pvforecast.setup.geocode")
    def test_successful_geocode(self, mock_geocode):
        """Test: Erfolgreiche Geocoding-Abfrage."""
        mock_geocode.return_value = GeoResult(
            latitude=51.83,
            longitude=7.28,
            display_name="Dülmen, NRW, Deutschland",
            city="Dülmen",
            state="NRW",
        )

        outputs = []
        inputs = iter(["48249", "j"])  # PLZ eingeben, bestätigen

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        lat, lon, name = wizard._prompt_location()

        assert lat == 51.83
        assert lon == 7.28
        assert "Dülmen" in name

    @patch("pvforecast.setup.geocode")
    def test_geocode_not_confirmed_retry(self, mock_geocode):
        """Test: Geocoding-Ergebnis nicht bestätigt, neuer Versuch."""
        mock_geocode.side_effect = [
            GeoResult(
                latitude=52.0,
                longitude=8.0,
                display_name="Falscher Ort",
                city="Falscher Ort",
            ),
            GeoResult(
                latitude=51.83,
                longitude=7.28,
                display_name="Dülmen",
                city="Dülmen",
                state="NRW",
            ),
        ]

        inputs = iter(["Berlin", "n", "Dülmen", "j"])  # Erst Berlin, ablehnen, dann Dülmen

        wizard = SetupWizard(
            output_func=lambda x: None,
            input_func=lambda _: next(inputs),
        )

        lat, lon, name = wizard._prompt_location()

        assert lat == 51.83
        assert lon == 7.28
        assert mock_geocode.call_count == 2

    @patch("pvforecast.setup.geocode")
    def test_empty_input_retry(self, mock_geocode):
        """Test: Leere Eingabe führt zu Wiederholung."""
        mock_geocode.return_value = GeoResult(
            latitude=51.83,
            longitude=7.28,
            display_name="Dülmen",
            city="Dülmen",
        )

        inputs = iter(["", "48249", "j"])  # Erst leer, dann PLZ

        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        wizard._prompt_location()

        # Sollte Warnung ausgeben
        assert any("Bitte einen Ort" in str(o) for o in outputs)

    @patch("pvforecast.setup.geocode")
    def test_geocode_no_results_retry(self, mock_geocode):
        """Test: Keine Ergebnisse führt zu Wiederholung."""
        mock_geocode.side_effect = [
            None,  # Keine Ergebnisse
            GeoResult(
                latitude=51.83,
                longitude=7.28,
                display_name="Dülmen",
                city="Dülmen",
            ),
        ]

        inputs = iter(["xyz123", "Dülmen", "j"])

        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        wizard._prompt_location()

        assert any("Keine Ergebnisse" in str(o) for o in outputs)


class TestPromptManualLocation:
    """Tests für _prompt_manual_location."""

    def test_valid_manual_input(self):
        """Test: Gültige manuelle Eingabe."""
        inputs = iter(["51.83", "7.28", "Mein Ort"])

        wizard = SetupWizard(
            output_func=lambda x: None,
            input_func=lambda _: next(inputs),
        )

        lat, lon, name = wizard._prompt_manual_location()

        assert lat == 51.83
        assert lon == 7.28
        assert name == "Mein Ort"

    def test_empty_name_uses_default(self):
        """Test: Leerer Name verwendet Default."""
        inputs = iter(["51.83", "7.28", ""])

        wizard = SetupWizard(
            output_func=lambda x: None,
            input_func=lambda _: next(inputs),
        )

        lat, lon, name = wizard._prompt_manual_location()

        assert name == "Mein Standort"

    def test_invalid_latitude_retry(self):
        """Test: Ungültiger Breitengrad führt zu Wiederholung."""
        inputs = iter(["abc", "51.83", "7.28", "Test"])

        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        wizard._prompt_manual_location()

        assert any("gültige Zahl" in str(o) for o in outputs)

    def test_latitude_out_of_range_retry(self):
        """Test: Breitengrad außerhalb des Bereichs."""
        inputs = iter(["95", "51.83", "7.28", "Test"])

        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        wizard._prompt_manual_location()

        assert any("-90 und 90" in str(o) for o in outputs)


class TestPromptSystem:
    """Tests für _prompt_system."""

    def test_valid_system_input(self):
        """Test: Gültige Anlagen-Eingabe."""
        inputs = iter(["9.92", "Meine Anlage"])

        wizard = SetupWizard(
            output_func=lambda x: None,
            input_func=lambda _: next(inputs),
        )

        kwp, name = wizard._prompt_system("Dülmen")

        assert kwp == 9.92
        assert name == "Meine Anlage"

    def test_empty_name_uses_default(self):
        """Test: Leerer Name verwendet Default mit Ortsname."""
        inputs = iter(["9.92", ""])

        wizard = SetupWizard(
            output_func=lambda x: None,
            input_func=lambda _: next(inputs),
        )

        kwp, name = wizard._prompt_system("Dülmen")

        assert name == "Dülmen PV"

    def test_invalid_kwp_retry(self):
        """Test: Ungültige kWp führt zu Wiederholung."""
        inputs = iter(["abc", "9.92", "Test"])

        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        wizard._prompt_system("Test")

        assert any("gültige Zahl" in str(o) for o in outputs)

    def test_negative_kwp_retry(self):
        """Test: Negative kWp führt zu Wiederholung."""
        inputs = iter(["-5", "9.92", "Test"])

        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        wizard._prompt_system("Test")

        assert any("größer als 0" in str(o) for o in outputs)

    def test_huge_kwp_confirmation(self):
        """Test: Sehr große kWp benötigt Bestätigung."""
        inputs = iter(["2000", "j", "Großanlage"])  # 2 MW, bestätigen

        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        kwp, _ = wizard._prompt_system("Test")

        assert kwp == 2000
        assert any("1 MW" in str(o) for o in outputs)


class TestPromptXGBoost:
    """Tests für _prompt_xgboost."""

    @patch("pvforecast.setup.subprocess.run")
    def test_install_xgboost(self, mock_run):
        """Test: XGBoost wird installiert."""
        mock_run.return_value = MagicMock(returncode=0)

        inputs = iter(["j"])

        # Simuliere dass xgboost nicht installiert ist
        with patch.dict("sys.modules", {"xgboost": None}):
            # Force ImportError
            import sys

            original = sys.modules.get("xgboost")
            if "xgboost" in sys.modules:
                del sys.modules["xgboost"]

            wizard = SetupWizard(
                output_func=lambda x: None,
                input_func=lambda _: next(inputs),
            )

            # Mock den Import-Check
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                result = wizard._prompt_xgboost()

            # Restore
            if original:
                sys.modules["xgboost"] = original

        assert result is True
        mock_run.assert_called_once()

    def test_skip_xgboost(self):
        """Test: XGBoost-Installation überspringen."""
        inputs = iter(["n"])

        # Force ImportError für xgboost check
        with patch("builtins.__import__", side_effect=ImportError("No module")):
            wizard = SetupWizard(
                output_func=lambda x: None,
                input_func=lambda _: next(inputs),
            )

            result = wizard._prompt_xgboost()

        assert result is False

    @patch("pvforecast.setup.subprocess.run")
    def test_xgboost_install_failure(self, mock_run):
        """Test: XGBoost-Installation schlägt fehl."""
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "pip", stderr="Error")

        inputs = iter(["j"])

        with patch("builtins.__import__", side_effect=ImportError("No module")):
            outputs = []
            wizard = SetupWizard(
                output_func=lambda x: outputs.append(x),
                input_func=lambda _: next(inputs),
            )

            result = wizard._prompt_xgboost()

        assert result is False
        assert any("fehlgeschlagen" in str(o) for o in outputs)


class TestRunInteractive:
    """Tests für run_interactive (Integration)."""

    @patch("pvforecast.setup.geocode")
    @patch("pvforecast.setup.get_config_path")
    @patch.object(Path, "mkdir", return_value=None)
    def test_full_wizard_flow(self, mock_mkdir, mock_config_path, mock_geocode, tmp_path):
        """Test: Vollständiger Wizard-Durchlauf."""
        config_file = tmp_path / "config.yaml"
        mock_config_path.return_value = config_file

        mock_geocode.return_value = GeoResult(
            latitude=51.83,
            longitude=7.28,
            display_name="Dülmen, NRW",
            city="Dülmen",
            state="NRW",
        )

        # Mock XGBoost als bereits installiert
        with patch.dict("sys.modules", {"xgboost": MagicMock()}):
            inputs = iter(
                [
                    "48249",  # PLZ
                    "j",  # Bestätigen
                    "9.92",  # kWp
                    "",  # Name (default)
                ]
            )

            wizard = SetupWizard(
                output_func=lambda x: None,
                input_func=lambda _: next(inputs),
            )

            result = wizard.run_interactive()

        assert result.config.latitude == 51.83
        assert result.config.longitude == 7.28
        assert result.config.peak_kwp == 9.92
        assert "Dülmen" in result.config.system_name
        assert result.config_path == config_file


class TestSetupResult:
    """Tests für SetupResult Dataclass."""

    def test_creation(self, tmp_path):
        """Test: SetupResult kann erstellt werden."""
        from pvforecast.config import Config

        config = Config(latitude=51.83, longitude=7.28, peak_kwp=9.92)
        result = SetupResult(
            config=config,
            config_path=tmp_path / "config.yaml",
            xgboost_installed=True,
        )

        assert result.config.latitude == 51.83
        assert result.xgboost_installed is True
