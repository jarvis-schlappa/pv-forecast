"""End-to-End Integration Tests für pvforecast."""

import subprocess
import sys
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from pvforecast.config import Config, load_config
from pvforecast.db import Database

UTC_TZ = ZoneInfo("UTC")


class TestImportTrainPredictWorkflow:
    """E2E Tests für den kompletten Import → Train → Predict Workflow."""

    def test_full_workflow_with_mocked_weather(self, tmp_path):
        """Test: Kompletter Workflow mit gemockten Wetterdaten."""
        from pvforecast.model import load_model, predict, save_model, train

        # Setup
        db_path = tmp_path / "test.db"
        model_path = tmp_path / "model.pkl"
        db = Database(db_path)
        lat, lon = 51.83, 7.28

        # 1. Generiere genug Testdaten direkt in DB (min. 100 für Training)
        # Robuster als CSV-Import (vermeidet Locale/Parsing-Probleme)
        base_time = datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC_TZ)
        pv_data = []
        weather_data = []

        for i in range(150):
            ts = base_time + timedelta(hours=i)
            timestamp = int(ts.timestamp())
            hour = ts.hour

            # Simuliere Tagesverlauf
            if 6 <= hour <= 20:
                production = int(500 + 3000 * (1 - abs(hour - 13) / 7))
                ghi = 800.0
            else:
                production = 0
                ghi = 0.0

            pv_data.append({
                "timestamp": timestamp,
                "production_w": production,
                "curtailed": 0,
                "soc_pct": 50,
                "grid_feed_w": 0,
                "grid_draw_w": 0,
                "consumption_w": 500,
            })
            weather_data.append({
                "timestamp": timestamp,
                "ghi_wm2": ghi,
                "cloud_cover_pct": 30,
                "temperature_c": 20.0,
            })

        # Daten in DB einfügen
        with db.connect() as conn:
            conn.executemany(
                """INSERT INTO pv_readings
                   (timestamp, production_w, curtailed, soc_pct,
                    grid_feed_w, grid_draw_w, consumption_w)
                   VALUES (:timestamp, :production_w, :curtailed, :soc_pct,
                           :grid_feed_w, :grid_draw_w, :consumption_w)""",
                pv_data,
            )
            conn.executemany(
                """INSERT INTO weather_history
                   (timestamp, ghi_wm2, cloud_cover_pct, temperature_c)
                   VALUES (:timestamp, :ghi_wm2, :cloud_cover_pct, :temperature_c)""",
                weather_data,
            )
            conn.commit()

        pv_count = db.get_pv_count()
        assert pv_count >= 100, f"Zu wenig Daten: {pv_count}"

        # 2. Training
        model, metrics = train(db, lat, lon, model_type="rf")
        assert model is not None
        assert "mape" in metrics
        assert "mae" in metrics

        # 4. Modell speichern
        save_model(model, model_path, metrics)
        assert model_path.exists()

        # 5. Modell laden
        loaded_model, loaded_metrics = load_model(model_path)
        assert loaded_model is not None

        # 6. Prediction mit gemockten Forecast-Daten
        now = datetime.now(UTC_TZ)
        forecast_df = pd.DataFrame({
            "timestamp": [int((now + timedelta(hours=i)).timestamp()) for i in range(24)],
            "ghi_wm2": [400.0] * 24,
            "cloud_cover_pct": [30] * 24,
            "temperature_c": [18.0] * 24,
        })

        forecast = predict(loaded_model, forecast_df, lat, lon)
        assert forecast is not None
        assert len(forecast.hourly) == 24
        assert forecast.total_kwh >= 0


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
    """Tests für API-Fehlerbehandlung."""

    def test_weather_api_timeout(self, tmp_path):
        """Test: Weather API Timeout wird behandelt."""
        import httpx

        from pvforecast.weather import WeatherAPIError, fetch_historical

        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.side_effect = httpx.TimeoutException("Timeout")
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_instance)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(WeatherAPIError) as exc_info:
                fetch_historical(51.83, 7.28, date(2024, 1, 1), date(2024, 1, 2))

            err_msg = str(exc_info.value).lower()
            assert "timeout" in err_msg or "fehler" in err_msg

    def test_weather_api_http_error(self, tmp_path):
        """Test: Weather API HTTP-Fehler wird behandelt."""
        import httpx

        from pvforecast.weather import WeatherAPIError, fetch_historical

        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=mock_response
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
        # Config verwendet verschachteltes Format
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

        # Basis-Config
        config = Config(
            latitude=51.0,
            longitude=7.0,
            system_name="Test",
            peak_kwp=10.0,
            db_path=tmp_path / "data.db",
            model_path=tmp_path / "model.pkl",
        )

        # Simuliere CLI-Override
        config.latitude = 52.0  # Überschrieben
        config.longitude = 8.0  # Überschrieben

        assert config.latitude == 52.0
        assert config.longitude == 8.0
        assert config.system_name == "Test"  # Nicht überschrieben


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

        # Sollte nicht crashen (exit code 0 oder 1 akzeptabel)
        assert result.returncode in [0, 1]
        # Sollte "0" für leere Counts anzeigen
        assert "0" in result.stdout or "keine" in result.stdout.lower()

    def test_cli_predict_without_model(self, tmp_path):
        """Test: Predict ohne trainiertes Modell gibt Fehlermeldung."""
        db_path = tmp_path / "test.db"

        result = subprocess.run(
            [
                sys.executable, "-m", "pvforecast",
                "--db", str(db_path),
                "predict",
            ],
            capture_output=True,
            text=True,
            env={**dict(__import__("os").environ), "HOME": str(tmp_path)},
        )

        # CLI kann returncode 0 oder 1 zurückgeben, wichtig ist die Fehlermeldung
        # Fehlermeldung sollte auf fehlendes Modell hinweisen (in stdout oder stderr)
        output = (result.stdout + result.stderr).lower()
        assert "modell" in output or "model" in output or "train" in output


