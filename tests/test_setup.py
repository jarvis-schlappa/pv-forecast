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
        assert any("ungewöhnlich hoch" in str(o) for o in outputs)


class TestPromptModel:
    """Tests für _prompt_model."""

    def test_choose_randomforest(self):
        """Test: RandomForest wird gewählt."""
        inputs = iter(["1"])

        wizard = SetupWizard(
            output_func=lambda x: None,
            input_func=lambda _: next(inputs),
        )

        model_type, xgb_installed = wizard._prompt_model()

        assert model_type == "rf"

    def test_choose_xgboost_when_available(self):
        """Test: XGBoost wird gewählt wenn bereits installiert."""
        inputs = iter(["2"])

        # Mock XGBoost als installiert
        with patch.dict("sys.modules", {"xgboost": MagicMock()}):
            wizard = SetupWizard(
                output_func=lambda x: None,
                input_func=lambda _: next(inputs),
            )

            model_type, xgb_installed = wizard._prompt_model()

        assert model_type == "xgb"
        assert xgb_installed is True

    @patch("pvforecast.setup.subprocess.run")
    @patch("sys.platform", "linux")  # Simulate non-macOS to skip libomp check
    def test_install_xgboost_on_demand(self, mock_run):
        """Test: XGBoost wird bei Bedarf installiert."""
        mock_run.return_value = MagicMock(returncode=0)

        inputs = iter(["2"])  # Wähle XGBoost

        # Simuliere dass xgboost nicht installiert ist
        import sys

        original = sys.modules.get("xgboost")
        if "xgboost" in sys.modules:
            del sys.modules["xgboost"]

        try:
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                wizard = SetupWizard(
                    output_func=lambda x: None,
                    input_func=lambda _: next(inputs),
                )

                model_type, xgb_installed = wizard._prompt_model()
        finally:
            if original:
                sys.modules["xgboost"] = original

        assert model_type == "xgb"
        assert xgb_installed is True
        mock_run.assert_called_once()

    @patch("pvforecast.setup.subprocess.run")
    @patch("sys.platform", "linux")  # Simulate non-macOS to skip libomp check
    def test_xgboost_install_failure_fallback(self, mock_run):
        """Test: Bei XGBoost-Installationsfehler Fallback auf RF."""
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "pip", stderr="Error")

        inputs = iter(["2"])  # Wähle XGBoost

        import sys

        original = sys.modules.get("xgboost")
        if "xgboost" in sys.modules:
            del sys.modules["xgboost"]

        try:
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                outputs = []
                wizard = SetupWizard(
                    output_func=lambda x: outputs.append(x),
                    input_func=lambda _: next(inputs),
                )

                model_type, xgb_installed = wizard._prompt_model()
        finally:
            if original:
                sys.modules["xgboost"] = original

        assert model_type == "rf"  # Fallback
        assert xgb_installed is False
        assert any("fehlgeschlagen" in str(o) for o in outputs)


class TestRunInteractive:
    """Tests für run_interactive (Integration)."""

    @patch("pvforecast.setup.geocode")
    @patch("pvforecast.setup.get_config_path")
    @patch("pvforecast.config._default_db_path")
    @patch("pvforecast.config._default_model_path")
    @patch.object(Path, "mkdir", return_value=None)
    def test_full_wizard_flow(
        self, mock_mkdir, mock_model_path, mock_db_path, mock_config_path, mock_geocode, tmp_path
    ):
        """Test: Vollständiger Wizard-Durchlauf."""
        config_file = tmp_path / "config.yaml"
        mock_config_path.return_value = config_file
        # Mock DB/Model paths to non-existent locations to avoid finding real data
        mock_db_path.return_value = tmp_path / "nonexistent.db"
        mock_model_path.return_value = tmp_path / "nonexistent.pkl"

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
                    "48249",  # 1. PLZ
                    "j",  # Bestätigen
                    "9.92",  # 2. kWp
                    "",  # Name (default)
                    "1",  # 3. Wetterdaten-Quelle Forecast: Open-Meteo
                    "1",  # 3. Wetterdaten-Quelle Historical: Open-Meteo
                    "2",  # 4. Modell: XGBoost
                    "n",  # 6. Daten importieren: nein
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
        assert result.model_type == "xgb"


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


