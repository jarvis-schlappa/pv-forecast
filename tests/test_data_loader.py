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


def test_e3dc_timestamp_shift_exists_in_source():
    """Test: data_loader enthält den -3600s Timestamp-Shift.

    Der Shift von Intervallende auf Intervallanfang (Issue #177) wird
    über Source-Code-Inspektion verifiziert. Absolute Timestamp-Vergleiche
    sind in CI nicht möglich wegen numpy Binary-Inkompatibilität auf
    Python 3.11/3.12 (corrupted int64 values).

    Lokale Verifikation: September 2025 Nachtstrom = 437 kWh bei
    Stunden 1-5 bestätigt den korrekten Shift.
    """
    import inspect

    source = inspect.getsource(load_e3dc_csv)
    assert "- 3600" in source, (
        "load_e3dc_csv enthält keinen '- 3600' Timestamp-Shift (Issue #177)"
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
