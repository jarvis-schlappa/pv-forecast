"""Tests für weather.py."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import pytest

from pvforecast.weather import (
    WeatherAPIError,
    _request_with_retry,
    find_weather_gaps,
)

UTC_TZ = ZoneInfo("UTC")


def get_month_hours(year: int, month: int) -> int:
    """Berechnet Stunden in einem Monat."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    days = (next_month - date(year, month, 1)).days
    return days * 24


@pytest.fixture
def mock_db_with_gaps():
    """Mock-DB die Lücken in 2022 und 2023 simuliert."""
    db = MagicMock()
    conn = MagicMock()
    db.connect.return_value.__enter__ = MagicMock(return_value=conn)
    db.connect.return_value.__exit__ = MagicMock(return_value=False)

    def mock_execute(query, params=None):
        result = MagicMock()
        if "COUNT" in query and params:
            start_ts, _ = params
            start_dt = datetime.fromtimestamp(start_ts, UTC_TZ)

            # Simuliere: 2019-2021 und 2024-2025 haben Daten, 2022-2023 nicht
            if start_dt.year in (2022, 2023):
                result.fetchone.return_value = (0,)  # Keine Daten
            else:
                # Volle Daten für den Monat
                hours = get_month_hours(start_dt.year, start_dt.month)
                result.fetchone.return_value = (hours,)
        return result

    conn.execute = mock_execute
    return db


@pytest.fixture
def mock_db_complete():
    """Mock-DB die vollständige Daten simuliert."""
    db = MagicMock()
    conn = MagicMock()
    db.connect.return_value.__enter__ = MagicMock(return_value=conn)
    db.connect.return_value.__exit__ = MagicMock(return_value=False)

    def mock_execute(query, params=None):
        result = MagicMock()
        if "COUNT" in query and params:
            start_ts, _ = params
            start_dt = datetime.fromtimestamp(start_ts, UTC_TZ)
            # Volle Daten für den Monat
            hours = get_month_hours(start_dt.year, start_dt.month)
            result.fetchone.return_value = (hours,)
        return result

    conn.execute = mock_execute
    return db


def test_find_weather_gaps_detects_missing_years(mock_db_with_gaps):
    """Test: Lücken in 2022 und 2023 werden erkannt."""
    start_ts = int(datetime(2019, 1, 1, tzinfo=UTC_TZ).timestamp())
    end_ts = int(datetime(2025, 12, 31, tzinfo=UTC_TZ).timestamp())

    gaps = find_weather_gaps(mock_db_with_gaps, start_ts, end_ts)

    # Sollte Lücken für 2022 und 2023 finden (24 Monate)
    assert len(gaps) == 24

    # Prüfe dass 2022 und 2023 dabei sind
    gap_years = {g[0].year for g in gaps}
    assert 2022 in gap_years
    assert 2023 in gap_years

    # 2019, 2020, 2021, 2024, 2025 sollten NICHT dabei sein
    assert 2019 not in gap_years
    assert 2020 not in gap_years
    assert 2021 not in gap_years
    assert 2024 not in gap_years
    assert 2025 not in gap_years


def test_find_weather_gaps_no_gaps(mock_db_complete):
    """Test: Keine Lücken bei vollständigen Daten."""
    start_ts = int(datetime(2024, 1, 1, tzinfo=UTC_TZ).timestamp())
    end_ts = int(datetime(2024, 12, 31, tzinfo=UTC_TZ).timestamp())

    gaps = find_weather_gaps(mock_db_complete, start_ts, end_ts)

    assert len(gaps) == 0


