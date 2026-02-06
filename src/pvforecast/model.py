"""ML-Modell für PV-Ertragsprognose."""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, pi, radians, sin
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import randint, uniform
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from pvforecast.db import Database

logger = logging.getLogger(__name__)

UTC_TZ = ZoneInfo("UTC")

# XGBoost ist optional - mit detaillierter Fehlererkennung
XGBOOST_AVAILABLE = False
XGBOOST_ERROR: str | None = None
XGBRegressor = None  # type: ignore

try:
    from xgboost import XGBRegressor

    XGBOOST_AVAILABLE = True
except ImportError:
    # Nicht installiert
    XGBOOST_ERROR = "not_installed"
    logger.debug("XGBoost nicht installiert")
except OSError as e:
    # Installiert aber Library-Fehler (z.B. libomp fehlt)
    error_str = str(e).lower()
    if "libomp" in error_str or "openmp" in error_str or "omp" in error_str:
        XGBOOST_ERROR = "libomp_missing"
        logger.debug(f"XGBoost: libomp fehlt - {e}")
    else:
        XGBOOST_ERROR = f"os_error: {e}"
        logger.debug(f"XGBoost OS-Fehler: {e}")
except Exception as e:
    XGBOOST_ERROR = f"unknown: {e}"
    logger.debug(f"XGBoost unbekannter Fehler: {e}")

# pvlib ist optional - für Clear-Sky-Index
PVLIB_AVAILABLE = False
try:
    from pvlib.location import Location

    PVLIB_AVAILABLE = True
except ImportError:
    logger.debug("pvlib nicht installiert - CSI nicht verfügbar")

# Verfügbare Modell-Typen
ModelType = Literal["rf", "xgb"]


class ModelNotFoundError(Exception):
    """Kein trainiertes Modell vorhanden."""

    pass


@dataclass
class HourlyForecast:
    """Einzelner Stundenwert der Prognose."""

    timestamp: datetime
    production_w: int
    ghi_wm2: float
    cloud_cover_pct: int


@dataclass
class Forecast:
    """Komplette Prognose."""

    hourly: list[HourlyForecast]
    total_kwh: float
    generated_at: datetime
    model_version: str = "rf-v1"


def encode_cyclic(values: pd.Series, max_value: float) -> tuple[pd.Series, pd.Series]:
    """
    Kodiert Werte zyklisch mit sin/cos.

    Args:
        values: Serie mit Werten (z.B. Stunden 0-23)
        max_value: Maximaler Wert des Zyklus (z.B. 24 für Stunden)

    Returns:
        Tuple aus (sin_values, cos_values)
    """
    angle = 2 * pi * values / max_value
    return np.sin(angle), np.cos(angle)


def calculate_sun_elevation(timestamp: int, lat: float, lon: float) -> float:
    """
    Berechnet die Sonnenhöhe (Elevation) für einen Zeitpunkt.

    Vereinfachte Formel, ausreichend für ML-Features.

    Args:
        timestamp: Unix timestamp (UTC)
        lat: Breitengrad
        lon: Längengrad

    Returns:
        Sonnenhöhe in Grad (-90 bis 90, negativ = unter Horizont)
    """
    dt = datetime.fromtimestamp(timestamp, UTC_TZ)

    # Tag des Jahres
    day_of_year = dt.timetuple().tm_yday

    # Deklination der Sonne (vereinfacht)
    declination = -23.45 * cos(radians(360 / 365 * (day_of_year + 10)))

    # Stundenwinkel
    hour = dt.hour + dt.minute / 60
    solar_time = hour + lon / 15  # Grobe Annäherung
    hour_angle = 15 * (solar_time - 12)

    # Sonnenhöhe
    lat_rad = radians(lat)
    dec_rad = radians(declination)
    ha_rad = radians(hour_angle)

    sin_elevation = sin(lat_rad) * sin(dec_rad) + cos(lat_rad) * cos(dec_rad) * cos(ha_rad)

    # Clamp to [-1, 1] to avoid math domain errors
    sin_elevation = max(-1, min(1, sin_elevation))

    elevation = asin(sin_elevation) * 180 / 3.14159

    return elevation


