"""Tests für den reset Befehl."""

import subprocess
from pathlib import Path


class TestResetCommand:
    """Tests für pvforecast reset."""

    def test_reset_help(self):
        """Test: --help zeigt Hilfe an."""
        result = subprocess.run(
            ["python", "-m", "pvforecast", "reset", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0
        assert "--all" in result.stdout
        assert "--database" in result.stdout
        assert "--model-file" in result.stdout
        assert "--configuration" in result.stdout
        assert "--force" in result.stdout
        assert "--dry-run" in result.stdout

    def test_reset_dry_run_all(self, tmp_path, monkeypatch):
        """Test: --all --dry-run zeigt alle Dateien."""
        # Temp-Verzeichnisse erstellen
        data_dir = tmp_path / ".local" / "share" / "pvforecast"
        config_dir = tmp_path / ".config" / "pvforecast"
        data_dir.mkdir(parents=True)
        config_dir.mkdir(parents=True)

        # Dummy-Dateien erstellen
        (data_dir / "data.db").write_text("dummy db")
        (data_dir / "model.pkl").write_text("dummy model")
        (config_dir / "config.yaml").write_text("dummy config")

        # HOME überschreiben
        monkeypatch.setenv("HOME", str(tmp_path))

        result = subprocess.run(
            ["python", "-m", "pvforecast", "reset", "--all", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            env={"HOME": str(tmp_path), "PATH": subprocess.os.environ.get("PATH", "")},
        )

        assert result.returncode == 0
        assert "Datenbank" in result.stdout
        assert "Modell" in result.stdout
        assert "Config" in result.stdout
        assert "Dry-run" in result.stdout

        # Dateien sollten noch existieren (dry-run!)
        assert (data_dir / "data.db").exists()
        assert (data_dir / "model.pkl").exists()
        assert (config_dir / "config.yaml").exists()

    def test_reset_force_deletes_files(self, tmp_path, monkeypatch):
        """Test: --force löscht ohne Bestätigung."""
        # Temp-Verzeichnisse erstellen
        data_dir = tmp_path / ".local" / "share" / "pvforecast"
        config_dir = tmp_path / ".config" / "pvforecast"
        data_dir.mkdir(parents=True)
        config_dir.mkdir(parents=True)

        # Dummy-Dateien erstellen
        db_file = data_dir / "data.db"
        model_file = data_dir / "model.pkl"
        config_file = config_dir / "config.yaml"
        db_file.write_text("dummy db")
        model_file.write_text("dummy model")
        config_file.write_text("dummy config")

        result = subprocess.run(
            ["python", "-m", "pvforecast", "reset", "--all", "--force"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            env={"HOME": str(tmp_path), "PATH": subprocess.os.environ.get("PATH", "")},
        )

        assert result.returncode == 0
        assert "Gelöscht" in result.stdout

        # Dateien sollten gelöscht sein
        assert not db_file.exists()
        assert not model_file.exists()
        assert not config_file.exists()

    def test_reset_database_only(self, tmp_path, monkeypatch):
        """Test: --database löscht nur Datenbank."""
        data_dir = tmp_path / ".local" / "share" / "pvforecast"
        config_dir = tmp_path / ".config" / "pvforecast"
        data_dir.mkdir(parents=True)
        config_dir.mkdir(parents=True)

        db_file = data_dir / "data.db"
        model_file = data_dir / "model.pkl"
        config_file = config_dir / "config.yaml"
        db_file.write_text("dummy db")
        model_file.write_text("dummy model")
        config_file.write_text("dummy config")

        result = subprocess.run(
            ["python", "-m", "pvforecast", "reset", "--database", "--force"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            env={"HOME": str(tmp_path), "PATH": subprocess.os.environ.get("PATH", "")},
        )

        assert result.returncode == 0

        # Nur DB gelöscht
        assert not db_file.exists()
        assert model_file.exists()
        assert config_file.exists()

    def test_reset_no_files_exist(self, tmp_path):
        """Test: Keine Dateien vorhanden → Hinweis."""
        result = subprocess.run(
            ["python", "-m", "pvforecast", "reset", "--all", "--force"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            env={"HOME": str(tmp_path), "PATH": subprocess.os.environ.get("PATH", "")},
        )

        assert result.returncode == 0
        assert "Keine Dateien zum Löschen" in result.stdout