class TestLibompCheck:
    """Tests für libomp-Check auf macOS (Issue #151)."""

    @patch("sys.platform", "linux")
    def test_skip_on_linux(self):
        """Test: libomp-Check wird auf Linux übersprungen."""
        wizard = SetupWizard(
            output_func=lambda x: None,
            input_func=lambda _: "",
        )
        assert wizard._check_libomp_macos() is True

    @patch("sys.platform", "darwin")
    @patch("pathlib.Path.exists")
    def test_libomp_already_installed(self, mock_exists):
        """Test: libomp bereits vorhanden."""
        mock_exists.return_value = True

        wizard = SetupWizard(
            output_func=lambda x: None,
            input_func=lambda _: "",
        )
        assert wizard._check_libomp_macos() is True

    @patch("sys.platform", "darwin")
    @patch("pathlib.Path.exists", return_value=False)
    @patch("pvforecast.setup.subprocess.run")
    def test_libomp_install_offered(self, mock_run, mock_exists):
        """Test: libomp-Installation wird angeboten."""
        # Homebrew check succeeds, install succeeds
        mock_run.return_value = MagicMock(returncode=0)

        inputs = iter(["j"])  # Ja, installieren
        outputs = []

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )
        result = wizard._check_libomp_macos()

        assert result is True
        assert any("libomp" in str(o) for o in outputs)
        assert mock_run.call_count == 2  # brew --version + brew install

    @patch("sys.platform", "darwin")
    @patch("pathlib.Path.exists", return_value=False)
    @patch("pvforecast.setup.subprocess.run")
    def test_libomp_install_declined(self, mock_run, mock_exists):
        """Test: libomp-Installation abgelehnt."""
        mock_run.return_value = MagicMock(returncode=0)  # Homebrew available

        inputs = iter(["n"])  # Nein
        outputs = []

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )
        result = wizard._check_libomp_macos()

        assert result is False
        assert any("nicht installiert" in str(o) for o in outputs)


class TestOptunaInstall:
    """Tests für Optuna-Installation bei Tuning (Issue #152)."""

    @patch("pvforecast.setup.subprocess.run")
    def test_install_optuna_method(self, mock_run):
        """Test: _install_optuna installiert Optuna."""
        mock_run.return_value = MagicMock(returncode=0)

        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: "",
        )

        result = wizard._install_optuna()

        assert result is True
        assert any("Optuna installiert" in str(o) for o in outputs)
        mock_run.assert_called_once()

    def test_optuna_already_installed(self):
        """Test: Keine Installation wenn Optuna bereits vorhanden."""
        inputs = iter(["2"])  # Schnelles Tuning
        outputs = []

        with patch.dict("sys.modules", {"optuna": MagicMock()}):
            wizard = SetupWizard(
                output_func=lambda x: outputs.append(x),
                input_func=lambda _: next(inputs),
            )
            wizard._existing_db_records = 5000

            result = wizard._prompt_tuning("xgb")

        assert result is True
        # Keine Installation angeboten
        assert not any("Optuna installieren?" in str(o) for o in outputs)


class TestTrainingAfterImport:
    """Tests für Training nach Import (Issue #149)."""

    def test_training_offered_after_import(self, tmp_path):
        """Test: Training wird nach erfolgreichem Import angeboten."""
        # Erstelle test CSV
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("timestamp,power\n2024-01-01 12:00,1000\n")

        inputs = iter(["j", str(csv_file), "j"])  # Import: ja, Pfad, Training: ja

        wizard = SetupWizard(
            output_func=lambda x: None,
            input_func=lambda _: next(inputs),
        )

        # Mock die Database und import_csv_files
        with patch("pvforecast.db.Database"):
            with patch("pvforecast.data_loader.import_csv_files", return_value=100):
                from pvforecast.config import Config
                config = Config(latitude=51.83, longitude=7.28, peak_kwp=9.92)

                wizard._prompt_import(config)

        # Wenn User "j" antwortet, sollte Flag gesetzt sein
        assert wizard._run_training_after_import is True

    def test_training_declined_after_import(self, tmp_path):
        """Test: Training nach Import ablehnen."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("timestamp,power\n2024-01-01 12:00,1000\n")

        inputs = iter(["j", str(csv_file), "n"])  # Training: nein
        outputs = []

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        with patch("pvforecast.db.Database"):
            with patch("pvforecast.data_loader.import_csv_files", return_value=100):
                from pvforecast.config import Config
                config = Config(latitude=51.83, longitude=7.28, peak_kwp=9.92)

                wizard._prompt_import(config)

        assert wizard._run_training_after_import is False


class TestExecuteTraining:
    """Tests für Training-Ausführung (Issue #149)."""

    def test_training_sets_flag_on_success(self, tmp_path):
        """Test: _training_completed wird bei Erfolg gesetzt."""
        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: "",
        )

        # Simuliere erfolgreiche Initialisierung
        wizard._training_completed = False

        # Mock alle Abhängigkeiten
        with patch("pvforecast.db.Database"):
            with patch("pvforecast.model.load_training_data") as mock_load:
                with patch("pvforecast.model.train") as mock_train:
                    with patch("pvforecast.model.save_model"):
                        with patch("pvforecast.config._default_model_path") as mock_path:
                            mock_path.return_value = tmp_path / "model.pkl"
                            mock_load.return_value = MagicMock()
                            mock_train.return_value = (MagicMock(), {"mape": 0.25})

                            from pvforecast.config import Config
                            config = Config(latitude=51.83, longitude=7.28, peak_kwp=9.92)

                            result = wizard._execute_training("xgb", config)

        assert result is True
        assert wizard._training_completed is True

    def test_training_handles_failure(self, tmp_path):
        """Test: Training-Fehler wird abgefangen."""
        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: "",
        )

        with patch("pvforecast.db.Database", side_effect=Exception("DB Error")):
            with patch("pvforecast.config._default_model_path") as mock_path:
                mock_path.return_value = tmp_path / "model.pkl"

                from pvforecast.config import Config
                config = Config(latitude=51.83, longitude=7.28, peak_kwp=9.92)

                result = wizard._execute_training("xgb", config)

        assert result is False
        assert wizard._training_completed is False
        assert any("fehlgeschlagen" in str(o) for o in outputs)


