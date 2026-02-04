"""Tests für config.py."""

from pathlib import Path

import pytest
import yaml

from pvforecast.config import Config, load_config


@pytest.fixture
def sample_config_file(tmp_path):
    """Erstellt eine Test-Config-Datei."""
    config_data = {
        "location": {
            "latitude": 48.13,
            "longitude": 11.58,
            "timezone": "Europe/Berlin",
        },
        "system": {
            "peak_kwp": 15.5,
            "name": "München PV",
        },
        "data": {
            "db_path": "/tmp/test.db",
            "model_path": "/tmp/test.pkl",
        },
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    return config_path


def test_load_config_from_file(sample_config_file):
    """Test: Config wird aus YAML-Datei geladen."""
    config = load_config(sample_config_file)

    assert config.latitude == 48.13
    assert config.longitude == 11.58
    assert config.peak_kwp == 15.5
    assert config.system_name == "München PV"
    assert config.db_path == Path("/tmp/test.db")


def test_load_config_defaults_when_missing(tmp_path):
    """Test: Defaults werden genutzt wenn Datei fehlt."""
    missing_path = tmp_path / "nonexistent.yaml"
    config = load_config(missing_path)

    # Default values
    assert config.latitude == 51.83
    assert config.longitude == 7.28
    assert config.peak_kwp == 9.92


def test_load_config_partial_file(tmp_path):
    """Test: Fehlende Felder werden mit Defaults gefüllt."""
    config_data = {
        "location": {
            "latitude": 50.0,
            # longitude fehlt
        },
        # system fehlt komplett
    }
    config_path = tmp_path / "partial.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    config = load_config(config_path)

    assert config.latitude == 50.0
    assert config.longitude == 7.28  # Default
    assert config.peak_kwp == 9.92  # Default


def test_config_to_dict():
    """Test: Config kann zu Dict konvertiert werden."""
    config = Config(latitude=50.0, longitude=8.0, peak_kwp=12.0)
    data = config.to_dict()

    assert data["location"]["latitude"] == 50.0
    assert data["location"]["longitude"] == 8.0
    assert data["system"]["peak_kwp"] == 12.0


def test_config_save_and_load(tmp_path):
    """Test: Config kann gespeichert und wieder geladen werden."""
    config = Config(
        latitude=52.5,
        longitude=13.4,
        peak_kwp=20.0,
        system_name="Berlin PV",
    )

    config_path = tmp_path / "saved.yaml"
    config.save(config_path)

    # Wieder laden
    loaded = load_config(config_path)

    assert loaded.latitude == 52.5
    assert loaded.longitude == 13.4
    assert loaded.peak_kwp == 20.0
    assert loaded.system_name == "Berlin PV"


def test_load_config_handles_invalid_yaml(tmp_path):
    """Test: Ungültiges YAML gibt Defaults zurück."""
    config_path = tmp_path / "invalid.yaml"
    with open(config_path, "w") as f:
        f.write("invalid: yaml: content: [")

    config = load_config(config_path)

    # Sollte Defaults nutzen
    assert config.latitude == 51.83


def test_config_expanduser_paths(tmp_path):
    """Test: Pfade mit ~ werden expandiert."""
    config_data = {
        "data": {
            "db_path": "~/mydata/pv.db",
        },
    }
    config_path = tmp_path / "paths.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    config = load_config(config_path)

    # ~ sollte expandiert sein
    assert "~" not in str(config.db_path)
    assert str(config.db_path).startswith(str(Path.home()))
