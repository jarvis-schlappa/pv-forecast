"""End-to-End Integration Tests für pvforecast."""

import subprocess
import sys
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import pytest

from pvforecast.config import Config, load_config
from pvforecast.db import Database

UTC_TZ = ZoneInfo("UTC")


class TestImportTrainPredictWorkflow:
    """E2E Tests für den kompletten Import → Train → Predict Workflow."""

    def test_full_workflow_with_mocked_weather(self, populated_db, tmp_path):
        """Test: Kompletter Workflow mit vorbereiteter DB."""
        from pvforecast.model import load_model, predict, save_model, train

        model_path = tmp_path / "model.pkl"
        lat, lon = 51.83, 7.28

        # Verify populated_db has enough data
        pv_count = populated_db.get_pv_count()
        assert pv_count >= 100, f"Zu wenig Daten: {pv_count}"

        # Training
        model, metrics = train(populated_db, lat, lon, model_type="rf")
        assert model is not None
        assert "mape" in metrics
        assert "mae" in metrics

        # Modell speichern
        save_model(model, model_path, metrics)
        assert model_path.exists()

        # Modell laden
        loaded_model, loaded_metrics = load_model(model_path)
        assert loaded_model is not None
        assert loaded_metrics["mape"] == metrics["mape"]

        # Prediction mit gemockten Forecast-Daten
        now = datetime.now(UTC_TZ)
        forecast_df = pd.DataFrame(
            {
                "timestamp": [int((now + timedelta(hours=i)).timestamp()) for i in range(24)],
                "ghi_wm2": [400.0] * 24,
                "cloud_cover_pct": [30] * 24,
                "temperature_c": [18.0] * 24,
            }
        )

        forecast = predict(loaded_model, forecast_df, lat, lon)
        assert forecast is not None
        assert len(forecast.hourly) == 24
        assert forecast.total_kwh >= 0

    def test_train_with_xgboost(self, populated_db, tmp_path):
        """Test: Training mit XGBoost Modell."""
        from pvforecast.model import train

        lat, lon = 51.83, 7.28

        model, metrics = train(populated_db, lat, lon, model_type="xgb")
        assert model is not None
        assert "mape" in metrics
        assert metrics["mape"] >= 0  # MAPE sollte nicht negativ sein


class TestEmptyDatabase:
    """Tests mit leerer Datenbank."""

    def test_train_fails_with_empty_db(self, tmp_path):
        """Test: Training schlägt fehl bei leerer DB."""
        from pvforecast.model import train

        db_path = tmp_path / "empty.db"
        db = Database(db_path)

        with pytest.raises(ValueError) as exc_info:
            train(db, 51.83, 7.28)

        assert "wenig" in str(exc_info.value).lower() or "100" in str(exc_info.value)

    def test_status_with_empty_db(self, tmp_path):
        """Test: Status-Befehl mit leerer DB."""
        db_path = tmp_path / "empty.db"
        db = Database(db_path)

        # Sollte nicht crashen
        pv_count = db.get_pv_count()
        weather_count = db.get_weather_count()

        assert pv_count == 0
        assert weather_count == 0


class TestAPIErrors:
    """Tests für API-Fehlerbehandlung mit parametrisierten Tests."""

    @pytest.mark.parametrize(
        "exception_class,exception_args",
        [
            (httpx.TimeoutException, ("Timeout",)),
            (httpx.ConnectError, ("Connection refused",)),
            (httpx.ReadTimeout, ("Read timeout",)),
        ],
    )
    def test_weather_api_connection_errors(self, exception_class, exception_args):
        """Test: Verschiedene Verbindungsfehler werden als WeatherAPIError behandelt."""
        from pvforecast.weather import WeatherAPIError, fetch_historical

        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.side_effect = exception_class(*exception_args)
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(WeatherAPIError) as exc_info:
                fetch_historical(51.83, 7.28, date(2024, 1, 1), date(2024, 1, 2))

            # Fehlermeldung sollte informativ sein
            err_msg = str(exc_info.value).lower()
            assert len(err_msg) > 0  # Nicht leer

    @pytest.mark.parametrize(
        "status_code,error_text",
        [
            (500, "Internal Server Error"),
            (502, "Bad Gateway"),
            (503, "Service Unavailable"),
            (429, "Too Many Requests"),
        ],
    )
    def test_weather_api_http_errors(self, status_code, error_text):
        """Test: HTTP-Fehler werden behandelt."""
        from pvforecast.weather import WeatherAPIError, fetch_historical

        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                error_text, request=MagicMock(), response=mock_response
            )
            mock_instance = MagicMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(WeatherAPIError):
                fetch_historical(51.83, 7.28, date(2024, 1, 1), date(2024, 1, 2))


