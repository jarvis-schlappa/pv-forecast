"""Open-Meteo API Client für Wetterdaten."""

from __future__ import annotations

import logging
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

UTC_TZ = ZoneInfo("UTC")


class WeatherAPIError(Exception):
    """Fehler bei Wetter-API."""

    pass


def fetch_historical(
    lat: float,
    lon: float,
    start: date,
    end: date,
    timeout: float = 30.0,
) -> pd.DataFrame:
    """
    Holt historische Wetterdaten von Open-Meteo Archive API.

    Args:
        lat: Breitengrad
        lon: Längengrad
        start: Startdatum
        end: Enddatum
        timeout: Request timeout in Sekunden

    Returns:
        DataFrame mit Spalten:
        - timestamp: Unix timestamp (UTC)
        - ghi_wm2: Globalstrahlung
        - cloud_cover_pct: Bewölkung
        - temperature_c: Temperatur

    Raises:
        WeatherAPIError: Bei API-Fehlern
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

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(HISTORICAL_API, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise WeatherAPIError(f"API-Fehler: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise WeatherAPIError(f"Verbindungsfehler: {e}") from e

    if "hourly" not in data:
        raise WeatherAPIError(f"Unerwartete API-Antwort: {data}")

    return _parse_weather_response(data)


def fetch_forecast(
    lat: float,
    lon: float,
    hours: int = 48,
    timeout: float = 30.0,
) -> pd.DataFrame:
    """
    Holt Wettervorhersage von Open-Meteo Forecast API.

    Args:
        lat: Breitengrad
        lon: Längengrad
        hours: Anzahl Stunden (max 384 = 16 Tage)
        timeout: Request timeout in Sekunden

    Returns:
        DataFrame mit gleichem Schema wie fetch_historical()

    Raises:
        WeatherAPIError: Bei API-Fehlern
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

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(FORECAST_API, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise WeatherAPIError(f"API-Fehler: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise WeatherAPIError(f"Verbindungsfehler: {e}") from e

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


def ensure_weather_history(
    db: Database,
    lat: float,
    lon: float,
    start_ts: int,
    end_ts: int,
) -> int:
    """
    Stellt sicher, dass Wetterdaten für einen Zeitraum vorhanden sind.
    Lädt fehlende Daten automatisch nach.

    Args:
        db: Database-Instanz
        lat: Breitengrad
        lon: Längengrad
        start_ts: Start Unix timestamp
        end_ts: End Unix timestamp

    Returns:
        Anzahl nachgeladener Datensätze
    """
    # Prüfe welche Daten fehlen
    with db.connect() as conn:
        result = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM weather_history"
        ).fetchone()
        existing_start, existing_end = result if result else (None, None)

    start_date = datetime.fromtimestamp(start_ts, UTC_TZ).date()
    end_date = datetime.fromtimestamp(end_ts, UTC_TZ).date()

    total_loaded = 0

    # Lade Daten in Chunks (Open-Meteo limitiert auf ~1 Jahr pro Request)
    chunk_days = 365
    current_start = start_date

    while current_start < end_date:
        current_end = min(current_start + timedelta(days=chunk_days), end_date)

        # Prüfe ob dieser Zeitraum schon vorhanden
        chunk_start_ts = int(datetime.combine(current_start, datetime.min.time())
                            .replace(tzinfo=UTC_TZ).timestamp())
        chunk_end_ts = int(datetime.combine(current_end, datetime.max.time())
                          .replace(tzinfo=UTC_TZ).timestamp())

        if existing_start and existing_end:
            if chunk_start_ts >= existing_start and chunk_end_ts <= existing_end:
                logger.debug(f"Wetterdaten vorhanden für {current_start} - {current_end}")
                current_start = current_end + timedelta(days=1)
                continue

        logger.info(f"Lade Wetterdaten: {current_start} bis {current_end}")
        try:
            df = fetch_historical(lat, lon, current_start, current_end)
            loaded = save_weather_to_db(df, db)
            total_loaded += loaded
        except WeatherAPIError as e:
            logger.error(f"Fehler beim Laden: {e}")

        current_start = current_end + timedelta(days=1)

    return total_loaded
