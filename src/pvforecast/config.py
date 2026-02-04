"""Konfiguration und Defaults für pvforecast."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _default_db_path() -> Path:
    return Path.home() / ".local" / "share" / "pvforecast" / "data.db"


def _default_model_path() -> Path:
    return Path.home() / ".local" / "share" / "pvforecast" / "model.pkl"


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


# Globale Default-Instanz
DEFAULT_CONFIG = Config()
