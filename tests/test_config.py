"""Tests für config.py."""

from pathlib import Path

import pytest
import yaml

from pvforecast.config import Config, ConfigValidationError, load_config


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


# === Validierungs-Tests ===


class TestConfigValidation:
    """Tests für Config-Validierung."""

    def test_valid_config(self):
        """Test: Gültige Config wird akzeptiert."""
        config = Config(latitude=50.0, longitude=10.0, peak_kwp=10.0)
        assert config.latitude == 50.0

    def test_invalid_latitude_too_high(self):
        """Test: Latitude > 90 wird abgelehnt."""
        with pytest.raises(ConfigValidationError) as exc_info:
            Config(latitude=91.0)
        assert "latitude" in str(exc_info.value)

    def test_invalid_latitude_too_low(self):
        """Test: Latitude < -90 wird abgelehnt."""
        with pytest.raises(ConfigValidationError) as exc_info:
            Config(latitude=-91.0)
        assert "latitude" in str(exc_info.value)

    def test_invalid_longitude_too_high(self):
        """Test: Longitude > 180 wird abgelehnt."""
        with pytest.raises(ConfigValidationError) as exc_info:
            Config(longitude=181.0)
        assert "longitude" in str(exc_info.value)

    def test_invalid_longitude_too_low(self):
        """Test: Longitude < -180 wird abgelehnt."""
        with pytest.raises(ConfigValidationError) as exc_info:
            Config(longitude=-181.0)
        assert "longitude" in str(exc_info.value)

    def test_invalid_peak_kwp_zero(self):
        """Test: peak_kwp = 0 wird abgelehnt."""
        with pytest.raises(ConfigValidationError) as exc_info:
            Config(peak_kwp=0)
        assert "peak_kwp" in str(exc_info.value)

    def test_invalid_peak_kwp_negative(self):
        """Test: Negative peak_kwp wird abgelehnt."""
        with pytest.raises(ConfigValidationError) as exc_info:
            Config(peak_kwp=-5.0)
        assert "peak_kwp" in str(exc_info.value)

    def test_invalid_system_name_empty(self):
        """Test: Leerer system_name wird abgelehnt."""
        with pytest.raises(ConfigValidationError) as exc_info:
            Config(system_name="")
        assert "system_name" in str(exc_info.value)

    def test_invalid_system_name_whitespace(self):
        """Test: system_name nur aus Whitespace wird abgelehnt."""
        with pytest.raises(ConfigValidationError) as exc_info:
            Config(system_name="   ")
        assert "system_name" in str(exc_info.value)

    def test_boundary_latitude_valid(self):
        """Test: Grenzwerte für latitude sind gültig."""
        config_north = Config(latitude=90.0)
        config_south = Config(latitude=-90.0)
        assert config_north.latitude == 90.0
        assert config_south.latitude == -90.0

    def test_boundary_longitude_valid(self):
        """Test: Grenzwerte für longitude sind gültig."""
        config_east = Config(longitude=180.0)
        config_west = Config(longitude=-180.0)
        assert config_east.longitude == 180.0
        assert config_west.longitude == -180.0


class TestConfigFromDict:
    """Tests für Config.from_dict()."""

    def test_from_dict_complete(self):
        """Test: Vollständiges Dict wird korrekt geparst."""
        data = {
            "location": {"latitude": 48.0, "longitude": 11.0, "timezone": "UTC"},
            "system": {"peak_kwp": 15.0, "name": "Test PV"},
            "data": {"db_path": "/tmp/db.sqlite", "model_path": "/tmp/model.pkl"},
            "api": {"weather_provider": "test-api"},
        }
        config = Config.from_dict(data)

        assert config.latitude == 48.0
        assert config.longitude == 11.0
        assert config.timezone == "UTC"
        assert config.peak_kwp == 15.0
        assert config.system_name == "Test PV"
        assert config.db_path == Path("/tmp/db.sqlite")
        assert config.weather_provider == "test-api"

    def test_from_dict_empty(self):
        """Test: Leeres Dict gibt Defaults."""
        config = Config.from_dict({})
        assert config.latitude == 51.83
        assert config.peak_kwp == 9.92

    def test_from_dict_partial(self):
        """Test: Teilweises Dict merged mit Defaults."""
        data = {"location": {"latitude": 50.0}}
        config = Config.from_dict(data)

        assert config.latitude == 50.0
        assert config.longitude == 7.28  # Default

    def test_from_dict_validates(self):
        """Test: from_dict validiert auch."""
        data = {"location": {"latitude": 999.0}}
        with pytest.raises(ConfigValidationError):
            Config.from_dict(data)

    def test_from_dict_to_dict_roundtrip(self):
        """Test: from_dict(to_dict()) ist identisch."""
        original = Config(
            latitude=52.5,
            longitude=13.4,
            peak_kwp=20.0,
            system_name="Berlin PV",
        )

        roundtrip = Config.from_dict(original.to_dict())

        assert roundtrip.latitude == original.latitude
        assert roundtrip.longitude == original.longitude
        assert roundtrip.peak_kwp == original.peak_kwp
        assert roundtrip.system_name == original.system_name


    def test_install_date_roundtrip(self):
        """Test: install_date wird korrekt gespeichert/geladen (#187)."""
        config = Config(install_date="2018-08-20")
        d = config.to_dict()
        assert d["system"]["install_date"] == "2018-08-20"

        restored = Config.from_dict(d)
        assert restored.install_date == "2018-08-20"

    def test_install_date_optional(self):
        """Test: Ohne install_date bleibt None (#187)."""
        config = Config.from_dict({})
        assert config.install_date is None
        # to_dict should not include install_date key
        d = config.to_dict()
        assert "install_date" not in d["system"]


class TestLoadConfigValidation:
    """Tests für Validierung beim Laden."""

    def test_load_invalid_config_raises(self, tmp_path):
        """Test: Ungültige Config-Datei wirft Fehler."""
        config_data = {
            "location": {"latitude": 999.0},  # Ungültig!
        }
        config_path = tmp_path / "invalid_values.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ConfigValidationError):
            load_config(config_path)
