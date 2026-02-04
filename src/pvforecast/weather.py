"""Open-Meteo API Client für Wetterdaten."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from pvforecast.db import Database

logger = logging.getLogger(__name__)

# Open-Meteo API Endpoints
HISTORICAL_API = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"

# Parameter die wir abfragen
WEATHER_PARAMS = "shortwave_radiation,cloud_cover,temperature_2m"

# Retry-Konfiguration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0  # Sekunden, wird exponentiell erhöht

UTC_TZ = ZoneInfo("UTC")


class WeatherAPIError(Exception):
    """Fehler bei Wetter-API."""

    pass


def _request_with_retry(
    url: str,
    params: dict,
    timeout: float = 30.0,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
) -> dict:
    """
    Führt HTTP GET Request mit Retry-Logic aus.

    Args:
        url: API URL
        params: Query-Parameter
        timeout: Request timeout in Sekunden
        max_retries: Maximale Anzahl Versuche
        retry_delay: Basis-Delay zwischen Versuchen (wird exponentiell erhöht)

    Returns:
        JSON Response als dict

    Raises:
        WeatherAPIError: Nach allen fehlgeschlagenen Versuchen
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            # HTTP-Fehler (4xx, 5xx) - nicht wiederholen bei Client-Fehlern
            if e.response.status_code < 500:
                raise WeatherAPIError(f"API-Fehler: {e.response.status_code}") from e
            last_error = e
            logger.warning(
                f"Server-Fehler {e.response.status_code}, "
                f"Versuch {attempt + 1}/{max_retries}"
            )

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            # Timeout oder Verbindungsfehler - wiederholen
            last_error = e
            logger.warning(
                f"Verbindungsfehler: {type(e).__name__}, "
                f"Versuch {attempt + 1}/{max_retries}"
            )

        except httpx.RequestError as e:
            # Andere Request-Fehler
            last_error = e
            logger.warning(
                f"Request-Fehler: {e}, "
                f"Versuch {attempt + 1}/{max_retries}"
            )

        # Warte vor nächstem Versuch (exponential backoff)
        if attempt < max_retries - 1:
            delay = retry_delay * (2 ** attempt)
            logger.info(f"Warte {delay:.1f}s vor nächstem Versuch...")
            time.sleep(delay)

    # Alle Versuche fehlgeschlagen
    raise WeatherAPIError(f"Fehlgeschlagen nach {max_retries} Versuchen: {last_error}")


def fetch_historical(
    lat: float,
    lon: float,
    start: date,
    end: date,
    timeout: float = 60.0,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> pd.DataFrame:
    """
    Holt historische Wetterdaten von Open-Meteo Archive API.

    Args:
        lat: Breitengrad
        lon: Längengrad
        start: Startdatum
        end: Enddatum
        timeout: Request timeout in Sekunden (default: 60)
        max_retries: Maximale Anzahl Versuche bei Fehlern (default: 3)

    Returns:
        DataFrame mit Spalten:
        - timestamp: Unix timestamp (UTC)
        - ghi_wm2: Globalstrahlung
        - cloud_cover_pct: Bewölkung
        - temperature_c: Temperatur

    Raises:
        WeatherAPIError: Bei API-Fehlern nach allen Retries
    """
    logger.info(f"Lade historische Wetterdaten: {start} bis {end}")

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": WEATHER_PARAMS,
        "timezone": "UTC",
    }

    data = _request_with_retry(
        HISTORICAL_API, params, timeout=timeout, max_retries=max_retries
    )

    if "hourly" not in data:
        raise WeatherAPIError(f"Unerwartete API-Antwort: {data}")

    return _parse_weather_response(data)


def fetch_forecast(
    lat: float,
    lon: float,
    hours: int = 48,
    timeout: float = 30.0,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> pd.DataFrame:
    """
    Holt Wettervorhersage von Open-Meteo Forecast API.

    Args:
        lat: Breitengrad
        lon: Längengrad
        hours: Anzahl Stunden (max 384 = 16 Tage)
        timeout: Request timeout in Sekunden
        max_retries: Maximale Anzahl Versuche bei Fehlern (default: 3)

    Returns:
        DataFrame mit gleichem Schema wie fetch_historical()

    Raises:
        WeatherAPIError: Bei API-Fehlern nach allen Retries
    """
    logger.info(f"Lade Wettervorhersage: {hours} Stunden")

    # forecast_hours bestimmt wie viele Stunden geladen werden
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": WEATHER_PARAMS,
        "timezone": "UTC",
        "forecast_hours": min(hours, 384),
    }

    data = _request_with_retry(
        FORECAST_API, params, timeout=timeout, max_retries=max_retries
    )

    if "hourly" not in data:
        raise WeatherAPIError(f"Unerwartete API-Antwort: {data}")

    df = _parse_weather_response(data)

    # Nur zukünftige Stunden (ab jetzt)
    now_ts = int(datetime.now(UTC_TZ).timestamp())
    df = df[df["timestamp"] >= now_ts].head(hours)

    return df


def _parse_weather_response(data: dict) -> pd.DataFrame:
    """Parst Open-Meteo JSON-Antwort zu DataFrame."""
    hourly = data["hourly"]

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(hourly["time"]),
            "ghi_wm2": hourly["shortwave_radiation"],
            "cloud_cover_pct": hourly["cloud_cover"],
            "temperature_c": hourly["temperature_2m"],
        }
    )

    # Timestamps sind bereits UTC, zu Unix konvertieren
    df["timestamp"] = df["timestamp"].astype("int64") // 10**9

    # None/NaN handling
    df["ghi_wm2"] = df["ghi_wm2"].fillna(0.0)
    df["cloud_cover_pct"] = df["cloud_cover_pct"].fillna(0).astype(int)
    df["temperature_c"] = df["temperature_c"].fillna(10.0)

    return df


