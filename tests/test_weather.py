"""Tests für weather.py."""

from datetime import date, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from pvforecast.weather import find_weather_gaps

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