FeatureMode = Literal["train", "today", "predict"]


def prepare_features(
    df: pd.DataFrame,
    lat: float,
    lon: float,
    peak_kwp: float | None = None,
    mode: FeatureMode = "train",
) -> pd.DataFrame:
    """
    Erstellt Feature-DataFrame für ML-Modell.

    Args:
        df: DataFrame mit timestamp, ghi_wm2, cloud_cover_pct, temperature_c,
            und optional: wind_speed_ms, humidity_pct, dhi_wm2, production_w
        lat: Breitengrad (für Sonnenhöhe)
        lon: Längengrad
        peak_kwp: Anlagenleistung in kWp (optional, für Normalisierung)
        mode: Feature-Modus:
            - "train": Training mit historischen Daten (alle Lags verfügbar)
            - "today": Prognose für heute (Produktions-Lags bis jetzt verfügbar)
            - "predict": Prognose für Zukunft (keine Produktions-Lags)

    Returns:
        DataFrame mit Features inkl. Wetter-Lags und Produktions-Lags
    """
    features = pd.DataFrame()

    # Zeitbasierte Features (zyklisch kodiert)
    timestamps = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    hours = timestamps.dt.hour
    months = timestamps.dt.month
    day_of_year = timestamps.dt.dayofyear

    # Zyklische Kodierung: sin/cos statt linearer Werte
    # So lernt das Modell, dass Stunde 23 und 0 benachbart sind
    features["hour_sin"], features["hour_cos"] = encode_cyclic(hours, 24)
    features["month_sin"], features["month_cos"] = encode_cyclic(months, 12)
    features["doy_sin"], features["doy_cos"] = encode_cyclic(day_of_year, 365)

    # Wetter-Features (Basis)
    features["ghi"] = df["ghi_wm2"]
    features["cloud_cover"] = df["cloud_cover_pct"]
    features["temperature"] = df["temperature_c"]

    # Erweiterte Wetter-Features (optional, Defaults wenn nicht vorhanden)
    features["wind_speed"] = df.get("wind_speed_ms", pd.Series([0.0] * len(df)))
    features["humidity"] = df.get("humidity_pct", pd.Series([50] * len(df)))
    features["dhi"] = df.get("dhi_wm2", pd.Series([0.0] * len(df)))

    # NaN-Handling für erweiterte Features
    features["wind_speed"] = features["wind_speed"].fillna(0.0)
    features["humidity"] = features["humidity"].fillna(50)
    features["dhi"] = features["dhi"].fillna(0.0)

    # Interaktions-Feature: Effektive Strahlung (GHI korrigiert um Bewölkung)
    features["effective_irradiance"] = features["ghi"] * (
        1 - features["cloud_cover"] / 100
    )

    # Sonnenhöhe berechnen
    features["sun_elevation"] = df["timestamp"].apply(
        lambda ts: calculate_sun_elevation(int(ts), lat, lon)
    )

    # Anlagenleistung als Feature (für Normalisierung/Transfer-Learning)
    if peak_kwp is not None:
        features["peak_kwp"] = peak_kwp

    # === Physikalische Features ===

    # Diffuse Fraction: Verhältnis diffuse/globale Strahlung
    # Hoher Wert = bewölkt, niedriger = klarer Himmel
    features["diffuse_fraction"] = features["dhi"] / (features["ghi"] + 1)

    # DNI (Direct Normal Irradiance) wenn verfügbar
    if "dni_wm2" in df.columns:
        features["dni"] = df["dni_wm2"].fillna(0)
    else:
        features["dni"] = 0.0

    # Modultemperatur (NOCT-basiert)
    # NOCT = 45°C (Nominal Operating Cell Temperature)
    NOCT = 45
    features["t_module"] = (
        features["temperature"]
        + (features["ghi"] / 800) * (NOCT - 20)
        - features["wind_speed"] * 2
    )

    # Temperatur-Derating: Module verlieren ~0.4%/°C über 25°C
    TEMP_COEFFICIENT = -0.004
    features["efficiency_factor"] = 1 + TEMP_COEFFICIENT * (features["t_module"] - 25)

    # Clear-Sky-Index (CSI): Verhältnis GHI zu theoretischem Maximum
    # Normalisiert Strahlung über Jahreszeiten hinweg
    if PVLIB_AVAILABLE and len(df) > 0:
        try:
            location = Location(lat, lon)
            # Timestamps für pvlib vorbereiten
            times = pd.DatetimeIndex(timestamps)
            # Clear-Sky GHI berechnen (Ineichen-Modell)
            clear_sky = location.get_clearsky(times, model="ineichen")
            clear_sky_ghi = clear_sky["ghi"].values
            # CSI = GHI / Clear-Sky GHI (mit Schutz vor Division durch 0)
            ghi_values = features["ghi"].values
            csi = np.zeros(len(ghi_values))
            mask = clear_sky_ghi > 10  # Nur berechnen wenn Clear-Sky > 10 W/m²
            csi[mask] = ghi_values[mask] / clear_sky_ghi[mask]
            # CSI auf sinnvollen Bereich begrenzen (kann >1 sein bei Reflexionen)
            features["csi"] = np.clip(csi, 0, 1.5)
        except Exception as e:
            logger.warning(f"CSI-Berechnung fehlgeschlagen: {e}")
            features["csi"] = 0.0
    else:
        # Fallback wenn pvlib nicht verfügbar
        features["csi"] = 0.0

    # === Lag-Features ===

    # Wetter-Lags (immer verfügbar, da Wetterdaten sequentiell)
    features["ghi_lag_1h"] = features["ghi"].shift(1).fillna(0)
    features["ghi_lag_3h"] = features["ghi"].shift(3).fillna(0)
    features["ghi_rolling_3h"] = features["ghi"].rolling(3, min_periods=1).mean()
    features["cloud_trend"] = features["cloud_cover"].diff().fillna(0)

    # Produktions-Lags (abhängig von mode und Datenverfügbarkeit)
    if "production_w" in df.columns and mode in ("train", "today"):
        # Historische Produktionsdaten verfügbar
        production = df["production_w"].reset_index(drop=True)
        features["production_lag_1h"] = production.shift(1).fillna(0)
        features["production_lag_2h"] = production.shift(2).fillna(0)
        features["production_lag_3h"] = production.shift(3).fillna(0)
        features["production_lag_24h"] = production.shift(24).fillna(0)
    else:
        # Keine Produktionsdaten oder predict-Modus → Nullen
        # Wichtig: Features müssen trotzdem existieren für konsistentes Feature-Set
        features["production_lag_1h"] = 0.0
        features["production_lag_2h"] = 0.0
        features["production_lag_3h"] = 0.0
        features["production_lag_24h"] = 0.0

    return features


