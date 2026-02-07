"""Command-Line Interface für pvforecast."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pvforecast import __version__
from pvforecast.config import (
    DEFAULT_CONFIG,
    Config,
    ConfigValidationError,
    get_config_path,
    load_config,
)
from pvforecast.data_loader import DataImportError, import_csv_files
from pvforecast.db import Database
from pvforecast.doctor import Doctor
from pvforecast.model import (
    EvaluationResult,
    Forecast,
    ModelNotFoundError,
    evaluate,
    load_model,
    predict,
    save_model,
    train,
    tune,
    tune_optuna,
)
from pvforecast.setup import SetupWizard
from pvforecast.sources.base import WeatherSourceError
from pvforecast.sources.hostrada import HOSTRADASource
from pvforecast.sources.mosmix import MOSMIXConfig, MOSMIXSource
from pvforecast.validation import (
    DependencyError,
    ValidationError,
    validate_csv_files,
    validate_latitude,
    validate_longitude,
)
from pvforecast.weather import (
    WeatherAPIError,
    ensure_weather_history,
    fetch_forecast,
    fetch_today,
)

logger = logging.getLogger(__name__)


def _get_forecast_source(config: Config, source_override: str | None = None):
    """
    Get the appropriate forecast source based on config or override.

    Args:
        config: Application config
        source_override: Override source name (mosmix, open-meteo)

    Returns:
        ForecastSource instance or None for legacy open-meteo
    """
    source = source_override or config.weather.forecast_provider

    if source == "mosmix":
        mosmix_config = MOSMIXConfig(
            station_id=config.weather.mosmix.station_id,
            use_mosmix_l=config.weather.mosmix.use_mosmix_l,
            lat=config.latitude,
            lon=config.longitude,
        )
        return MOSMIXSource(mosmix_config)
    elif source == "open-meteo":
        return None  # Use legacy weather.py functions
    else:
        raise ValueError(f"Unknown forecast source: {source}")


def _get_historical_source(config: Config, source_override: str | None = None):
    """
    Get the appropriate historical source based on config or override.

    Args:
        config: Application config
        source_override: Override source name (hostrada, open-meteo)

    Returns:
        HistoricalSource instance or None for legacy open-meteo
    """
    source = source_override or config.weather.historical_provider

    if source == "hostrada":
        return HOSTRADASource(
            latitude=config.latitude,
            longitude=config.longitude,
        )
    elif source == "open-meteo":
        return None  # Use legacy weather.py functions
    else:
        raise ValueError(f"Unknown historical source: {source}")


def format_duration(seconds: float) -> str:
    """Formatiert Sekunden als lesbare Dauer."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if secs == 0:
        return f"{minutes}m"
    return f"{minutes}m {secs}s"


