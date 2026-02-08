"""Tests für DWD weather sources (MOSMIX, HOSTRADA)."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from pvforecast.sources.base import (
    DownloadError,
)
from pvforecast.sources.hostrada import HOSTRADASource
from pvforecast.sources.mosmix import (
    MOSMIXConfig,
    MOSMIXSource,
    calculate_relative_humidity,
    estimate_dhi,
)
from pvforecast.sources.openmeteo import OpenMeteoConfig, OpenMeteoSource

# =============================================================================
# MOSMIX Tests
# =============================================================================


class TestMOSMIXConfig:
    """Tests for MOSMIXConfig dataclass."""

    def test_default_config(self):
        """Test default MOSMIX config values."""
        config = MOSMIXConfig(lat=51.83, lon=7.28)
        assert config.station_id == "P0051"
        assert config.use_mosmix_l is True
        assert config.lat == 51.83
        assert config.lon == 7.28

    def test_custom_station(self):
        """Test custom station ID."""
        config = MOSMIXConfig(station_id="10315", lat=52.52, lon=13.40)
        assert config.station_id == "10315"


class TestRelativeHumidityCalculation:
    """Tests for calculate_relative_humidity function."""

    def test_saturated_air(self):
        """When temperature equals dewpoint, RH should be 100%."""
        # Same temp and dewpoint = saturated air
        rh = calculate_relative_humidity(temperature_c=20.0, dewpoint_c=20.0)
        assert rh == 100

    def test_typical_summer_day(self):
        """Test typical summer conditions: 25°C, dewpoint 15°C ≈ 55% RH."""
        rh = calculate_relative_humidity(temperature_c=25.0, dewpoint_c=15.0)
        # Expected: ~53-57% RH
        assert 50 <= rh <= 60

    def test_dry_winter_day(self):
        """Test cold dry conditions: 0°C, dewpoint -10°C ≈ 47% RH."""
        rh = calculate_relative_humidity(temperature_c=0.0, dewpoint_c=-10.0)
        # Expected: ~45-50% RH
        assert 40 <= rh <= 55

    def test_humid_tropical(self):
        """Test humid tropical: 30°C, dewpoint 25°C ≈ 74% RH."""
        rh = calculate_relative_humidity(temperature_c=30.0, dewpoint_c=25.0)
        # Expected: ~72-78% RH
        assert 70 <= rh <= 80

    def test_dewpoint_below_freezing(self):
        """Test with dewpoint below freezing: 5°C, dewpoint -5°C ≈ 50% RH."""
        rh = calculate_relative_humidity(temperature_c=5.0, dewpoint_c=-5.0)
        # Expected: ~48-53% RH
        assert 45 <= rh <= 55

    def test_clamping_low(self):
        """RH should never go below 0%."""
        # Extreme dry case (very large temp-dewpoint spread)
        rh = calculate_relative_humidity(temperature_c=40.0, dewpoint_c=-20.0)
        assert rh >= 0

    def test_clamping_high(self):
        """RH should never exceed 100%."""
        # Dewpoint slightly above temp (shouldn't happen, but handle gracefully)
        rh = calculate_relative_humidity(temperature_c=20.0, dewpoint_c=21.0)
        assert rh <= 100

    def test_extreme_cold_fallback(self):
        """Test fallback for extreme temperatures near formula limits."""
        # Temperature near -243°C (near absolute formula limit)
        rh = calculate_relative_humidity(temperature_c=-250.0, dewpoint_c=-260.0)
        assert rh == 50  # Fallback value


class TestMOSMIXSource:
    """Tests for MOSMIXSource."""

    @pytest.fixture
    def mosmix_source(self):
        """Create MOSMIX source for testing."""
        config = MOSMIXConfig(
            station_id="P0051",
            lat=51.83,
            lon=7.28,
        )
        return MOSMIXSource(config)

    def test_build_url(self, mosmix_source):
        """Test URL generation."""
        url = mosmix_source._build_url()
        assert "P0051" in url
        assert "MOSMIX_L_LATEST" in url
        assert url.endswith(".kmz")

    def test_parse_kml_valid(self, mosmix_source):
        """Test KML parsing with valid data."""
        # Minimal valid KML structure
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"
     xmlns:dwd="https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd">
  <Document>
    <ExtendedData>
      <dwd:ProductDefinition>
        <dwd:ForecastTimeSteps>
          <dwd:TimeStep>2026-02-07T12:00:00.000Z</dwd:TimeStep>
          <dwd:TimeStep>2026-02-07T13:00:00.000Z</dwd:TimeStep>
        </dwd:ForecastTimeSteps>
      </dwd:ProductDefinition>
    </ExtendedData>
    <Placemark>
      <ExtendedData>
        <dwd:Forecast dwd:elementName="Rad1h">
          <dwd:value>360.0 720.0</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="TTT">
          <dwd:value>278.15 279.15</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="Neff">
          <dwd:value>50 60</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="FF">
          <dwd:value>3.5 4.0</dwd:value>
        </dwd:Forecast>
      </ExtendedData>
    </Placemark>
  </Document>
</kml>"""

        df = mosmix_source._parse_kml(kml_content)

        assert len(df) == 2
        assert "timestamp" in df.columns
        assert "ghi_wm2" in df.columns
        assert "temperature_c" in df.columns
        assert "cloud_cover_pct" in df.columns

        # Check conversions
        # Rad1h: 360 kJ/m² -> 100 W/m² (360/3.6)
        assert df["ghi_wm2"].iloc[0] == pytest.approx(100.0, rel=0.01)
        # TTT: 278.15 K -> 5.0 °C
        assert df["temperature_c"].iloc[0] == pytest.approx(5.0, rel=0.01)
        # Neff: 50%
        assert df["cloud_cover_pct"].iloc[0] == 50

    def test_parse_kml_with_dewpoint(self, mosmix_source):
        """Test KML parsing calculates humidity from dewpoint."""
        # KML with both TTT (temperature) and TD (dewpoint)
        # TTT: 293.15 K = 20°C, TD: 283.15 K = 10°C
        # Expected RH: ~52-53%
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"
     xmlns:dwd="https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd">
  <Document>
    <ExtendedData>
      <dwd:ProductDefinition>
        <dwd:ForecastTimeSteps>
          <dwd:TimeStep>2026-02-07T12:00:00.000Z</dwd:TimeStep>
        </dwd:ForecastTimeSteps>
      </dwd:ProductDefinition>
    </ExtendedData>
    <Placemark>
      <ExtendedData>
        <dwd:Forecast dwd:elementName="Rad1h">
          <dwd:value>500.0</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="TTT">
          <dwd:value>293.15</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="TD">
          <dwd:value>283.15</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="Neff">
          <dwd:value>30</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="FF">
          <dwd:value>2.0</dwd:value>
        </dwd:Forecast>
      </ExtendedData>
    </Placemark>
  </Document>
