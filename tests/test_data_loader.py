"""Tests für data_loader."""

from datetime import datetime, timezone

import pytest

from pvforecast.data_loader import import_to_db, load_e3dc_csv

# numpy binary incompatibility on Python 3.11 corrupts int64 timestamps
_NUMPY_BROKEN = False
try:
    import numpy as np
    a = np.array([1717210800], dtype="int64")
    if int(a[0]) != 1717210800:
        _NUMPY_BROKEN = True
except Exception:
    pass


def test_load_e3dc_csv(sample_csv):
    """Test: CSV wird korrekt geladen."""
    df = load_e3dc_csv(sample_csv)

    assert len(df) == 15
    assert "timestamp" in df.columns
    assert "production_w" in df.columns
    assert "curtailed" in df.columns

    # Prüfe Werte
    assert df["production_w"].max() == 4200
    assert df["production_w"].min() == 0


@pytest.mark.skipif(_NUMPY_BROKEN, reason="numpy binary incompatibility corrupts int64")
def test_e3dc_timestamp_shifted_to_interval_start(sample_csv):
    """Test: E3DC Timestamps werden um -1h auf Intervallanfang verschoben.

    E3DC exportiert Timestamps am Intervallende: 06:00 CEST = Produktion 05:00-06:00.
    Nach Import soll der Timestamp den Intervallanfang repräsentieren (05:00 CEST = 03:00 UTC).
    """
    df = load_e3dc_csv(sample_csv)

    # sample_csv erste Zeile: "01.06.2024 06:00:00" (CEST = UTC+2)
    # E3DC-Timestamp 06:00 CEST = 04:00 UTC (Intervallende)
    # Nach Shift -1h: 03:00 UTC (Intervallanfang = 05:00 CEST)
    first_ts = int(df["timestamp"].iloc[0])
    expected = int(datetime(2024, 6, 1, 3, 0, 0, tzinfo=timezone.utc).timestamp())
    assert first_ts == expected, (
        f"Erster Timestamp {first_ts} != erwartet {expected} "
        f"(06:00 CEST → 04:00 UTC → -1h = 03:00 UTC)"
    )

    # Zusätzlich: Differenz zwischen erstem und zweitem Timestamp = 3600s (1h)
    second_ts = int(df["timestamp"].iloc[1])
    assert second_ts - first_ts == 3600, (
        f"Stunden-Abstand {second_ts - first_ts}s != 3600s"
    )


def test_import_to_db(sample_csv, temp_db):
    """Test: Import in Datenbank funktioniert."""
    df = load_e3dc_csv(sample_csv)
    count = import_to_db(df, temp_db)

    assert count == 15
    assert temp_db.get_pv_count() == 15


def test_import_idempotent(sample_csv, temp_db):
    """Test: Doppelter Import fügt keine Duplikate ein."""
    df = load_e3dc_csv(sample_csv)

    count1 = import_to_db(df, temp_db)
    import_to_db(df, temp_db)

    assert count1 == 15
    # Zweiter Import sollte keine neuen Zeilen einfügen
    assert temp_db.get_pv_count() == 15