def test_find_weather_gaps_single_month():
    """Test: Einzelner fehlender Monat wird erkannt."""
    db = MagicMock()
    conn = MagicMock()
    db.connect.return_value.__enter__ = MagicMock(return_value=conn)
    db.connect.return_value.__exit__ = MagicMock(return_value=False)

    def mock_execute(query, params=None):
        result = MagicMock()
        if "COUNT" in query:
            result.fetchone.return_value = (0,)  # Keine Daten
        return result

    conn.execute = mock_execute

    start_ts = int(datetime(2024, 3, 1, tzinfo=UTC_TZ).timestamp())
    end_ts = int(datetime(2024, 3, 31, tzinfo=UTC_TZ).timestamp())

    gaps = find_weather_gaps(db, start_ts, end_ts)

    assert len(gaps) == 1
    assert gaps[0][0] == date(2024, 3, 1)
    assert gaps[0][1] == date(2024, 3, 31)


def test_find_weather_gaps_respects_min_gap_hours():
    """Test: min_gap_hours Parameter wird beachtet."""
    db = MagicMock()
    conn = MagicMock()
    db.connect.return_value.__enter__ = MagicMock(return_value=conn)
    db.connect.return_value.__exit__ = MagicMock(return_value=False)

    def mock_execute(query, params=None):
        result = MagicMock()
        if "COUNT" in query:
            # Fast volle Daten für Januar (744h - 10h = 734h)
            result.fetchone.return_value = (734,)
        return result

    conn.execute = mock_execute

    start_ts = int(datetime(2024, 1, 1, tzinfo=UTC_TZ).timestamp())
    end_ts = int(datetime(2024, 1, 31, tzinfo=UTC_TZ).timestamp())

    # Mit min_gap_hours=24: 10 fehlende Stunden < 24, keine Lücke
    gaps = find_weather_gaps(db, start_ts, end_ts, min_gap_hours=24)
    assert len(gaps) == 0

    # Mit min_gap_hours=5: 10 fehlende Stunden >= 5, Lücke!
    gaps = find_weather_gaps(db, start_ts, end_ts, min_gap_hours=5)
    assert len(gaps) == 1


# === Retry-Logic Tests ===


