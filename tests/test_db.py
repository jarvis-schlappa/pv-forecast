"""Tests für db.py."""



from pvforecast.db import Database


class TestDatabase:
    """Tests für Database-Klasse."""

    def test_create_new_database(self, tmp_path):
        """Test: Neue Datenbank wird erstellt."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)

        assert db_path.exists()
        assert db.get_pv_count() == 0
        assert db.get_weather_count() == 0

    def test_create_database_creates_parent_dirs(self, tmp_path):
        """Test: Parent-Verzeichnisse werden erstellt."""
        db_path = tmp_path / "subdir" / "nested" / "test.db"
        Database(db_path)  # Creates DB and parent dirs

        assert db_path.exists()
        assert db_path.parent.exists()

    def test_insert_and_count_pv_readings(self, tmp_path):
        """Test: PV-Daten einfügen und zählen."""
        db = Database(tmp_path / "test.db")

        with db.connect() as conn:
            conn.execute(
                "INSERT INTO pv_readings (timestamp, production_w) VALUES (?, ?)",
                (1704067200, 1000),
            )
            conn.execute(
                "INSERT INTO pv_readings (timestamp, production_w) VALUES (?, ?)",
                (1704070800, 2000),
            )

        assert db.get_pv_count() == 2

    def test_insert_and_count_weather(self, tmp_path):
        """Test: Wetterdaten einfügen und zählen."""
        db = Database(tmp_path / "test.db")

        with db.connect() as conn:
            conn.execute(
                """INSERT INTO weather_history
                   (timestamp, ghi_wm2, cloud_cover_pct, temperature_c)
                   VALUES (?, ?, ?, ?)""",
                (1704067200, 500.0, 30, 15.0),
            )

        assert db.get_weather_count() == 1

    def test_get_pv_date_range(self, tmp_path):
        """Test: PV-Datumsbereich abfragen."""
        db = Database(tmp_path / "test.db")

        # Daten einfügen
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO pv_readings (timestamp, production_w) VALUES (?, ?)",
                (1704067200, 1000),  # 2024-01-01 00:00
            )
            conn.execute(
                "INSERT INTO pv_readings (timestamp, production_w) VALUES (?, ?)",
                (1704153600, 2000),  # 2024-01-02 00:00
            )

        start, end = db.get_pv_date_range()

        assert start == 1704067200
        assert end == 1704153600

    def test_get_pv_date_range_empty(self, tmp_path):
        """Test: Leere DB gibt (None, None) zurück."""
        db = Database(tmp_path / "test.db")

        start, end = db.get_pv_date_range()

        assert start is None
        assert end is None

    def test_context_manager_commits(self, tmp_path):
        """Test: Context Manager committed automatisch."""
        db = Database(tmp_path / "test.db")

        with db.connect() as conn:
            conn.execute(
                "INSERT INTO pv_readings (timestamp, production_w) VALUES (?, ?)",
                (1704067200, 1000),
            )

        # Nach Context Manager sollte committed sein
        assert db.get_pv_count() == 1

    def test_multiple_connections(self, tmp_path):
        """Test: Mehrere Connections funktionieren."""
        db = Database(tmp_path / "test.db")

        with db.connect() as conn1:
            conn1.execute(
                "INSERT INTO pv_readings (timestamp, production_w) VALUES (?, ?)",
                (1704067200, 1000),
            )

        with db.connect() as conn2:
            result = conn2.execute(
                "SELECT production_w FROM pv_readings WHERE timestamp = ?",
                (1704067200,),
            ).fetchone()

        assert result[0] == 1000

    def test_schema_version_stored(self, tmp_path):
        """Test: Schema-Version wird gespeichert."""
        from pvforecast.db import SCHEMA_VERSION

        db = Database(tmp_path / "test.db")

        with db.connect() as conn:
            result = conn.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()

        assert result is not None
        assert result[0] == str(SCHEMA_VERSION)
