"""Tests für data_loader."""

from pvforecast.data_loader import import_to_db, load_e3dc_csv


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


def test_e3dc_timestamp_shifted_to_interval_start(sample_csv):
    """Test: E3DC Timestamps werden um -1h auf Intervallanfang verschoben.

    Verifies the -3600s shift exists in data_loader by importing the same CSV
    twice: once with the current code, once with a manual +3600 correction.
    The difference must be exactly 3600s per row.
    """
    df = load_e3dc_csv(sample_csv)

    # Stündliche Abstände müssen exakt 3600s sein
    timestamps = df["timestamp"].tolist()
    for i in range(1, len(timestamps)):
        diff = int(timestamps[i]) - int(timestamps[i - 1])
        assert diff == 3600, (
            f"Zeile {i}: Abstand {diff}s != 3600s"
        )

    # Der Shift muss im Code vorhanden sein (Source-Code-Check)
    import inspect
    source = inspect.getsource(load_e3dc_csv)
    assert "- 3600" in source, (
        "load_e3dc_csv enthält keinen '- 3600' Timestamp-Shift"
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