</kml>"""

        df = mosmix_source._parse_kml(kml_content)

        assert len(df) == 1
        assert "humidity_pct" in df.columns
        # 20°C temp, 10°C dewpoint -> ~52% RH
        assert 50 <= df["humidity_pct"].iloc[0] <= 55
        # dewpoint_c should be dropped from output
        assert "dewpoint_c" not in df.columns

    def test_parse_kml_missing_dewpoint_fallback(self, mosmix_source):
        """Test humidity fallback to 50% when dewpoint is missing."""
        # KML without TD element
        kml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"
     xmlns:dwd="https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd">
  <Document>
    <ExtendedData>
      <dwd:ProductDefinition>
        <dwd:ForecastTimeSteps>
          <dwd:TimeStep>2026-02-07T12:00:00.000Z</dwd:TimeStep>
        </dwd:ForecastTimeSteps>
      </dwd:ProductDefinition>
    </ExtendedData>
    <Placemark>
      <ExtendedData>
        <dwd:Forecast dwd:elementName="Rad1h">
          <dwd:value>500.0</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="TTT">
          <dwd:value>293.15</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="Neff">
          <dwd:value>30</dwd:value>
        </dwd:Forecast>
        <dwd:Forecast dwd:elementName="FF">
          <dwd:value>2.0</dwd:value>
        </dwd:Forecast>
      </ExtendedData>
    </Placemark>
  </Document>
</kml>"""

        df = mosmix_source._parse_kml(kml_content)

        assert len(df) == 1
        assert "humidity_pct" in df.columns
        # Without TD, should fall back to 50%
        assert df["humidity_pct"].iloc[0] == 50

    def test_estimate_dhi_clear_sky(self, mosmix_source):
        """Test DHI estimation for clear sky (high kt)."""
        # Clear sky at noon, high sun elevation - summer day
        ghi = 800.0
        sun_elevation = 60.0  # High sun
        timestamp = datetime(2026, 6, 21, 12, 0)  # Summer solstice

        dhi = estimate_dhi(ghi, sun_elevation, timestamp)

        # DHI should be less than GHI
        assert dhi < ghi
        # DHI should be positive
        assert dhi > 0
        # For clear sky (high kt), DHI should be modest fraction of GHI
        assert dhi < ghi * 0.5

    def test_estimate_dhi_low_ghi(self, mosmix_source):
        """Test DHI estimation for low GHI (low kt = cloudy/diffuse)."""
        ghi = 150.0  # Low GHI indicates clouds
        sun_elevation = 30.0
        timestamp = datetime(2026, 2, 8, 12, 0)  # Winter

        dhi = estimate_dhi(ghi, sun_elevation, timestamp)

        # Under clouds (low kt), DHI should be higher fraction of GHI
        assert dhi > 0
        assert dhi <= ghi
        # Low kt means high diffuse fraction
        diffuse_fraction = dhi / ghi
        assert diffuse_fraction > 0.5  # Mostly diffuse

    def test_estimate_dhi_night(self, mosmix_source):
        """Test DHI estimation at night returns 0."""
        ghi = 0.0
        sun_elevation = -10.0  # Below horizon
        timestamp = datetime(2026, 2, 8, 22, 0)

        dhi = estimate_dhi(ghi, sun_elevation, timestamp)

        assert dhi == 0.0

    def test_estimate_dhi_physical_kt(self, mosmix_source):
        """Test that kt is calculated physically (GHI / GHI_extra)."""
        # Known values for verification
        sun_elevation = 30.0  # degrees
        timestamp = datetime(2026, 2, 8, 12, 0)  # Feb 8 = DOY 39

        # Calculate expected GHI_extra
        import math
        doy = 39
        solar_constant = 1361
        day_angle = 2 * math.pi * doy / 365
        eccentricity = 1 + 0.033 * math.cos(day_angle)
        sin_alt = math.sin(math.radians(sun_elevation))
        ghi_extra = solar_constant * eccentricity * sin_alt  # ~691 W/m²

        # Test 1: GHI = GHI_extra → kt = 1.0 → low diffuse fraction
        ghi_clear = ghi_extra
        dhi_clear = estimate_dhi(ghi_clear, sun_elevation, timestamp)
        df_clear = dhi_clear / ghi_clear
        assert df_clear < 0.2  # kt=1 → Erbs gives ~0.165

        # Test 2: GHI = 0.3 * GHI_extra → kt = 0.3 → high diffuse fraction
        ghi_cloudy = 0.3 * ghi_extra
        dhi_cloudy = estimate_dhi(ghi_cloudy, sun_elevation, timestamp)
        df_cloudy = dhi_cloudy / ghi_cloudy
        assert df_cloudy > 0.7  # kt=0.3 → Erbs gives ~0.87

    @patch("pvforecast.sources.mosmix.httpx.Client")
    def test_fetch_forecast_http_error(self, mock_client, mosmix_source):
        """Test error handling for HTTP errors."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        with pytest.raises(DownloadError):
            mosmix_source.fetch_forecast(hours=24)


# =============================================================================
# HOSTRADA Tests
# =============================================================================


class TestHOSTRADASource:
    """Tests for HOSTRADASource."""

    @pytest.fixture
    def hostrada_source(self):
        """Create HOSTRADA source for testing."""
        return HOSTRADASource(
            latitude=51.83,
            longitude=7.28,
            show_progress=False,
        )

    def test_source_name(self, hostrada_source):
        """Test source name property."""
        assert hostrada_source.source_name == "hostrada"

    def test_get_available_range(self, hostrada_source):
        """Test available range returns valid dates."""
        earliest, latest = hostrada_source.get_available_range()

        assert earliest == date(1995, 1, 1)
        assert latest < date.today()
        assert latest > date(2020, 1, 1)

    def test_get_file_url(self, hostrada_source):
        """Test URL generation for HOSTRADA files."""
        url = hostrada_source._get_file_url(
            param_dir="radiation_downwelling",
            var_name="rsds",
            year=2019,
            month=1,
        )

        assert "radiation_downwelling" in url
        assert "rsds_1hr_HOSTRADA" in url
        assert "2019010100" in url
        assert "20190131" in url
        assert url.endswith(".nc")

    def test_get_file_url_february(self, hostrada_source):
        """Test URL generation handles February correctly."""
        url = hostrada_source._get_file_url(
            param_dir="radiation_downwelling",
            var_name="rsds",
            year=2020,  # Leap year
            month=2,
        )

        assert "20200229" in url  # Leap year has 29 days

    def test_estimate_dhi(self, hostrada_source):
        """Test DHI estimation from GHI."""
        times = pd.DatetimeIndex(
            [
                datetime(2026, 6, 21, 12, 0),  # Summer noon
                datetime(2026, 6, 21, 0, 0),  # Night
            ]
        )
        ghi = np.array([800.0, 0.0])

        dhi = hostrada_source._estimate_dhi(ghi, times)

        # Noon: DHI should be positive but less than GHI
        assert 0 < dhi[0] < ghi[0]
        # Night: DHI should be 0
        assert dhi[1] == 0.0

    def test_cloud_cover_oktas_conversion(self, hostrada_source):
        """Test that cloud cover is converted from oktas to percent."""
        # This tests the conversion logic in fetch_historical
        # 8 oktas = 100%, 4 oktas = 50%, 0 oktas = 0%
        oktas = np.array([0, 4, 8])
        expected_percent = np.array([0, 50, 100])

        # Apply the same conversion as in hostrada.py
        percent = oktas * 12.5
        percent = np.clip(percent, 0, 100).astype(int)

        np.testing.assert_array_equal(percent, expected_percent)


# =============================================================================
# Integration Tests (require network, skip in CI)
# =============================================================================


@pytest.mark.integration
class TestMOSMIXIntegration:
    """Integration tests for MOSMIX (require network access)."""

    @pytest.fixture
    def mosmix_source(self):
        config = MOSMIXConfig(station_id="P0051", lat=51.83, lon=7.28)
        return MOSMIXSource(config)

    def test_fetch_forecast_real(self, mosmix_source):
        """Test fetching real MOSMIX data."""
        df = mosmix_source.fetch_forecast(hours=24)

        assert len(df) >= 24
        assert "timestamp" in df.columns
        assert "ghi_wm2" in df.columns
        assert "temperature_c" in df.columns
        assert "cloud_cover_pct" in df.columns
        assert "dhi_wm2" in df.columns

        # Sanity checks
        assert df["ghi_wm2"].min() >= 0
        assert df["cloud_cover_pct"].min() >= 0
        assert df["cloud_cover_pct"].max() <= 100


@pytest.mark.integration
class TestHOSTRADAIntegration:
    """Integration tests for HOSTRADA (require network access)."""

    @pytest.fixture
    def hostrada_source(self):
        return HOSTRADASource(
            latitude=51.83,
            longitude=7.28,
            show_progress=False,
        )

    def test_fetch_historical_real(self, hostrada_source):
        """Test fetching real HOSTRADA data (small range)."""
        # Fetch just 2 days to minimize download
        df = hostrada_source.fetch_historical(
            start=date(2019, 1, 1),
            end=date(2019, 1, 2),
        )

        assert len(df) >= 24  # At least 1 full day
        assert "timestamp" in df.columns
        assert "ghi_wm2" in df.columns
        assert "temperature_c" in df.columns
        assert "cloud_cover_pct" in df.columns

        # Sanity checks
        assert df["ghi_wm2"].min() >= 0
        assert df["cloud_cover_pct"].min() >= 0
        assert df["cloud_cover_pct"].max() <= 100


# =============================================================================
# OpenMeteoSource Tests
# =============================================================================


class TestOpenMeteoConfig:
    """Tests for OpenMeteoConfig dataclass."""

    def test_default_config(self):
        """Test default config values."""
        config = OpenMeteoConfig()
        assert config.lat == 51.83
        assert config.lon == 7.28
        assert config.timeout == 30.0
        assert config.max_retries == 3

    def test_custom_location(self):
        """Test custom location config."""
        config = OpenMeteoConfig(lat=52.52, lon=13.40)
        assert config.lat == 52.52
        assert config.lon == 13.40


class TestOpenMeteoSource:
    """Tests for OpenMeteoSource."""

    @pytest.fixture
    def openmeteo_source(self):
        """Create Open-Meteo source for testing."""
        config = OpenMeteoConfig(lat=51.83, lon=7.28)
        return OpenMeteoSource(config)

    def test_parse_response_valid(self, openmeteo_source):
        """Test parsing valid API response."""
        mock_response = {
            "hourly": {
                "time": ["2026-02-08T12:00", "2026-02-08T13:00"],
                "shortwave_radiation": [500.0, 600.0],
                "cloud_cover": [30, 40],
                "temperature_2m": [15.0, 16.0],
                "wind_speed_10m": [5.0, 6.0],
                "relative_humidity_2m": [60, 55],
                "diffuse_radiation": [100.0, 120.0],
                "direct_normal_irradiance": [400.0, 450.0],
            }
        }

        df = openmeteo_source._parse_response(mock_response)

        assert len(df) == 2
        assert "timestamp" in df.columns
        assert "ghi_wm2" in df.columns
        assert "cloud_cover_pct" in df.columns
        assert "temperature_c" in df.columns
        assert "humidity_pct" in df.columns
        assert "dhi_wm2" in df.columns
        assert "dni_wm2" in df.columns

        # Check values
        assert df["ghi_wm2"].iloc[0] == 500.0
        assert df["cloud_cover_pct"].iloc[0] == 30
        assert df["temperature_c"].iloc[0] == 15.0
        assert df["humidity_pct"].iloc[0] == 60

    def test_parse_response_with_missing_values(self, openmeteo_source):
        """Test parsing response with missing optional fields."""
        mock_response = {
            "hourly": {
                "time": ["2026-02-08T12:00"],
                "shortwave_radiation": [500.0],
                "cloud_cover": [30],
                "temperature_2m": [15.0],
                # Optional fields missing
            }
        }

        df = openmeteo_source._parse_response(mock_response)

        assert len(df) == 1
        # Defaults should be applied
        assert df["wind_speed_ms"].iloc[0] == 0.0
        assert df["humidity_pct"].iloc[0] == 50
        assert df["dhi_wm2"].iloc[0] == 0.0
        assert df["dni_wm2"].iloc[0] == 0.0

    def test_parse_response_invalid(self, openmeteo_source):
        """Test parsing invalid response raises ParseError."""
        from pvforecast.sources.base import ParseError

        with pytest.raises(ParseError):
            openmeteo_source._parse_response({"error": "invalid"})

    def test_get_available_range(self, openmeteo_source):
        """Test available range returns valid dates."""
        earliest, latest = openmeteo_source.get_available_range()

        assert earliest == date(1940, 1, 1)
        assert latest < date.today()

    @patch("pvforecast.sources.openmeteo.httpx.Client")
    def test_request_retry_on_429(self, mock_client, openmeteo_source):
        """Test retry logic on rate limiting."""
        import httpx

        # First call returns 429, second succeeds
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Rate limited", request=MagicMock(), response=mock_response_429
        )

        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {
            "hourly": {
                "time": [],
                "shortwave_radiation": [],
                "cloud_cover": [],
                "temperature_2m": [],
            }
        }
        mock_response_ok.raise_for_status.return_value = None

        mock_client.return_value.__enter__.return_value.get.side_effect = [
            mock_response_429,
            mock_response_ok,
        ]

        # Reduce retry delay for test
        openmeteo_source.config.retry_delay = 0.01

        result = openmeteo_source._request_with_retry("http://test", {})
        assert "hourly" in result

    @patch("pvforecast.sources.openmeteo.httpx.Client")
    def test_request_fails_on_4xx(self, mock_client, openmeteo_source):
        """Test 4xx errors (except 429) don't retry."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad request", request=MagicMock(), response=mock_response
        )

        mock_client.return_value.__enter__.return_value.get.return_value = mock_response

        with pytest.raises(DownloadError, match="API error: 400"):
            openmeteo_source._request_with_retry("http://test", {})


