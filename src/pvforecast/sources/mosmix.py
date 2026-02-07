"""DWD MOSMIX forecast data source."""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import asin, cos, pi, radians, sin
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from pvforecast.sources.base import (
    DownloadError,
    ForecastSource,
    ParseError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# MOSMIX KML Namespaces
KML_NS = {
    "kml": "http://www.opengis.net/kml/2.2",
    "dwd": "https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd",
}

UTC_TZ = ZoneInfo("UTC")


@dataclass
class MOSMIXConfig:
    """Configuration for MOSMIX data source."""

    station_id: str = "P0051"  # Default: Dülmen
    use_mosmix_l: bool = True  # MOSMIX_L (115 params) vs MOSMIX_S (40 params)
    lat: float = 51.83  # For sun elevation calculation
    lon: float = 7.28
    timeout: float = 30.0
    max_retries: int = 3


# Default retry settings
DEFAULT_RETRY_DELAY = 2.0


def _calculate_sun_elevation(timestamp: int, lat: float, lon: float) -> float:
    """
    Calculate sun elevation angle for a given timestamp and location.
    
    Args:
        timestamp: Unix timestamp (UTC)
        lat: Latitude in degrees
        lon: Longitude in degrees
    
    Returns:
        Sun elevation in degrees (-90 to 90, negative = below horizon)
    """
    dt = datetime.fromtimestamp(timestamp, UTC_TZ)
    day_of_year = dt.timetuple().tm_yday

    # Solar declination (simplified)
    declination = -23.45 * cos(radians(360 / 365 * (day_of_year + 10)))

    # Hour angle
    hour = dt.hour + dt.minute / 60
    solar_time = hour + lon / 15
    hour_angle = 15 * (solar_time - 12)

    # Sun elevation
    lat_rad = radians(lat)
    dec_rad = radians(declination)
    ha_rad = radians(hour_angle)

    sin_elevation = sin(lat_rad) * sin(dec_rad) + cos(lat_rad) * cos(dec_rad) * cos(
        ha_rad
    )
    sin_elevation = max(-1, min(1, sin_elevation))

    return asin(sin_elevation) * 180 / pi


def estimate_dhi(ghi: float, cloud_cover_pct: float, sun_elevation: float) -> float:
    """
    Estimate DHI from GHI and cloud cover using simplified Erbs model.
    
    MOSMIX doesn't provide DHI, so we estimate it for the ML model's
    diffuse_fraction feature.
    
    Args:
        ghi: Global Horizontal Irradiance [W/m²]
        cloud_cover_pct: Cloud cover [0-100%]
        sun_elevation: Sun elevation angle [degrees]
    
    Returns:
        Estimated Diffuse Horizontal Irradiance [W/m²]
    """
    if sun_elevation <= 0 or ghi <= 0:
        return 0.0

    # Clearness index approximation from cloud cover
    # kt ~ 1 for clear sky, ~0.2 for overcast
    kt = max(0.1, 1.0 - cloud_cover_pct / 100 * 0.8)

    # Erbs model for diffuse fraction
    if kt <= 0.22:
        diffuse_fraction = 1.0 - 0.09 * kt
    elif kt <= 0.80:
        diffuse_fraction = (
            0.9511
            - 0.1604 * kt
            + 4.388 * kt**2
            - 16.638 * kt**3
            + 12.336 * kt**4
        )
    else:
        diffuse_fraction = 0.165

    return ghi * diffuse_fraction


class MOSMIXSource(ForecastSource):
    """
    DWD MOSMIX weather forecast data source.
    
    MOSMIX provides statistical post-processed forecasts for ~5400 stations
    worldwide, with hourly resolution up to 240 hours (10 days).
    
    Data is published as KMZ files (zipped KML/XML).
    
    Attributes:
        config: MOSMIXConfig with station and connection settings
    
    Example:
        >>> source = MOSMIXSource(MOSMIXConfig(station_id="P0051"))
        >>> forecast = source.fetch_forecast(hours=48)
        >>> print(forecast.head())
    """

    BASE_URL = "https://opendata.dwd.de/weather/local_forecasts/mos"

    # MOSMIX parameter mapping: element_name -> (output_column, converter)
    PARAM_MAP: dict[str, tuple[str, callable]] = {
        "Rad1h": ("ghi_wm2", lambda x: x / 3.6 if x is not None else 0.0),  # kJ/m² → W/m²
        "TTT": ("temperature_c", lambda x: x - 273.15 if x is not None else 10.0),  # K → °C
        "Neff": ("cloud_cover_pct", lambda x: int(x) if x is not None else 0),  # %
        "FF": ("wind_speed_ms", lambda x: x if x is not None else 0.0),  # m/s
        "PPPP": ("pressure_pa", lambda x: x if x is not None else 101300),  # Pa
        "SunD1": ("sunshine_s", lambda x: x if x is not None else 0),  # seconds
    }

    def __init__(self, config: MOSMIXConfig | None = None):
        """
        Initialize MOSMIX source.
        
        Args:
            config: Optional MOSMIXConfig, uses defaults if not provided
        """
        self.config = config or MOSMIXConfig()

    def _build_url(self, latest: bool = True) -> str:
        """Build URL for MOSMIX data download."""
        variant = "MOSMIX_L" if self.config.use_mosmix_l else "MOSMIX_S"
        station = self.config.station_id

        if latest:
            # Single station latest file
            return (
                f"{self.BASE_URL}/{variant}/single_stations/{station}/kml/"
                f"{variant}_LATEST_{station}.kmz"
            )
        else:
            # All stations (much larger file)
            return f"{self.BASE_URL}/{variant}/all_stations/kml/"

    def _download_kmz(self, url: str) -> bytes:
        """
        Download KMZ file with retry logic.
        
        Args:
            url: URL to download
        
        Returns:
            Raw KMZ bytes
        
        Raises:
            DownloadError: If download fails after retries
        """
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                with httpx.Client(timeout=self.config.timeout) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    return response.content

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise DownloadError(
                        f"MOSMIX station {self.config.station_id} not found"
                    ) from e
                last_error = e
                logger.warning(f"HTTP error {e.response.status_code}, retry {attempt + 1}")

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                logger.warning(f"Connection error: {e}, retry {attempt + 1}")

            # Wait before retry (simple backoff)
            if attempt < self.config.max_retries - 1:
                import time

                time.sleep(DEFAULT_RETRY_DELAY * (attempt + 1))

        raise DownloadError(f"Failed after {self.config.max_retries} retries: {last_error}")

    def _extract_kml(self, kmz_data: bytes) -> str:
        """
        Extract KML content from KMZ (ZIP) archive.
        
        Args:
            kmz_data: Raw KMZ bytes
        
        Returns:
            KML XML string
        
        Raises:
            ParseError: If KMZ cannot be extracted
        """
        try:
            with zipfile.ZipFile(io.BytesIO(kmz_data)) as zf:
                # Find the KML file (usually named like MOSMIX_L_2026020709_P0051.kml)
                kml_files = [n for n in zf.namelist() if n.endswith(".kml")]
                if not kml_files:
                    raise ParseError("No KML file found in KMZ archive")

                kml_content = zf.read(kml_files[0])
                return kml_content.decode("iso-8859-1")

        except zipfile.BadZipFile as e:
            raise ParseError(f"Invalid KMZ file: {e}") from e

    def _parse_kml(self, kml_content: str, max_hours: int | None = None) -> pd.DataFrame:
        """
        Parse MOSMIX KML to DataFrame.
        
        Args:
            kml_content: KML XML string
            max_hours: Maximum hours to return (None = all)
        
        Returns:
            DataFrame with weather data
        
        Raises:
            ParseError: If KML structure is invalid
        """
        try:
            root = ET.fromstring(kml_content)
        except ET.ParseError as e:
            raise ParseError(f"Invalid KML XML: {e}") from e

        # Extract timestamps from ForecastTimeSteps
        timesteps_elem = root.find(".//dwd:ForecastTimeSteps", KML_NS)
        if timesteps_elem is None:
            raise ParseError("No ForecastTimeSteps found in KML")

        timestamps = []
        for ts_elem in timesteps_elem.findall("dwd:TimeStep", KML_NS):
            if ts_elem.text:
                # Parse ISO timestamp: 2026-02-07T10:00:00.000Z
                dt = datetime.fromisoformat(ts_elem.text.replace("Z", "+00:00"))
                timestamps.append(int(dt.timestamp()))

        if not timestamps:
            raise ParseError("No timestamps found in KML")

        logger.debug(f"Found {len(timestamps)} forecast timestamps")

        # Find Placemark with station data
        placemark = root.find(".//kml:Placemark", KML_NS)
        if placemark is None:
            raise ParseError("No Placemark found in KML")

        # Extract forecast data for each parameter
        data: dict[str, list] = {"timestamp": timestamps}

        for element_name, (column_name, converter) in self.PARAM_MAP.items():
            forecast_elem = placemark.find(
                f".//dwd:Forecast[@dwd:elementName='{element_name}']", KML_NS
            )

            if forecast_elem is not None:
                value_elem = forecast_elem.find("dwd:value", KML_NS)
                if value_elem is not None and value_elem.text:
                    # Parse space-separated values
                    raw_values = value_elem.text.strip().split()
                    values = []
                    for v in raw_values:
                        v = v.strip()
                        if v == "-" or v == "":
                            values.append(None)
                        else:
                            try:
                                values.append(float(v))
                            except ValueError:
                                values.append(None)

                    # Apply converter and pad/trim to match timestamps
                    converted = [converter(v) for v in values]
                    if len(converted) < len(timestamps):
                        converted.extend([converter(None)] * (len(timestamps) - len(converted)))
                    data[column_name] = converted[: len(timestamps)]
                else:
                    data[column_name] = [converter(None)] * len(timestamps)
            else:
                logger.debug(f"Parameter {element_name} not found in KML")
                data[column_name] = [converter(None)] * len(timestamps)

        # Create DataFrame
        df = pd.DataFrame(data)

        # Add derived columns
        df["humidity_pct"] = 50  # MOSMIX doesn't have humidity, use default

        # Calculate sun elevation and estimate DHI
        sun_elevations = [
            _calculate_sun_elevation(ts, self.config.lat, self.config.lon)
            for ts in df["timestamp"]
        ]

        df["dhi_wm2"] = [
            estimate_dhi(ghi, cloud, elev)
            for ghi, cloud, elev in zip(
                df["ghi_wm2"], df["cloud_cover_pct"], sun_elevations
            )
        ]

        # DNI estimation (simplified: DNI = (GHI - DHI) / cos(zenith))
        # For now, set to 0 as it's less critical
        df["dni_wm2"] = 0.0

        # Limit to requested hours
        if max_hours is not None and len(df) > max_hours:
            df = df.head(max_hours)

        # Ensure correct column order
        output_columns = [
            "timestamp",
            "ghi_wm2",
            "cloud_cover_pct",
            "temperature_c",
            "wind_speed_ms",
            "humidity_pct",
            "dhi_wm2",
            "dni_wm2",
        ]

        return df[[c for c in output_columns if c in df.columns]]

    def fetch_forecast(self, hours: int = 240) -> pd.DataFrame:
        """
        Fetch MOSMIX forecast for the next N hours.
        
        Args:
            hours: Number of hours (max 240 for MOSMIX)
        
        Returns:
            DataFrame with forecast data
        
        Raises:
            DownloadError: If download fails
            ParseError: If parsing fails
        """
        logger.info(f"Fetching MOSMIX forecast for station {self.config.station_id}")

        url = self._build_url(latest=True)
        logger.debug(f"Download URL: {url}")

        kmz_data = self._download_kmz(url)
        kml_content = self._extract_kml(kmz_data)

        df = self._parse_kml(kml_content, max_hours=min(hours, 240))

        logger.info(f"Fetched {len(df)} hours of forecast data")
        return df

    def fetch_today(self, tz: str) -> pd.DataFrame:
        """
        Fetch forecast data for today.
        
        Filters the full forecast to only include hours from today
        in the specified timezone.
        
        Args:
            tz: Timezone string (e.g., "Europe/Berlin")
        
        Returns:
            DataFrame with today's forecast
        """
        from zoneinfo import ZoneInfo

        local_tz = ZoneInfo(tz)
        now = datetime.now(local_tz)
        today = now.date()

        # Fetch full forecast
        df = self.fetch_forecast(hours=48)  # 2 days should cover today

        # Filter to today
        df["date"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df["date"] = df["date"].dt.tz_convert(local_tz).dt.date
        df = df[df["date"] == today].drop(columns=["date"])

        return df.reset_index(drop=True)

    def get_issue_time(self) -> datetime | None:
        """
        Get the issue time of the latest MOSMIX forecast.
        
        Returns:
            Issue time as datetime, or None if not available
        """
        # This would require parsing the KML header
        # For now, return None
        return None
