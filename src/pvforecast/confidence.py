"""Empirische Fehlerbänder nach Wetterklasse für PV-Prognosen.

Berechnet P10/P90 Konfidenzintervalle basierend auf historischen
Tagesfehlern aus dem Observation Log, gruppiert nach Wetterklasse
(klar/teilbewölkt/bedeckt).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Wetterklassen-Grenzen (durchschnittlicher cloud_cover_pct pro Tag)
CLEAR_THRESHOLD = 30       # < 30% = klar
PARTLY_THRESHOLD = 70      # 30-70% = teilbewölkt, > 70% = bedeckt

# Mindest-Datenpunkte pro Klasse für klassenspezifische Konfidenz
MIN_SAMPLES_PER_CLASS = 3

# Fallback wenn keine Observation-Daten verfügbar
FALLBACK_ERROR_P10 = -0.50  # -50%
FALLBACK_ERROR_P90 = 0.50   # +50%


@dataclass
class WeatherClass:
    """Wetterklasse mit Fehlerbändern."""

    name: str        # "klar", "teilbewölkt", "bedeckt"
    emoji: str       # ☀️, ⛅, ☁️
    error_p10: float  # 10. Perzentil des relativen Fehlers
    error_p90: float  # 90. Perzentil des relativen Fehlers
    n_days: int       # Anzahl Tage in dieser Klasse


@dataclass
class ConfidenceResult:
    """Ergebnis der Konfidenz-Berechnung für eine Prognose."""

    forecast_kwh: float
    p10_kwh: float           # Untere Grenze (P10)
    p90_kwh: float           # Obere Grenze (P90)
    weather_class: str       # "klar", "teilbewölkt", "bedeckt"
    weather_emoji: str       # ☀️, ⛅, ☁️
    uncertainty: str         # "gering", "mittel", "hoch"
    uncertainty_emoji: str   # 🟢, 🟡, 🔴
    n_days: int              # Basis-Datenpunkte
    avg_cloud_cover: float   # Durchschnittliche Bewölkung des Prognosetags

    @property
    def range_str(self) -> str:
        """Formatiertes Intervall, z.B. '23–33 kWh'."""
        return f"{self.p10_kwh:.0f}–{self.p90_kwh:.0f} kWh"


def parse_observation_log(log_path: Path) -> list[dict]:
    """Parst das Observation Log und extrahiert Prognose vs. Ist pro Tag.

    Returns:
        Liste von Dicts mit 'date', 'actual_kwh', 'forecast_kwh', 'deviation_pct'
    """
    if not log_path.exists():
        return []

    text = log_path.read_text(encoding="utf-8")
    entries = []

    # Split by "## YYYY-MM-DD" headers
    sections = re.split(r"^## (\d{4}-\d{2}-\d{2})\s*$", text, flags=re.MULTILINE)

    # sections[0] is preamble, then alternating date/content pairs
    for i in range(1, len(sections), 2):
        date_str = sections[i]
        content = sections[i + 1] if i + 1 < len(sections) else ""

        actual = _extract_float(r"\*\*Ertrag:\*\*\s*([\d.]+)\s*kWh", content)
        forecast = _extract_float(r"\*\*Modell-Prognose:\*\*\s*([\d.]+)\s*kWh", content)

        if actual is not None and forecast is not None and forecast > 0:
            rel_error = (actual - forecast) / forecast
            entries.append({
                "date": date_str,
                "actual_kwh": actual,
                "forecast_kwh": forecast,
                "rel_error": rel_error,
            })

    return entries


def get_daily_cloud_cover(db_path: Path, dates: list[str]) -> dict[str, float]:
    """Holt durchschnittlichen cloud_cover_pct pro Tag aus forecast_history.

    Verwendet den letzten verfügbaren Forecast (höchstes issued_at) pro Tag
    und mittelt die Tagesstunden (06:00–20:00 Lokalzeit).

    Args:
        db_path: Pfad zur SQLite-Datenbank
        dates: Liste von Datumsstrings 'YYYY-MM-DD'

    Returns:
        Dict {date_str: avg_cloud_cover_pct}
    """
    if not db_path.exists() or not dates:
        return {}

    conn = sqlite3.connect(str(db_path))
    result = {}

    for date_str in dates:
        # Letzte verfügbare Prognose für diesen Tag verwenden
        # Mittele nur Tagesstunden (6-20 Uhr) für bessere Repräsentativität
        row = conn.execute("""
            SELECT AVG(cloud_cover_pct)
            FROM forecast_history
            WHERE date(target_time, 'unixepoch', 'localtime') = ?
              AND CAST(strftime('%H', target_time, 'unixepoch', 'localtime')
                  AS INTEGER) BETWEEN 6 AND 20
              AND source = 'open-meteo'
              AND issued_at = (
                  SELECT MAX(issued_at) FROM forecast_history
                  WHERE date(target_time, 'unixepoch', 'localtime') = ?
                    AND source = 'open-meteo'
              )
        """, (date_str, date_str)).fetchone()

        if row and row[0] is not None:
            result[date_str] = float(row[0])

    conn.close()
    return result


def classify_weather(avg_cloud: float) -> tuple[str, str]:
    """Klassifiziert Bewölkung in Wetterklasse.

    Returns:
        (name, emoji) Tuple
    """
    if avg_cloud < CLEAR_THRESHOLD:
        return "klar", "☀️"
    elif avg_cloud < PARTLY_THRESHOLD:
        return "teilbewölkt", "⛅"
    else:
        return "bedeckt", "☁️"


def compute_error_bands(
    log_path: Path,
    db_path: Path,
) -> dict[str, WeatherClass]:
    """Berechnet empirische Fehlerbänder pro Wetterklasse.

    Returns:
        Dict {weather_class_name: WeatherClass}
    """
    entries = parse_observation_log(log_path)
    if not entries:
        return _fallback_bands()

    dates = [e["date"] for e in entries]
    cloud_cover = get_daily_cloud_cover(db_path, dates)

    # Fehler nach Wetterklasse gruppieren
    class_errors: dict[str, list[float]] = {
        "klar": [],
        "teilbewölkt": [],
        "bedeckt": [],
    }

    for entry in entries:
        avg_cloud = cloud_cover.get(entry["date"])
        if avg_cloud is None:
            continue
        cls_name, _ = classify_weather(avg_cloud)
        class_errors[cls_name].append(entry["rel_error"])

    # Globale Fehler als Fallback
    all_errors = [e["rel_error"] for e in entries if e["date"] in cloud_cover]

    bands = {}
    for cls_name, emoji in [("klar", "☀️"), ("teilbewölkt", "⛅"), ("bedeckt", "☁️")]:
        errors = class_errors[cls_name]
        if len(errors) >= MIN_SAMPLES_PER_CLASS:
            arr = np.array(errors)
            bands[cls_name] = WeatherClass(
                name=cls_name,
                emoji=emoji,
                error_p10=float(np.percentile(arr, 10)),
                error_p90=float(np.percentile(arr, 90)),
                n_days=len(errors),
            )
        elif all_errors:
            # Fallback: globale Verteilung
            arr = np.array(all_errors)
            bands[cls_name] = WeatherClass(
                name=cls_name,
                emoji=emoji,
                error_p10=float(np.percentile(arr, 10)),
                error_p90=float(np.percentile(arr, 90)),
                n_days=len(all_errors),
            )
        else:
            bands[cls_name] = WeatherClass(
                name=cls_name,
                emoji=emoji,
                error_p10=FALLBACK_ERROR_P10,
                error_p90=FALLBACK_ERROR_P90,
                n_days=0,
            )

    return bands


def compute_confidence(
    forecast_kwh: float,
    avg_cloud_cover: float,
    log_path: Path,
    db_path: Path,
) -> ConfidenceResult:
    """Berechnet Konfidenzintervall für eine Tagesprognose.

    Args:
        forecast_kwh: Modell-Prognose in kWh
        avg_cloud_cover: Durchschnittlicher cloud_cover_pct für den Tag (6-20 Uhr)
        log_path: Pfad zum Observation Log
        db_path: Pfad zur SQLite-Datenbank

    Returns:
        ConfidenceResult mit P10/P90 und Metadaten
    """
    bands = compute_error_bands(log_path, db_path)
    cls_name, cls_emoji = classify_weather(avg_cloud_cover)
    band = bands[cls_name]

    # P10/P90 berechnen
    p10 = max(0, forecast_kwh * (1 + band.error_p10))
    p90 = max(0, forecast_kwh * (1 + band.error_p90))

    # Sicherstellen dass p10 <= p90
    if p10 > p90:
        p10, p90 = p90, p10

    # Unsicherheit bewerten (Breite des Intervalls relativ zur Prognose)
    if forecast_kwh > 0:
        spread = (p90 - p10) / forecast_kwh
    else:
        spread = 0

    if spread < 0.3:
        uncertainty = "gering"
        uncertainty_emoji = "🟢"
    elif spread < 0.6:
        uncertainty = "mittel"
        uncertainty_emoji = "🟡"
    else:
        uncertainty = "hoch"
        uncertainty_emoji = "🔴"

    return ConfidenceResult(
        forecast_kwh=forecast_kwh,
        p10_kwh=round(p10, 1),
        p90_kwh=round(p90, 1),
        weather_class=cls_name,
        weather_emoji=cls_emoji,
        uncertainty=uncertainty,
        uncertainty_emoji=uncertainty_emoji,
        n_days=band.n_days,
        avg_cloud_cover=avg_cloud_cover,
    )


def get_forecast_cloud_cover(
    db_path: Path,
    target_date: str,
    source: str = "open-meteo",
) -> float | None:
    """Holt den durchschnittlichen cloud_cover für einen Prognosetag (6-20 Uhr).

    Args:
        db_path: Pfad zur SQLite-Datenbank
        target_date: Datum als 'YYYY-MM-DD'
        source: Wetter-Quelle

    Returns:
        Durchschnittlicher cloud_cover_pct oder None
    """
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("""
        SELECT AVG(cloud_cover_pct)
        FROM forecast_history
        WHERE date(target_time, 'unixepoch', 'localtime') = ?
          AND CAST(strftime('%H', target_time, 'unixepoch', 'localtime')
              AS INTEGER) BETWEEN 6 AND 20
          AND source = ?
          AND issued_at = (
              SELECT MAX(issued_at) FROM forecast_history
              WHERE date(target_time, 'unixepoch', 'localtime') = ?
                AND source = ?
          )
    """, (target_date, source, target_date, source)).fetchone()
    conn.close()

    if row and row[0] is not None:
        return float(row[0])
    return None


def _fallback_bands() -> dict[str, WeatherClass]:
    """Gibt konservative Fallback-Fehlerbänder zurück."""
    return {
        name: WeatherClass(
            name=name,
            emoji=emoji,
            error_p10=FALLBACK_ERROR_P10,
            error_p90=FALLBACK_ERROR_P90,
            n_days=0,
        )
        for name, emoji in [("klar", "☀️"), ("teilbewölkt", "⛅"), ("bedeckt", "☁️")]
    }


def _extract_float(pattern: str, text: str) -> float | None:
    """Extrahiert eine Float-Zahl aus Text per Regex."""
    match = re.search(pattern, text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None