@pytest.mark.integration
class TestOpenMeteoIntegration:
    """Integration tests for Open-Meteo (require network access)."""

    @pytest.fixture
    def openmeteo_source(self):
        return OpenMeteoSource(OpenMeteoConfig(lat=51.83, lon=7.28))

    def test_fetch_forecast_real(self, openmeteo_source):
        """Test fetching real Open-Meteo forecast."""
        # Pass explicit now to disable past-filtering (Issue #109: parameter injection)
        # This gives us all forecast hours regardless of CI server time
        from datetime import datetime
        from zoneinfo import ZoneInfo

        ref_time = datetime.now(ZoneInfo("UTC"))
        df = openmeteo_source.fetch_forecast(hours=24, now=ref_time)

        assert len(df) >= 20  # Should have most of the 24 hours
        assert "timestamp" in df.columns
        assert "ghi_wm2" in df.columns
        assert "temperature_c" in df.columns
        assert "cloud_cover_pct" in df.columns
        assert "humidity_pct" in df.columns

        # Sanity checks
        assert df["ghi_wm2"].min() >= 0
        assert df["cloud_cover_pct"].min() >= 0
        assert df["cloud_cover_pct"].max() <= 100
        assert df["humidity_pct"].min() >= 0
        assert df["humidity_pct"].max() <= 100

    def test_fetch_today_real(self, openmeteo_source):
        """Test fetching today's weather."""
        # Use fixed reference time at noon to avoid midnight edge cases
        # (Issue #109 lesson: parameter injection > mocking)
        from datetime import datetime
        from zoneinfo import ZoneInfo

        ref_time = datetime.now(ZoneInfo("Europe/Berlin")).replace(hour=12, minute=0, second=0)
        df = openmeteo_source.fetch_today("Europe/Berlin", now=ref_time)

        assert len(df) >= 12  # At least half a day
        assert "timestamp" in df.columns
        assert "ghi_wm2" in df.columns

    def test_fetch_historical_real(self, openmeteo_source):
        """Test fetching historical data (small range)."""
        df = openmeteo_source.fetch_historical(
            start=date(2024, 1, 1),
            end=date(2024, 1, 2),
        )

        assert len(df) >= 24  # At least 1 full day
        assert "timestamp" in df.columns
        assert "ghi_wm2" in df.columns
        assert "temperature_c" in df.columns

        # Sanity checks
        assert df["ghi_wm2"].min() >= 0
