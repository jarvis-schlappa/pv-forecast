"""Import und Normalisierung von E3DC CSV-Exporten."""

from __future__ import annotations

import logging
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from pvforecast.db import Database

logger = logging.getLogger(__name__)

# E3DC CSV Spalten-Mapping (Deutsch → intern)
COLUMN_MAPPING = {
    "Zeitstempel": "timestamp",
    "Ladezustand [%]": "soc_pct",
    "Solarproduktion [W]": "production_w",
    "Batterie Laden [W]": "battery_charge_w",
    "Batterie Entladen [W]": "battery_discharge_w",
    "Netzeinspeisung [W]": "grid_feed_w",
    "Netzbezug [W]": "grid_draw_w",
    "Hausverbrauch [W]": "consumption_w",
    "Abregelungsgrenze [W]": "curtail_limit_w",
}

# Timezone für E3DC Daten (lokale Zeit)
LOCAL_TZ = ZoneInfo("Europe/Berlin")
UTC_TZ = ZoneInfo("UTC")


class DataImportError(Exception):
    """Fehler beim Datenimport."""

    pass


def load_e3dc_csv(csv_path: Path) -> pd.DataFrame:
    """
    Lädt E3DC CSV und normalisiert die Daten.

    Args:
        csv_path: Pfad zur CSV-Datei

    Returns:
        DataFrame mit normalisierten Spalten:
        - timestamp: Unix timestamp (UTC)
        - production_w: int
        - curtailed: bool (1 wenn Abregelung aktiv)
        - soc_pct, grid_feed_w, grid_draw_w, consumption_w

    Raises:
        DataImportError: Wenn Datei nicht existiert oder ungültiges Format
    """
    if not csv_path.exists():
        raise DataImportError(f"CSV nicht gefunden: {csv_path}")

    logger.debug(f"Lade CSV: {csv_path}")

    try:
        df = pd.read_csv(
            csv_path,
            sep=";",
            decimal=",",
            encoding="utf-8",
        )
    except Exception as e:
        raise DataImportError(f"Fehler beim Lesen der CSV: {e}") from e

    # Prüfe ob erwartete Spalten vorhanden
    missing = set(COLUMN_MAPPING.keys()) - set(df.columns)
    if missing:
        # Versuche mit den wichtigsten Spalten weiterzumachen
        required = {"Zeitstempel", "Solarproduktion [W]"}
        if required - set(df.columns):
            raise DataImportError(f"Fehlende Spalten: {required - set(df.columns)}")
        logger.warning(f"Optionale Spalten fehlen: {missing}")

    # Spalten umbenennen
    df = df.rename(columns={k: v for k, v in COLUMN_MAPPING.items() if k in df.columns})

    # Timestamp parsen (deutsches Format: DD.MM.YYYY HH:MM:SS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%d.%m.%Y %H:%M:%S")

    # Lokale Zeit → UTC konvertieren
    # ambiguous="NaT" für mehrdeutige Zeiten (Zeitumstellung), werden später gefiltert
    df["timestamp"] = (
        df["timestamp"]
        .dt.tz_localize(LOCAL_TZ, ambiguous="NaT", nonexistent="NaT")
        .dt.tz_convert(UTC_TZ)
    )

    # Zeilen mit NaT timestamps entfernen (Zeitumstellungs-Probleme)
    before_count = len(df)
    df = df.dropna(subset=["timestamp"])
    dropped = before_count - len(df)
    if dropped > 0:
        logger.warning(f"{dropped} Zeilen wegen Zeitumstellung übersprungen")

    # Zu Unix timestamp (Sekunden)
    df["timestamp"] = df["timestamp"].astype("int64") // 10**9

    # E3DC Timestamps = Intervallende → auf Intervallanfang shiften (-1h)
    # E3DC meldet z.B. 08:00 für Produktion von 07:00-08:00.
    # Wir normalisieren auf Intervallanfang (wie Open-Meteo, DWD).
    df["timestamp"] = df["timestamp"] - 3600

    # Abregelung erkennen: wenn curtail_limit_w < production_w + Toleranz
    if "curtail_limit_w" in df.columns:
        df["curtailed"] = (
            (df["curtail_limit_w"] > 0) & (df["production_w"] >= df["curtail_limit_w"] * 0.95)
        ).astype(int)
        df = df.drop(columns=["curtail_limit_w"])
    else:
        df["curtailed"] = 0

    # Batterie-Spalten entfernen (nicht benötigt für Prognose)
    df = df.drop(columns=["battery_charge_w", "battery_discharge_w"], errors="ignore")

    # Typen sicherstellen
    int_cols = ["production_w", "soc_pct", "grid_feed_w", "grid_draw_w", "consumption_w"]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    logger.debug(f"Geladen: {len(df)} Datensätze")
    return df


def import_to_db(df: pd.DataFrame, db: Database) -> int:
    """
    Importiert DataFrame in SQLite-Datenbank.

    Args:
        df: DataFrame von load_e3dc_csv()
        db: Database-Instanz

    Returns:
        Anzahl neu eingefügter Zeilen
    """
    columns = [
        "timestamp",
        "production_w",
        "curtailed",
        "soc_pct",
        "grid_feed_w",
        "grid_draw_w",
        "consumption_w",
    ]

    # Nur vorhandene Spalten
    columns = [c for c in columns if c in df.columns]

    placeholders = ", ".join(["?"] * len(columns))
    column_names = ", ".join(columns)

    def to_python(val):
        """Konvertiert numpy/pandas Typen zu Python nativen Typen."""
        if pd.isna(val):
            return None
        if hasattr(val, "item"):  # numpy scalar
            return val.item()
        return val

    # Alle Zeilen in Liste von Tupeln konvertieren (für executemany)
    # itertuples() ist ~100x schneller als iterrows()
    all_values = [
        tuple(to_python(getattr(row, c, None)) for c in columns)
        for row in df[columns].itertuples(index=False)
    ]

    # SQL-Statement bauen (Spalten sind aus interner Konstante, nicht User-Input)
    sql = "INSERT OR IGNORE INTO pv_readings (" + column_names + ") VALUES (" + placeholders + ")"

    with db.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM pv_readings").fetchone()[0]
        conn.executemany(sql, all_values)
        after = conn.execute("SELECT COUNT(*) FROM pv_readings").fetchone()[0]
        inserted = after - before

    logger.debug(f"Importiert: {inserted} neue Datensätze")
    return inserted


def import_csv_files(csv_paths: list[Path], db: Database) -> int:
    """
    Importiert mehrere CSV-Dateien.

    Args:
        csv_paths: Liste von CSV-Pfaden
        db: Database-Instanz

    Returns:
        Gesamtzahl neu eingefügter Zeilen
    """
    total = 0
    n_files = len(csv_paths)
    for i, path in enumerate(csv_paths, 1):
        try:
            df = load_e3dc_csv(path)
            count = import_to_db(df, db)
            total += count
            logger.info(f"[{i}/{n_files}] {path.name}: {count} neue Datensätze")
        except DataImportError as e:
            logger.error(f"[{i}/{n_files}] Fehler bei {path}: {e}")
    return total
