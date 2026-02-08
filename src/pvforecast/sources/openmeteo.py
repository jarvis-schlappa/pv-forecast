"""Open-Meteo weather data source."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from pvforecast.sources.base import (
    DownloadError,
    ForecastSource,
    HistoricalSource,
    ParseError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Open-Meteo API Endpoints
HISTORICAL_API = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"

# Parameters to fetch
WEATHER_PARAMS = (
    "shortwave_radiation,cloud_cover,temperature_2m,"
    "wind_speed_10m,relative_humidity_2m,diffuse_radiation,"
    "direct_normal_irradiance"
)

UTC_TZ = ZoneInfo("UTC")


@dataclass
class OpenMeteoConfig:
    """Configuration for Open-Meteo data source."""

    lat: float = 51.83
    lon: float = 7.28
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 2.0


class OpenMeteoSource(ForecastSource, HistoricalSource):
    """
    Open-Meteo weather data source.

    Implements both ForecastSource and HistoricalSource interfaces,
    providing access to Open-Meteo's forecast and archive APIs.

    Attributes:
        config: OpenMeteoConfig with location and connection settings

    Example:
        >>> source = OpenMeteoSource(OpenMeteoConfig(lat=51.83, lon=7.28))
        >>> forecast = source.fetch_forecast(hours=48)
        >>> historical = source.fetch_historical(date(2024, 1, 1), date(2024, 1, 31))
    """

    def __init__(self, config: OpenMeteoConfig | None = None):
        """
        Initialize Open-Meteo source.

        Args:
            config: Optional OpenMeteoConfig, uses defaults if not provided
        """
        self.config = config or OpenMeteoConfig()

    def _request_with_retry(self, url: str, params: dict, timeout: float | None = None) -> dict:
        """
        Execute HTTP GET request with retry logic.

        Args:
            url: API URL
            params: Query parameters
            timeout: Request timeout (uses config default if None)

        Returns:
            JSON response as dict

        Raises:
            DownloadError: After all retries failed
        """
        timeout = timeout or self.config.timeout
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()

            except httpx.HTTPStatusError as e:
                status = e.response.status_code

                if status == 429:
                    last_error = e
                    logger.warning(f"Rate limited (429), retry {attempt + 1}")
                elif status < 500:
                    raise DownloadError(f"API error: {status}") from e
                else:
                    last_error = e
                    logger.warning(f"Server error {status}, retry {attempt + 1}")

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                logger.warning(f"Connection error: {type(e).__name__}, retry {attempt + 1}")

            except httpx.RequestError as e:
                last_error = e
                logger.warning(f"Request error: {e}, retry {attempt + 1}")

            # Exponential backoff with jitter
            if attempt < self.config.max_retries - 1:
                base_delay = self.config.retry_delay * (2**attempt)
                jitter = 0.5 + random.random()
                delay = base_delay * jitter
                logger.info(f"Waiting {delay:.1f}s before retry...")
                time.sleep(delay)

        raise DownloadError(f"Failed after {self.config.max_retries} retries: {last_error}")

    def _parse_response(self, data: dict) -> pd.DataFrame:
        """
        Parse Open-Meteo JSON response to DataFrame.

        Args:
            data: API response JSON

        Returns:
            DataFrame with standardized weather columns

        Raises:
            ParseError: If response format is invalid
        """
        if "hourly" not in data:
            raise ParseError(f"Unexpected API response: {data}")

        hourly = data["hourly"]

        df = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(hourly["time"]),
                "ghi_wm2": hourly["shortwave_radiation"],
                "cloud_cover_pct": hourly["cloud_cover"],
                "temperature_c": hourly["temperature_2m"],
                "wind_speed_ms": hourly.get("wind_speed_10m"),
                "humidity_pct": hourly.get("relative_humidity_2m"),
                "dhi_wm2": hourly.get("diffuse_radiation"),
                "dni_wm2": hourly.get("direct_normal_irradiance"),
            }
        )

        # Convert to Unix timestamp
        df["timestamp"] = df["timestamp"].astype("int64") // 10**9

        # Fill NaN with defaults
        df["ghi_wm2"] = df["ghi_wm2"].fillna(0.0)
        df["cloud_cover_pct"] = df["cloud_cover_pct"].fillna(0).astype(int)
        df["temperature_c"] = df["temperature_c"].fillna(10.0)
        df["wind_speed_ms"] = df["wind_speed_ms"].fillna(0.0)
        df["humidity_pct"] = df["humidity_pct"].fillna(50).astype(int)
        df["dhi_wm2"] = df["dhi_wm2"].fillna(0.0)
        df["dni_wm2"] = df["dni_wm2"].fillna(0.0)

        return df

    def fetch_forecast(self, hours: int = 48) -> pd.DataFrame:
        """
        Fetch weather forecast for the next N hours.

        Args:
            hours: Number of hours (max 384 = 16 days)

        Returns:
            DataFrame with forecast data

        Raises:
            DownloadError: If download fails
            ParseError: If parsing fails
        """
        logger.info(f"Fetching Open-Meteo forecast: {hours} hours")

        params = {
            "latitude": self.config.lat,
            "longitude": self.config.lon,
            "hourly": WEATHER_PARAMS,
            "timezone": "UTC",
            "forecast_hours": min(hours, 384),
        }

        data = self._request_with_retry(FORECAST_API, params)
        df = self._parse_response(data)

        # Filter to future hours only (with 1h buffer for clock drift)
        now_ts = int(datetime.now(UTC_TZ).timestamp()) - 3600
        df = df[df["timestamp"] >= now_ts].head(hours)

        logger.info(f"Fetched {len(df)} hours of forecast data")
        return df

    def fetch_today(self, tz: str) -> pd.DataFrame:
        """
        Fetch weather data for today (past hours + forecast).

        Combines past_hours (00:00 to now) and forecast_hours (now to 23:59)
        for a complete daily picture.

        Args:
            tz: Timezone string (e.g., "Europe/Berlin")

        Returns:
            DataFrame with today's weather data

        Raises:
            DownloadError: If download fails
            ParseError: If parsing fails
        """
        local_tz = ZoneInfo(tz)
        now = datetime.now(local_tz)
        current_hour = now.hour

        # past_hours: 00:00 to now (+2 buffer)
        past_hours = current_hour + 2
        # forecast_hours: now to end of day (+1 buffer)
        forecast_hours = 24 - current_hour + 1

        logger.info(f"Fetching Open-Meteo today: past={past_hours}h, forecast={forecast_hours}h")

        params = {
            "latitude": self.config.lat,
            "longitude": self.config.lon,
            "hourly": WEATHER_PARAMS,
            "timezone": "UTC",
            "past_hours": past_hours,
            "forecast_hours": forecast_hours,
        }

        data = self._request_with_retry(FORECAST_API, params)
        df = self._parse_response(data)

        # Filter to today only
        today = now.date()
        weather_dates = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        weather_dates_local = weather_dates.dt.tz_convert(local_tz).dt.date
        today_mask = weather_dates_local == today

        if today_mask.sum() == 0:
            # Edge case at midnight/date boundary - return unfiltered data
            logger.warning(f"No weather data exactly for {today}, returning {len(df)} hours")
        else:
            df = df[today_mask].copy()

        logger.info(f"Fetched {len(df)} hours for today")
        return df.reset_index(drop=True)

    def fetch_historical(self, start: date, end: date) -> pd.DataFrame:
        """
        Fetch historical weather data for a date range.

        Args:
            start: Start date (inclusive)
            end: End date (inclusive)

        Returns:
            DataFrame with historical weather data

        Raises:
            DownloadError: If download fails
            ParseError: If parsing fails
        """
        logger.info(f"Fetching Open-Meteo historical: {start} to {end}")

        params = {
            "latitude": self.config.lat,
            "longitude": self.config.lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": WEATHER_PARAMS,
            "timezone": "UTC",
        }

        # Use longer timeout for historical data (larger responses)
        data = self._request_with_retry(HISTORICAL_API, params, timeout=60.0)
        df = self._parse_response(data)

        logger.info(f"Fetched {len(df)} hours of historical data")
        return df

    def get_available_range(self) -> tuple[date, date] | None:
        """
        Get the available date range for Open-Meteo archive.

        Returns:
            Tuple of (earliest_date, latest_date)
        """
        # Open-Meteo archive goes back to 1940, up to ~5 days ago
        from datetime import timedelta

        earliest = date(1940, 1, 1)
        latest = date.today() - timedelta(days=5)
        return (earliest, latest)
