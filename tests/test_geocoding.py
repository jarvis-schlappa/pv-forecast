"""Tests für das Geocoding-Modul."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from pvforecast.geocoding import (
    GeocodingError,
    GeoResult,
    _parse_address,
    geocode,
    geocode_postal_code,
)


class TestGeoResult:
    """Tests für die GeoResult Dataclass."""

    def test_creation(self):
        """Test: GeoResult kann erstellt werden."""
        result = GeoResult(
            latitude=51.83,
            longitude=7.28,
            display_name="Dülmen, Coesfeld, NRW, Deutschland",
            city="Dülmen",
            state="Nordrhein-Westfalen",
            country="Deutschland",
            country_code="DE",
        )
        assert result.latitude == 51.83
        assert result.longitude == 7.28
        assert result.city == "Dülmen"
        assert result.country_code == "DE"

    def test_short_name_with_city_and_state(self):
        """Test: short_name mit Stadt und Bundesland."""
        result = GeoResult(
            latitude=51.83,
            longitude=7.28,
            display_name="Dülmen, Coesfeld, NRW, Deutschland",
            city="Dülmen",
            state="NRW",
        )
        assert result.short_name() == "Dülmen, NRW"

    def test_short_name_city_only(self):
        """Test: short_name nur mit Stadt."""
        result = GeoResult(
            latitude=51.83,
            longitude=7.28,
            display_name="Dülmen, Deutschland",
            city="Dülmen",
        )
        assert result.short_name() == "Dülmen"

    def test_short_name_fallback_to_display_name(self):
        """Test: short_name Fallback auf display_name."""
        result = GeoResult(
            latitude=51.83,
            longitude=7.28,
            display_name="Dülmen, Coesfeld, NRW, Deutschland",
        )
        assert result.short_name() == "Dülmen, Coesfeld"

    def test_short_name_empty(self):
        """Test: short_name bei leeren Feldern."""
        result = GeoResult(
            latitude=51.83,
            longitude=7.28,
            display_name="",
        )
        assert result.short_name() == ""


class TestParseAddress:
    """Tests für _parse_address Hilfsfunktion."""

    def test_full_address(self):
        """Test: Vollständige Adresse parsen."""
        address = {
            "city": "Dülmen",
            "state": "Nordrhein-Westfalen",
            "country": "Deutschland",
            "country_code": "de",
        }
        city, state, country, cc = _parse_address(address)
        assert city == "Dülmen"
        assert state == "Nordrhein-Westfalen"
        assert country == "Deutschland"
        assert cc == "DE"

    def test_town_instead_of_city(self):
        """Test: 'town' wird als Stadt erkannt."""
        address = {"town": "Kleinstadt", "country_code": "de"}
        city, _, _, _ = _parse_address(address)
        assert city == "Kleinstadt"

    def test_village_instead_of_city(self):
        """Test: 'village' wird als Stadt erkannt."""
        address = {"village": "Dorf", "country_code": "at"}
        city, _, _, _ = _parse_address(address)
        assert city == "Dorf"

    def test_municipality_instead_of_city(self):
        """Test: 'municipality' wird als Stadt erkannt."""
        address = {"municipality": "Gemeinde"}
        city, _, _, _ = _parse_address(address)
        assert city == "Gemeinde"

    def test_empty_address(self):
        """Test: Leere Adresse."""
        city, state, country, cc = _parse_address({})
        assert city is None
        assert state is None
        assert country is None
        assert cc is None


class TestGeocode:
    """Tests für die geocode Funktion."""

    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    def test_successful_geocode(self, mock_rate_limit, mock_client_class):
        """Test: Erfolgreiche Geocoding-Abfrage."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "lat": "51.8333",
                "lon": "7.2833",
                "display_name": "Dülmen, Coesfeld, NRW, Deutschland",
                "address": {
                    "city": "Dülmen",
                    "state": "Nordrhein-Westfalen",
                    "country": "Deutschland",
                    "country_code": "de",
                },
            }
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = geocode("48249 Dülmen")

        assert result is not None
        assert result.latitude == 51.8333
        assert result.longitude == 7.2833
        assert result.city == "Dülmen"
        assert result.country_code == "DE"

    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    def test_no_results(self, mock_rate_limit, mock_client_class):
        """Test: Keine Ergebnisse gefunden."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = geocode("xyznonexistent12345")

        assert result is None

    def test_empty_query(self):
        """Test: Leerer Suchbegriff."""
        result = geocode("")
        assert result is None

        result = geocode("   ")
        assert result is None

    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    @patch("pvforecast.geocoding.time.sleep")
    def test_timeout_with_retry(self, mock_sleep, mock_rate_limit, mock_client_class):
        """Test: Timeout mit Retry."""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        with pytest.raises(GeocodingError) as exc_info:
            geocode("Dülmen")

        assert "fehlgeschlagen nach 3 Versuchen" in str(exc_info.value)
        assert mock_client.get.call_count == 3  # 3 Retries

    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    def test_http_error(self, mock_rate_limit, mock_client_class):
        """Test: HTTP-Fehler (nicht 429)."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        with pytest.raises(GeocodingError) as exc_info:
            geocode("Dülmen")

        assert "HTTP-Fehler 500" in str(exc_info.value)

    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    @patch("pvforecast.geocoding.time.sleep")
    def test_rate_limit_429_with_retry(self, mock_sleep, mock_rate_limit, mock_client_class):
        """Test: Rate-Limit (429) mit Retry."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Too Many Requests", request=MagicMock(), response=mock_response
        )

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        with pytest.raises(GeocodingError) as exc_info:
            geocode("Dülmen")

        assert "fehlgeschlagen nach 3 Versuchen" in str(exc_info.value)
        assert mock_client.get.call_count == 3

    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    def test_country_codes_filter(self, mock_rate_limit, mock_client_class):
        """Test: Country-Codes werden als Parameter übergeben."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        geocode("Berlin", country_codes="de")

        # Prüfe dass countrycodes in params enthalten ist
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["countrycodes"] == "de"

    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    def test_no_country_codes(self, mock_rate_limit, mock_client_class):
        """Test: Weltweite Suche ohne Country-Code-Filter."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        geocode("New York", country_codes=None)

        # countrycodes sollte NICHT in params sein
        call_args = mock_client.get.call_args
        assert "countrycodes" not in call_args[1]["params"]


class TestGeocodePostalCode:
    """Tests für die geocode_postal_code Funktion."""

    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    def test_successful_postal_code(self, mock_rate_limit, mock_client_class):
        """Test: Erfolgreiche PLZ-Suche."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "lat": "51.8333",
                "lon": "7.2833",
                "display_name": "48249, Dülmen, NRW, Deutschland",
                "address": {
                    "city": "Dülmen",
                    "postcode": "48249",
                    "country_code": "de",
                },
            }
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = geocode_postal_code("48249")

        assert result is not None
        assert result.city == "Dülmen"

    @patch("pvforecast.geocoding.geocode")
    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    def test_fallback_to_geocode(self, mock_rate_limit, mock_client_class, mock_geocode):
        """Test: Fallback auf geocode() wenn strukturierte Suche nichts findet."""
        mock_response = MagicMock()
        mock_response.json.return_value = []  # Keine Ergebnisse
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        mock_geocode.return_value = GeoResult(
            latitude=51.83, longitude=7.28, display_name="Fallback"
        )

        result = geocode_postal_code("48249")

        assert result is not None
        mock_geocode.assert_called_once()

    def test_empty_postal_code(self):
        """Test: Leere PLZ."""
        result = geocode_postal_code("")
        assert result is None

    def test_postal_code_normalization(self):
        """Test: PLZ wird normalisiert (Leerzeichen/Sonderzeichen entfernt)."""
        with patch("pvforecast.geocoding.httpx.Client") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = []
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_class.return_value = mock_client

            with patch("pvforecast.geocoding._enforce_rate_limit"):
                with patch("pvforecast.geocoding.geocode", return_value=None):
                    geocode_postal_code("48-249")

            # PLZ sollte normalisiert sein
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["postalcode"] == "48249"

    @patch("pvforecast.geocoding.httpx.Client")
    @patch("pvforecast.geocoding._enforce_rate_limit")
    def test_network_error(self, mock_rate_limit, mock_client_class):
        """Test: Netzwerkfehler."""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError("Network Error")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        with pytest.raises(GeocodingError) as exc_info:
            geocode_postal_code("48249")

        assert "Netzwerkfehler" in str(exc_info.value)