def _check_xgboost_available() -> None:
    """
    Prüft ob XGBoost verfügbar ist und gibt hilfreiche Fehlermeldungen.

    Raises:
        DependencyError: Mit spezifischer Fehlermeldung und Lösungshinweis
    """
    from pvforecast.validation import DependencyError

    if XGBOOST_AVAILABLE:
        return

    if XGBOOST_ERROR == "not_installed":
        raise DependencyError(
            "XGBoost ist nicht installiert.\n"
            "Installation: pip install pvforecast[xgb]\n"
            "Oder: pip install xgboost"
        )
    elif XGBOOST_ERROR == "libomp_missing":
        raise DependencyError(
            "XGBoost benötigt OpenMP (libomp), das auf diesem System fehlt.\n"
            "\n"
            "Installation:\n"
            "  macOS:  brew install libomp\n"
            "  Ubuntu: sudo apt install libgomp1\n"
            "  Fedora: sudo dnf install libgomp\n"
            "\n"
            "Nach der Installation pvforecast neu starten."
        )
    else:
        raise DependencyError(
            f"XGBoost konnte nicht geladen werden: {XGBOOST_ERROR}\n"
            "Versuche: pip install --force-reinstall xgboost"
        )


def _create_pipeline(model_type: ModelType) -> Pipeline:
    """
    Erstellt ML-Pipeline für den angegebenen Modelltyp.

    Args:
        model_type: 'rf' für RandomForest, 'xgb' für XGBoost

    Returns:
        sklearn Pipeline mit Scaler und Modell

    Raises:
        DependencyError: Wenn XGBoost nicht verfügbar ist
    """
    if model_type == "xgb":
        _check_xgboost_available()
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    XGBRegressor(
                        n_estimators=100,
                        max_depth=6,
                        learning_rate=0.1,
                        min_child_weight=5,
                        random_state=42,
                        n_jobs=-1,
                        verbosity=0,
                    ),
                ),
            ]
        )
    else:  # rf (default)
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=100,
                        max_depth=15,
                        min_samples_leaf=5,
                        random_state=42,
                        n_jobs=-1,
                    ),
                ),
            ]
        )