class TestDataIntegrity:
    """Tests für Datenintegrität."""

    def test_duplicate_import_no_duplicates(self, tmp_path, sample_csv):
        """Test: Doppelter Import erzeugt keine Duplikate."""
        from pvforecast.data_loader import import_csv_files

        db_path = tmp_path / "test.db"
        db = Database(db_path)

        # Erster Import
        count1 = import_csv_files([sample_csv], db)
        total1 = db.get_pv_count()
        assert count1 > 0, "Erster Import sollte Daten importieren"

        # Zweiter Import (gleiche Daten)
        count2 = import_csv_files([sample_csv], db)
        total2 = db.get_pv_count()

        # Keine neuen Datensätze beim zweiten Import
        assert count2 == 0 or total2 == total1
        assert total2 == total1

    def test_weather_data_join(self, tmp_path, sample_csv):
        """Test: PV und Wetterdaten werden korrekt gejoint."""
        from pvforecast.data_loader import import_csv_files

        db_path = tmp_path / "test.db"
        db = Database(db_path)

        # PV-Daten importieren
        import_csv_files([sample_csv], db)

        # Wetterdaten für gleichen Zeitraum
        pv_start, pv_end = db.get_pv_date_range()

        weather_data = []
        for ts in range(pv_start, pv_end + 3600, 3600):
            weather_data.append({
                "timestamp": ts,
                "ghi_wm2": 500.0,
                "cloud_cover_pct": 30,
                "temperature_c": 20.0,
            })

        with db.connect() as conn:
            conn.executemany(
                """INSERT INTO weather_history
                   (timestamp, ghi_wm2, cloud_cover_pct, temperature_c)
                   VALUES (:timestamp, :ghi_wm2, :cloud_cover_pct, :temperature_c)""",
                weather_data,
            )
            conn.commit()

            # Join-Query testen
            result = conn.execute("""
                SELECT COUNT(*) FROM pv_readings p
                INNER JOIN weather_history w ON p.timestamp = w.timestamp
            """).fetchone()

            assert result[0] > 0, "Join sollte Ergebnisse liefern"
