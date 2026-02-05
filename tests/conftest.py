"""Pytest fixtures für pvforecast tests."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pvforecast.db import Database

UTC_TZ = ZoneInfo("UTC")


@pytest.fixture
def temp_db():
    """Erstellt eine temporäre Datenbank."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    db = Database(db_path)
    yield db

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def sample_csv(tmp_path):
    """Erstellt eine Test-CSV im E3DC Format (deutsches Locale)."""
    header = (
        '"Zeitstempel";"Ladezustand [%]";"Solarproduktion [W]";'
        '"Batterie Laden [W]";"Batterie Entladen [W]";"Netzeinspeisung [W]";'
        '"Netzbezug [W]";"Hausverbrauch [W]";"Abregelungsgrenze [W]"'
    )
    csv_content = f"""{header}
01.06.2024 06:00:00;50;100;0;0;0;300;400;5000
01.06.2024 07:00:00;50;500;200;0;0;100;400;5000
01.06.2024 08:00:00;55;1200;800;0;50;50;400;5000
01.06.2024 09:00:00;65;2500;1500;0;500;0;500;5000
01.06.2024 10:00:00;75;3500;2000;0;1000;0;500;5000
01.06.2024 11:00:00;85;4000;1500;0;2000;0;500;5000
01.06.2024 12:00:00;90;4200;1000;0;2700;0;500;5000
01.06.2024 13:00:00;92;3800;500;0;2800;0;500;5000
01.06.2024 14:00:00;90;3200;0;200;2500;0;500;5000
01.06.2024 15:00:00;85;2400;0;500;1400;0;500;5000
01.06.2024 16:00:00;80;1500;0;400;600;0;500;5000
01.06.2024 17:00:00;75;800;0;300;0;0;500;5000
01.06.2024 18:00:00;70;300;0;200;0;100;400;5000
01.06.2024 19:00:00;65;50;0;100;0;350;400;5000
01.06.2024 20:00:00;60;0;0;50;0;350;400;5000
"""
    csv_path = tmp_path / "test_export.csv"
    csv_path.write_text(csv_content)
    return csv_path


@pytest.fixture
def sample_weather_data():
    """
    Generiert wiederverwendbare Wetterdaten für 150 Stunden.

    Returns:
        list[dict]: Liste von Wetterdaten-Dictionaries mit timestamp, ghi_wm2,
                    cloud_cover_pct, temperature_c
    """
    base_time = datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC_TZ)
    weather_data = []

    for i in range(150):
        ts = base_time + timedelta(hours=i)
        timestamp = int(ts.timestamp())
        hour = ts.hour

        # Simuliere Tagesverlauf
        if 6 <= hour <= 20:
            ghi = 800.0 * (1 - abs(hour - 13) / 10)  # Peak um 13 Uhr
            cloud_cover = 20 + (hour % 5) * 5  # Leichte Variation
        else:
            ghi = 0.0
            cloud_cover = 50

        weather_data.append(
            {
                "timestamp": timestamp,
                "ghi_wm2": ghi,
                "cloud_cover_pct": cloud_cover,
                "temperature_c": 15.0 + 10.0 * (1 - abs(hour - 14) / 14),
            }
        )

    return weather_data


@pytest.fixture
def sample_pv_data():
    """
    Generiert wiederverwendbare PV-Daten für 150 Stunden.

    Returns:
        list[dict]: Liste von PV-Reading-Dictionaries
    """
    base_time = datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC_TZ)
    pv_data = []

    for i in range(150):
        ts = base_time + timedelta(hours=i)
        timestamp = int(ts.timestamp())
        hour = ts.hour

        # Simuliere Tagesverlauf (korreliert mit Wetter)
        if 6 <= hour <= 20:
            production = int(500 + 3000 * (1 - abs(hour - 13) / 7))
        else:
            production = 0

        pv_data.append(
            {
                "timestamp": timestamp,
                "production_w": production,
                "curtailed": 0,
                "soc_pct": 50 + (i % 40),  # Variiert zwischen 50-90%
                "grid_feed_w": max(0, production - 500),
                "grid_draw_w": max(0, 500 - production),
                "consumption_w": 500,
            }
        )

    return pv_data