# Wetter-Emojis für Ausgabe
WEATHER_EMOJI = {
    (0, 10): "☀️",  # klar
    (10, 30): "🌤️",  # leicht bewölkt
    (30, 60): "⛅",  # teilweise bewölkt
    (60, 85): "🌥️",  # überwiegend bewölkt
    (85, 101): "☁️",  # bedeckt
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


def cmd_fetch_forecast(args: argparse.Namespace, config: Config) -> int:
    """Fetches weather forecast data from configured source."""
    source_name = getattr(args, "source", None) or config.weather.forecast_provider
    hours = getattr(args, "hours", 48)
    output_format = getattr(args, "format", "table")

    print(f"🌤️  Fetching forecast from {source_name}...")

    try:
        source = _get_forecast_source(config, source_name)

        if source is None:
            # Legacy open-meteo
            weather_df = fetch_forecast(config.latitude, config.longitude, hours=hours)
        else:
            weather_df = source.fetch_forecast(hours=hours)

    except WeatherSourceError as e:
        print(f"❌ Fehler: {e}", file=sys.stderr)
        return 1
    except WeatherAPIError as e:
        print(f"❌ Fehler: {e}", file=sys.stderr)
        return 1

    if len(weather_df) == 0:
        print("❌ Keine Wetterdaten verfügbar.", file=sys.stderr)
        return 1

    # Output
    if output_format == "json":
        import json

        records = weather_df.to_dict(orient="records")
        # Convert timestamps to ISO format
        for r in records:
            if "timestamp" in r:
                r["timestamp"] = datetime.fromtimestamp(r["timestamp"], ZoneInfo("UTC")).isoformat()
        print(json.dumps(records, indent=2))
    elif output_format == "csv":
        print(weather_df.to_csv(index=False))
    else:
        # Table format
        tz = ZoneInfo(config.timezone)
        print()
        print(f"Weather Forecast ({source_name})")
        print(f"Station: {config.weather.mosmix.station_id}" if source_name == "mosmix" else "")
        print("=" * 70)
        print(f"{'Zeit':18} {'GHI':>8} {'Wolken':>8} {'Temp':>8} {'DHI':>8}")
        print("-" * 70)

        for _, row in weather_df.head(24).iterrows():
            dt = datetime.fromtimestamp(row["timestamp"], tz)
            time_str = dt.strftime("%d.%m. %H:%M")
            ghi = row.get("ghi_wm2", 0)
            cloud = row.get("cloud_cover_pct", 0)
            temp = row.get("temperature_c", 0)
            dhi = row.get("dhi_wm2", 0)
            emoji = get_weather_emoji(int(cloud))

            print(f"{time_str:18} {ghi:>7.0f}W {cloud:>6}% {emoji} {temp:>6.1f}°C {dhi:>7.1f}W")

        if len(weather_df) > 24:
            print(f"... ({len(weather_df) - 24} weitere Stunden)")
        print()

    print(f"✅ {len(weather_df)} Stunden Forecast geladen")
    return 0


def cmd_fetch_historical(args: argparse.Namespace, config: Config) -> int:
    """Fetches historical weather data from configured source."""
    from datetime import date

    source_name = getattr(args, "source", None) or config.weather.historical_provider
    output_format = getattr(args, "format", "table")

    # Parse date range
    start_str = getattr(args, "start", None)
    end_str = getattr(args, "end", None)

    if not start_str or not end_str:
        # Default: last 7 days
        end_date = date.today() - timedelta(days=60)  # HOSTRADA ~2 months behind
        start_date = end_date - timedelta(days=6)
    else:
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)

    print(f"🌤️  Fetching historical data from {source_name}...")
    print(f"   Range: {start_date} to {end_date}")

    # Warning for HOSTRADA due to massive download size
    if source_name == "hostrada":
        force_download = getattr(args, "force", False)

        # Check which months already exist in DB (skip if --force)
        from pvforecast.db import Database

        db = Database(config.db_path)
        existing_months = db.get_weather_months_with_data() if not force_download else set()

        # Calculate requested months
        requested_months: set[tuple[int, int]] = set()
        current = date(start_date.year, start_date.month, 1)
        end_month = date(end_date.year, end_date.month, 1)
        while current <= end_month:
            requested_months.add((current.year, current.month))
            # Next month
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        # Find missing months
        missing_months = requested_months - existing_months

        if not missing_months:
            print("✅ Alle angeforderten Monate sind bereits in der Datenbank.")
            return 0

        # Sort for display
        missing_sorted = sorted(missing_months)
        months = len(missing_months)
        est_gb = months * 0.15 * 5  # ~150 MB per month per parameter, 5 parameters

        print()
        if existing_months & requested_months:
            skipped = len(requested_months) - len(missing_months)
            print(f"ℹ️  {skipped} Monate bereits in DB, überspringe diese.")
        print("⚠️  HOSTRADA lädt komplette Deutschland-Raster herunter.")
        print(f"    Fehlende Monate: {months}")
        print(f"    Geschätzter Download: ~{est_gb:.1f} GB ({months} Monate × 5 Parameter)")
        lat, lon = config.latitude, config.longitude
        print(f"    Extrahierte Daten: wenige MB (nur Gridpunkt {lat:.2f}°N, {lon:.2f}°E)")
        print()
        print("    Für regelmäßige Updates empfehlen wir Open-Meteo.")
        print("    HOSTRADA eignet sich für einmaliges Training mit historischen Daten.")
        print()

        skip_confirm = getattr(args, "yes", False)
        if not skip_confirm:
            try:
                confirm = input("Fortfahren? [y/N]: ").strip().lower()
                if confirm not in ("y", "yes", "j", "ja"):
                    print("Abgebrochen.")
                    return 0
            except (EOFError, KeyboardInterrupt):
                print("\nAbgebrochen.")
                return 0

        # Adjust date range to only fetch missing months
        first_missing = min(missing_sorted)
        last_missing = max(missing_sorted)
        start_date = date(first_missing[0], first_missing[1], 1)
        # End date = last day of last missing month
        if last_missing[1] == 12:
            end_date = date(last_missing[0] + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(last_missing[0], last_missing[1] + 1, 1) - timedelta(days=1)

    try:
        source = _get_historical_source(config, source_name)

        if source is None:
            print("❌ Open-Meteo historical not implemented via this command yet.", file=sys.stderr)
            print("   Use 'pvforecast import' instead.", file=sys.stderr)
            return 1

        weather_df = source.fetch_historical(start_date, end_date)

    except WeatherSourceError as e:
        print(f"❌ Fehler: {e}", file=sys.stderr)
        return 1

    if len(weather_df) == 0:
        print("❌ Keine Wetterdaten verfügbar.", file=sys.stderr)
        return 1

    # Output
    if output_format == "json":
        records = weather_df.reset_index().to_dict(orient="records")
        # Convert timestamps
        for r in records:
            if "timestamp" in r:
                r["timestamp"] = datetime.fromtimestamp(r["timestamp"], ZoneInfo("UTC")).isoformat()
            if "index" in r:
                r["time"] = str(r.pop("index"))
        print(json.dumps(records, indent=2, default=str))
    elif output_format == "csv":
        print(weather_df.to_csv())
    else:
        # Table format
        ZoneInfo(config.timezone)
        print()
        print(f"Historical Weather ({source_name})")
        print("=" * 80)
        print(f"{'Zeit':18} {'GHI':>8} {'Wolken':>8} {'Temp':>8} {'Feuchte':>8} {'Wind':>8}")
        print("-" * 80)

        # Show daily summaries
        weather_df_display = weather_df.copy()
        weather_df_display["date"] = weather_df_display.index.date

        for dt, day_df in weather_df_display.groupby("date"):
            ghi_sum = day_df["ghi_wm2"].sum() / 1000  # kWh/m²
            cloud_avg = day_df["cloud_cover_pct"].mean()
            temp_avg = day_df["temperature_c"].mean()
            humid_avg = day_df["humidity_pct"].mean()
            wind_avg = day_df["wind_speed_ms"].mean()
            emoji = get_weather_emoji(int(cloud_avg))

            print(
                f"{str(dt):18} {ghi_sum:>6.1f}kWh {cloud_avg:>6.0f}% {emoji} "
                f"{temp_avg:>6.1f}°C {humid_avg:>6.0f}% {wind_avg:>6.1f}m/s"
            )

        print()

    total_hours = len(weather_df)
    total_days = total_hours / 24
    print(f"✅ {total_hours} Stunden ({total_days:.0f} Tage) historische Daten geladen")
    return 0


def cmd_predict(args: argparse.Namespace, config: Config) -> int:
    """Führt Prognose aus."""
    import pandas as pd

    tz = ZoneInfo(config.timezone)
    source_name = getattr(args, "source", None)

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
        source = _get_forecast_source(config, source_name)
        if source is None:
            # Legacy open-meteo
            weather_df = fetch_forecast(config.latitude, config.longitude, hours=hours_needed)
        else:
            weather_df = source.fetch_forecast(hours=hours_needed)
    except WeatherSourceError as e:
        print(f"❌ Fehler bei Wetterabfrage: {e}", file=sys.stderr)
        return 1
    except WeatherAPIError as e:
        print(f"❌ Fehler bei Wetterabfrage: {e}", file=sys.stderr)
        return 1

    if len(weather_df) == 0:
        print("❌ Keine Wetterdaten verfügbar.", file=sys.stderr)
        return 1

    # Filtere auf Ziel-Tage (volle Tage morgen + übermorgen etc.)
    # Vektorisierte Datums-Filterung statt apply()
    weather_dates = pd.to_datetime(weather_df["timestamp"], unit="s", utc=True)
    weather_dates_local = weather_dates.dt.tz_convert(tz).dt.date
    weather_df = weather_df[weather_dates_local.isin(target_dates)]

    if len(weather_df) == 0:
        print("❌ Keine Wetterdaten für die Ziel-Tage verfügbar.", file=sys.stderr)
        return 1

    # Prognose erstellen (mode="predict" für Zukunftsprognose ohne Produktions-Lags)
    forecast = predict(
        model, weather_df, config.latitude, config.longitude, config.peak_kwp, mode="predict"
    )

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
    tz = ZoneInfo(config.timezone)
    source_name = getattr(args, "source", None)

    # Modell laden
    try:
        model, metrics = load_model(config.model_path)
    except ModelNotFoundError:
        print("❌ Kein trainiertes Modell gefunden.", file=sys.stderr)
        print("   Führe erst 'pvforecast train' aus.", file=sys.stderr)
        return 1

    today = datetime.now(tz).date()

    # Wetterdaten für heute holen
    try:
        source = _get_forecast_source(config, source_name)
        if source is None:
            # Legacy open-meteo (nutzt Retry-Logic aus weather.py)
            weather_df = fetch_today(config.latitude, config.longitude, tz)
        else:
            # DWD source - fetch_today returns full day
            weather_df = source.fetch_today(str(tz))
    except WeatherSourceError as e:
        print(f"❌ Fehler bei Wetterabfrage: {e}", file=sys.stderr)
        return 1
    except WeatherAPIError as e:
        print(f"❌ Fehler bei Wetterabfrage: {e}", file=sys.stderr)
        return 1

    # TODO: Für bessere Today-Prognose: Produktionsdaten bis jetzt aus DB holen
    # und mit weather_df mergen, dann mode="today" verwenden.
    # Aktuell: mode="predict" (ohne Produktions-Lags)
    forecast = predict(
        model, weather_df, config.latitude, config.longitude, config.peak_kwp, mode="predict"
    )

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

    # Validiere CSV-Dateien (existieren, lesbar, .csv Endung)
    csv_paths = validate_csv_files(args.files)

    start_time = time.perf_counter()
    total = import_csv_files(csv_paths, db)
    elapsed = time.perf_counter() - start_time

    print(f"✅ Import abgeschlossen in {format_duration(elapsed)}: {total} neue Datensätze")
    print(f"   Datenbank: {config.db_path}")
    print(f"   Gesamt in DB: {db.get_pv_count()} PV-Datensätze")

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
    weather_start = time.perf_counter()
    try:
        loaded = ensure_weather_history(db, config.latitude, config.longitude, pv_start, pv_end)
        weather_elapsed = time.perf_counter() - weather_start
        if loaded > 0:
            duration = format_duration(weather_elapsed)
            print(f"   {loaded} neue Wetterdatensätze geladen in {duration}")
    except WeatherAPIError as e:
        print(f"⚠️  Wetter-API Fehler: {e}", file=sys.stderr)
        print("   Versuche Training mit vorhandenen Daten...", file=sys.stderr)

    weather_count = db.get_weather_count()
    print(f"🌡️  Wetterdatensätze: {weather_count}")

    # Training
    model_type = getattr(args, "model", "rf")
    since_year = getattr(args, "since", None)
    model_name = "XGBoost" if model_type == "xgb" else "RandomForest"

    if since_year:
        print(f"🧠 Trainiere {model_name} Modell (Daten ab {since_year})...")
    else:
        print(f"🧠 Trainiere {model_name} Modell...")

    train_start = time.perf_counter()
    try:
        model, metrics = train(
            db,
            config.latitude,
            config.longitude,
            model_type,
            since_year=since_year,
            peak_kwp=config.peak_kwp,
        )
    except ValueError as e:
        print(f"❌ Training fehlgeschlagen: {e}", file=sys.stderr)
        return 1
    train_elapsed = time.perf_counter() - train_start

    # Modell speichern
    save_model(model, config.model_path, metrics)

    print("")
    print(f"✅ Training abgeschlossen in {format_duration(train_elapsed)}!")
    print(f"   MAPE: {metrics['mape']:.1f}%")
    print(f"   MAE:  {metrics['mae']:.0f} W")
    print(f"   RMSE: {metrics['rmse']:.0f} W")
    print(f"   R²:   {metrics['r2']:.3f}")
    print(f"   Trainingsdaten: {metrics['n_train']}")
    print(f"   Testdaten: {metrics['n_test']}")
    if since_year:
        print(f"   Daten ab: {since_year}")
    print(f"   Modell: {config.model_path}")

    return 0


def cmd_tune(args: argparse.Namespace, config: Config) -> int:
    """Hyperparameter-Tuning mit RandomizedSearchCV oder Optuna."""
    db = Database(config.db_path)

    # Prüfe ob genug Daten vorhanden
    pv_count = db.get_pv_count()
    if pv_count < 500:
        print(f"❌ Zu wenig PV-Daten: {pv_count} (mindestens 500 empfohlen)", file=sys.stderr)
        return 1

    print(f"📊 PV-Datensätze: {pv_count}")

    # Zeitbereich der PV-Daten
    pv_start, pv_end = db.get_pv_date_range()
    if not pv_start or not pv_end:
        print("❌ Keine PV-Daten gefunden.", file=sys.stderr)
        return 1

    # Wetterdaten sicherstellen
    print("🌤️  Prüfe Wetterdaten...")
    weather_start = time.perf_counter()
    try:
        loaded = ensure_weather_history(db, config.latitude, config.longitude, pv_start, pv_end)
        weather_elapsed = time.perf_counter() - weather_start
        if loaded > 0:
            duration = format_duration(weather_elapsed)
            print(f"   {loaded} neue Wetterdatensätze geladen in {duration}")
    except WeatherAPIError as e:
        print(f"⚠️  Wetter-API Fehler: {e}", file=sys.stderr)

    # Parameter aus args
    model_type = getattr(args, "model", "xgb")
    method = getattr(args, "method", "random")
    n_iter = getattr(args, "trials", 50)
    cv_splits = getattr(args, "cv", 5)
    timeout = getattr(args, "timeout", None)
    since_year = getattr(args, "since", None)
    model_name = "XGBoost" if model_type == "xgb" else "RandomForest"
    method_name = "Optuna" if method == "optuna" else "RandomizedSearchCV"

    print()
    print(f"🔧 Hyperparameter-Tuning für {model_name}")
    print(f"   Methode: {method_name}")
    print(f"   Trials: {n_iter}")
    print(f"   CV-Splits: {cv_splits}")
    if timeout and method == "optuna":
        print(f"   Timeout: {timeout}s")
    if since_year:
        print(f"   Daten ab: {since_year}")
    print()
    print("⏳ Das kann einige Minuten dauern...")
    print()

    tune_start = time.perf_counter()
    try:
        if method == "optuna":
            best_model, metrics, best_params = tune_optuna(
                db,
                config.latitude,
                config.longitude,
                model_type=model_type,
                n_trials=n_iter,
                cv_splits=cv_splits,
                timeout=timeout,
                show_progress=True,
                since_year=since_year,
                peak_kwp=config.peak_kwp,
            )
        else:
            best_model, metrics, best_params = tune(
                db,
                config.latitude,
                config.longitude,
                model_type=model_type,
                n_iter=n_iter,
                cv_splits=cv_splits,
                since_year=since_year,
                peak_kwp=config.peak_kwp,
            )
    except DependencyError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"❌ Tuning fehlgeschlagen: {e}", file=sys.stderr)
        return 1
    tune_elapsed = time.perf_counter() - tune_start

    # Modell speichern
    save_model(best_model, config.model_path, metrics)

    print()
    print("=" * 50)
    print(f"✅ Tuning abgeschlossen in {format_duration(tune_elapsed)}!")
    print("=" * 50)
    print()
    print("📊 Performance:")
    print(f"   MAPE: {metrics['mape']:.1f}%")
    print(f"   MAE:  {metrics['mae']:.0f} W")
    print(f"   RMSE: {metrics['rmse']:.0f} W")
    print(f"   R²:   {metrics['r2']:.3f}")
    print(f"   CV-Score (MAE): {metrics['best_cv_score']:.0f} W")

    # Optuna-spezifische Stats
    if method == "optuna":
        print()
        print("📈 Optuna-Statistiken:")
        print(f"   Trials abgeschlossen: {metrics.get('n_trials_complete', 'N/A')}")
        print(f"   Trials gepruned: {metrics.get('n_trials_pruned', 'N/A')}")

    print()
    print("🎯 Beste Parameter:")
    for param, value in best_params.items():
        # np.float64 und andere float-artige Typen erkennen
        try:
            float_val = float(value)
            # Prüfen ob es wirklich ein Float ist (nicht int als float)
            if float_val != int(float_val):
                print(f"   {param}: {float_val:.4f}")
            else:
                print(f"   {param}: {int(float_val)}")
        except (TypeError, ValueError):
            print(f"   {param}: {value}")
    print()
    print(f"💾 Modell gespeichert: {config.model_path}")

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
            print(
                f"   PV-Zeitraum: {datetime.fromtimestamp(pv_start).date()} "
                f"bis {datetime.fromtimestamp(pv_end).date()}"
            )
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
                if metrics.get("rmse"):
                    print(f"   RMSE: {metrics.get('rmse')} W")
                if metrics.get("r2"):
                    print(f"   R²: {metrics.get('r2')}")
                print(f"   Trainiert auf: {metrics.get('n_samples', '?')} Datensätze")
            else:
                print("   ✅ Vorhanden (keine Metriken)")
        except Exception as e:
            print(f"   ⚠️  Fehler beim Laden: {e}")
    else:
        print("   ❌ Nicht vorhanden")

    return 0


