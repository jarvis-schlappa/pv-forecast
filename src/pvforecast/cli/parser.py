"""Argument parser for pvforecast CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from pvforecast import __version__
from pvforecast.config import DEFAULT_CONFIG


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
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Reduzierte Ausgabe (unterdrückt Progress-Infos)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch-forecast
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

    # fetch-historical
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
    p_import.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        dest="sub_quiet",
        help="Reduzierte Ausgabe",
    )

    # today
    p_today = subparsers.add_parser("today", help="Prognose für heute")
    p_today.add_argument(
        "--source",
        choices=["mosmix", "open-meteo"],
        default=None,
        help="Wetter-Datenquelle (default: aus Config)",
    )
    p_today.add_argument(
        "--full",
        action="store_true",
        help="Ganzer Tag inkl. vergangener Stunden",
    )
    p_today.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        dest="sub_quiet",
        help="Reduzierte Ausgabe",
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
    p_train.add_argument(
        "--until",
        type=int,
        default=None,
        metavar="YEAR",
        help="Nur Daten bis zu diesem Jahr verwenden (z.B. --until 2023)",
    )
    p_train.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        dest="sub_quiet",
        help="Reduzierte Ausgabe",
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
    p_tune.add_argument(
        "--until",
        type=int,
        default=None,
        metavar="YEAR",
        help="Nur Daten bis zu diesem Jahr verwenden (z.B. --until 2023)",
    )
    p_tune.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        dest="sub_quiet",
        help="Reduzierte Ausgabe",
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

    # forecast-accuracy
    p_accuracy = subparsers.add_parser(
        "forecast-accuracy",
        help="Analysiert Forecast-Genauigkeit vs. Ground Truth",
    )
    p_accuracy.add_argument(
        "--days",
        type=int,
        default=None,
        help="Nur die letzten N Tage analysieren (default: alle)",
    )
    p_accuracy.add_argument(
        "--source",
        choices=["mosmix", "open-meteo"],
        default=None,
        help="Nur diese Quelle analysieren (default: alle)",
    )
    p_accuracy.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Ausgabeformat (default: table)",
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