def train(
    db: Database,
    lat: float,
    lon: float,
    model_type: ModelType = "rf",
    since_year: int | None = None,
    peak_kwp: float | None = None,
) -> tuple[Pipeline, dict]:
    """
    Trainiert Modell auf allen Daten in der Datenbank.

    Args:
        db: Database-Instanz
        lat: Breitengrad
        lon: Längengrad
        model_type: 'rf' für RandomForest (default), 'xgb' für XGBoost
        since_year: Nur Daten ab diesem Jahr verwenden (optional)

    Returns:
        (sklearn Pipeline, metrics dict mit 'mape', 'mae', 'n_samples', 'model_type')
    """
    if since_year:
        logger.info(f"Lade Trainingsdaten ab {since_year}...")
    else:
        logger.info("Lade Trainingsdaten aus Datenbank...")

    with db.connect() as conn:
        # Join PV und Wetter-Daten
        query = """
            SELECT
                p.timestamp,
                p.production_w,
                w.ghi_wm2,
                w.cloud_cover_pct,
                w.temperature_c,
                w.wind_speed_ms,
                w.humidity_pct,
                w.dhi_wm2,
                w.dni_wm2
            FROM pv_readings p
            INNER JOIN weather_history w ON p.timestamp = w.timestamp
            WHERE p.curtailed = 0  -- Keine abgeregelten Daten
              AND p.production_w >= 0
              AND w.ghi_wm2 IS NOT NULL
        """
        if since_year:
            query += f" AND p.timestamp >= strftime('%s', '{since_year}-01-01')"
        df = pd.read_sql_query(query, conn)

    if len(df) < 100:
        raise ValueError(f"Zu wenig Trainingsdaten: {len(df)} (mindestens 100 benötigt)")

    logger.info(f"Trainingsdaten: {len(df)} Datensätze")

    # Features erstellen (mode="train" für historische Daten)
    X = prepare_features(df, lat, lon, peak_kwp=peak_kwp, mode="train")
    y = df["production_w"]

    # Zeitbasierter Split (80% Training, 20% Test)
    split_idx = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    logger.info(f"Training: {len(X_train)}, Test: {len(X_test)}")

    # Pipeline erstellen
    model_name = "XGBoost" if model_type == "xgb" else "RandomForest"
    logger.info(f"Erstelle {model_name} Pipeline...")
    pipeline = _create_pipeline(model_type)

    # Training
    logger.info(f"Trainiere {model_name}...")
    pipeline.fit(X_train, y_train)

    # Evaluation
    y_pred = pipeline.predict(X_test)

    # MAPE nur für Stunden mit relevanter Produktion (>100W)
    # Bei niedrigen Werten verzerrt MAPE stark (10W real vs 20W pred = 100% Fehler)
    mape_threshold = 100  # Watt
    mask = y_test > mape_threshold
    if mask.sum() > 0:
        mape = mean_absolute_percentage_error(y_test[mask], y_pred[mask]) * 100
    else:
        mape = 0.0

    mae = mean_absolute_error(y_test, y_pred)

    metrics = {
        "mape": round(mape, 2),
        "mae": round(mae, 2),
        "n_samples": len(df),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "model_type": model_type,
        "since_year": since_year,
    }

    logger.info(f"{model_name} Training abgeschlossen. MAPE: {mape:.1f}%, MAE: {mae:.0f}W")

    return pipeline, metrics


