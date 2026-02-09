"""Helper functions for pvforecast CLI."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from pvforecast.config import Config
from pvforecast.db import Database
from pvforecast.sources.hostrada import HOSTRADASource
from pvforecast.sources.mosmix import MOSMIXConfig, MOSMIXSource
from pvforecast.sources.openmeteo import OpenMeteoConfig, OpenMeteoSource

logger = logging.getLogger(__name__)
UTC_TZ = ZoneInfo("UTC")


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


def fetch_and_archive_forecast(
    config: Config,
    hours: int,
    source_override: str | None = None,
) -> pd.DataFrame:
    """
    Fetch forecast and automatically archive it for later analysis.

    This function wraps the forecast fetch with automatic persistence
    to enable Forecast vs Reality comparisons later.

    Args:
        config: Application config
        hours: Number of hours to fetch
        source_override: Override source name

    Returns:
        DataFrame with weather forecast data
    """
    source = get_forecast_source(config, source_override)
    source_name = source_override or config.weather.forecast_provider

    # Fetch the forecast
    weather_df = source.fetch_forecast(hours=hours)

    # Archive it (non-blocking, errors logged but not raised)
    try:
        _archive_forecast(config, weather_df, source_name)
    except Exception as e:
        logger.warning(f"Forecast-Archivierung fehlgeschlagen: {e}")

    return weather_df


def _archive_forecast(config: Config, weather_df: pd.DataFrame, source: str) -> None:
    """
    Archive forecast data to database.

    Args:
        config: Application config with db_path
        weather_df: DataFrame with forecast data
        source: Source name (e.g., 'open-meteo')
    """
    if weather_df.empty:
        return

    db = Database(config.db_path)
    issued_at = int(datetime.now(UTC_TZ).timestamp())

    # Convert DataFrame to list of dicts for storage
    forecasts = []
    for _, row in weather_df.iterrows():
        forecasts.append({
            "target_time": int(row["timestamp"]),
            "ghi_wm2": row.get("ghi_wm2"),
            "cloud_cover_pct": row.get("cloud_cover_pct"),
            "temperature_c": row.get("temperature_c"),
            "wind_speed_ms": row.get("wind_speed_ms"),
            "humidity_pct": row.get("humidity_pct"),
            "dhi_wm2": row.get("dhi_wm2"),
            "dni_wm2": row.get("dni_wm2"),
        })

    count = db.store_forecast(issued_at, source, forecasts)
    if count > 0:
        logger.debug(f"Forecast archiviert: {count} Einträge für {source}")
