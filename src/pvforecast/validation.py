"""Input-Validierung für pvforecast.

Bietet benutzerfreundliche Validierung und Fehlermeldungen.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path


class ValidationError(ValueError):
    """Benutzerfreundlicher Validierungsfehler.

    Diese Exception wird für User-Input-Fehler verwendet
    und soll ohne Stacktrace angezeigt werden.
    """

    pass


def validate_latitude(value: float) -> float:
    """Validiert Breitengrad.

    Args:
        value: Breitengrad (-90 bis 90)

    Returns:
        Validierter Wert

    Raises:
        ValidationError: Bei ungültigem Wert
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(f"Breitengrad muss eine Zahl sein, nicht '{type(value).__name__}'")
    if not -90 <= value <= 90:
        raise ValidationError(f"Breitengrad muss zwischen -90 und 90 liegen, ist aber {value}")
    return float(value)


def validate_longitude(value: float) -> float:
    """Validiert Längengrad.

    Args:
        value: Längengrad (-180 bis 180)

    Returns:
        Validierter Wert

    Raises:
        ValidationError: Bei ungültigem Wert
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(f"Längengrad muss eine Zahl sein, nicht '{type(value).__name__}'")
    if not -180 <= value <= 180:
        raise ValidationError(f"Längengrad muss zwischen -180 und 180 liegen, ist aber {value}")
    return float(value)


def validate_path_exists(path: Path | str, description: str = "Datei") -> Path:
    """Validiert, dass ein Pfad existiert.

    Args:
        path: Zu prüfender Pfad
        description: Beschreibung für Fehlermeldung (z.B. "CSV-Datei")

    Returns:
        Path-Objekt

    Raises:
        ValidationError: Wenn Pfad nicht existiert
    """
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise ValidationError(f"{description} nicht gefunden: {path}")
    return path


def validate_path_readable(path: Path | str, description: str = "Datei") -> Path:
    """Validiert, dass ein Pfad existiert und lesbar ist.

    Args:
        path: Zu prüfender Pfad
        description: Beschreibung für Fehlermeldung

    Returns:
        Path-Objekt

    Raises:
        ValidationError: Wenn Pfad nicht existiert oder nicht lesbar
    """
    path = validate_path_exists(path, description)
    if not os.access(path, os.R_OK):
        raise ValidationError(f"{description} ist nicht lesbar: {path}")
    return path


def validate_path_writable(path: Path | str, description: str = "Datei") -> Path:
    """Validiert, dass ein Pfad beschreibbar ist (oder erstellt werden kann).

    Args:
        path: Zu prüfender Pfad
        description: Beschreibung für Fehlermeldung

    Returns:
        Path-Objekt

    Raises:
        ValidationError: Wenn Pfad nicht beschreibbar
    """
    path = Path(path).expanduser().resolve()

    if path.exists():
        if not os.access(path, os.W_OK):
            raise ValidationError(f"{description} ist nicht beschreibbar: {path}")
    else:
        # Prüfe ob Parent-Verzeichnis existiert und beschreibbar ist
        parent = path.parent
        if not parent.exists():
            # Versuche Parent zu erstellen
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise ValidationError(f"Verzeichnis kann nicht erstellt werden: {parent}") from None
        if not os.access(parent, os.W_OK):
            raise ValidationError(f"Verzeichnis ist nicht beschreibbar: {parent}")
    return path


def validate_date(
    value: str | date,
    description: str = "Datum",
    min_date: date | None = None,
    max_date: date | None = None,
) -> date:
    """Validiert ein Datum.

    Args:
        value: Datum als String (YYYY-MM-DD oder DD.MM.YYYY) oder date-Objekt
        description: Beschreibung für Fehlermeldung
        min_date: Frühestes erlaubtes Datum
        max_date: Spätestes erlaubtes Datum

    Returns:
        date-Objekt

    Raises:
        ValidationError: Bei ungültigem Datum
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        d = value
    elif isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, str):
        d = parse_date_string(value, description)
    else:
        raise ValidationError(f"{description} muss ein Datum sein, nicht '{type(value).__name__}'")

    if min_date and d < min_date:
        raise ValidationError(f"{description} ({d}) liegt vor dem Minimum ({min_date})")
    if max_date and d > max_date:
        raise ValidationError(f"{description} ({d}) liegt nach dem Maximum ({max_date})")

    return d