def cmd_evaluate(args: argparse.Namespace, config: Config) -> int:
    """Evaluiert das Modell gegen echte Daten (Backtesting)."""
    from datetime import datetime

    # Modell laden
    try:
        model, _ = load_model(config.model_path)
    except ModelNotFoundError:
        print("❌ Kein trainiertes Modell gefunden!")
        print(f"   Pfad: {config.model_path}")
        print("   Tipp: Erst 'pvforecast train' ausführen")
        return 1

    # Jahr ermitteln
    year = args.year if args.year else datetime.now().year - 1

    # Datenbank öffnen und Evaluation durchführen
    db = Database(config.db_path)

    try:
        result = evaluate(
            model=model,
            db=db,
            lat=config.latitude,
            lon=config.longitude,
            peak_kwp=config.peak_kwp,
            year=year,
        )
    except ValueError as e:
        print(f"❌ {e}")
        return 1

    # Ausgabe formatieren
    _print_evaluation_result(result)
    return 0


def _print_evaluation_result(result: EvaluationResult) -> None:
    """Formatiert und gibt EvaluationResult aus."""
    print(f"📊 Backtesting für {result.year}")
    print("=" * 50)
    print(f"📈 Datenpunkte: {result.data_points:,}")

    print()
    print("📉 Gesamtmetriken:")
    print(f"   MAE:  {result.mae:.0f} W")
    print(f"   RMSE: {result.rmse:.0f} W")
    print(f"   R²:   {result.r2:.3f}")
    print(f"   MAPE: {result.mape:.1f}% (nur Stunden > 100W)")

    # Skill Score vs Persistence
    if result.skill_score is not None and result.mae_persistence is not None:
        print()
        print("🎯 Skill Score (vs. Persistence):")
        # Berechne ML MAE aus Skill Score für Anzeige
        ml_mae = result.mae_persistence * (1 - result.skill_score / 100)
        print(f"   ML-Modell MAE:      {ml_mae:.0f} W")
        print(f"   Persistence MAE:    {result.mae_persistence:.0f} W")
        if result.skill_score > 0:
            print(f"   Skill Score:        +{result.skill_score:.1f}% (ML ist besser)")
        else:
            print(f"   Skill Score:        {result.skill_score:.1f}% (Persistence ist besser)")

    # Performance nach Wetterbedingungen
    print()
    print("🌤️  Performance nach Wetter:")
    for wb in result.weather_breakdown:
        print(f"   {wb.label:22} MAE {wb.mae:5.0f}W, MAPE {wb.mape:5.1f}%")
    print()

    # Jahresübersicht
    print(f"☀️  Jahresertrag {result.year}:")
    print(f"   Tatsächlich:  {result.total_actual_kwh:,.0f} kWh")
    print(f"   Vorhersage:   {result.total_predicted_kwh:,.0f} kWh")
    print(f"   Abweichung:   {result.total_error_kwh:+,.0f} kWh ({result.total_error_pct:+.1f}%)")
    print()

    # Monatsübersicht
    print("📅 Monatliche Abweichung:")
    month_names = [
        "Jan",
        "Feb",
        "Mär",
        "Apr",
        "Mai",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Okt",
        "Nov",
        "Dez",
    ]

    for month in range(1, 13):
        month_data = result.monthly[result.monthly["month"] == month]
        if len(month_data) > 0:
            err = month_data.iloc[0]["error_pct"]
            bar = "█" * min(10, int(abs(err) / 2))
            sign = "+" if err > 0 else "-" if err < 0 else " "
            print(f"   {month_names[month - 1]}: {sign}{abs(err):5.1f}% {bar}")
        else:
            print(f"   {month_names[month - 1]}: keine Daten")