def save_weather_to_db(df: pd.DataFrame, db: Database) -> int:
    """
    Speichert Wetterdaten in Datenbank.

    Args:
        df: DataFrame von fetch_historical/fetch_forecast
        db: Database-Instanz

    Returns:
        Anzahl eingefügter Zeilen
    """
    inserted = 0
    with db.connect() as conn:
        for _, row in df.iterrows():
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO weather_history
                       (timestamp, ghi_wm2, cloud_cover_pct, temperature_c)
                       VALUES (?, ?, ?, ?)""",
                    (
                        int(row["timestamp"]),
                        float(row["ghi_wm2"]),
                        int(row["cloud_cover_pct"]),
                        float(row["temperature_c"]),
                    ),
                )
                inserted += 1
            except Exception as e:
                logger.warning(f"Fehler bei {row['timestamp']}: {e}")

    logger.info(f"Wetterdaten gespeichert: {inserted} Datensätze")
    return inserted


def find_weather_gaps(
    db: Database,
    start_ts: int,
    end_ts: int,
    min_gap_hours: int = 24,
) -> list[tuple[date, date]]:
    """
    Findet Lücken in den Wetterdaten.

    Args:
        db: Database-Instanz
        start_ts: Start Unix timestamp
        end_ts: End Unix timestamp
        min_gap_hours: Minimale Lückengröße in Stunden (default: 24)

    Returns:
        Liste von (start_date, end_date) Tupeln für fehlende Zeiträume
    """
    start_date = datetime.fromtimestamp(start_ts, UTC_TZ).date()
    end_date = datetime.fromtimestamp(end_ts, UTC_TZ).date()

    gaps = []
    current_month_start = date(start_date.year, start_date.month, 1)

    while current_month_start <= end_date:
        # Monatsende berechnen
        if current_month_start.month == 12:
            next_month = date(current_month_start.year + 1, 1, 1)
        else:
            next_month = date(current_month_start.year, current_month_start.month + 1, 1)
        current_month_end = next_month - timedelta(days=1)

        # Auf gewünschten Zeitraum beschränken
        check_start = max(current_month_start, start_date)
        check_end = min(current_month_end, end_date)

        # Timestamps für Abfrage
        check_start_ts = int(
            datetime.combine(check_start, datetime.min.time())
            .replace(tzinfo=UTC_TZ)
            .timestamp()
        )
        check_end_ts = int(
            datetime.combine(check_end, datetime.max.time())
            .replace(tzinfo=UTC_TZ)
            .timestamp()
        )

        # Zähle vorhandene Stunden in DB
        with db.connect() as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM weather_history WHERE timestamp >= ? AND timestamp <= ?",
                (check_start_ts, check_end_ts),
            ).fetchone()
            existing_hours = result[0] if result else 0

        # Erwartete Stunden
        expected_hours = (check_end - check_start).days * 24 + 24

        # Wenn mehr als min_gap_hours fehlen, als Lücke markieren
        missing_hours = expected_hours - existing_hours
        if missing_hours >= min_gap_hours:
            gaps.append((check_start, check_end))
            logger.debug(
                f"Lücke gefunden: {check_start} - {check_end} "
                f"({missing_hours} Stunden fehlen)"
            )

        current_month_start = next_month

    return gaps


def ensure_weather_history(
    db: Database,
    lat: float,
    lon: float,
    start_ts: int,
    end_ts: int,
) -> int:
    """
    Stellt sicher, dass Wetterdaten für einen Zeitraum vorhanden sind.
    Lädt fehlende Daten automatisch nach, erkennt auch Lücken in der Mitte.

    Args:
        db: Database-Instanz
        lat: Breitengrad
        lon: Längengrad
        start_ts: Start Unix timestamp
        end_ts: End Unix timestamp

    Returns:
        Anzahl nachgeladener Datensätze
    """
    # Finde alle Lücken
    gaps = find_weather_gaps(db, start_ts, end_ts)

    if not gaps:
        logger.info("Keine Wetterdaten-Lücken gefunden")
        return 0

    logger.info(f"Gefundene Lücken: {len(gaps)} Zeiträume")

    total_loaded = 0

    # Lade fehlende Zeiträume (kombiniere aufeinanderfolgende Monate)
    # Open-Meteo erlaubt bis zu ~1 Jahr pro Request
    max_chunk_days = 365

    i = 0
    while i < len(gaps):
        chunk_start = gaps[i][0]
        chunk_end = gaps[i][1]

        # Kombiniere aufeinanderfolgende Lücken bis max_chunk_days
        while i + 1 < len(gaps):
            next_gap = gaps[i + 1]
            # Prüfe ob nächste Lücke direkt anschließt und noch in Chunk passt
            if (next_gap[0] - chunk_end).days <= 1:
                potential_end = next_gap[1]
                if (potential_end - chunk_start).days <= max_chunk_days:
                    chunk_end = potential_end
                    i += 1
                else:
                    break
            else:
                break

        logger.info(f"Lade Wetterdaten: {chunk_start} bis {chunk_end}")
        try:
            df = fetch_historical(lat, lon, chunk_start, chunk_end)
            loaded = save_weather_to_db(df, db)
            total_loaded += loaded
        except WeatherAPIError as e:
            logger.error(f"Fehler beim Laden: {e}")

        i += 1

    return total_loaded