class TestRequestWithRetry:
    """Tests für _request_with_retry Funktion."""

    def test_success_on_first_attempt(self):
        """Test: Erfolg beim ersten Versuch."""
        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": "test"}
            mock_client.return_value.__enter__.return_value.get.return_value = (
                mock_response
            )

            result = _request_with_retry(
                "https://api.test.com", {"param": "value"}, max_retries=3
            )

            assert result == {"data": "test"}
            # Nur ein Aufruf
            assert mock_client.return_value.__enter__.return_value.get.call_count == 1

    def test_retry_on_timeout(self):
        """Test: Retry bei Timeout-Fehler."""
        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_get = mock_client.return_value.__enter__.return_value.get

            # Erster Versuch: Timeout, zweiter: Erfolg
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": "success"}
            mock_get.side_effect = [
                httpx.TimeoutException("Timeout"),
                mock_response,
            ]

            with patch("pvforecast.weather.time.sleep"):  # Skip delays
                result = _request_with_retry(
                    "https://api.test.com", {}, max_retries=3
                )

            assert result == {"data": "success"}
            assert mock_get.call_count == 2

    def test_retry_on_connect_error(self):
        """Test: Retry bei Verbindungsfehler."""
        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_get = mock_client.return_value.__enter__.return_value.get

            # Zwei Verbindungsfehler, dann Erfolg
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": "success"}
            mock_get.side_effect = [
                httpx.ConnectError("Connection refused"),
                httpx.ConnectError("Connection refused"),
                mock_response,
            ]

            with patch("pvforecast.weather.time.sleep"):
                result = _request_with_retry(
                    "https://api.test.com", {}, max_retries=3
                )

            assert result == {"data": "success"}
            assert mock_get.call_count == 3

    def test_fail_after_max_retries(self):
        """Test: Fehlschlag nach allen Retries."""
        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_get = mock_client.return_value.__enter__.return_value.get
            mock_get.side_effect = httpx.TimeoutException("Timeout")

            with patch("pvforecast.weather.time.sleep"):
                with pytest.raises(WeatherAPIError) as exc_info:
                    _request_with_retry(
                        "https://api.test.com", {}, max_retries=3
                    )

            assert "Fehlgeschlagen nach 3 Versuchen" in str(exc_info.value)
            assert mock_get.call_count == 3

    def test_no_retry_on_client_error(self):
        """Test: Kein Retry bei HTTP 4xx Fehlern."""
        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_get = mock_client.return_value.__enter__.return_value.get

            # 404 Fehler - sollte nicht wiederholt werden
            mock_response = MagicMock()
            mock_response.status_code = 404
            error = httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_response
            )
            mock_get.side_effect = error

            with pytest.raises(WeatherAPIError) as exc_info:
                _request_with_retry("https://api.test.com", {}, max_retries=3)

            assert "API-Fehler: 404" in str(exc_info.value)
            # Nur ein Versuch bei Client-Fehlern
            assert mock_get.call_count == 1

    def test_retry_on_server_error(self):
        """Test: Retry bei HTTP 5xx Fehlern."""
        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_get = mock_client.return_value.__enter__.return_value.get

            # 503 Fehler, dann Erfolg
            mock_error_response = MagicMock()
            mock_error_response.status_code = 503
            error = httpx.HTTPStatusError(
                "Service Unavailable", request=MagicMock(), response=mock_error_response
            )

            mock_success_response = MagicMock()
            mock_success_response.json.return_value = {"data": "success"}

            mock_get.side_effect = [error, mock_success_response]

            with patch("pvforecast.weather.time.sleep"):
                result = _request_with_retry(
                    "https://api.test.com", {}, max_retries=3
                )

            assert result == {"data": "success"}
            assert mock_get.call_count == 2

    def test_retry_on_rate_limit_429(self):
        """Test: Retry bei HTTP 429 (Rate Limit)."""
        with patch("pvforecast.weather.httpx.Client") as mock_client:
            mock_get = mock_client.return_value.__enter__.return_value.get

            # 429 Rate Limit, dann Erfolg
            mock_error_response = MagicMock()
            mock_error_response.status_code = 429
            error = httpx.HTTPStatusError(
                "Too Many Requests", request=MagicMock(), response=mock_error_response
            )

            mock_success_response = MagicMock()
            mock_success_response.json.return_value = {"data": "success"}

            mock_get.side_effect = [error, mock_success_response]

            with patch("pvforecast.weather.time.sleep"):
                with patch("pvforecast.weather.random.random", return_value=0.5):
                    result = _request_with_retry(
                        "https://api.test.com", {}, max_retries=3
                    )

            assert result == {"data": "success"}
            assert mock_get.call_count == 2


# === Bulk Insert Tests ===


class TestSaveWeatherToDb:
    """Tests für save_weather_to_db()."""

    def test_save_empty_dataframe(self, tmp_path):
        """Test: Leerer DataFrame gibt 0 zurück."""
        from pvforecast.db import Database
        from pvforecast.weather import save_weather_to_db

        db = Database(tmp_path / "test.db")


        df = pd.DataFrame(columns=["timestamp", "ghi_wm2", "cloud_cover_pct", "temperature_c"])
        result = save_weather_to_db(df, db)

        assert result == 0

    def test_save_single_record(self, tmp_path):
        """Test: Einzelner Datensatz wird gespeichert."""
        from pvforecast.db import Database
        from pvforecast.weather import save_weather_to_db

        db = Database(tmp_path / "test.db")


        df = pd.DataFrame([{
            "timestamp": 1704067200,  # 2024-01-01 00:00 UTC
            "ghi_wm2": 100.0,
            "cloud_cover_pct": 50,
            "temperature_c": 10.0,
        }])
        result = save_weather_to_db(df, db)

        assert result == 1
        assert db.get_weather_count() == 1

    def test_save_multiple_records(self, tmp_path):
        """Test: Mehrere Datensätze werden in einem Bulk gespeichert."""
        from pvforecast.db import Database
        from pvforecast.weather import save_weather_to_db

        db = Database(tmp_path / "test.db")


        # 100 Datensätze
        records = [
            {
                "timestamp": 1704067200 + i * 3600,
                "ghi_wm2": float(i * 10),
                "cloud_cover_pct": i % 100,
                "temperature_c": 10.0 + i * 0.1,
            }
            for i in range(100)
        ]
        df = pd.DataFrame(records)
        result = save_weather_to_db(df, db)

        assert result == 100
        assert db.get_weather_count() == 100

    def test_save_replaces_existing(self, tmp_path):
        """Test: Bestehende Datensätze werden ersetzt (REPLACE)."""
        from pvforecast.db import Database
        from pvforecast.weather import save_weather_to_db

        db = Database(tmp_path / "test.db")


        # Erster Insert
        df1 = pd.DataFrame([{
            "timestamp": 1704067200,
            "ghi_wm2": 100.0,
            "cloud_cover_pct": 50,
            "temperature_c": 10.0,
        }])
        save_weather_to_db(df1, db)

        # Zweiter Insert mit gleichem Timestamp, anderen Werten
        df2 = pd.DataFrame([{
            "timestamp": 1704067200,
            "ghi_wm2": 200.0,  # Geändert
            "cloud_cover_pct": 75,  # Geändert
            "temperature_c": 15.0,  # Geändert
        }])
        save_weather_to_db(df2, db)

        # Sollte immer noch nur 1 Datensatz sein (ersetzt, nicht doppelt)
        assert db.get_weather_count() == 1

        # Werte sollten die neuen sein
        with db.connect() as conn:
            row = conn.execute(
                "SELECT ghi_wm2, cloud_cover_pct FROM weather_history WHERE timestamp = ?",
                (1704067200,)
            ).fetchone()
            assert row[0] == 200.0
            assert row[1] == 75


