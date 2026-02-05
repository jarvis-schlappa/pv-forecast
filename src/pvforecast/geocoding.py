"""Geocoding via OpenStreetMap Nominatim API.

Ermöglicht die Umwandlung von PLZ/Ortsnamen in Koordinaten.
Beachtet Nominatim Usage Policy: max 1 Request/Sekunde, User-Agent erforderlich.

Dokumentation: https://nominatim.org/release-docs/latest/api/Search/
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from pvforecast import __version__

logger = logging.getLogger(__name__)

# Nominatim API Konfiguration
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = f"pvforecast/{__version__} (https://github.com/jarvis-schlappa/pv-forecast)"

# Rate-Limiting: Zeitpunkt des letzten Requests
_last_request_time: float = 0.0
_MIN_REQUEST_INTERVAL = 1.0  # Sekunden (Nominatim Policy)

# Timeout und Retry-Konfiguration
DEFAULT_TIMEOUT = 10.0  # Sekunden
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # Sekunden zwischen Retries


class GeocodingError(Exception):
    """Fehler bei der Geocoding-Abfrage."""

    pass


@dataclass
class GeoResult:
    """Ergebnis einer Geocoding-Abfrage.

    Attributes:
        latitude: Breitengrad (WGS84)
        longitude: Längengrad (WGS84)
        display_name: Vollständiger Anzeigename von Nominatim
        city: Stadt/Gemeinde (falls verfügbar)
        state: Bundesland/Region (falls verfügbar)
        country: Land (falls verfügbar)
        country_code: ISO 3166-1 alpha-2 Ländercode
    """

    latitude: float
    longitude: float
    display_name: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    country_code: str | None = None

    def short_name(self) -> str:
        """Kurzer Anzeigename (Stadt, Region)."""
        parts = []
        if self.city:
            parts.append(self.city)
        if self.state:
            parts.append(self.state)
        if not parts and self.display_name:
            # Fallback: Erste zwei Teile des display_name
            display_parts = self.display_name.split(", ")[:2]
            return ", ".join(display_parts)
        return ", ".join(parts)


def _enforce_rate_limit() -> None:
    """Stellt sicher, dass Rate-Limit eingehalten wird."""
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        sleep_time = _MIN_REQUEST_INTERVAL - elapsed
        logger.debug(f"Rate-Limit: Warte {sleep_time:.2f}s")
        time.sleep(sleep_time)
    _last_request_time = time.monotonic()


def _parse_address(address: dict) -> tuple[str | None, str | None, str | None, str | None]:
    """Extrahiert Stadt, Bundesland, Land und Ländercode aus Nominatim-Adresse.

    Args:
        address: Adress-Dictionary aus Nominatim-Response

    Returns:
        Tuple (city, state, country, country_code)
    """
    # Stadt: verschiedene Felder probieren (Priorität)
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
    )

    state = address.get("state")
    country = address.get("country")
    country_code = address.get("country_code", "").upper() or None

    return city, state, country, country_code


def geocode(
    query: str,
    country_codes: str | None = "de,at,ch",
    timeout: float = DEFAULT_TIMEOUT,
) -> GeoResult | None:
    """Sucht Koordinaten für eine PLZ oder einen Ortsnamen.

    Args:
        query: Suchbegriff (PLZ, Ortsname, oder Kombination wie "48249 Dülmen")
        country_codes: Komma-getrennte ISO 3166-1 alpha-2 Ländercodes zur Einschränkung.
                      Default: "de,at,ch" (Deutschland, Österreich, Schweiz).
                      None für weltweite Suche.
        timeout: Timeout in Sekunden

    Returns:
        GeoResult bei Erfolg, None wenn nichts gefunden

    Raises:
        GeocodingError: Bei API-Fehlern oder Netzwerkproblemen
    """
    if not query or not query.strip():
        return None

    query = query.strip()
    logger.debug(f"Geocoding: '{query}'")

    params: dict[str, str | int] = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
    }

    if country_codes:
        params["countrycodes"] = country_codes

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _enforce_rate_limit()

            with httpx.Client(timeout=timeout) as client:
                response = client.get(NOMINATIM_URL, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

            if not data:
                logger.debug(f"Keine Ergebnisse für '{query}'")
                return None

            result = data[0]
            address = result.get("address", {})
            city, state, country, country_code = _parse_address(address)

            geo_result = GeoResult(
                latitude=float(result["lat"]),
                longitude=float(result["lon"]),
                display_name=result.get("display_name", ""),
                city=city,
                state=state,
                country=country,
                country_code=country_code,
            )

            logger.debug(
                f"Gefunden: {geo_result.short_name()} "
                f"({geo_result.latitude}, {geo_result.longitude})"
            )
            return geo_result

        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(f"Timeout bei Geocoding (Versuch {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        except httpx.HTTPStatusError as e:
            # Bei 429 (Too Many Requests) länger warten
            if e.response.status_code == 429:
                last_error = e
                logger.warning(f"Rate-Limit erreicht (Versuch {attempt}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * 2)
            else:
                raise GeocodingError(f"HTTP-Fehler {e.response.status_code}: {e}") from e

        except httpx.RequestError as e:
            last_error = e
            logger.warning(f"Netzwerkfehler bei Geocoding (Versuch {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    # Alle Retries fehlgeschlagen
    raise GeocodingError(f"Geocoding fehlgeschlagen nach {MAX_RETRIES} Versuchen: {last_error}")


def geocode_postal_code(
    postal_code: str,
    country_code: str = "de",
    timeout: float = DEFAULT_TIMEOUT,
) -> GeoResult | None:
    """Sucht Koordinaten für eine Postleitzahl.

    Spezialisierte Funktion für PLZ-Suche mit besserem Matching.

    Args:
        postal_code: Postleitzahl (z.B. "48249")
        country_code: ISO 3166-1 alpha-2 Ländercode (default: "de")
        timeout: Timeout in Sekunden

    Returns:
        GeoResult bei Erfolg, None wenn nichts gefunden

    Raises:
        GeocodingError: Bei API-Fehlern
    """
    # PLZ normalisieren (nur Ziffern/Buchstaben)
    postal_code = "".join(c for c in postal_code if c.isalnum())

    if not postal_code:
        return None

    # Strukturierte Suche: "postalcode" Parameter für besseres Matching
    params: dict[str, str | int] = {
        "postalcode": postal_code,
        "country": country_code,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
    }

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    try:
        _enforce_rate_limit()

        with httpx.Client(timeout=timeout) as client:
            response = client.get(NOMINATIM_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

        if not data:
            # Fallback: Freie Suche mit PLZ
            logger.debug("Strukturierte PLZ-Suche ohne Ergebnis, versuche Freitext")
            return geocode(postal_code, country_codes=country_code, timeout=timeout)

        result = data[0]
        address = result.get("address", {})
        city, state, country, cc = _parse_address(address)

        return GeoResult(
            latitude=float(result["lat"]),
            longitude=float(result["lon"]),
            display_name=result.get("display_name", ""),
            city=city,
            state=state,
            country=country,
            country_code=cc,
        )

    except httpx.RequestError as e:
        raise GeocodingError(f"Netzwerkfehler: {e}") from e
    except httpx.HTTPStatusError as e:
        raise GeocodingError(f"HTTP-Fehler {e.response.status_code}") from e