def cmd_setup(args: argparse.Namespace, config: Config) -> int:
    """Führt den interaktiven Setup-Wizard aus."""
    config_path = get_config_path()

    if config_path.exists() and not args.force:
        print(f"⚠️  Config existiert bereits: {config_path}")
        print("   Verwende --force um zu überschreiben.")
        return 1

    wizard = SetupWizard()
    try:
        wizard.run_interactive()
        return 0
    except KeyboardInterrupt:
        print("\n⚠️  Setup abgebrochen.")
        return 130


def cmd_reset(args: argparse.Namespace, config: Config) -> int:
    """Setzt Datenbank, Modell und/oder Config zurück."""
    from pvforecast.config import _default_config_path

    # Pfade bestimmen
    db_path = Path(config.db_path)
    model_path = Path(config.model_path)
    config_path = _default_config_path()

    # Targets bestimmen
    targets: list[str] = []
    if args.all:
        targets = ["db", "model", "config"]
    else:
        if args.database:
            targets.append("db")
        if args.model_file:
            targets.append("model")
        if args.configuration:
            targets.append("config")

    # Interaktive Auswahl wenn keine Flags
    if not targets and not args.force:
        print("⚠️  Reset - Daten werden unwiderruflich gelöscht!")
        print()
        print("Was soll gelöscht werden?")
        print()

        # Datenbank
        db_info = "nicht vorhanden"
        if db_path.exists():
            try:
                db = Database(db_path)
                with db.connect() as conn:
                    pv_count = conn.execute("SELECT COUNT(*) FROM pv_readings").fetchone()[0]
                db_info = f"{pv_count:,} PV-Datensätze"
            except Exception:
                db_info = "vorhanden"
        response = input(f"  [D]atenbank ({db_info})? [j/N]: ").strip().lower()
        if response in ("j", "y", "d"):
            targets.append("db")

        # Modell
        model_info = "nicht vorhanden"
        if model_path.exists():
            try:
                model_data = load_model(model_path)
                model_info = f"{model_data.model_type}, MAPE {model_data.mape:.1f}%"
            except Exception:
                model_info = "vorhanden"
        response = input(f"  [M]odell ({model_info})? [j/N]: ").strip().lower()
        if response in ("j", "y", "m"):
            targets.append("model")

        # Config
        config_info = "nicht vorhanden"
        if config_path.exists():
            config_info = f"{config.system_name}, {config.peak_kwp} kWp"
        response = input(f"  [C]onfig ({config_info})? [j/N]: ").strip().lower()
        if response in ("j", "y", "c"):
            targets.append("config")

        print()

    if not targets:
        print("Nichts ausgewählt. Abbruch.")
        return 0

    # Zusammenfassung anzeigen
    print("Folgende Dateien werden gelöscht:")
    files_to_delete: list[Path] = []

    if "db" in targets:
        if db_path.exists():
            size = db_path.stat().st_size / 1024 / 1024
            print(f"  📊 Datenbank: {db_path} ({size:.1f} MB)")
            files_to_delete.append(db_path)
        else:
            print(f"  📊 Datenbank: {db_path} (nicht vorhanden)")

    if "model" in targets:
        if model_path.exists():
            size = model_path.stat().st_size / 1024 / 1024
            print(f"  🧠 Modell: {model_path} ({size:.1f} MB)")
            files_to_delete.append(model_path)
        else:
            print(f"  🧠 Modell: {model_path} (nicht vorhanden)")

    if "config" in targets:
        if config_path.exists():
            print(f"  ⚙️  Config: {config_path}")
            files_to_delete.append(config_path)
        else:
            print(f"  ⚙️  Config: {config_path} (nicht vorhanden)")

    print()

    if not files_to_delete:
        print("Keine Dateien zum Löschen vorhanden.")
        return 0

    # Dry-run
    if args.dry_run:
        print("(Dry-run: Keine Dateien wurden gelöscht)")
        return 0

    # Bestätigung
    if not args.force:
        response = input("Wirklich löschen? [j/N]: ").strip().lower()
        if response not in ("j", "y"):
            print("Abbruch.")
            return 1

    # Löschen
    for file_path in files_to_delete:
        try:
            file_path.unlink()
            print(f"✅ Gelöscht: {file_path}")
        except PermissionError:
            print(f"❌ Keine Berechtigung: {file_path}")
            return 1
        except Exception as e:
            print(f"❌ Fehler beim Löschen von {file_path}: {e}")
            return 1

    print()
    print("Reset abgeschlossen.")
    if "config" in targets:
        print("Tipp: 'pvforecast setup' für Neueinrichtung")

    return 0