def tune(
    db: Database,
    lat: float,
    lon: float,
    model_type: ModelType = "xgb",
    n_iter: int = 50,
    cv_splits: int = 5,
    since_year: int | None = None,
    peak_kwp: float | None = None,
) -> tuple[Pipeline, dict, dict]:
    """
    Hyperparameter-Tuning mit RandomizedSearchCV.

    Args:
        db: Database-Instanz
        lat: Breitengrad
        lon: Längengrad
        model_type: 'rf' für RandomForest, 'xgb' für XGBoost
        n_iter: Anzahl der Kombinationen (default: 50)
        cv_splits: Anzahl der CV-Splits (default: 5)
        since_year: Nur Daten ab diesem Jahr verwenden (optional)

    Returns:
        (beste Pipeline, metrics dict, beste Parameter dict)
    """
    logger.info(f"Starte Hyperparameter-Tuning ({n_iter} Iterationen, {cv_splits}-fold CV)...")

    # Daten laden (gleiche Query wie train())
    with db.connect() as conn:
        query = """
            SELECT
                p.timestamp,
                p.production_w,
                w.ghi_wm2,
                w.cloud_cover_pct,
                w.temperature_c,
                w.wind_speed_ms,
                w.humidity_pct,
                w.dhi_wm2,
                w.dni_wm2
            FROM pv_readings p
            INNER JOIN weather_history w ON p.timestamp = w.timestamp
            WHERE p.curtailed = 0
              AND p.production_w >= 0
              AND w.ghi_wm2 IS NOT NULL
        """
        if since_year:
            query += f" AND p.timestamp >= strftime('%s', '{since_year}-01-01')"
        df = pd.read_sql_query(query, conn)

    if len(df) < 500:
        raise ValueError(f"Zu wenig Daten für Tuning: {len(df)} (mindestens 500 empfohlen)")

    logger.info(f"Tuning-Daten: {len(df)} Datensätze")

    # Features erstellen (mode="train" für historische Daten)
    X = prepare_features(df, lat, lon, peak_kwp=peak_kwp, mode="train")
    y = df["production_w"]

    # Parameter-Suchraum definieren
    if model_type == "xgb":
        if not XGBOOST_AVAILABLE:
            raise ValueError(
                "XGBoost nicht installiert. Installiere mit: pip install pvforecast[xgb]"
            )
        param_dist = {
            "model__n_estimators": randint(100, 500),
            "model__max_depth": randint(4, 13),  # 4-12
            "model__learning_rate": uniform(0.01, 0.29),  # 0.01-0.3
            "model__min_child_weight": randint(1, 11),  # 1-10
            "model__subsample": uniform(0.6, 0.4),  # 0.6-1.0
            "model__colsample_bytree": uniform(0.6, 0.4),  # 0.6-1.0
        }
        model_name = "XGBoost"
    else:
        param_dist = {
            "model__n_estimators": randint(100, 500),
            "model__max_depth": randint(5, 25),  # 5-24
            "model__min_samples_split": randint(2, 20),
            "model__min_samples_leaf": randint(1, 15),
        }
        model_name = "RandomForest"

    # Pipeline erstellen
    pipeline = _create_pipeline(model_type)

    # TimeSeriesSplit für zeitliche Daten
    cv = TimeSeriesSplit(n_splits=cv_splits)

    # RandomizedSearchCV
    logger.info(f"Starte RandomizedSearchCV für {model_name}...")
    search = RandomizedSearchCV(
        pipeline,
        param_distributions=param_dist,
        n_iter=n_iter,
        cv=cv,
        scoring="neg_mean_absolute_error",
        n_jobs=-1,
        verbose=1,
        random_state=42,
    )

    search.fit(X, y)

    # Beste Parameter extrahieren (ohne "model__" Prefix)
    best_params = {k.replace("model__", ""): v for k, v in search.best_params_.items()}

    logger.info("Trainiere finales Modell mit besten Parametern...")

    # Neue Pipeline mit besten Parametern erstellen
    # (search.best_estimator_ ist auf ALLEN Daten trainiert - Data Leakage!)
    if model_type == "xgb":
        best_pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", XGBRegressor(**best_params, random_state=42, n_jobs=-1, verbosity=0)),
        ])
    else:
        best_pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", RandomForestRegressor(**best_params, random_state=42, n_jobs=-1)),
        ])

    # Split für Training/Test (80/20)
    split_idx = int(len(df) * 0.8)
    X_train = X.iloc[:split_idx]
    y_train = y.iloc[:split_idx]
    X_test = X.iloc[split_idx:]
    y_test = y.iloc[split_idx:]

    # Nur auf 80% trainieren
    best_pipeline.fit(X_train, y_train)

    # Evaluation auf echten Test-Daten (nicht im Training gesehen)
    y_pred = best_pipeline.predict(X_test)

    # MAPE für relevante Produktion (>100W)
    mape_threshold = 100
    mask = y_test > mape_threshold
    if mask.sum() > 0:
        mape = mean_absolute_percentage_error(y_test[mask], y_pred[mask]) * 100
    else:
        mape = 0.0

    mae = mean_absolute_error(y_test, y_pred)

    metrics = {
        "mape": round(mape, 2),
        "mae": round(mae, 2),
        "n_samples": len(df),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "model_type": model_type,
        "tuned": True,
        "method": "random",
        "n_iter": n_iter,
        "cv_splits": cv_splits,
        "best_cv_score": round(-search.best_score_, 2),  # MAE (negiert zurück)
        "since_year": since_year,
    }

    logger.info("Tuning abgeschlossen!")
    logger.debug(f"Beste Parameter (raw): {best_params}")
    logger.info(f"CV-Score (MAE): {-search.best_score_:.0f}W")
    logger.info(f"Test-MAPE: {mape:.1f}%, Test-MAE: {mae:.0f}W")

    return best_pipeline, metrics, best_params