class TestRateLimiting:
    """Tests für Rate-Limiting."""

    @patch("pvforecast.geocoding.time.sleep")
    @patch("pvforecast.geocoding.time.monotonic")
    def test_rate_limit_enforced(self, mock_monotonic, mock_sleep):
        """Test: Rate-Limit wird eingehalten."""
        from pvforecast import geocoding as geocoding_module
        from pvforecast.geocoding import _enforce_rate_limit

        # Setze letzte Request-Zeit
        geocoding_module._last_request_time = 100.0

        # Simuliere: 0.5 Sekunden vergangen (zu früh für nächsten Request)
        mock_monotonic.return_value = 100.5

        _enforce_rate_limit()

        # Sollte 0.5 Sekunden warten
        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 0.4 < sleep_time < 0.6  # Ungefähr 0.5s

    @patch("pvforecast.geocoding.time.sleep")
    @patch("pvforecast.geocoding.time.monotonic")
    def test_no_wait_if_enough_time_passed(self, mock_monotonic, mock_sleep):
        """Test: Kein Warten wenn genug Zeit vergangen."""
        import pvforecast.geocoding as geocoding_module

        geocoding_module._last_request_time = 100.0
        mock_monotonic.return_value = 102.0  # 2 Sekunden vergangen

        from pvforecast.geocoding import _enforce_rate_limit

        _enforce_rate_limit()

        mock_sleep.assert_not_called()


# Integration Test (optional, nur wenn NOMINATIM_INTEGRATION_TEST env var gesetzt)
class TestIntegration:
    """Integration-Tests mit echtem Nominatim API (optional)."""

    @pytest.mark.skip(reason="Integration-Test - nur manuell ausführen")
    def test_real_geocode_duelmen(self):
        """Test: Echte Geocoding-Abfrage für Dülmen."""
        result = geocode("48249 Dülmen")

        assert result is not None
        assert 51.8 < result.latitude < 51.9
        assert 7.2 < result.longitude < 7.4
        assert result.city is not None

    @pytest.mark.skip(reason="Integration-Test - nur manuell ausführen")
    def test_real_geocode_vienna(self):
        """Test: Echte Geocoding-Abfrage für Wien."""
        result = geocode("Wien", country_codes="at")

        assert result is not None
        assert result.country_code == "AT"