@pytest.fixture
def populated_db(tmp_path, sample_pv_data, sample_weather_data):
    """
    Erstellt eine Datenbank mit 150 Stunden PV- und Wetterdaten.

    Ideal für Training- und Predict-Tests.
    """
    db_path = tmp_path / "populated.db"
    db = Database(db_path)

    with db.connect() as conn:
        conn.executemany(
            """INSERT INTO pv_readings
               (timestamp, production_w, curtailed, soc_pct,
                grid_feed_w, grid_draw_w, consumption_w)
               VALUES (:timestamp, :production_w, :curtailed, :soc_pct,
                       :grid_feed_w, :grid_draw_w, :consumption_w)""",
            sample_pv_data,
        )
        conn.executemany(
            """INSERT INTO weather_history
               (timestamp, ghi_wm2, cloud_cover_pct, temperature_c)
               VALUES (:timestamp, :ghi_wm2, :cloud_cover_pct, :temperature_c)""",
            sample_weather_data,
        )
        conn.commit()

    return db


# CSV-Fixtures für verschiedene Formate/Locales

# E3DC CSV Header (aufgeteilt für Zeilenlänge)
_CSV_HEADER_PARTS = [
    '"Zeitstempel"',
    '"Ladezustand [%]"',
    '"Solarproduktion [W]"',
    '"Batterie Laden [W]"',
    '"Batterie Entladen [W]"',
    '"Netzeinspeisung [W]"',
    '"Netzbezug [W]"',
    '"Hausverbrauch [W]"',
    '"Abregelungsgrenze [W]"',
]
CSV_HEADER = ";".join(_CSV_HEADER_PARTS)


@pytest.fixture
def csv_german_format(tmp_path):
    """CSV im deutschen Format (Semikolon, dd.mm.yyyy)."""
    content = f"""{CSV_HEADER}
01.06.2024 10:00:00;75;3500;2000;0;1000;0;500;5000
01.06.2024 11:00:00;85;4000;1500;0;2000;0;500;5000
01.06.2024 12:00:00;90;4200;1000;0;2700;0;500;5000
"""
    path = tmp_path / "german.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def csv_with_bom(tmp_path):
    """CSV mit UTF-8 BOM (Windows Excel Export)."""
    content = f"""{CSV_HEADER}
01.06.2024 10:00:00;75;3500;2000;0;1000;0;500;5000
01.06.2024 11:00:00;85;4000;1500;0;2000;0;500;5000
"""
    path = tmp_path / "with_bom.csv"
    path.write_text(content, encoding="utf-8-sig")  # UTF-8 with BOM
    return path


@pytest.fixture
def csv_missing_optional_columns(tmp_path):
    """CSV mit fehlenden optionalen Spalten (nur Zeitstempel + Solarproduktion)."""
    content = """"Zeitstempel";"Ladezustand [%]";"Solarproduktion [W]"
01.06.2024 10:00:00;75;3500
"""
    path = tmp_path / "missing_optional.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def csv_missing_required_columns(tmp_path):
    """CSV mit fehlenden required Spalten (kein Zeitstempel oder Solarproduktion)."""
    content = """"Ladezustand [%]";"Batterie Laden [W]"
75;2000
"""
    path = tmp_path / "missing_required.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def csv_empty(tmp_path):
    """Leere CSV (nur Header)."""
    content = f"""{CSV_HEADER}
"""
    path = tmp_path / "empty.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def csv_invalid_dates(tmp_path):
    """CSV mit ungültigen Datumsformaten."""
    content = f"""{CSV_HEADER}
invalid-date;75;3500;2000;0;1000;0;500;5000
"""
    path = tmp_path / "invalid_dates.csv"
    path.write_text(content, encoding="utf-8")
    return path