class TestShowTestForecast:
    """Tests für Test-Prognose am Ende (Issue #150)."""

    def test_no_forecast_without_model(self, tmp_path):
        """Test: Keine Prognose wenn kein Modell vorhanden."""
        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: "",
        )

        with patch("pvforecast.config._default_model_path") as mock_path:
            mock_path.return_value = tmp_path / "nonexistent.pkl"

            from pvforecast.config import Config
            config = Config(latitude=51.83, longitude=7.28, peak_kwp=9.92)

            wizard._show_test_forecast(config)

        # Keine Test-Prognose Ausgabe wenn Modell fehlt
        assert not any("Test-Prognose" in str(o) for o in outputs)

    def test_forecast_handles_errors_gracefully(self, tmp_path):
        """Test: Fehler bei Prognose werden abgefangen."""
        model_file = tmp_path / "model.pkl"
        model_file.touch()

        outputs = []
        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: "",
        )

        with patch("pvforecast.config._default_model_path") as mock_path:
            mock_path.return_value = model_file
            # load_model wirft Fehler
            with patch("pvforecast.model.load_model", side_effect=Exception("Load error")):
                from pvforecast.config import Config
                config = Config(latitude=51.83, longitude=7.28, peak_kwp=9.92)

                # Sollte nicht abstürzen
                wizard._show_test_forecast(config)

        # Sollte Fehlermeldung ausgeben
        assert any("nicht verfügbar" in str(o) for o in outputs)


class TestHOSTRADALoadInSetup:
    """Tests für Issue #155: HOSTRADA-Dateien im Setup laden."""

    def test_hostrada_load_offered_when_files_found(self, tmp_path):
        """Test: Laden wird angeboten wenn NetCDF-Dateien gefunden werden."""
        # Erstelle fake NetCDF-Dateien
        hostrada_dir = tmp_path / "hostrada"
        hostrada_dir.mkdir()
        (hostrada_dir / "rsds_1hr_HOSTRADA-v1-0_BE_gn_2023010100-2023013123.nc").touch()
        (hostrada_dir / "tas_1hr_HOSTRADA-v1-0_BE_gn_2023010100-2023013123.nc").touch()

        outputs = []
        inputs = iter([
            "j",               # Lokales Verzeichnis angeben? [j/N]
            str(hostrada_dir), # Pfad
            "n",               # Wetterdaten jetzt laden? [J/n] - ablehnen
        ])

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        # Setze Koordinaten (normalerweise aus _prompt_location)
        wizard._latitude = 51.83
        wizard._longitude = 7.28

        result = wizard._prompt_hostrada_path()

        # Sollte Pfad zurückgeben
        assert result == str(hostrada_dir)
        # Sollte Dateien gefunden melden
        assert any("2 NetCDF-Dateien gefunden" in str(o) for o in outputs)

    def test_hostrada_load_skipped_without_coordinates(self, tmp_path):
        """Test: Laden wird nicht angeboten wenn Koordinaten fehlen."""
        hostrada_dir = tmp_path / "hostrada"
        hostrada_dir.mkdir()
        (hostrada_dir / "test.nc").touch()

        outputs = []
        inputs = iter([
            "j",               # Lokales Verzeichnis angeben?
            str(hostrada_dir), # Pfad
        ])

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        # Keine Koordinaten gesetzt!
        wizard._latitude = None
        wizard._longitude = None

        result = wizard._prompt_hostrada_path()

        # Sollte nicht nach Laden fragen (keine "Wetterdaten jetzt laden" Frage)
        assert not any("Wetterdaten jetzt in Datenbank laden" in str(o) for o in outputs)