def cmd_doctor(args: argparse.Namespace, config: Config) -> int:
    """Führt Diagnose-Checks aus."""
    doctor = Doctor()
    return doctor.run()


def cmd_config(args: argparse.Namespace, config: Config) -> int:
    """Verwaltet die Konfiguration."""
    config_path = get_config_path()

    if args.path:
        print(config_path)
        return 0

    if args.init:
        if config_path.exists():
            print(f"⚠️  Config existiert bereits: {config_path}")
            print("   Lösche die Datei manuell um neu zu erstellen.")
            return 1
        config.save(config_path)
        print(f"✅ Config erstellt: {config_path}")
        return 0

    # Default: --show
    print("PV-Forecast Konfiguration")
    print("=" * 50)
    print()
    print(f"📄 Config-Datei: {config_path}")
    if config_path.exists():
        print("   Status: ✅ vorhanden")
    else:
        print("   Status: ❌ nicht vorhanden (nutze Defaults)")
        print("   Tipp: 'pvforecast config --init' zum Erstellen")
    print()
    print("📍 Standort:")
    print(f"   Latitude:  {config.latitude}")
    print(f"   Longitude: {config.longitude}")
    print(f"   Timezone:  {config.timezone}")
    print()
    print("⚡ Anlage:")
    print(f"   Name:      {config.system_name}")
    print(f"   Peak:      {config.peak_kwp} kWp")
    print()
    print("💾 Pfade:")
    print(f"   Datenbank: {config.db_path}")
    print(f"   Modell:    {config.model_path}")

    return 0