# Optuna ist optional
OPTUNA_AVAILABLE = False
try:
    import optuna

    OPTUNA_AVAILABLE = True
except ImportError:
    optuna = None  # type: ignore


def _check_optuna_available() -> None:
    """
    Prüft ob Optuna verfügbar ist.

    Raises:
        DependencyError: Wenn Optuna nicht installiert ist
    """
    from pvforecast.validation import DependencyError

    if not OPTUNA_AVAILABLE:
        raise DependencyError(
            "Optuna ist nicht installiert.\n"
            "Installation: pip install pvforecast[tune]\n"
            "Oder: pip install optuna"
        )


def tune_optuna(
    db: Database,
    lat: float,
    lon: float,
    model_type: ModelType = "xgb",
    n_trials: int = 50,
    cv_splits: int = 5,
    timeout: int | None = None,
    show_progress: bool = True,
    since_year: int | None = None,
    peak_kwp: float | None = None,
) -> tuple[Pipeline, dict, dict]:
    """
    Hyperparameter-Tuning mit Optuna (Bayesian Optimization).

    Vorteile gegenüber RandomizedSearchCV:
    - Lernt aus vorherigen Trials (Bayesian Optimization)
    - Pruning bricht aussichtslose Trials früh ab
    - Bessere Konvergenz bei weniger Trials

    Args:
        db: Database-Instanz
        lat: Breitengrad
        lon: Längengrad
        model_type: 'rf' für RandomForest, 'xgb' für XGBoost
        n_trials: Anzahl der Trials (default: 50)
        cv_splits: Anzahl der CV-Splits (default: 5)
        timeout: Maximale Laufzeit in Sekunden (optional)
        show_progress: Progress-Bar anzeigen (default: True)
        since_year: Nur Daten ab diesem Jahr verwenden (optional)

    Returns:
        (beste Pipeline, metrics dict, beste Parameter dict)
    """
    import numpy as np

    _check_optuna_available()
    if model_type == "xgb":
        _check_xgboost_available()

    logger.info(f"Starte Optuna-Tuning ({n_trials} Trials, {cv_splits}-fold CV)...")

    # Daten laden
    with db.connect() as conn:
        query = """
            SELECT
                p.timestamp,
                p.production_w,
                w.ghi_wm2,
                w.cloud_cover_pct,
                w.temperature_c,
                w.wind_speed_ms,
                w.humidity_pct,
                w.dhi_wm2,
                w.dni_wm2
            FROM pv_readings p
            INNER JOIN weather_history w ON p.timestamp = w.timestamp
            WHERE p.curtailed = 0
              AND p.production_w >= 0
              AND w.ghi_wm2 IS NOT NULL
        """
        if since_year:
            query += f" AND p.timestamp >= strftime('%s', '{since_year}-01-01')"
        df = pd.read_sql_query(query, conn)

    if len(df) < 500:
        raise ValueError(f"Zu wenig Daten für Tuning: {len(df)} (mindestens 500 empfohlen)")

    logger.info(f"Tuning-Daten: {len(df)} Datensätze")

    # Features erstellen (mode="train" für historische Daten)
    X = prepare_features(df, lat, lon, peak_kwp=peak_kwp, mode="train")
    y = df["production_w"].values

    # TimeSeriesSplit für CV
    cv = TimeSeriesSplit(n_splits=cv_splits)

    # Objective-Funktion definieren
    def objective(trial: optuna.Trial) -> float:
        # Parameter-Sampling je nach Modell-Typ
        if model_type == "xgb":
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 500),
                "max_depth": trial.suggest_int("max_depth", 4, 12),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            }
        else:  # rf
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 500),
                "max_depth": trial.suggest_int("max_depth", 5, 24),
                "min_samples_split": trial.suggest_int("min_samples_split", 2, 20),
                "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 15),
            }

        # Cross-Validation mit Pruning
        fold_scores = []
        for step, (train_idx, val_idx) in enumerate(cv.split(X)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            # Scaler fitten
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_val_scaled = scaler.transform(X_val)

            # Modell erstellen und trainieren
            if model_type == "xgb":
                model = XGBRegressor(
                    **params,
                    random_state=42,
                    n_jobs=-1,
                    verbosity=0,
                )
            else:
                model = RandomForestRegressor(
                    **params,
                    random_state=42,
                    n_jobs=-1,
                )

            model.fit(X_train_scaled, y_train)

            # Evaluieren
            y_pred = model.predict(X_val_scaled)
            mae = mean_absolute_error(y_val, y_pred)
            fold_scores.append(mae)

            # Pruning: Intermediate Value reporten
            trial.report(np.mean(fold_scores), step)

            # Sollte dieser Trial abgebrochen werden?
            if trial.should_prune():
                raise optuna.TrialPruned()

        return np.mean(fold_scores)

    # Optuna Study erstellen
    # Logging-Level reduzieren (vermischt sich sonst mit Progress-Bar)
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    study = optuna.create_study(
        direction="minimize",  # MAE minimieren
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=2),
    )

    # Optimierung starten
    study.optimize(
        objective,
        n_trials=n_trials,
        timeout=timeout,
        show_progress_bar=show_progress,
    )

    # Beste Parameter
    best_params = study.best_params
    logger.info(f"Beste Parameter: {best_params}")
    logger.info(f"Bester CV-Score (MAE): {study.best_value:.0f}W")

    # Statistiken
    n_pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
    n_complete = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
    logger.info(f"Trials: {n_complete} abgeschlossen, {n_pruned} gepruned")

    # Finale Pipeline mit besten Parametern trainieren
    logger.info("Trainiere finales Modell mit besten Parametern...")

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        (
            "model",
            XGBRegressor(**best_params, random_state=42, n_jobs=-1, verbosity=0)
            if model_type == "xgb"
            else RandomForestRegressor(**best_params, random_state=42, n_jobs=-1),
        ),
    ])

    # Auf allen Daten trainieren (für finales Modell)
    # Aber Test-Evaluation auf den letzten 20%
    split_idx = int(len(df) * 0.8)
    X_train_full = X.iloc[:split_idx]
    y_train_full = y[:split_idx]
    X_test = X.iloc[split_idx:]
    y_test = y[split_idx:]

    pipeline.fit(X_train_full, y_train_full)

    # Evaluation
    y_pred = pipeline.predict(X_test)

    # MAPE für relevante Produktion (>100W)
    mape_threshold = 100
    mask = y_test > mape_threshold
    if mask.sum() > 0:
        mape = mean_absolute_percentage_error(y_test[mask], y_pred[mask]) * 100
    else:
        mape = 0.0

    mae = mean_absolute_error(y_test, y_pred)

    metrics = {
        "mape": round(mape, 2),
        "mae": round(mae, 2),
        "n_samples": len(df),
        "n_test": len(X_test),
        "model_type": model_type,
        "tuned": True,
        "method": "optuna",
        "n_trials": n_trials,
        "n_trials_complete": n_complete,
        "n_trials_pruned": n_pruned,
        "cv_splits": cv_splits,
        "best_cv_score": round(study.best_value, 2),
        "since_year": since_year,
    }

    logger.info("Optuna-Tuning abgeschlossen!")
    logger.info(f"Test-MAPE: {mape:.1f}%, Test-MAE: {mae:.0f}W")

    return pipeline, metrics, best_params


