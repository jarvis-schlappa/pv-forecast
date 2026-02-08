"""SQLite Datenbank-Layer für pvforecast."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

# Schema Version für Migrations
SCHEMA_VERSION = 3

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
    temperature_c       REAL,                 -- Temperatur °C
    -- Erweiterte Features (v2)
    wind_speed_ms       REAL,                 -- Windgeschwindigkeit m/s
    humidity_pct        INTEGER,              -- Relative Luftfeuchtigkeit %
    dhi_wm2             REAL,                 -- Diffusstrahlung W/m²
    -- v3
    dni_wm2             REAL                  -- Direktnormalstrahlung W/m²
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

# Migration von Schema v1 zu v2
MIGRATION_V1_TO_V2 = """
ALTER TABLE weather_history ADD COLUMN wind_speed_ms REAL;
ALTER TABLE weather_history ADD COLUMN humidity_pct INTEGER;
ALTER TABLE weather_history ADD COLUMN dhi_wm2 REAL;
"""

# Migration von Schema v2 zu v3
MIGRATION_V2_TO_V3 = """
ALTER TABLE weather_history ADD COLUMN dni_wm2 REAL;
"""


class Database:
    """SQLite Datenbank-Wrapper für pvforecast."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_schema()
        self._enable_wal_mode()

    def _ensure_schema(self) -> None:
        """Erstellt Schema falls nicht vorhanden und führt Migrationen durch."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)

            # Aktuelle Schema-Version prüfen
            try:
                result = conn.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()
                current_version = int(result[0]) if result else 1
            except sqlite3.OperationalError:
                # metadata Tabelle existiert noch nicht
                current_version = 1

            # Migrationen durchführen
            if current_version < 2:
                self._migrate_v1_to_v2(conn)
            if current_version < 3:
                self._migrate_v2_to_v3(conn)

            # Schema-Version setzen
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    def _migrate_v1_to_v2(self, conn: sqlite3.Connection) -> None:
        """Migration von Schema v1 zu v2: Erweiterte Wetter-Features."""
        # Prüfe ob Spalten bereits existieren
        cursor = conn.execute("PRAGMA table_info(weather_history)")
        columns = {row[1] for row in cursor.fetchall()}

        if "wind_speed_ms" not in columns:
            conn.execute("ALTER TABLE weather_history ADD COLUMN wind_speed_ms REAL")
        if "humidity_pct" not in columns:
            conn.execute("ALTER TABLE weather_history ADD COLUMN humidity_pct INTEGER")
        if "dhi_wm2" not in columns:
            conn.execute("ALTER TABLE weather_history ADD COLUMN dhi_wm2 REAL")

    def _migrate_v2_to_v3(self, conn: sqlite3.Connection) -> None:
        """Migration von Schema v2 zu v3: DNI hinzufügen."""
        cursor = conn.execute("PRAGMA table_info(weather_history)")
        columns = {row[1] for row in cursor.fetchall()}

        if "dni_wm2" not in columns:
            conn.execute("ALTER TABLE weather_history ADD COLUMN dni_wm2 REAL")

    def _enable_wal_mode(self) -> None:
        """Aktiviert WAL-Mode für bessere Parallelität."""
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")

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

    def get_weather_months_with_data(self) -> set[tuple[int, int]]:
        """Returns set of (year, month) tuples that have weather data."""
        with self.connect() as conn:
            result = conn.execute("""
                SELECT DISTINCT
                    CAST(strftime('%Y', timestamp, 'unixepoch') AS INTEGER) as year,
                    CAST(strftime('%m', timestamp, 'unixepoch') AS INTEGER) as month
                FROM weather_history
            """).fetchall()
            return {(row[0], row[1]) for row in result}
