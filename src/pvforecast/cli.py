"""Command-Line Interface für pvforecast."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pvforecast import __version__
from pvforecast.config import DEFAULT_CONFIG, Config
from pvforecast.data_loader import DataImportError, import_csv_files
from pvforecast.db import Database
from pvforecast.model import (
    Forecast,
    ModelNotFoundError,
    load_model,
    predict,
    save_model,
    train,
)
from pvforecast.weather import (
    WeatherAPIError,
    ensure_weather_history,
    fetch_forecast,
)

logger = logging.getLogger(__name__)

# Wetter-Emojis für Ausgabe
WEATHER_EMOJI = {
    (0, 10): "☀️",      # klar
    (10, 30): "🌤️",    # leicht bewölkt
    (30, 60): "⛅",     # teilweise bewölkt
    (60, 85): "🌥️",    # überwiegend bewölkt
    (85, 101): "☁️",   # bedeckt
}


def get_weather_emoji(cloud_cover: int) -> str:
    """Gibt Wetter-Emoji basierend auf Bewölkung zurück."""
    for (low, high), emoji in WEATHER_EMOJI.items():
        if low <= cloud_cover < high:
            return emoji
    return "☁️"


def format_forecast_table(forecast: Forecast, config: Config) -> str:
    """Formatiert Prognose als Tabelle."""
    tz = ZoneInfo(config.timezone)
    lines = []

    lines.append("")
    lines.append(f"PV-Ertragsprognose für {config.system_name} ({config.peak_kwp} kWp)")
    lines.append(f"Erstellt: {forecast.generated_at.astimezone(tz).strftime('%d.%m.%Y %H:%M')}")
    lines.append("")
    lines.append("═" * 60)
    lines.append("Zusammenfassung")
    lines.append("─" * 60)

    # Tages-Summen berechnen
    daily_kwh: dict[str, float] = {}
    for h in forecast.hourly:
        day_key = h.timestamp.astimezone(tz).strftime("%d.%m.")
        daily_kwh[day_key] = daily_kwh.get(day_key, 0) + h.production_w / 1000

    for day, kwh in daily_kwh.items():
        lines.append(f"  {day}:  {kwh:>6.1f} kWh")

    lines.append("  " + "─" * 20)
    lines.append(f"  Gesamt:  {forecast.total_kwh:>6.1f} kWh")
    lines.append("")
    lines.append("═" * 60)
    lines.append("Stundenwerte")
    lines.append("─" * 60)
    lines.append("  Zeit           Ertrag   Wetter")
    lines.append("  " + "─" * 35)

    for h in forecast.hourly:
        local_time = h.timestamp.astimezone(tz)
        time_str = local_time.strftime("%d.%m. %H:%M")
        emoji = get_weather_emoji(h.cloud_cover_pct)

        # Nur Stunden mit Produktion anzeigen (oder Tagesstunden)
        if h.production_w > 0 or 6 <= local_time.hour <= 20:
            lines.append(f"  {time_str}   {h.production_w:>5} W   {emoji}")

    lines.append("")
    return "\n".join(lines)


def format_forecast_json(forecast: Forecast) -> str:
    """Formatiert Prognose als JSON."""
    data = {
        "generated_at": forecast.generated_at.isoformat(),
        "total_kwh": forecast.total_kwh,
        "model_version": forecast.model_version,
        "hourly": [
            {
                "timestamp": h.timestamp.isoformat(),
                "production_w": h.production_w,
                "ghi_wm2": h.ghi_wm2,
                "cloud_cover_pct": h.cloud_cover_pct,
            }
            for h in forecast.hourly
        ],
    }
    return json.dumps(data, indent=2)


def cmd_predict(args: argparse.Namespace, config: Config) -> int:
    """Führt Prognose aus."""
    tz = ZoneInfo(config.timezone)

    # Modell laden
    try:
        model, metrics = load_model(config.model_path)
    except ModelNotFoundError:
        print("❌ Kein trainiertes Modell gefunden.", file=sys.stderr)
        print("   Führe erst 'pvforecast train' aus.", file=sys.stderr)
        return 1

    # Berechne Ziel-Tage (morgen, übermorgen, ...)
    today = datetime.now(tz).date()
    target_dates = [today + timedelta(days=i) for i in range(1, args.days + 1)]

    # Genug Stunden holen um alle Ziel-Tage abzudecken
    hours_needed = (args.days + 1) * 24  # +1 Tag Puffer

    # Wettervorhersage holen
    try:
        weather_df = fetch_forecast(
            config.latitude, config.longitude, hours=hours_needed
        )
    except WeatherAPIError as e:
        print(f"❌ Fehler bei Wetterabfrage: {e}", file=sys.stderr)
        return 1

    if len(weather_df) == 0:
        print("❌ Keine Wetterdaten verfügbar.", file=sys.stderr)
        return 1

    # Filtere auf Ziel-Tage (volle Tage morgen + übermorgen etc.)
    weather_df = weather_df[
        weather_df["timestamp"].apply(
            lambda ts: datetime.fromtimestamp(ts, tz).date() in target_dates
        )
    ]

    if len(weather_df) == 0:
        print("❌ Keine Wetterdaten für die Ziel-Tage verfügbar.", file=sys.stderr)
        return 1

    # Prognose erstellen
    forecast = predict(model, weather_df, config.latitude, config.longitude)

    # Ausgabe formatieren
    if args.format == "json":
        print(format_forecast_json(forecast))
    elif args.format == "csv":
        print("timestamp,production_w,ghi_wm2,cloud_cover_pct")
        for h in forecast.hourly:
            print(f"{h.timestamp.isoformat()},{h.production_w},{h.ghi_wm2},{h.cloud_cover_pct}")
    else:
        print(format_forecast_table(forecast, config))

    return 0


def cmd_today(args: argparse.Namespace, config: Config) -> int:
    """Zeigt Prognose für heute (ganzer Tag)."""
    import httpx
    import pandas as pd

    Database(config.db_path)
    tz = ZoneInfo(config.timezone)

    # Modell laden
    try:
        model, metrics = load_model(config.model_path)
    except ModelNotFoundError:
        print("❌ Kein trainiertes Modell gefunden.", file=sys.stderr)
        print("   Führe erst 'pvforecast train' aus.", file=sys.stderr)
        return 1

    today = datetime.now(tz).date()
    current_hour = datetime.now(tz).hour

    # Wetterdaten für ganzen Tag: past_hours für Vergangenheit, forecast für Rest
    # past_hours=aktuelle Stunde+1 deckt 00:00 bis jetzt ab
    past_hours = current_hour + 2  # +2 für Puffer
    forecast_hours = 24 - current_hour + 1  # Rest des Tages

    try:
        params = {
            "latitude": config.latitude,
            "longitude": config.longitude,
            "hourly": "shortwave_radiation,cloud_cover,temperature_2m",
            "timezone": "UTC",
            "past_hours": past_hours,
            "forecast_hours": forecast_hours,
        }
        with httpx.Client(timeout=30) as client:
            response = client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            data = response.json()

        hourly = data["hourly"]
        weather_df = pd.DataFrame({
            "timestamp": pd.to_datetime(hourly["time"]).astype("int64") // 10**9,
            "ghi_wm2": hourly["shortwave_radiation"],
            "cloud_cover_pct": hourly["cloud_cover"],
            "temperature_c": hourly["temperature_2m"],
        })
        weather_df["ghi_wm2"] = weather_df["ghi_wm2"].fillna(0.0)
        weather_df["cloud_cover_pct"] = weather_df["cloud_cover_pct"].fillna(0).astype(int)
        weather_df["temperature_c"] = weather_df["temperature_c"].fillna(10.0)

    except Exception as e:
        print(f"❌ Fehler bei Wetterabfrage: {e}", file=sys.stderr)
        return 1

    # Filtere auf heute
    weather_df = weather_df[
        weather_df["timestamp"].apply(
            lambda ts: datetime.fromtimestamp(ts, tz).date() == today
        )
    ]

    if len(weather_df) == 0:
        print("❌ Keine Wetterdaten für heute verfügbar.", file=sys.stderr)
        return 1

    # Prognose erstellen
    forecast = predict(model, weather_df, config.latitude, config.longitude)

    # Ausgabe
    now_hour = datetime.now(tz).hour
    print()
    print(f"PV-Prognose für heute ({today.strftime('%d.%m.%Y')})")
    print(f"{config.system_name} ({config.peak_kwp} kWp)")
    print()
    print("═" * 50)
    print(f"  Erwarteter Tagesertrag:  {forecast.total_kwh:>6.1f} kWh")
    print("═" * 50)
    print()
    print("  Stundenwerte")
    print("  " + "─" * 35)

    for h in forecast.hourly:
        local = h.timestamp.astimezone(tz)
        emoji = get_weather_emoji(h.cloud_cover_pct)
        # Markiere aktuelle Stunde
        marker = " ◄" if local.hour == now_hour else ""
        if h.production_w > 0 or 6 <= local.hour <= 20:
            print(f"  {local.strftime('%H:%M')}   {h.production_w:>5} W   {emoji}{marker}")

    print()
    return 0


def cmd_import(args: argparse.Namespace, config: Config) -> int:
    """Importiert CSV-Dateien."""
    db = Database(config.db_path)

    csv_paths = [Path(p) for p in args.files]

    # Prüfe ob Dateien existieren
    for path in csv_paths:
        if not path.exists():
            print(f"❌ Datei nicht gefunden: {path}", file=sys.stderr)
            return 1

    try:
        total = import_csv_files(csv_paths, db)
        print(f"✅ Import abgeschlossen: {total} neue Datensätze")
        print(f"   Datenbank: {config.db_path}")
        print(f"   Gesamt in DB: {db.get_pv_count()} PV-Datensätze")
    except DataImportError as e:
        print(f"❌ Import-Fehler: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_train(args: argparse.Namespace, config: Config) -> int:
    """Trainiert das ML-Modell."""
    db = Database(config.db_path)

    # Prüfe ob PV-Daten vorhanden
    pv_count = db.get_pv_count()
    if pv_count == 0:
        print("❌ Keine PV-Daten in Datenbank.", file=sys.stderr)
        print("   Führe erst 'pvforecast import <csv>' aus.", file=sys.stderr)
        return 1

    print(f"📊 PV-Datensätze: {pv_count}")

    # Zeitbereich der PV-Daten
    pv_start, pv_end = db.get_pv_date_range()
    if not pv_start or not pv_end:
        print("❌ Keine PV-Daten gefunden.", file=sys.stderr)
        return 1

    print(f"📅 Zeitraum: {datetime.fromtimestamp(pv_start)} bis {datetime.fromtimestamp(pv_end)}")

    # Historische Wetterdaten laden
    print("🌤️  Lade historische Wetterdaten...")
    try:
        loaded = ensure_weather_history(
            db, config.latitude, config.longitude, pv_start, pv_end
        )
        if loaded > 0:
            print(f"   {loaded} neue Wetterdatensätze geladen")
    except WeatherAPIError as e:
        print(f"⚠️  Wetter-API Fehler: {e}", file=sys.stderr)
        print("   Versuche Training mit vorhandenen Daten...", file=sys.stderr)

    weather_count = db.get_weather_count()
    print(f"🌡️  Wetterdatensätze: {weather_count}")

    # Training
    print("🧠 Trainiere Modell...")
    try:
        model, metrics = train(db, config.latitude, config.longitude)
    except ValueError as e:
        print(f"❌ Training fehlgeschlagen: {e}", file=sys.stderr)
        return 1

    # Modell speichern
    save_model(model, config.model_path, metrics)

    print("")
    print("✅ Training abgeschlossen!")
    print(f"   MAPE: {metrics['mape']:.1f}%")
    print(f"   MAE:  {metrics['mae']:.0f} W")
    print(f"   Trainingsdaten: {metrics['n_train']}")
    print(f"   Testdaten: {metrics['n_test']}")
    print(f"   Modell: {config.model_path}")

    return 0


def cmd_status(args: argparse.Namespace, config: Config) -> int:
    """Zeigt Status der Datenbank und des Modells."""
    print("PV-Forecast Status")
    print("=" * 40)
    print()

    # Konfiguration
    print("📍 Standort:")
    print(f"   {config.system_name}")
    print(f"   {config.latitude}°N, {config.longitude}°E")
    print(f"   {config.peak_kwp} kWp")
    print()

    # Datenbank
    print(f"💾 Datenbank: {config.db_path}")
    if config.db_path.exists():
        db = Database(config.db_path)
        pv_count = db.get_pv_count()
        weather_count = db.get_weather_count()

        print(f"   PV-Datensätze: {pv_count}")
        print(f"   Wetter-Datensätze: {weather_count}")

        pv_start, pv_end = db.get_pv_date_range()
        if pv_start and pv_end:
            print(f"   PV-Zeitraum: {datetime.fromtimestamp(pv_start).date()} "
                  f"bis {datetime.fromtimestamp(pv_end).date()}")
    else:
        print("   ❌ Nicht vorhanden")
    print()

    # Modell
    print(f"🧠 Modell: {config.model_path}")
    if config.model_path.exists():
        try:
            _, metrics = load_model(config.model_path)
            if metrics:
                print(f"   MAPE: {metrics.get('mape', '?')}%")
                print(f"   MAE: {metrics.get('mae', '?')} W")
                print(f"   Trainiert auf: {metrics.get('n_samples', '?')} Datensätze")
            else:
                print("   ✅ Vorhanden (keine Metriken)")
        except Exception as e:
            print(f"   ⚠️  Fehler beim Laden: {e}")
    else:
        print("   ❌ Nicht vorhanden")

    return 0


def cmd_evaluate(args: argparse.Namespace, config: Config) -> int:
    """Evaluiert das Modell gegen echte Daten."""
    # TODO: Implementierung
    print("⚠️  evaluate noch nicht implementiert")
    return 0


def create_parser() -> argparse.ArgumentParser:
    """Erstellt den Argument-Parser."""
    parser = argparse.ArgumentParser(
        prog="pvforecast",
        description="PV-Ertragsprognose auf Basis historischer Daten und Wettervorhersage",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--db",
        type=Path,
        help=f"Pfad zur Datenbank (default: {DEFAULT_CONFIG.db_path})",
    )
    parser.add_argument(
        "--lat",
        type=float,
        help=f"Breitengrad (default: {DEFAULT_CONFIG.latitude})",
    )
    parser.add_argument(
        "--lon",
        type=float,
        help=f"Längengrad (default: {DEFAULT_CONFIG.longitude})",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Ausführliche Ausgabe",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # predict
    p_predict = subparsers.add_parser("predict", help="Erstellt PV-Prognose")
    p_predict.add_argument(
        "--days",
        type=int,
        default=2,
        help="Anzahl Tage ab morgen (default: 2 = morgen + übermorgen)",
    )
    p_predict.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Ausgabeformat (default: table)",
    )

    # import
    p_import = subparsers.add_parser("import", help="Importiert E3DC CSV-Dateien")
    p_import.add_argument(
        "files",
        nargs="+",
        help="CSV-Dateien zum Importieren",
    )

    # today
    subparsers.add_parser("today", help="Prognose für heute")

    # train
    subparsers.add_parser("train", help="Trainiert das ML-Modell")

    # status
    subparsers.add_parser("status", help="Zeigt Status an")

    # evaluate
    p_evaluate = subparsers.add_parser("evaluate", help="Evaluiert Modell-Performance")
    p_evaluate.add_argument(
        "--year",
        type=int,
        help="Jahr für Evaluation",
    )

    return parser


def main() -> int:
    """Hauptfunktion."""
    parser = create_parser()
    args = parser.parse_args()

    # Logging konfigurieren
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s" if not args.verbose else "%(levelname)s: %(message)s",
    )

    # Config erstellen
    config = Config()
    if args.db:
        config.db_path = args.db
    if args.lat:
        config.latitude = args.lat
    if args.lon:
        config.longitude = args.lon

    config.ensure_dirs()

    # Command ausführen
    commands = {
        "predict": cmd_predict,
        "today": cmd_today,
        "import": cmd_import,
        "train": cmd_train,
        "status": cmd_status,
        "evaluate": cmd_evaluate,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        return cmd_func(args, config)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
