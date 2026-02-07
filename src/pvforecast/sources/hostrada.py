"""HOSTRADA historical weather data source.

HOSTRADA (Hochaufgelöster Stündlicher Rasterdatensatz) provides hourly
gridded weather data for Germany from 1995 onwards.

Data source: DWD Open Data
URL: https://opendata.dwd.de/climate_environment/CDC/grids_germany/hourly/hostrada/
"""

import hashlib
import logging
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
import pandas as pd
import xarray as xr

from .base import DownloadError, HistoricalSource, ParseError, WeatherSourceError

logger = logging.getLogger(__name__)

# Base URL for HOSTRADA data
HOSTRADA_BASE_URL = "https://opendata.dwd.de/climate_environment/CDC/grids_germany/hourly/hostrada"

# Parameter mapping: our name -> HOSTRADA directory and variable
HOSTRADA_PARAMS = {
    "ghi": ("radiation_downwelling", "rsds"),
    "temperature": ("air_temperature_mean", "tas"),
    "cloud_cover": ("cloud_cover", "clt"),
    "humidity": ("humidity_relative", "hurs"),
    "wind_speed": ("wind_speed", "sfcWind"),
}


@dataclass
class GridPoint:
    """A point on the HOSTRADA grid."""
    y_idx: int
    x_idx: int
    lat: float
    lon: float
    distance_km: float