def save_model(model: Pipeline, path: Path, metrics: dict | None = None) -> None:
    """Speichert Modell und optional Metriken."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Version basierend auf Modell-Typ
    model_type = metrics.get("model_type", "rf") if metrics else "rf"
    version = f"{model_type}-v1"

    data = {
        "model": model,
        "metrics": metrics,
        "version": version,
        "created_at": datetime.now(UTC_TZ).isoformat(),
    }

    with open(path, "wb") as f:
        pickle.dump(data, f)

    logger.info(f"Modell gespeichert: {path} (Version: {version})")


def load_model(path: Path) -> tuple[Pipeline, dict | None]:
    """
    Lädt gespeichertes Modell.

    Returns:
        (Pipeline, metrics dict oder None)

    Raises:
        ModelNotFoundError: Wenn Modell nicht existiert
    """
    if not path.exists():
        raise ModelNotFoundError(f"Kein Modell gefunden: {path}")

    with open(path, "rb") as f:
        data = pickle.load(f)

    if isinstance(data, dict):
        return data["model"], data.get("metrics")
    else:
        # Altes Format (nur Pipeline)
        return data, None


def predict(
    model: Pipeline,
    weather_df: pd.DataFrame,
    lat: float,
    lon: float,
    peak_kwp: float | None = None,
    mode: FeatureMode = "predict",
) -> Forecast:
    """
    Erstellt Prognose basierend auf Wettervorhersage.

    Args:
        model: Trainierte sklearn Pipeline
        weather_df: DataFrame mit timestamp, ghi_wm2, cloud_cover_pct, temperature_c
            und optional production_w für today-Prognose
        lat: Breitengrad
        lon: Längengrad
        peak_kwp: Anlagenleistung in kWp
        mode: "today" für Prognose mit Produktions-Lags, "predict" für Zukunft

    Returns:
        Forecast-Objekt mit Stundenwerten und Summe
    """
    if len(weather_df) == 0:
        return Forecast(
            hourly=[],
            total_kwh=0.0,
            generated_at=datetime.now(UTC_TZ),
        )

    # Features erstellen (mode bestimmt ob Produktions-Lags verfügbar)
    X = prepare_features(weather_df, lat, lon, peak_kwp=peak_kwp, mode=mode)

    # Vorhersage
    predictions = model.predict(X)

    # Negative Werte auf 0 setzen
    predictions = [max(0, int(p)) for p in predictions]

    # Nacht-Stunden auf 0 setzen (Sonnenhöhe < 0)
    for i, row in enumerate(X.itertuples()):
        if row.sun_elevation < 0:
            predictions[i] = 0

    # Hourly Forecasts erstellen
    hourly = []
    for _, row in weather_df.iterrows():
        hourly.append(
            HourlyForecast(
                timestamp=datetime.fromtimestamp(int(row["timestamp"]), UTC_TZ),
                production_w=predictions[len(hourly)],
                ghi_wm2=float(row["ghi_wm2"]),
                cloud_cover_pct=int(row["cloud_cover_pct"]),
            )
        )

    # Summe berechnen (Wh → kWh)
    total_wh = sum(predictions)
    total_kwh = total_wh / 1000

    return Forecast(
        hourly=hourly,
        total_kwh=round(total_kwh, 2),
        generated_at=datetime.now(UTC_TZ),
    )
