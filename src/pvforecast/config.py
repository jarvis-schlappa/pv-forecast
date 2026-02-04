"""Konfiguration und Defaults für pvforecast."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _default_db_path() -> Path:
    return Path.home() / ".local" / "share" / "pvforecast" / "data.db"


def _default_model_path() -> Path:
    return Path.home() / ".local" / "share" / "pvforecast" / "model.pkl"


def _default_config_path() -> Path:
    return Path.home() / ".config" / "pvforecast" / "config.yaml"


@dataclass
class Config:
    """Konfiguration für pvforecast."""

    # Standort
    latitude: float = 51.83
    longitude: float = 7.28
    timezone: str = "Europe/Berlin"

    # Anlage
    peak_kwp: float = 9.92
    system_name: str = "Dülmen PV"

    # Pfade
    db_path: Path = field(default_factory=_default_db_path)
    model_path: Path = field(default_factory=_default_model_path)

    # API
    weather_provider: str = "open-meteo"

    def ensure_dirs(self) -> None:
        """Erstellt notwendige Verzeichnisse."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict:
        """Konvertiert Config zu Dictionary."""
        return {
            "location": {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "timezone": self.timezone,
            },
            "system": {
                "peak_kwp": self.peak_kwp,
                "name": self.system_name,
            },
            "data": {
                "db_path": str(self.db_path),
                "model_path": str(self.model_path),
            },
            "api": {
                "weather_provider": self.weather_provider,
            },
        }

    def save(self, path: Path | None = None) -> None:
        """Speichert Config als YAML-Datei."""
        if path is None:
            path = _default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, allow_unicode=True)
        logger.info(f"Config gespeichert: {path}")


def load_config(path: Path | None = None) -> Config:
    """
    Lädt Konfiguration aus YAML-Datei.

    Args:
        path: Pfad zur Config-Datei (default: ~/.config/pvforecast/config.yaml)

    Returns:
        Config-Objekt mit Werten aus Datei, oder Defaults wenn nicht vorhanden
    """
    if path is None:
        path = _default_config_path()

    if not path.exists():
        logger.debug(f"Keine Config-Datei gefunden: {path}")
        return Config()

    logger.info(f"Lade Config: {path}")

    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.warning(f"Fehler beim Lesen der Config: {e}")
        return Config()

    # Config aus YAML-Daten erstellen
    config = Config()

    # Location
    if "location" in data:
        loc = data["location"]
        if "latitude" in loc:
            config.latitude = float(loc["latitude"])
        if "longitude" in loc:
            config.longitude = float(loc["longitude"])
        if "timezone" in loc:
            config.timezone = str(loc["timezone"])

    # System
    if "system" in data:
        sys = data["system"]
        if "peak_kwp" in sys:
            config.peak_kwp = float(sys["peak_kwp"])
        if "name" in sys:
            config.system_name = str(sys["name"])

    # Data paths
    if "data" in data:
        d = data["data"]
        if "db_path" in d:
            config.db_path = Path(d["db_path"]).expanduser()
        if "model_path" in d:
            config.model_path = Path(d["model_path"]).expanduser()

    # API
    if "api" in data:
        api = data["api"]
        if "weather_provider" in api:
            config.weather_provider = str(api["weather_provider"])

    return config


def get_config_path() -> Path:
    """Gibt den Standard-Pfad für die Config-Datei zurück."""
    return _default_config_path()


# Globale Default-Instanz
DEFAULT_CONFIG = Config()