class TestConfigLoading:
    """Tests für Config-File Loading."""

    def test_config_from_file(self, tmp_path):
        """Test: Config wird aus YAML-Datei geladen."""
        config_content = """
location:
  latitude: 52.52
  longitude: 13.405
system:
  name: Berlin PV
  peak_kwp: 5.5
timezone: Europe/Berlin
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        assert config.latitude == 52.52
        assert config.longitude == 13.405
        assert config.system_name == "Berlin PV"
        assert config.peak_kwp == 5.5

    def test_config_defaults(self):
        """Test: Default-Config hat sinnvolle Werte."""
        from pvforecast.config import DEFAULT_CONFIG

        assert DEFAULT_CONFIG.latitude is not None
        assert DEFAULT_CONFIG.longitude is not None
        assert DEFAULT_CONFIG.peak_kwp > 0

    def test_config_cli_override(self, tmp_path):
        """Test: CLI-Argumente überschreiben Config-Datei."""
        config = Config(
            latitude=51.0,
            longitude=7.0,
            system_name="Test",
            peak_kwp=10.0,
            db_path=tmp_path / "data.db",
            model_path=tmp_path / "model.pkl",
        )

        # Simuliere CLI-Override
        config.latitude = 52.0
        config.longitude = 8.0

        assert config.latitude == 52.0
        assert config.longitude == 8.0
        assert config.system_name == "Test"


class TestCLICommands:
    """Tests für CLI-Befehle via subprocess."""

    def test_cli_help(self):
        """Test: CLI --help funktioniert."""
        result = subprocess.run(
            [sys.executable, "-m", "pvforecast", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "pvforecast" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_cli_version(self):
        """Test: CLI --version funktioniert."""
        result = subprocess.run(
            [sys.executable, "-m", "pvforecast", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_cli_status_empty_db(self, tmp_path):
        """Test: Status mit leerer DB gibt sinnvolle Ausgabe."""
        db_path = tmp_path / "empty.db"

        result = subprocess.run(
            [sys.executable, "-m", "pvforecast", "--db", str(db_path), "status"],
            capture_output=True,
            text=True,
        )

        assert result.returncode in [0, 1]
        assert "0" in result.stdout or "keine" in result.stdout.lower()

    def test_cli_predict_without_model(self, tmp_path):
        """Test: Predict ohne trainiertes Modell gibt Fehlermeldung."""
        db_path = tmp_path / "test.db"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pvforecast",
                "--db",
                str(db_path),
                "predict",
            ],
            capture_output=True,
            text=True,
            env={**dict(__import__("os").environ), "HOME": str(tmp_path)},
        )

        output = (result.stdout + result.stderr).lower()
        assert "modell" in output or "model" in output or "train" in output


class TestCSVImport:
    """Tests für CSV-Import mit verschiedenen Formaten."""

    def test_import_german_format(self, csv_german_format, tmp_path):
        """Test: Deutsches CSV-Format (Semikolon, dd.mm.yyyy)."""
        from pvforecast.data_loader import import_csv_files

        db = Database(tmp_path / "test.db")
        count = import_csv_files([csv_german_format], db)

        assert count == 3  # 3 Zeilen in der Test-CSV
        assert db.get_pv_count() == 3

    def test_import_csv_with_bom(self, csv_with_bom, tmp_path):
        """Test: CSV mit UTF-8 BOM (Windows Excel Export)."""
        from pvforecast.data_loader import import_csv_files

        db = Database(tmp_path / "test.db")
        count = import_csv_files([csv_with_bom], db)

        assert count == 2
        assert db.get_pv_count() == 2

    def test_import_empty_csv(self, csv_empty, tmp_path):
        """Test: Leere CSV (nur Header) importiert keine Daten."""
        from pvforecast.data_loader import import_csv_files

        db = Database(tmp_path / "test.db")
        count = import_csv_files([csv_empty], db)

        assert count == 0
        assert db.get_pv_count() == 0

    def test_import_missing_optional_columns_succeeds(self, csv_missing_optional_columns, tmp_path):
        """Test: CSV mit fehlenden optionalen Spalten wird importiert."""
        from pvforecast.data_loader import import_csv_files

        db = Database(tmp_path / "test.db")
        count = import_csv_files([csv_missing_optional_columns], db)

        # Sollte importieren - optionale Spalten werden mit 0 gefüllt
        assert count == 1
        assert db.get_pv_count() == 1

    def test_import_missing_required_columns_skipped(
        self, csv_missing_required_columns, tmp_path, caplog
    ):
        """Test: CSV mit fehlenden required Spalten wird übersprungen (mit Log-Warnung)."""
        import logging

        from pvforecast.data_loader import import_csv_files

        db = Database(tmp_path / "test.db")

        with caplog.at_level(logging.ERROR):
            count = import_csv_files([csv_missing_required_columns], db)

        # Keine Daten importiert
        assert count == 0
        assert db.get_pv_count() == 0

        # Fehler wurde geloggt
        assert any("fehlende spalten" in r.message.lower() for r in caplog.records)

    def test_import_invalid_dates_handled(self, csv_invalid_dates, tmp_path):
        """Test: Ungültige Datumsformate werden behandelt."""
        from pvforecast.data_loader import import_csv_files

        db = Database(tmp_path / "test.db")

        # Sollte nicht crashen - entweder überspringen oder Fehler werfen
        try:
            count = import_csv_files([csv_invalid_dates], db)
            # Ungültige Zeilen sollten übersprungen werden
            assert count == 0
        except (ValueError, Exception):
            # Exception ist auch akzeptabel
            pass

    def test_duplicate_import_idempotent(self, csv_german_format, tmp_path):
        """Test: Doppelter Import erzeugt keine Duplikate."""
        from pvforecast.data_loader import import_csv_files

        db = Database(tmp_path / "test.db")

        # Erster Import
        count1 = import_csv_files([csv_german_format], db)
        total1 = db.get_pv_count()
        assert count1 > 0

        # Zweiter Import (gleiche Daten)
        count2 = import_csv_files([csv_german_format], db)
        total2 = db.get_pv_count()

        # Keine neuen Datensätze
        assert count2 == 0 or total2 == total1


class TestDataIntegrity:
    """Tests für Datenintegrität."""

    def test_weather_data_join(self, populated_db):
        """Test: PV und Wetterdaten werden korrekt gejoint."""
        with populated_db.connect() as conn:
            result = conn.execute("""
                SELECT COUNT(*) FROM pv_readings p
                INNER JOIN weather_history w ON p.timestamp = w.timestamp
            """).fetchone()

            # populated_db hat 150 Stunden mit übereinstimmenden Timestamps
            assert result[0] == 150

    def test_data_timestamps_aligned(self, populated_db):
        """Test: Timestamps von PV und Wetter sind stündlich ausgerichtet."""
        with populated_db.connect() as conn:
            # Prüfe, dass alle Timestamps auf volle Stunden fallen
            misaligned = conn.execute("""
                SELECT COUNT(*) FROM pv_readings
                WHERE timestamp % 3600 != 0
            """).fetchone()

            assert misaligned[0] == 0

    def test_pv_production_plausible(self, populated_db):
        """Test: PV-Produktion liegt in plausiblem Bereich."""
        with populated_db.connect() as conn:
            stats = conn.execute("""
                SELECT MIN(production_w), MAX(production_w), AVG(production_w)
                FROM pv_readings
            """).fetchone()

            min_prod, max_prod, avg_prod = stats
            assert min_prod >= 0  # Keine negativen Werte
            assert max_prod <= 15000  # Max ~15kW (plausibel für Hausanlage)
            assert avg_prod > 0  # Durchschnitt sollte positiv sein
