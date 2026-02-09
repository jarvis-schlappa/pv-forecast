"""Command implementations for pvforecast CLI."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pvforecast.config import Config, get_config_path
from pvforecast.data_loader import import_csv_files
from pvforecast.db import Database
from pvforecast.doctor import Doctor
from pvforecast.model import (
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
from pvforecast.validation import (
    DependencyError,
    validate_csv_files,
)
from pvforecast.weather import (
    WeatherAPIError,
    ensure_weather_history,
)

from .formatters import (
    format_duration,
    format_forecast_json,
    format_forecast_table,
    get_weather_emoji,
    print_evaluation_result,
)
from .helpers import get_forecast_source, get_historical_source

# Module-level quiet flag (set by cli.__init__.set_quiet_mode)
_quiet_mode = False


def set_quiet_mode(quiet: bool) -> None:
    """Set the module-level quiet mode flag."""
    global _quiet_mode
    _quiet_mode = quiet


def qprint(*args, **kwargs) -> None:
    """Print only if not in quiet mode. Use for progress/info messages."""
    if not _quiet_mode:
        print(*args, **kwargs)


def cmd_fetch_forecast(args: argparse.Namespace, config: Config) -> int:
    """Fetches weather forecast data from configured source."""
    source_name = getattr(args, "source", None) or config.weather.forecast_provider
    hours = getattr(args, "hours", 48)
    output_format = getattr(args, "format", "table")

    print(f"🌤️  Fetching forecast from {source_name}...")

    try:
        source = get_forecast_source(config, source_name)
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
        db = Database(config.db_path)
        existing_db_months = db.get_weather_months_with_data() if not force_download else set()

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

        # Find months missing from DB
        missing_from_db = requested_months - existing_db_months

        if not missing_from_db:
            print("✅ Alle angeforderten Monate sind bereits in der Datenbank.")
            return 0

        # Check which of the missing months have local files
        local_dir = config.weather.hostrada.local_dir
        source = HOSTRADASource(
            latitude=config.latitude,
            longitude=config.longitude,
            local_dir=local_dir,
        )
        local_months = source.get_local_months(start_date, end_date) if local_dir else set()

        # Months available locally (but not in DB yet)
        local_not_in_db = missing_from_db & local_months

        # Months that need download
        need_download = missing_from_db - local_months

        # Show status
        print()
        if existing_db_months & requested_months:
            skipped = len(requested_months) - len(missing_from_db)
            print(f"ℹ️  {skipped} Monate bereits in DB, überspringe diese.")

        if local_not_in_db:
            print(f"📁 {len(local_not_in_db)} Monate lokal → Import (kein Download)")

        if need_download:
            months = len(need_download)
            est_gb = months * 0.75  # ~750 MB per month (5 parameters × ~150 MB each)

            print("⚠️  HOSTRADA lädt komplette Deutschland-Raster herunter.")
            print(f"    Fehlende Monate: {months}")
            print(f"    Geschätzter Download: ~{est_gb:.1f} GB (~750 MB/Monat)")
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
        else:
            # All missing months are available locally - no download needed
            print("✅ Alle fehlenden Monate sind lokal verfügbar, kein Download nötig.")
            print()

        # Adjust date range to only fetch months missing from DB
        missing_sorted = sorted(missing_from_db)
        first_missing = min(missing_sorted)
        last_missing = max(missing_sorted)
        start_date = date(first_missing[0], first_missing[1], 1)
        # End date = last day of last missing month
        if last_missing[1] == 12:
            end_date = date(last_missing[0] + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(last_missing[0], last_missing[1] + 1, 1) - timedelta(days=1)

    try:
        source = get_historical_source(config, source_name)
        weather_df = source.fetch_historical(start_date, end_date)

    except WeatherSourceError as e:
        print(f"❌ Fehler: {e}", file=sys.stderr)
        return 1

    if len(weather_df) == 0:
        print("❌ Keine Wetterdaten verfügbar.", file=sys.stderr)
        return 1

    # Output (only for explicit json/csv format - default just saves to DB)
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
    # Default: no table output, just save to DB

    # Save to database
    db = Database(config.db_path)

    # Convert DataFrame to records for DB insert
    records = []
    for idx, row in weather_df.iterrows():
        ts = idx.timestamp() if hasattr(idx, "timestamp") else idx
        records.append(
            (
                int(ts),
                float(row.get("ghi_wm2", 0)),
                float(row.get("cloud_cover_pct", 0)),
                float(row.get("temperature_c", 0)),
                float(row.get("wind_speed_ms", 0)),
                float(row.get("humidity_pct", 0)),
                float(row.get("dhi_wm2", 0)),
                float(row.get("dni_wm2", 0)),
            )
        )

    if records:
        with db.connect() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO weather_history
                   (timestamp, ghi_wm2, cloud_cover_pct, temperature_c,
                    wind_speed_ms, humidity_pct, dhi_wm2, dni_wm2)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                records,
            )
        print(f"💾 {len(records)} Datensätze in Datenbank gespeichert")

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
        source = get_forecast_source(config, source_name)
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
    model_version = metrics.get("model_version") if metrics else None
    forecast = predict(
        model, weather_df, config.latitude, config.longitude, config.peak_kwp,
        mode="predict", model_version=model_version
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
    full_day = getattr(args, "full", False)

    # Modell laden
    try:
        model, metrics = load_model(config.model_path)
    except ModelNotFoundError:
        print("❌ Kein trainiertes Modell gefunden.", file=sys.stderr)
        print("   Führe erst 'pvforecast train' aus.", file=sys.stderr)
        return 1

    today = datetime.now(tz).date()
    now_hour = datetime.now(tz).hour

    # Wetterdaten für heute holen
    try:
        source = get_forecast_source(config, source_name)
        weather_df = source.fetch_today(str(tz))

        # MOSMIX liefert nur Prognose ab jetzt (keine past_hours)
        if source_name == "mosmix" and full_day and now_hour > 6:
            print(
                "ℹ️  MOSMIX liefert nur Prognosen ab jetzt (kein --full möglich).",
                file=sys.stderr,
            )
    except WeatherSourceError as e:
        print(f"❌ Fehler bei Wetterabfrage: {e}", file=sys.stderr)
        return 1
    except WeatherAPIError as e:
        print(f"❌ Fehler bei Wetterabfrage: {e}", file=sys.stderr)
        return 1

    # Produktionsdaten für heute aus DB holen (für mode="today" mit Lags)
    # Funktioniert nur mit Open-Meteo, da MOSMIX keine past_hours liefert
    predict_mode = "predict"  # Default: keine Produktions-Lags
    if source_name == "open-meteo" and len(weather_df) > 0:
        db = Database(config.db_path)
        # Zeitraum: erste bis letzte Stunde im weather_df
        start_ts = int(weather_df["timestamp"].min())
        end_ts = int(weather_df["timestamp"].max())
        production_data = db.get_production_data(start_ts, end_ts)

        if production_data:
            # Produktionsdaten zum DataFrame hinzufügen
            weather_df["production_w"] = weather_df["timestamp"].map(
                lambda ts: production_data.get(int(ts), 0)
            )
            predict_mode = "today"
            qprint(f"📊 Nutze {len(production_data)} historische Produktionswerte für Prognose")

    # Prognose berechnen
    model_version = metrics.get("model_version") if metrics else None
    forecast = predict(
        model, weather_df, config.latitude, config.longitude, config.peak_kwp,
        mode=predict_mode, model_version=model_version
    )

    # Ausgabe
    if _quiet_mode:
        # Kompakte Ausgabe bei --quiet
        print(f"{forecast.total_kwh:.1f} kWh")
    else:
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
            # Markiere aktuelle Stunde und vergangene
            if local.hour == now_hour:
                marker = " ◄"
            elif local.hour < now_hour:
                marker = " ○"  # vergangen (kurz)
            else:
                marker = ""
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

    if _quiet_mode:
        print(f"✅ Import: {total} neue Datensätze")
    else:
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

    qprint(f"📊 PV-Datensätze: {pv_count}")

    # Zeitbereich der PV-Daten
    pv_start, pv_end = db.get_pv_date_range()
    if not pv_start or not pv_end:
        print("❌ Keine PV-Daten gefunden.", file=sys.stderr)
        return 1

    qprint(f"📅 Zeitraum: {datetime.fromtimestamp(pv_start)} bis {datetime.fromtimestamp(pv_end)}")

    # Historische Wetterdaten laden
    historical_provider = config.weather.historical_provider

    if historical_provider == "hostrada":
        # HOSTRADA muss separat geladen werden (große Downloads)
        weather_count_before = db.get_weather_count()
        if weather_count_before == 0:
            print("⚠️  HOSTRADA als Quelle konfiguriert, aber keine Wetterdaten vorhanden.")
            print("   Lade zuerst historische Daten:")
            print("   pvforecast fetch-historical --source hostrada \\")
            print("       --start 2019-01-01 --end 2024-12-31")
            print()
            print("   Oder nutze Open-Meteo für schnellen Start:")
            print("   pvforecast train --model xgb  (lädt automatisch von Open-Meteo)")
            return 1
        else:
            qprint(f"🌤️  Verwende vorhandene Wetterdaten ({weather_count_before:,} Datensätze)")
    else:
        # Open-Meteo: Automatisch nachladen
        qprint("🌤️  Lade historische Wetterdaten (Open-Meteo)...")
        weather_start = time.perf_counter()
        try:
            loaded = ensure_weather_history(db, config.latitude, config.longitude, pv_start, pv_end)
            weather_elapsed = time.perf_counter() - weather_start
            if loaded > 0:
                duration = format_duration(weather_elapsed)
                qprint(f"   {loaded} neue Wetterdatensätze geladen in {duration}")
        except WeatherAPIError as e:
            print(f"⚠️  Wetter-API Fehler: {e}", file=sys.stderr)
            print("   Versuche Training mit vorhandenen Daten...", file=sys.stderr)

    weather_count = db.get_weather_count()
    qprint(f"🌡️  Wetterdatensätze: {weather_count}")

    # Training
    model_type = getattr(args, "model", "rf")
    since_year = getattr(args, "since", None)
    until_year = getattr(args, "until", None)
    model_name = "XGBoost" if model_type == "xgb" else "RandomForest"

    if since_year and until_year:
        qprint(f"🧠 Trainiere {model_name} Modell (Daten {since_year}-{until_year})...")
    elif since_year:
        qprint(f"🧠 Trainiere {model_name} Modell (Daten ab {since_year})...")
    elif until_year:
        qprint(f"🧠 Trainiere {model_name} Modell (Daten bis {until_year})...")
    else:
        qprint(f"🧠 Trainiere {model_name} Modell...")

    train_start = time.perf_counter()
    try:
        model, metrics = train(
            db,
            config.latitude,
            config.longitude,
            model_type,
            since_year=since_year,
            until_year=until_year,
            peak_kwp=config.peak_kwp,
        )
    except ValueError as e:
        print(f"❌ Training fehlgeschlagen: {e}", file=sys.stderr)
        return 1
    train_elapsed = time.perf_counter() - train_start

    # Modell speichern
    save_model(model, config.model_path, metrics)

    if _quiet_mode:
        # Kompakte Ausgabe bei --quiet
        print(f"✅ Training: MAPE {metrics['mape']:.1f}%, MAE {metrics['mae']:.0f}W")
    else:
        print("")
        print(f"✅ Training abgeschlossen in {format_duration(train_elapsed)}!")
        print(f"   MAPE: {metrics['mape']:.1f}%")
        print(f"   MAE:  {metrics['mae']:.0f} W")
        print(f"   RMSE: {metrics['rmse']:.0f} W")
        print(f"   R²:   {metrics['r2']:.3f}")
        print(f"   Trainingsdaten: {metrics['n_train']}")
        print(f"   Testdaten: {metrics['n_test']}")
        if since_year or until_year:
            range_str = f"{since_year or 'Anfang'}-{until_year or 'Ende'}"
            print(f"   Zeitraum: {range_str}")
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

    qprint(f"📊 PV-Datensätze: {pv_count}")

    # Zeitbereich der PV-Daten
    pv_start, pv_end = db.get_pv_date_range()
    if not pv_start or not pv_end:
        print("❌ Keine PV-Daten gefunden.", file=sys.stderr)
        return 1

    # Wetterdaten sicherstellen
    qprint("🌤️  Prüfe Wetterdaten...")
    weather_start = time.perf_counter()
    try:
        loaded = ensure_weather_history(db, config.latitude, config.longitude, pv_start, pv_end)
        weather_elapsed = time.perf_counter() - weather_start
        if loaded > 0:
            duration = format_duration(weather_elapsed)
            qprint(f"   {loaded} neue Wetterdatensätze geladen in {duration}")
    except WeatherAPIError as e:
        print(f"⚠️  Wetter-API Fehler: {e}", file=sys.stderr)

    # Parameter aus args
    model_type = getattr(args, "model", "xgb")
    method = getattr(args, "method", "random")
    n_iter = getattr(args, "trials", 50)
    cv_splits = getattr(args, "cv", 5)
    timeout = getattr(args, "timeout", None)
    since_year = getattr(args, "since", None)
    until_year = getattr(args, "until", None)
    model_name = "XGBoost" if model_type == "xgb" else "RandomForest"
    method_name = "Optuna" if method == "optuna" else "RandomizedSearchCV"

    qprint()
    qprint(f"🔧 Hyperparameter-Tuning für {model_name}")
    qprint(f"   Methode: {method_name}")
    qprint(f"   Trials: {n_iter}")
    qprint(f"   CV-Splits: {cv_splits}")
    if timeout and method == "optuna":
        qprint(f"   Timeout: {timeout}s")
    if since_year or until_year:
        range_str = f"{since_year or 'Anfang'}-{until_year or 'Ende'}"
        qprint(f"   Zeitraum: {range_str}")
    qprint()
    qprint("⏳ Das kann einige Minuten dauern...")
    qprint()

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
                until_year=until_year,
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
                until_year=until_year,
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

    if _quiet_mode:
        # Kompakte Ausgabe bei --quiet
        print(f"✅ Tuning: MAPE {metrics['mape']:.1f}%, MAE {metrics['mae']:.0f}W")
    else:
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
    print_evaluation_result(result)
    return 0


def cmd_setup(args: argparse.Namespace, config: Config) -> int:
    """Führt den interaktiven Setup-Wizard aus."""
    config_path = get_config_path()

    # Bei existierender Config fragen ob überschreiben
    if config_path.exists() and not args.force:
        print(f"ℹ️  Config existiert bereits: {config_path}")
        try:
            response = input("   Konfiguration aktualisieren? [J/n]: ").strip().lower()
            if response in ("n", "no", "nein"):
                print("   Abgebrochen.")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("\n   Abgebrochen.")
            return 0

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
                _, metrics = load_model(model_path)
                model_type = metrics.get("model_type", "?")
                mape = metrics.get("mape")
                if mape is not None:
                    model_info = f"{model_type}, MAPE {mape:.1f}%"
                else:
                    model_info = model_type
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
