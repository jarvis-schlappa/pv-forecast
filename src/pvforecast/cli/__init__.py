"""Command-Line Interface für pvforecast.

This package provides the CLI for pvforecast, split into:
- parser.py: Argument parsing (create_parser)
- commands.py: Command implementations (cmd_*)
- formatters.py: Output formatting
- helpers.py: Shared helper functions
"""

from __future__ import annotations

import logging
import sys

from pvforecast.config import (
    ConfigValidationError,
    load_config,
)
from pvforecast.data_loader import DataImportError
from pvforecast.model import ModelNotFoundError
from pvforecast.sources.base import WeatherSourceError
from pvforecast.validation import (
    DependencyError,
    ValidationError,
    validate_latitude,
    validate_longitude,
)
from pvforecast.weather import WeatherAPIError

from .commands import (
    cmd_config,
    cmd_doctor,
    cmd_evaluate,
    cmd_fetch_forecast,
    cmd_fetch_historical,
    cmd_forecast_accuracy,
    cmd_import,
    cmd_predict,
    cmd_reset,
    cmd_setup,
    cmd_status,
    cmd_today,
    cmd_train,
    cmd_tune,
    set_quiet_mode,
)
from .parser import create_parser

__all__ = ["main", "create_parser"]


def main() -> int:
    """Hauptfunktion."""
    parser = create_parser()
    args = parser.parse_args()

    # Quiet-Mode ermitteln (global oder subparser-level)
    quiet = args.quiet or getattr(args, "sub_quiet", False)

    # Logging konfigurieren
    if quiet:
        level = logging.WARNING
    elif args.verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s" if not args.verbose else "%(levelname)s: %(message)s",
    )

    # HTTP-Logs nur bei --verbose anzeigen
    if not args.verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Quiet-Mode global setzen (für commands.qprint)
    set_quiet_mode(quiet)

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


def _run_command(args, parser) -> int:
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
        "forecast-accuracy": cmd_forecast_accuracy,
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
