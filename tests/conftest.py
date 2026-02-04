"""Pytest fixtures für pvforecast tests."""

import tempfile
from pathlib import Path

import pytest

from pvforecast.db import Database


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
    """Erstellt eine Test-CSV im E3DC Format."""
    header = (
        '"Zeitstempel";"Ladezustand [%]";"Solarproduktion [W]";'
        '"Batterie Laden [W]";"Batterie Entladen [W]";"Netzeinspeisung [W]";'
        '"Netzbezug [W]";"Hausverbrauch [W]";"Abregelungsgrenze [W]"'
    )
    csv_content = f'''{header}
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
'''
    csv_path = tmp_path / "test_export.csv"
    csv_path.write_text(csv_content)
    return csv_path
