"""Abstract base classes for weather data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class WeatherSourceError(Exception):
    """Base exception for weather source errors."""

    pass


class DownloadError(WeatherSourceError):
    """Error downloading data from source."""

    pass


class ParseError(WeatherSourceError):
    """Error parsing source data format."""

    pass


@dataclass
class WeatherRecord:
    """
    Unified weather data record.
    
    All sources convert their native format to this structure.
    """

    timestamp: int  # Unix timestamp (UTC)
    ghi_wm2: float  # Global Horizontal Irradiance [W/m²]
    cloud_cover_pct: int  # Cloud cover [0-100%]
    temperature_c: float  # Temperature at 2m [°C]
    wind_speed_ms: float  # Wind speed at 10m [m/s]
    humidity_pct: int  # Relative humidity [0-100%]
    dhi_wm2: float  # Diffuse Horizontal Irradiance [W/m²] (0 if unavailable)
    dni_wm2: float  # Direct Normal Irradiance [W/m²] (0 if unavailable)


class ForecastSource(ABC):
    """
    Abstract interface for forecast data sources.
    
    Implementations: MOSMIXSource, (legacy: OpenMeteoForecastSource)
    """

    @abstractmethod
    def fetch_forecast(self, hours: int = 240) -> pd.DataFrame:
        """
        Fetch weather forecast for the next N hours.
        
        Args:
            hours: Number of hours to forecast (max depends on source)
        
        Returns:
            DataFrame with columns:
                - timestamp: Unix timestamp (UTC)
                - ghi_wm2: Global irradiance [W/m²]
                - cloud_cover_pct: Cloud cover [%]
                - temperature_c: Temperature [°C]
                - wind_speed_ms: Wind speed [m/s]
                - humidity_pct: Humidity [%]
                - dhi_wm2: Diffuse irradiance [W/m²]
                - dni_wm2: Direct normal irradiance [W/m²]
        
        Raises:
            DownloadError: If data cannot be fetched
            ParseError: If data format is invalid
        """
        ...

    @abstractmethod
    def fetch_today(self, tz: str) -> pd.DataFrame:
        """
        Fetch weather data for today (past hours + forecast).
        
        Args:
            tz: Timezone string (e.g., "Europe/Berlin")
        
        Returns:
            DataFrame with same schema as fetch_forecast()
        
        Raises:
            DownloadError: If data cannot be fetched
            ParseError: If data format is invalid
        """
        ...


class HistoricalSource(ABC):
    """
    Abstract interface for historical weather data sources.
    
    Implementations: HOSTRADASource, (legacy: OpenMeteoArchiveSource)
    """

    @abstractmethod
    def fetch_historical(self, start: date, end: date) -> pd.DataFrame:
        """
        Fetch historical weather data for a date range.
        
        Args:
            start: Start date (inclusive)
            end: End date (inclusive)
        
        Returns:
            DataFrame with same schema as ForecastSource.fetch_forecast()
        
        Raises:
            DownloadError: If data cannot be fetched
            ParseError: If data format is invalid
        """
        ...

    @abstractmethod
    def get_available_range(self) -> tuple[date, date] | None:
        """
        Get the available date range for this source.
        
        Returns:
            Tuple of (earliest_date, latest_date) or None if unknown
        """
        ...