def create_parser() -> argparse.ArgumentParser:
    """Erstellt den Argument-Parser."""
    parser = argparse.ArgumentParser(
        prog="pvforecast",
        description="PV-Ertragsprognose auf Basis historischer Daten und Wettervorhersage",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
        "-v",
        "--verbose",
        action="store_true",
        help="Ausführliche Ausgabe",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch-forecast (new)
    p_fetch = subparsers.add_parser("fetch-forecast", help="Holt Wettervorhersage")
    p_fetch.add_argument(
        "--source",
        choices=["mosmix", "open-meteo"],
        default=None,
        help="Datenquelle (default: aus Config)",
    )
    p_fetch.add_argument(
        "--hours",
        type=int,
        default=48,
        help="Anzahl Stunden (default: 48)",
    )
    p_fetch.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Ausgabeformat (default: table)",
    )

    # fetch-historical (new)
    p_fetch_hist = subparsers.add_parser("fetch-historical", help="Holt historische Wetterdaten")
    p_fetch_hist.add_argument(
        "--source",
        choices=["hostrada", "open-meteo"],
        default=None,
        help="Datenquelle (default: aus Config)",
    )
    p_fetch_hist.add_argument(
        "--start",
        type=str,
        default=None,
        help="Startdatum (YYYY-MM-DD)",
    )
    p_fetch_hist.add_argument(
        "--end",
        type=str,
        default=None,
        help="Enddatum (YYYY-MM-DD)",
    )
    p_fetch_hist.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Ausgabeformat (default: table)",
    )
    p_fetch_hist.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Bestätigung überspringen (für Automatisierung)",
    )
    p_fetch_hist.add_argument(
        "--force",
        action="store_true",
        help="Existierende Daten ignorieren und neu herunterladen",
    )

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
    p_predict.add_argument(
        "--source",
        choices=["mosmix", "open-meteo"],
        default=None,
        help="Wetter-Datenquelle (default: aus Config)",
    )

    # import
    p_import = subparsers.add_parser("import", help="Importiert E3DC CSV-Dateien")
    p_import.add_argument(
        "files",
        nargs="+",
        help="CSV-Dateien zum Importieren",
    )

    # today
    p_today = subparsers.add_parser("today", help="Prognose für heute")
    p_today.add_argument(
        "--source",
        choices=["mosmix", "open-meteo"],
        default=None,
        help="Wetter-Datenquelle (default: aus Config)",
    )

    # train
    p_train = subparsers.add_parser("train", help="Trainiert das ML-Modell")
    p_train.add_argument(
        "--model",
        choices=["rf", "xgb"],
        default="rf",
        help="Modell-Typ: rf=RandomForest (default), xgb=XGBoost",
    )
    p_train.add_argument(
        "--since",
        type=int,
        default=None,
        metavar="YEAR",
        help="Nur Daten ab diesem Jahr verwenden (z.B. --since 2022)",
    )

    # tune
    p_tune = subparsers.add_parser("tune", help="Hyperparameter-Tuning")
    p_tune.add_argument(
        "--model",
        choices=["rf", "xgb"],
        default="xgb",
        help="Modell-Typ: rf=RandomForest, xgb=XGBoost (default)",
    )
    p_tune.add_argument(
        "--method",
        choices=["random", "optuna"],
        default="random",
        help="Tuning-Methode: random=RandomizedSearchCV (default), optuna=Bayesian Optimization",
    )
    p_tune.add_argument(
        "--trials",
        type=int,
        default=50,
        help="Anzahl Iterationen/Trials (default: 50)",
    )
    p_tune.add_argument(
        "--cv",
        type=int,
        default=5,
        help="Anzahl CV-Splits (default: 5)",
    )
    p_tune.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Maximale Laufzeit in Sekunden (nur für Optuna)",
    )
    p_tune.add_argument(
        "--since",
        type=int,
        default=None,
        metavar="YEAR",
        help="Nur Daten ab diesem Jahr verwenden (z.B. --since 2022)",
    )

    # status
    subparsers.add_parser("status", help="Zeigt Status an")

    # evaluate
    p_evaluate = subparsers.add_parser("evaluate", help="Evaluiert Modell-Performance")
    p_evaluate.add_argument(
        "--year",
        type=int,
        help="Jahr für Evaluation",
    )

    # config
    p_config = subparsers.add_parser("config", help="Konfiguration verwalten")
    p_config.add_argument(
        "--show",
        action="store_true",
        help="Aktuelle Konfiguration anzeigen",
    )
    p_config.add_argument(
        "--init",
        action="store_true",
        help="Config-Datei mit Defaults erstellen",
    )
    p_config.add_argument(
        "--path",
        action="store_true",
        help="Pfad zur Config-Datei anzeigen",
    )

    # setup
    p_setup = subparsers.add_parser("setup", help="Interaktiver Einrichtungs-Assistent")
    p_setup.add_argument(
        "--force",
        action="store_true",
        help="Überschreibe existierende Konfiguration",
    )

    # doctor
    subparsers.add_parser("doctor", help="Diagnose und Systemcheck")

    # reset
    p_reset = subparsers.add_parser("reset", help="Setzt Daten zurück (Datenbank/Modell/Config)")
    p_reset.add_argument(
        "--all",
        action="store_true",
        help="Alles löschen (Datenbank, Modell, Config)",
    )
    p_reset.add_argument(
        "--database",
        action="store_true",
        help="Nur Datenbank löschen",
    )
    p_reset.add_argument(
        "--model-file",
        action="store_true",
        dest="model_file",
        help="Nur Modell löschen",
    )
    p_reset.add_argument(
        "--configuration",
        action="store_true",
        dest="configuration",
        help="Nur Config löschen",
    )
    p_reset.add_argument(
        "--force",
        action="store_true",
        help="Keine Bestätigung (für Skripte)",
    )
    p_reset.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, nichts löschen",
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

    # HTTP-Logs nur bei --verbose anzeigen
    if not args.verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    try:
        return _run_command(args, parser)
    except ValidationError as e:
        # Benutzerfreundliche Fehlermeldung ohne Stacktrace
        print(f"❌ Fehler: {e}", file=sys.stderr)
        return 1
    except ConfigValidationError as e:
        print(f"❌ Konfigurationsfehler: {e}", file=sys.stderr)
        return 1
    except DependencyError as e:
        print(f"❌ Fehlende Abhängigkeit:\n{e}", file=sys.stderr)
        return 1
    except DataImportError as e:
        print(f"❌ Importfehler: {e}", file=sys.stderr)
        return 1
    except WeatherAPIError as e:
        print(f"❌ Wetter-API-Fehler: {e}", file=sys.stderr)
        return 1
    except WeatherSourceError as e:
        print(f"❌ Wetter-Source-Fehler: {e}", file=sys.stderr)
        return 1
    except ModelNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        print("   Tipp: Führe erst 'pvforecast train' aus.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n⚠️  Abgebrochen.", file=sys.stderr)
        return 130


def _run_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Führt den Befehl aus (innere Funktion für Fehlerbehandlung)."""
    # Config aus Datei laden (falls vorhanden)
    config = load_config()

    # CLI-Argumente überschreiben Config-Datei
    if args.db:
        config.db_path = args.db
    if args.lat:
        try:
            config.latitude = validate_latitude(args.lat)
        except ValidationError as e:
            print(f"❌ Ungültiger Breitengrad: {e}", file=sys.stderr)
            sys.exit(1)
    if args.lon:
        try:
            config.longitude = validate_longitude(args.lon)
        except ValidationError as e:
            print(f"❌ Ungültiger Längengrad: {e}", file=sys.stderr)
            sys.exit(1)

    config.ensure_dirs()

    # Command ausführen
    commands = {
        "fetch-forecast": cmd_fetch_forecast,
        "fetch-historical": cmd_fetch_historical,
        "predict": cmd_predict,
        "today": cmd_today,
        "import": cmd_import,
        "train": cmd_train,
        "tune": cmd_tune,
        "status": cmd_status,
        "evaluate": cmd_evaluate,
        "config": cmd_config,
        "setup": cmd_setup,
        "doctor": cmd_doctor,
        "reset": cmd_reset,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        return cmd_func(args, config)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