def parse_date_string(value: str, description: str = "Datum") -> date:
    """Parst einen Datums-String.

    Unterstützte Formate:
    - YYYY-MM-DD (ISO)
    - DD.MM.YYYY (Deutsch)
    - DD.MM.YY (Deutsch kurz)

    Args:
        value: Datums-String
        description: Beschreibung für Fehlermeldung

    Returns:
        date-Objekt

    Raises:
        ValidationError: Bei ungültigem Format
    """
    value = value.strip()

    # ISO Format: YYYY-MM-DD
    if "-" in value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Deutsches Format: DD.MM.YYYY oder DD.MM.YY
    if "." in value:
        parts = value.split(".")
        if len(parts) == 3:
            try:
                if len(parts[2]) == 4:
                    return datetime.strptime(value, "%d.%m.%Y").date()
                elif len(parts[2]) == 2:
                    return datetime.strptime(value, "%d.%m.%y").date()
            except ValueError:
                pass

    raise ValidationError(
        f"Ungültiges {description}: '{value}'. Erlaubte Formate: YYYY-MM-DD oder DD.MM.YYYY"
    )


def validate_date_range(
    start: date,
    end: date,
    start_desc: str = "Startdatum",
    end_desc: str = "Enddatum",
) -> tuple[date, date]:
    """Validiert, dass Start vor Ende liegt.

    Args:
        start: Startdatum
        end: Enddatum
        start_desc: Beschreibung für Startdatum
        end_desc: Beschreibung für Enddatum

    Returns:
        Tuple (start, end)

    Raises:
        ValidationError: Wenn Start nach Ende liegt
    """
    if start > end:
        raise ValidationError(f"{start_desc} ({start}) liegt nach {end_desc} ({end})")
    return start, end


def validate_positive_int(value: int, description: str = "Wert") -> int:
    """Validiert, dass ein Wert eine positive Ganzzahl ist.

    Args:
        value: Zu prüfender Wert
        description: Beschreibung für Fehlermeldung

    Returns:
        Validierter Wert

    Raises:
        ValidationError: Bei ungültigem Wert
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(
            f"{description} muss eine Ganzzahl sein, nicht '{type(value).__name__}'"
        )
    if value <= 0:
        raise ValidationError(f"{description} muss positiv sein, ist aber {value}")
    return value


def validate_positive_float(value: float, description: str = "Wert") -> float:
    """Validiert, dass ein Wert eine positive Zahl ist.

    Args:
        value: Zu prüfender Wert
        description: Beschreibung für Fehlermeldung

    Returns:
        Validierter Wert

    Raises:
        ValidationError: Bei ungültigem Wert
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(f"{description} muss eine Zahl sein, nicht '{type(value).__name__}'")
    if value <= 0:
        raise ValidationError(f"{description} muss positiv sein, ist aber {value}")
    return float(value)


def validate_csv_files(paths: list[Path | str]) -> list[Path]:
    """Validiert eine Liste von CSV-Dateien.

    Args:
        paths: Liste von Pfaden

    Returns:
        Liste validierter Path-Objekte

    Raises:
        ValidationError: Wenn keine Dateien angegeben oder Dateien nicht existieren
    """
    if not paths:
        raise ValidationError("Keine CSV-Dateien angegeben")

    validated = []
    for p in paths:
        path = validate_path_readable(p, "CSV-Datei")
        if not path.suffix.lower() == ".csv":
            raise ValidationError(f"Datei ist keine CSV-Datei: {path} (Endung: {path.suffix})")
        validated.append(path)

    return validated
