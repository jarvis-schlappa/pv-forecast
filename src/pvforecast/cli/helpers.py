"""Helper functions for pvforecast CLI."""

from __future__ import annotations

from pvforecast.config import Config
from pvforecast.sources.hostrada import HOSTRADASource
from pvforecast.sources.mosmix import MOSMIXConfig, MOSMIXSource
from pvforecast.sources.openmeteo import OpenMeteoConfig, OpenMeteoSource


def get_forecast_source(config: Config, source_override: str | None = None):
    """
    Get the appropriate forecast source based on config or override.

    Args:
        config: Application config
        source_override: Override source name (mosmix, open-meteo)

    Returns:
        ForecastSource instance
    """
    source = source_override or config.weather.forecast_provider

    if source == "mosmix":
        mosmix_config = MOSMIXConfig(
            station_id=config.weather.mosmix.station_id,
            use_mosmix_l=config.weather.mosmix.use_mosmix_l,
            lat=config.latitude,
            lon=config.longitude,
        )
        return MOSMIXSource(mosmix_config)
    elif source == "open-meteo":
        return OpenMeteoSource(OpenMeteoConfig(lat=config.latitude, lon=config.longitude))
    else:
        raise ValueError(f"Unknown forecast source: {source}")


def get_historical_source(config: Config, source_override: str | None = None):
    """
    Get the appropriate historical source based on config or override.

    Args:
        config: Application config
        source_override: Override source name (hostrada, open-meteo)

    Returns:
        HistoricalSource instance
    """
    source = source_override or config.weather.historical_provider

    if source == "hostrada":
        local_dir = config.weather.hostrada.local_dir
        return HOSTRADASource(
            latitude=config.latitude,
            longitude=config.longitude,
            local_dir=local_dir,
        )
    elif source == "open-meteo":
        return OpenMeteoSource(OpenMeteoConfig(lat=config.latitude, lon=config.longitude))
    else:
        raise ValueError(f"Unknown historical source: {source}")