class TestExtendedWeatherFeatures:
    """Tests für erweiterte Wetter-Features (Wind, Humidity, DHI)."""

    def test_save_extended_features(self, tmp_path):
        """Test: Erweiterte Features werden gespeichert."""
        from pvforecast.db import Database
        from pvforecast.weather import save_weather_to_db

        db = Database(tmp_path / "test.db")

        df = pd.DataFrame([{
            "timestamp": 1704067200,
            "ghi_wm2": 500.0,
            "cloud_cover_pct": 30,
            "temperature_c": 15.0,
            "wind_speed_ms": 5.5,
            "humidity_pct": 65,
            "dhi_wm2": 150.0,
        }])
        result = save_weather_to_db(df, db)

        assert result == 1

        with db.connect() as conn:
            row = conn.execute(
                """SELECT wind_speed_ms, humidity_pct, dhi_wm2
                   FROM weather_history WHERE timestamp = ?""",
                (1704067200,)
            ).fetchone()
            assert row[0] == 5.5
            assert row[1] == 65
            assert row[2] == 150.0

    def test_parse_response_with_extended_features(self):
        """Test: API-Response mit erweiterten Features wird korrekt geparst."""
        from pvforecast.weather import _parse_weather_response

        data = {
            "hourly": {
                "time": ["2024-01-01T12:00", "2024-01-01T13:00"],
                "shortwave_radiation": [500.0, 600.0],
                "cloud_cover": [30, 40],
                "temperature_2m": [15.0, 16.0],
                "wind_speed_10m": [5.5, 6.0],
                "relative_humidity_2m": [65, 70],
                "diffuse_radiation": [150.0, 180.0],
            }
        }

        df = _parse_weather_response(data)

        assert len(df) == 2
        assert df["wind_speed_ms"].iloc[0] == 5.5
        assert df["humidity_pct"].iloc[0] == 65
        assert df["dhi_wm2"].iloc[0] == 150.0

    def test_parse_response_missing_extended_features(self):
        """Test: Fehlende erweiterte Features bekommen Defaults."""
        from pvforecast.weather import _parse_weather_response

        data = {
            "hourly": {
                "time": ["2024-01-01T12:00"],
                "shortwave_radiation": [500.0],
                "cloud_cover": [30],
                "temperature_2m": [15.0],
                # Keine erweiterten Features
            }
        }

        df = _parse_weather_response(data)

        assert len(df) == 1
        assert df["wind_speed_ms"].iloc[0] == 0.0  # Default
        assert df["humidity_pct"].iloc[0] == 50    # Default
        assert df["dhi_wm2"].iloc[0] == 0.0        # Default

    def test_db_migration_adds_columns(self, tmp_path):
        """Test: DB-Migration fügt neue Spalten hinzu."""
        import sqlite3

        db_path = tmp_path / "test.db"

        # Erstelle alte DB ohne neue Spalten
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE weather_history (
                timestamp INTEGER PRIMARY KEY,
                ghi_wm2 REAL NOT NULL,
                cloud_cover_pct INTEGER,
                temperature_c REAL
            )
        """)
        conn.execute("""
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)
        """)
        conn.execute("INSERT INTO metadata VALUES ('schema_version', '1')")
        conn.execute("""
            INSERT INTO weather_history VALUES (1704067200, 500.0, 30, 15.0)
        """)
        conn.commit()
        conn.close()

        # Jetzt mit Database öffnen - sollte migrieren
        from pvforecast.db import Database
        db = Database(db_path)

        # Prüfe dass neue Spalten existieren
        with db.connect() as conn:
            cursor = conn.execute("PRAGMA table_info(weather_history)")
            columns = {row[1] for row in cursor.fetchall()}

            assert "wind_speed_ms" in columns
            assert "humidity_pct" in columns
            assert "dhi_wm2" in columns

            # Alte Daten sollten NULL haben für neue Spalten
            row = conn.execute(
                "SELECT wind_speed_ms, humidity_pct, dhi_wm2 FROM weather_history"
            ).fetchone()
            assert row[0] is None
            assert row[1] is None
            assert row[2] is None


class TestFetchToday:
    """Tests für fetch_today Funktion."""

    def test_fetch_today_uses_retry_logic(self):
        """Test: fetch_today nutzt _request_with_retry."""
        from pvforecast.weather import fetch_today

        tz = ZoneInfo("Europe/Berlin")
        mock_now = datetime(2026, 2, 6, 12, 0, tzinfo=tz)
        # 2026-02-06 12:00 UTC als Unix-Timestamp
        ts_today = 1770379200

        with patch("pvforecast.weather._request_with_retry") as mock_request, \
             patch("pvforecast.weather._parse_weather_response") as mock_parse, \
             patch("pvforecast.weather._get_now", return_value=mock_now):
            mock_request.return_value = {"hourly": {}}
            mock_parse.return_value = pd.DataFrame({
                "timestamp": [ts_today],
                "ghi_wm2": [500.0],
                "cloud_cover_pct": [30],
                "temperature_c": [10.0],
                "wind_speed_ms": [5.0],
                "humidity_pct": [60],
                "dhi_wm2": [100.0],
                "dni_wm2": [400.0],
            })

            fetch_today(51.0, 7.0, tz)

            # Prüfe dass _request_with_retry aufgerufen wurde
            mock_request.assert_called_once()
            call_args = mock_request.call_args

            # Prüfe API URL (Forecast API)
            assert "api.open-meteo.com" in call_args[0][0]

            # Prüfe dass past_hours und forecast_hours gesetzt sind
            params = call_args[0][1]
            assert "past_hours" in params
            assert "forecast_hours" in params
            # Um 12:00 sollte past_hours=14 (12+2 Puffer)
            assert params["past_hours"] == 14

    def test_fetch_today_filters_to_today(self):
        """Test: fetch_today filtert auf heute."""
        from pvforecast.weather import fetch_today

        tz = ZoneInfo("Europe/Berlin")
        mock_now = datetime(2026, 2, 6, 12, 0, tzinfo=tz)
        # UTC Zeiten als Unix-Timestamps:
        # 2026-02-05T22:00 UTC = 2026-02-05 23:00 Berlin (gestern)
        # 2026-02-05T23:00 UTC = 2026-02-06 00:00 Berlin (heute)
        # 2026-02-06T12:00 UTC = 2026-02-06 13:00 Berlin (heute)
        # 2026-02-06T23:00 UTC = 2026-02-07 00:00 Berlin (morgen)
        ts_yesterday = 1770328800  # 2026-02-05 22:00 UTC
        ts_today_1 = 1770332400    # 2026-02-05 23:00 UTC
        ts_today_2 = 1770379200    # 2026-02-06 12:00 UTC
        ts_tomorrow = 1770418800   # 2026-02-06 23:00 UTC

        with patch("pvforecast.weather._request_with_retry") as mock_request, \
             patch("pvforecast.weather._parse_weather_response") as mock_parse, \
             patch("pvforecast.weather._get_now", return_value=mock_now):
            mock_request.return_value = {"hourly": {}}
            mock_parse.return_value = pd.DataFrame({
                "timestamp": [ts_yesterday, ts_today_1, ts_today_2, ts_tomorrow],
                "ghi_wm2": [0.0, 100.0, 500.0, 0.0],
                "cloud_cover_pct": [50, 30, 20, 60],
                "temperature_c": [5.0, 6.0, 12.0, 4.0],
                "wind_speed_ms": [3.0, 4.0, 5.0, 3.0],
                "humidity_pct": [70, 65, 50, 75],
                "dhi_wm2": [0.0, 50.0, 150.0, 0.0],
                "dni_wm2": [0.0, 80.0, 400.0, 0.0],
            })

            df = fetch_today(51.0, 7.0, tz)

            # Nur Daten für heute (2026-02-06 in Berlin)
            assert len(df) == 2
            timestamps = pd.to_datetime(df["timestamp"], unit="s", utc=True)
            dates = timestamps.dt.tz_convert(tz).dt.date
            assert all(d == date(2026, 2, 6) for d in dates)

    def test_fetch_today_raises_on_no_data(self):
        """Test: fetch_today wirft Fehler wenn keine Daten für heute."""
        from pvforecast.weather import fetch_today

        tz = ZoneInfo("Europe/Berlin")
        mock_now = datetime(2026, 2, 6, 12, 0, tzinfo=tz)
        # 2026-02-04 10:00 UTC (zwei Tage vor "heute")
        ts_old = 1770199200

        with patch("pvforecast.weather._request_with_retry") as mock_request, \
             patch("pvforecast.weather._parse_weather_response") as mock_parse, \
             patch("pvforecast.weather._get_now", return_value=mock_now):
            mock_request.return_value = {"hourly": {}}
            mock_parse.return_value = pd.DataFrame({
                "timestamp": [ts_old],
                "ghi_wm2": [500.0],
                "cloud_cover_pct": [30],
                "temperature_c": [10.0],
                "wind_speed_ms": [5.0],
                "humidity_pct": [60],
                "dhi_wm2": [100.0],
                "dni_wm2": [400.0],
            })

            with pytest.raises(WeatherAPIError, match="Keine Wetterdaten für heute"):
                fetch_today(51.0, 7.0, tz)

    def test_fetch_today_accepts_string_timezone(self):
        """Test: fetch_today akzeptiert Timezone als String."""
        from pvforecast.weather import fetch_today

        tz = ZoneInfo("Europe/Berlin")
        mock_now = datetime(2026, 2, 6, 12, 0, tzinfo=tz)
        # 2026-02-06 12:00 UTC
        ts_today = 1770379200

        with patch("pvforecast.weather._request_with_retry") as mock_request, \
             patch("pvforecast.weather._parse_weather_response") as mock_parse, \
             patch("pvforecast.weather._get_now", return_value=mock_now):
            mock_request.return_value = {"hourly": {}}
            mock_parse.return_value = pd.DataFrame({
                "timestamp": [ts_today],
                "ghi_wm2": [500.0],
                "cloud_cover_pct": [30],
                "temperature_c": [10.0],
                "wind_speed_ms": [5.0],
                "humidity_pct": [60],
                "dhi_wm2": [100.0],
                "dni_wm2": [400.0],
            })

            # String statt ZoneInfo
            df = fetch_today(51.0, 7.0, "Europe/Berlin")

            assert len(df) == 1
