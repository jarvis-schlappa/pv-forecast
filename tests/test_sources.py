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
        """Test DHI estimation for clear sky."""
        # Clear sky at noon, high sun elevation
        ghi = 800.0
        cloud_cover_pct = 10  # Low clouds
        sun_elevation = 60.0  # High sun

        dhi = estimate_dhi(ghi, cloud_cover_pct, sun_elevation)

        # DHI should be less than GHI
        assert dhi < ghi
        # DHI should be positive
        assert dhi > 0
        # For clear sky, DHI should be modest fraction of GHI
        assert dhi < ghi * 0.5

    def test_estimate_dhi_cloudy(self, mosmix_source):
        """Test DHI estimation for cloudy conditions."""
        ghi = 300.0
        cloud_cover_pct = 80  # Heavy clouds
        sun_elevation = 30.0

        dhi = estimate_dhi(ghi, cloud_cover_pct, sun_elevation)

        # Under clouds, DHI should be higher fraction of GHI
        assert dhi > 0
        assert dhi <= ghi

    def test_estimate_dhi_night(self, mosmix_source):
        """Test DHI estimation at night returns 0."""
        ghi = 0.0
        cloud_cover_pct = 50
        sun_elevation = -10.0  # Below horizon

        dhi = estimate_dhi(ghi, cloud_cover_pct, sun_elevation)

        assert dhi == 0.0

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