class HOSTRADASource(HistoricalSource):
    """HOSTRADA historical weather data source.
    
    Provides hourly gridded weather data for any location in Germany.
    Data is available from 1995 to approximately 1-2 months before present.
    
    Args:
        latitude: Location latitude (46.68 - 55.53)
        longitude: Location longitude (4.63 - 16.35)
        cache_dir: Directory for caching downloaded NetCDF files
        timeout: HTTP request timeout in seconds
    """
    
    def __init__(
        self,
        latitude: float,
        longitude: float,
        cache_dir: Optional[Path] = None,
        timeout: float = 120.0,
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "hostrada_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self._grid_point: Optional[GridPoint] = None
        
    @property
    def source_name(self) -> str:
        return "hostrada"
    
    def _get_file_url(self, param_dir: str, var_name: str, year: int, month: int) -> str:
        """Build URL for a monthly HOSTRADA file."""
        # Calculate last day of month
        if month == 12:
            last_day = 31
        else:
            next_month = datetime(year, month + 1, 1)
            last_day = (next_month - pd.Timedelta(days=1)).day
            
        # Format: rsds_1hr_HOSTRADA-v1-0_BE_gn_YYYYMM0100-YYYYMMDDhh.nc
        filename = f"{var_name}_1hr_HOSTRADA-v1-0_BE_gn_{year}{month:02d}0100-{year}{month:02d}{last_day}23.nc"
        return f"{HOSTRADA_BASE_URL}/{param_dir}/{filename}"
    
    def _get_cache_path(self, url: str) -> Path:
        """Get cache path for a URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        filename = url.split("/")[-1]
        return self.cache_dir / f"{url_hash}_{filename}"
    
    def _download_file(self, url: str) -> Path:
        """Download file with caching."""
        cache_path = self._get_cache_path(url)
        
        if cache_path.exists():
            logger.debug(f"Using cached file: {cache_path}")
            return cache_path
            
        logger.info(f"Downloading: {url}")
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                
            cache_path.write_bytes(response.content)
            logger.debug(f"Cached to: {cache_path}")
            return cache_path
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise WeatherSourceError(f"HOSTRADA file not found: {url}") from e
            raise WeatherSourceError(f"HTTP error downloading {url}: {e}") from e
        except httpx.RequestError as e:
            raise WeatherSourceError(f"Request error downloading {url}: {e}") from e
    
    def _find_grid_point(self, ds: xr.Dataset) -> GridPoint:
        """Find nearest grid point to target coordinates."""
        if self._grid_point is not None:
            return self._grid_point
            
        lat_diff = np.abs(ds.lat.values - self.latitude)
        lon_diff = np.abs(ds.lon.values - self.longitude)
        distance = np.sqrt(lat_diff**2 + lon_diff**2)
        
        min_idx = np.unravel_index(np.argmin(distance), distance.shape)
        y_idx, x_idx = min_idx
        
        grid_lat = float(ds.lat[y_idx, x_idx])
        grid_lon = float(ds.lon[y_idx, x_idx])
        distance_deg = float(distance[y_idx, x_idx])
        distance_km = distance_deg * 111  # Approximate conversion
        
        self._grid_point = GridPoint(
            y_idx=y_idx,
            x_idx=x_idx,
            lat=grid_lat,
            lon=grid_lon,
            distance_km=distance_km,
        )
        
        logger.info(
            f"Grid point for ({self.latitude:.4f}, {self.longitude:.4f}): "
            f"({grid_lat:.4f}, {grid_lon:.4f}), distance: {distance_km:.1f} km"
        )
        
        return self._grid_point
    
    def _extract_timeseries(
        self,
        file_path: Path,
        var_name: str,
    ) -> pd.Series:
        """Extract time series for a single variable from NetCDF file."""
        ds = xr.open_dataset(file_path)
        
        try:
            grid_point = self._find_grid_point(ds)
            data = ds[var_name][:, grid_point.y_idx, grid_point.x_idx]
            
            # Convert to pandas Series
            series = pd.Series(
                data.values,
                index=pd.DatetimeIndex(data.time.values),
                name=var_name,
            )
            return series
        finally:
            ds.close()
    
    def fetch_historical(self, start: date, end: date) -> pd.DataFrame:
        """Fetch historical weather data for a date range.
        
        Args:
            start: Start date (inclusive)
            end: End date (inclusive)
                       
        Returns:
            DataFrame with columns matching the standard schema:
                - timestamp: Unix timestamp (UTC)
                - ghi_wm2: Global irradiance [W/m²]
                - cloud_cover_pct: Cloud cover [%]
                - temperature_c: Temperature [°C]
                - wind_speed_ms: Wind speed [m/s]
                - humidity_pct: Humidity [%]
                - dhi_wm2: Diffuse irradiance [W/m²] (estimated)
                - dni_wm2: Direct normal irradiance [W/m²] (0)
        """
        parameters = ["ghi", "temperature", "cloud_cover", "humidity", "wind_speed"]
        
        # Convert dates to datetime for internal processing
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time().replace(microsecond=0))
        
        # Generate list of months to download
        months = []
        current = datetime(start.year, start.month, 1)
        while current <= end_dt:
            months.append((current.year, current.month))
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)
        
        logger.info(f"Fetching {len(months)} months of HOSTRADA data for {len(parameters)} parameters")
        
        # Fetch each parameter
        all_series = {}
        
        for param in parameters:
            param_dir, var_name = HOSTRADA_PARAMS[param]
            param_data = []
            
            for year, month in months:
                try:
                    url = self._get_file_url(param_dir, var_name, year, month)
                    file_path = self._download_file(url)
                    series = self._extract_timeseries(file_path, var_name)
                    param_data.append(series)
                except WeatherSourceError as e:
                    logger.warning(f"Failed to fetch {param} for {year}-{month:02d}: {e}")
                    continue
                    
            if param_data:
                all_series[param] = pd.concat(param_data)
        
        if not all_series:
            raise DownloadError("No data could be fetched for the specified range")
            
        # Combine into DataFrame
        df = pd.DataFrame(all_series)
        
        # Filter to requested date range
        df = df[(df.index >= start_dt) & (df.index <= end_dt)]
        
        # Convert to standard schema
        result = pd.DataFrame()
        result["timestamp"] = df.index.astype(np.int64) // 10**9  # Unix timestamp
        
        # GHI
        if "ghi" in df.columns:
            result["ghi_wm2"] = df["ghi"].values
        else:
            result["ghi_wm2"] = 0.0
            
        # Temperature (convert from Kelvin if needed)
        if "temperature" in df.columns:
            temp = df["temperature"].values
            if np.nanmean(temp) > 200:  # Likely Kelvin
                temp = temp - 273.15
            result["temperature_c"] = temp
        else:
            result["temperature_c"] = 0.0
            
        # Cloud cover (HOSTRADA uses oktas 0-8, convert to percent 0-100)
        if "cloud_cover" in df.columns:
            cc = df["cloud_cover"].values
            if np.nanmax(cc) <= 8.0:  # Oktas 0-8
                cc = cc * 12.5  # Convert to percent (8 oktas = 100%)
            result["cloud_cover_pct"] = np.clip(cc, 0, 100).astype(int)
        else:
            result["cloud_cover_pct"] = 0
            
        # Humidity
        if "humidity" in df.columns:
            result["humidity_pct"] = df["humidity"].values.astype(int)
        else:
            result["humidity_pct"] = 0
            
        # Wind speed
        if "wind_speed" in df.columns:
            result["wind_speed_ms"] = df["wind_speed"].values
        else:
            result["wind_speed_ms"] = 0.0
            
        # DHI estimation using Erbs model (same as MOSMIX)
        result["dhi_wm2"] = self._estimate_dhi(
            result["ghi_wm2"].values,
            df.index,
        )
        
        # DNI not available from HOSTRADA
        result["dni_wm2"] = 0.0
        
        result = result.set_index(df.index)
        
        logger.info(f"Fetched {len(result)} hourly records from HOSTRADA")
        return result
    
    def _estimate_dhi(self, ghi: np.ndarray, times: pd.DatetimeIndex) -> np.ndarray:
        """Estimate DHI from GHI using Erbs model."""
        # Simple zenith angle calculation
        day_of_year = times.dayofyear.values
        hour = times.hour.values + times.minute.values / 60.0
        
        # Solar declination
        declination = 23.45 * np.sin(np.radians(360 * (284 + day_of_year) / 365))
        
        # Hour angle
        hour_angle = 15 * (hour - 12)
        
        # Solar altitude
        lat_rad = np.radians(self.latitude)
        decl_rad = np.radians(declination)
        ha_rad = np.radians(hour_angle)
        
        sin_alt = (np.sin(lat_rad) * np.sin(decl_rad) + 
                   np.cos(lat_rad) * np.cos(decl_rad) * np.cos(ha_rad))
        sin_alt = np.clip(sin_alt, 0, 1)
        
        # Extraterrestrial radiation
        solar_constant = 1361  # W/m²
        day_angle = 2 * np.pi * day_of_year / 365
        eccentricity = 1 + 0.033 * np.cos(day_angle)
        ghi_extra = solar_constant * eccentricity * sin_alt
        
        # Clearness index
        with np.errstate(divide='ignore', invalid='ignore'):
            kt = np.where(ghi_extra > 0, ghi / ghi_extra, 0)
        kt = np.clip(kt, 0, 1)
        
        # Erbs model for diffuse fraction
        df = np.where(
            kt <= 0.22,
            1.0 - 0.09 * kt,
            np.where(
                kt <= 0.80,
                0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4,
                0.165
            )
        )
        
        dhi = df * ghi
        return np.clip(dhi, 0, ghi)
    
    def get_available_range(self) -> Optional[tuple[date, date]]:
        """Get the available date range for HOSTRADA data.
        
        Returns:
            Tuple of (earliest_date, latest_date)
        """
        # HOSTRADA data starts from 1995-01-01
        # Latest data is typically 1-2 months before present
        earliest = date(1995, 1, 1)
        
        # Estimate latest available (conservative: 2 months ago)
        now = datetime.now()
        if now.month <= 2:
            latest = date(now.year - 1, now.month + 10, 1)
        else:
            latest = date(now.year, now.month - 2, 1)
            
        return earliest, latest