class TestWeatherCheckBeforeTraining:
    """Tests für Issue #156: Wetterdaten vor Training prüfen."""

    def test_training_checks_weather_data(self, tmp_path):
        """Test: Training prüft ob Wetterdaten vorhanden sind."""
        outputs = []
        inputs = iter(["n"])  # Wetterdaten laden? - ablehnen

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        with patch("pvforecast.config._default_model_path") as mock_model_path:
            mock_model_path.return_value = tmp_path / "model.pkl"

            # Mock Database
            with patch("pvforecast.db.Database") as MockDB:
                mock_db = MagicMock()
                mock_db.get_weather_count.return_value = 0  # Keine Wetterdaten!
                MockDB.return_value = mock_db

                from pvforecast.config import Config
                config = Config(
                    latitude=51.83,
                    longitude=7.28,
                    peak_kwp=9.92,
                    db_path=tmp_path / "test.db",
                )

                result = wizard._execute_training("rf", config)

        # Training sollte abbrechen
        assert result is False
        assert wizard._training_completed is False
        # Warnung sollte ausgegeben werden
        assert any("Keine Wetterdaten vorhanden" in str(o) for o in outputs)

    def test_training_proceeds_with_weather_data(self, tmp_path):
        """Test: Training läuft wenn Wetterdaten vorhanden sind."""
        outputs = []

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: "",
        )

        with patch("pvforecast.config._default_model_path") as mock_model_path:
            mock_model_path.return_value = tmp_path / "model.pkl"

            # Mock Database mit Wetterdaten
            with patch("pvforecast.db.Database") as MockDB:
                mock_db = MagicMock()
                mock_db.get_weather_count.return_value = 1000  # Wetterdaten vorhanden!
                MockDB.return_value = mock_db

                # Mock train function
                with patch("pvforecast.model.train") as mock_train:
                    mock_model = MagicMock()
                    mock_metrics = {"mape": 0.25}
                    mock_train.return_value = (mock_model, mock_metrics)

                    # Mock save_model
                    with patch("pvforecast.model.save_model"):
                        from pvforecast.config import Config
                        config = Config(
                            latitude=51.83,
                            longitude=7.28,
                            peak_kwp=9.92,
                            db_path=tmp_path / "test.db",
                        )

                        result = wizard._execute_training("rf", config)

        # Training sollte erfolgreich sein
        assert result is True
        assert wizard._training_completed is True
        # Keine Warnung über fehlende Wetterdaten
        assert not any("Keine Wetterdaten vorhanden" in str(o) for o in outputs)


class TestFetchWeatherForTraining:
    """Tests für _fetch_weather_for_training Methode."""

    def test_fetch_weather_declined(self, tmp_path):
        """Test: Benutzer lehnt Wetterdaten-Laden ab."""
        outputs = []
        inputs = iter(["n"])  # Ablehnen

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        from pvforecast.config import Config
        config = Config(
            latitude=51.83,
            longitude=7.28,
            peak_kwp=9.92,
            db_path=tmp_path / "test.db",
        )

        result = wizard._fetch_weather_for_training(config)

        assert result == 0

    def test_fetch_weather_no_pv_data(self, tmp_path):
        """Test: Fehler wenn keine PV-Daten vorhanden."""
        outputs = []
        inputs = iter(["j"])  # Zustimmen

        wizard = SetupWizard(
            output_func=lambda x: outputs.append(x),
            input_func=lambda _: next(inputs),
        )

        with patch("pvforecast.db.Database") as MockDB:
            mock_db = MagicMock()
            mock_db.get_pv_date_range.return_value = None  # Keine PV-Daten
            MockDB.return_value = mock_db

            from pvforecast.config import Config
            config = Config(
                latitude=51.83,
                longitude=7.28,
                peak_kwp=9.92,
                db_path=tmp_path / "test.db",
            )

            result = wizard._fetch_weather_for_training(config)

        assert result == 0
        assert any("Keine PV-Daten" in str(o) for o in outputs)
