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


class ConfigValidationError(ValueError):
    """Fehler bei Config-Validierung."""

    pass


def _default_hostrada_cache() -> Path:
    return Path.home() / ".cache" / "pvforecast" / "hostrada"


@dataclass
class MOSMIXConfig:
    """MOSMIX-spezifische Konfiguration."""

    station_id: str = "P0051"  # Default: Dülmen
    use_mosmix_l: bool = True  # MOSMIX_L (115 params) vs MOSMIX_S (40 params)


@dataclass
class HOSTRADAConfig:
    """HOSTRADA-spezifische Konfiguration."""

    # Optionales lokales Verzeichnis mit vorhandenen NetCDF-Dateien
    local_dir: str | None = None


@dataclass
class WeatherConfig:
    """Weather sources configuration."""

    # Provider selection: "mosmix" | "open-meteo"
    forecast_provider: str = "mosmix"
    historical_provider: str = "hostrada"

    # Source-specific configs
    mosmix: MOSMIXConfig = field(default_factory=MOSMIXConfig)
    hostrada: HOSTRADAConfig = field(default_factory=HOSTRADAConfig)


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

    # Weather sources (new)
    weather: WeatherConfig = field(default_factory=WeatherConfig)

    # Legacy: weather_provider (deprecated, use weather.forecast_provider)
    weather_provider: str = "open-meteo"

    def __post_init__(self) -> None:
        """Validiert Config nach Erstellung."""
        if not -90 <= self.latitude <= 90:
            raise ConfigValidationError(
                f"latitude muss zwischen -90 und 90 liegen, ist: {self.latitude}"
            )
        if not -180 <= self.longitude <= 180:
            raise ConfigValidationError(
                f"longitude muss zwischen -180 und 180 liegen, ist: {self.longitude}"
            )
        if self.peak_kwp <= 0:
            raise ConfigValidationError(f"peak_kwp muss positiv sein, ist: {self.peak_kwp}")
        if not self.system_name or not self.system_name.strip():
            raise ConfigValidationError("system_name darf nicht leer sein")

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
            "weather": {
                "forecast_provider": self.weather.forecast_provider,
                "historical_provider": self.weather.historical_provider,
                "mosmix": {
                    "station_id": self.weather.mosmix.station_id,
                    "use_mosmix_l": self.weather.mosmix.use_mosmix_l,
                },
                "hostrada": {
                    "cache_dir": str(self.weather.hostrada.cache_dir),
                },
            },
            # Legacy (deprecated)
            "api": {
                "weather_provider": self.weather_provider,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        """
        Erstellt Config aus Dictionary.

        Args:
            data: Dictionary im gleichen Format wie to_dict()

        Returns:
            Config-Instanz

        Raises:
            ConfigValidationError: Bei ungültigen Werten
        """
        kwargs = {}

        # Location
        if "location" in data:
            loc = data["location"]
            if "latitude" in loc:
                kwargs["latitude"] = float(loc["latitude"])
            if "longitude" in loc:
                kwargs["longitude"] = float(loc["longitude"])
            if "timezone" in loc:
                kwargs["timezone"] = str(loc["timezone"])

        # System
        if "system" in data:
            sys = data["system"]
            if "peak_kwp" in sys:
                kwargs["peak_kwp"] = float(sys["peak_kwp"])
            if "name" in sys:
                kwargs["system_name"] = str(sys["name"])

        # Data paths
        if "data" in data:
            d = data["data"]
            if "db_path" in d:
                kwargs["db_path"] = Path(d["db_path"]).expanduser()
            if "model_path" in d:
                kwargs["model_path"] = Path(d["model_path"]).expanduser()

        # Weather sources (new format)
        if "weather" in data:
            w = data["weather"]
            mosmix_cfg = MOSMIXConfig()
            hostrada_cfg = HOSTRADAConfig()

            if "mosmix" in w:
                m = w["mosmix"]
                if "station_id" in m:
                    mosmix_cfg.station_id = str(m["station_id"])
                if "use_mosmix_l" in m:
                    mosmix_cfg.use_mosmix_l = bool(m["use_mosmix_l"])

            if "hostrada" in w:
                h = w["hostrada"]
                if "cache_dir" in h:
                    hostrada_cfg.cache_dir = Path(h["cache_dir"]).expanduser()

            kwargs["weather"] = WeatherConfig(
                forecast_provider=str(w.get("forecast_provider", "mosmix")),
                historical_provider=str(w.get("historical_provider", "hostrada")),
                mosmix=mosmix_cfg,
                hostrada=hostrada_cfg,
            )

        # Legacy API section (deprecated, for backwards compatibility)
        if "api" in data:
            api = data["api"]
            if "weather_provider" in api:
                kwargs["weather_provider"] = str(api["weather_provider"])
                # Also set new config if weather section not present
                if "weather" not in data:
                    provider = str(api["weather_provider"])
                    kwargs["weather"] = WeatherConfig(
                        forecast_provider=provider,
                        historical_provider=(
                            "open-meteo" if provider == "open-meteo" else "hostrada"
                        ),
                    )

        return cls(**kwargs)

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

    Raises:
        ConfigValidationError: Bei ungültigen Werten in der Config-Datei
    """
    if path is None:
        path = _default_config_path()

    if not path.exists():
        logger.debug(f"Keine Config-Datei gefunden: {path}")
        return Config()

    logger.debug(f"Lade Config: {path}")

    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.warning(f"Fehler beim Lesen der Config: {e}")
        return Config()

    return Config.from_dict(data)


def get_config_path() -> Path:
    """Gibt den Standard-Pfad für die Config-Datei zurück."""
    return _default_config_path()


# Globale Default-Instanz
DEFAULT_CONFIG = Config()
