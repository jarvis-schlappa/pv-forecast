"""SQLite Datenbank-Layer für pvforecast."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

# Schema Version für Migrations
SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- PV-Ertragsdaten (aus E3DC CSV)
CREATE TABLE IF NOT EXISTS pv_readings (
    timestamp       INTEGER PRIMARY KEY,  -- Unix timestamp (UTC)
    production_w    INTEGER NOT NULL,     -- Solarproduktion [W]
    curtailed       INTEGER DEFAULT 0,    -- 1 wenn Abregelung aktiv war
    soc_pct         INTEGER,              -- Ladezustand [%]
    grid_feed_w     INTEGER,              -- Netzeinspeisung [W]
    grid_draw_w     INTEGER,              -- Netzbezug [W]
    consumption_w   INTEGER               -- Hausverbrauch [W]
);

-- Historische Wetterdaten (von Open-Meteo)
CREATE TABLE IF NOT EXISTS weather_history (
    timestamp           INTEGER PRIMARY KEY,  -- Unix timestamp (UTC)
    ghi_wm2             REAL NOT NULL,        -- Globalstrahlung W/m²
    cloud_cover_pct     INTEGER,              -- Bewölkung %
    temperature_c       REAL                  -- Temperatur °C
);

-- Metadaten
CREATE TABLE IF NOT EXISTS metadata (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

-- Indizes für schnelle Zeitbereichs-Abfragen
CREATE INDEX IF NOT EXISTS idx_pv_timestamp ON pv_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_weather_timestamp ON weather_history(timestamp);
"""


class Database:
    """SQLite Datenbank-Wrapper für pvforecast."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Erstellt Schema falls nicht vorhanden."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            # Schema-Version setzen
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager für Datenbankverbindung."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_pv_count(self) -> int:
        """Anzahl PV-Datensätze."""
        with self.connect() as conn:
            result = conn.execute("SELECT COUNT(*) FROM pv_readings").fetchone()
            return result[0] if result else 0

    def get_weather_count(self) -> int:
        """Anzahl Wetter-Datensätze."""
        with self.connect() as conn:
            result = conn.execute("SELECT COUNT(*) FROM weather_history").fetchone()
            return result[0] if result else 0

    def get_pv_date_range(self) -> tuple[int | None, int | None]:
        """Gibt (min_timestamp, max_timestamp) der PV-Daten zurück."""
        with self.connect() as conn:
            result = conn.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM pv_readings"
            ).fetchone()
            return (result[0], result[1]) if result else (None, None)

    def get_weather_date_range(self) -> tuple[int | None, int | None]:
        """Gibt (min_timestamp, max_timestamp) der Wetterdaten zurück."""
        with self.connect() as conn:
            result = conn.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM weather_history"
            ).fetchone()
            return (result[0], result[1]) if result else (None, None)
