"""Tests für model.py."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from pvforecast.model import (
    HourlyForecast,
    ModelNotFoundError,
    calculate_sun_elevation,
    load_model,
    load_training_data,
    prepare_features,
    save_model,
)

UTC_TZ = ZoneInfo("UTC")


class TestSunElevation:
    """Tests für Sonnenhöhen-Berechnung."""

    def test_noon_summer_positive(self):
        """Test: Mittag im Sommer hat positive Elevation."""
        # 21. Juni 2024, 12:00 UTC, Dülmen (51.83, 7.28)
        ts = int(datetime(2024, 6, 21, 12, 0, tzinfo=UTC_TZ).timestamp())
        elevation = calculate_sun_elevation(ts, 51.83, 7.28)

        assert elevation > 50  # Sommer-Mittag sollte hoch sein

    def test_midnight_negative(self):
        """Test: Mitternacht hat negative Elevation."""
        # 21. Juni 2024, 00:00 UTC
        ts = int(datetime(2024, 6, 21, 0, 0, tzinfo=UTC_TZ).timestamp())
        elevation = calculate_sun_elevation(ts, 51.83, 7.28)

        assert elevation < 0

    def test_winter_lower_than_summer(self):
        """Test: Winter-Mittag ist niedriger als Sommer-Mittag."""
        # Sommer-Mittag
        ts_summer = int(datetime(2024, 6, 21, 12, 0, tzinfo=UTC_TZ).timestamp())
        elev_summer = calculate_sun_elevation(ts_summer, 51.83, 7.28)

        # Winter-Mittag
        ts_winter = int(datetime(2024, 12, 21, 12, 0, tzinfo=UTC_TZ).timestamp())
        elev_winter = calculate_sun_elevation(ts_winter, 51.83, 7.28)

        assert elev_winter < elev_summer

    def test_equator_higher_elevation(self):
        """Test: Äquator hat höhere Mittags-Elevation."""
        ts = int(datetime(2024, 3, 21, 12, 0, tzinfo=UTC_TZ).timestamp())

        elev_equator = calculate_sun_elevation(ts, 0.0, 0.0)
        elev_germany = calculate_sun_elevation(ts, 51.83, 7.28)

        assert elev_equator > elev_germany

    def test_precision_known_values(self):
        """Test: Bekannte Sonnenhöhen-Werte für Präzisionsprüfung.

        Sommersonnenwende (21.6.) Mittag am Äquator sollte nahe 66.5° sein
        (90° - 23.5° Ekliptik-Neigung).
        """
        # 21. Juni 2024, 12:00 UTC am Äquator
        ts = int(datetime(2024, 6, 21, 12, 0, tzinfo=UTC_TZ).timestamp())
        elev = calculate_sun_elevation(ts, 0.0, 0.0)

        # Erwarteter Wert: ~66.5° (90 - 23.44 Ekliptik)
        assert 64.0 < elev < 69.0, f"Erwartete ~66.5°, bekam {elev:.1f}°"


class TestPrepareFeatures:
    """Tests für Feature-Erstellung."""

    def test_basic_features(self):
        """Test: Grundlegende Features werden erstellt."""
        df = pd.DataFrame(
            [
                {
                    "timestamp": 1704067200,  # 2024-01-01 00:00 UTC
                    "ghi_wm2": 0.0,
                    "cloud_cover_pct": 80,
                    "temperature_c": 5.0,
                },
                {
                    "timestamp": 1704110400,  # 2024-01-01 12:00 UTC
                    "ghi_wm2": 300.0,
                    "cloud_cover_pct": 20,
                    "temperature_c": 10.0,
                },
            ]
        )

        features = prepare_features(df, 51.83, 7.28)

        # Zyklische Zeit-Features
        assert "hour_sin" in features.columns
        assert "hour_cos" in features.columns
        assert "month_sin" in features.columns
        assert "month_cos" in features.columns
        assert "doy_sin" in features.columns
        assert "doy_cos" in features.columns
        # Wetter-Features
        assert "ghi" in features.columns
        assert "temperature" in features.columns
        assert "sun_elevation" in features.columns
        # cloud_cover und effective_irradiance entfernt (#168)

        assert len(features) == 2

    def test_hour_feature_cyclic(self):
        """Test: Stunden-Feature ist zyklisch kodiert."""
        import numpy as np

        # 2024-01-01 00:00 UTC and 12:00 UTC
        df = pd.DataFrame(
            [
                {"timestamp": 1704067200, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 0},
                {"timestamp": 1704110400, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 0},
            ]
        )

        features = prepare_features(df, 51.83, 7.28)

        # Stunde 0: sin(0) = 0, cos(0) = 1
        assert np.isclose(features.iloc[0]["hour_sin"], 0, atol=1e-10)
        assert np.isclose(features.iloc[0]["hour_cos"], 1, atol=1e-10)
        # Stunde 12: sin(π) = 0, cos(π) = -1
        assert np.isclose(features.iloc[1]["hour_sin"], 0, atol=1e-10)
        assert np.isclose(features.iloc[1]["hour_cos"], -1, atol=1e-10)

    def test_month_feature_cyclic(self):
        """Test: Monat-Feature ist zyklisch kodiert."""
        import numpy as np

        # January and July 2024
        df = pd.DataFrame(
            [
                {"timestamp": 1704067200, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 0},
                {"timestamp": 1719792000, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 0},
            ]
        )

        features = prepare_features(df, 51.83, 7.28)

        # Januar (Monat 1): sin(2π * 1/12) = 0.5, cos(2π * 1/12) ≈ 0.866
        assert np.isclose(features.iloc[0]["month_sin"], 0.5, atol=1e-10)
        assert np.isclose(features.iloc[0]["month_cos"], np.sqrt(3) / 2, atol=1e-10)
        # Juli (Monat 7): sin(2π * 7/12) ≈ -0.5, cos(2π * 7/12) ≈ -0.866
        assert np.isclose(features.iloc[1]["month_sin"], -0.5, atol=1e-10)
        assert np.isclose(features.iloc[1]["month_cos"], -np.sqrt(3) / 2, atol=1e-10)

    def test_peak_kwp_feature(self):
        """Test: peak_kwp wird als Feature hinzugefügt wenn angegeben."""
        df = pd.DataFrame(
            [
                {
                    "timestamp": 1704067200,
                    "ghi_wm2": 500,
                    "cloud_cover_pct": 20,
                    "temperature_c": 15,
                },
                {
                    "timestamp": 1704110400,
                    "ghi_wm2": 800,
                    "cloud_cover_pct": 10,
                    "temperature_c": 20,
                },
            ]
        )

        # Ohne peak_kwp
        features_no_kwp = prepare_features(df, 51.83, 7.28)
        assert "peak_kwp" not in features_no_kwp.columns

        # Mit peak_kwp
        features_with_kwp = prepare_features(df, 51.83, 7.28, peak_kwp=9.92)
        assert "peak_kwp" in features_with_kwp.columns
        assert features_with_kwp.iloc[0]["peak_kwp"] == 9.92
        assert features_with_kwp.iloc[1]["peak_kwp"] == 9.92

    def test_weather_lag_features(self):
        """Test: Wetter-Lag-Features werden korrekt berechnet."""
        df = pd.DataFrame(
            [
                {
                    "timestamp": 1704067200,
                    "ghi_wm2": 100,
                    "cloud_cover_pct": 10,
                    "temperature_c": 5,
                },
                {
                    "timestamp": 1704070800,
                    "ghi_wm2": 200,
                    "cloud_cover_pct": 20,
                    "temperature_c": 8,
                },
                {
                    "timestamp": 1704074400,
                    "ghi_wm2": 300,
                    "cloud_cover_pct": 30,
                    "temperature_c": 10,
                },
                {
                    "timestamp": 1704078000,
                    "ghi_wm2": 400,
                    "cloud_cover_pct": 25,
                    "temperature_c": 12,
                },
            ]
        )

        features = prepare_features(df, 51.83, 7.28)

        # Wetter-Lags prüfen
        assert "ghi_lag_1h" in features.columns
        assert "ghi_lag_3h" in features.columns
        assert "ghi_rolling_3h" in features.columns
        # cloud_trend entfernt (#168)

        # ghi_lag_1h: 0, 100, 200, 300 (erste ist 0 weil fillna)
        assert features.iloc[0]["ghi_lag_1h"] == 0
        assert features.iloc[1]["ghi_lag_1h"] == 100
        assert features.iloc[2]["ghi_lag_1h"] == 200
        assert features.iloc[3]["ghi_lag_1h"] == 300

        # ghi_rolling_3h: rolling mean mit min_periods=1
        # [100], [100,200], [100,200,300], [200,300,400]
        assert features.iloc[0]["ghi_rolling_3h"] == 100
        assert features.iloc[1]["ghi_rolling_3h"] == 150  # (100+200)/2
        assert features.iloc[2]["ghi_rolling_3h"] == 200  # (100+200+300)/3
        assert features.iloc[3]["ghi_rolling_3h"] == 300  # (200+300+400)/3

    # production_lag Tests entfernt (#170):
    # - Features wurden komplett entfernt, da sie im Predict-Modus
    #   immer 0 waren und zu massiver Unterschätzung führten

    def test_physics_features(self):
        """Test: Physikalische Features (diffuse_fraction, t_module, efficiency)."""
        df = pd.DataFrame(
            [
                {
                    "timestamp": 1704067200,
                    "ghi_wm2": 800,
                    "cloud_cover_pct": 20,
                    "temperature_c": 25,
                    "wind_speed_ms": 2.0,
                    "dhi_wm2": 200,
                },
                {
                    "timestamp": 1704070800,
                    "ghi_wm2": 1000,
                    "cloud_cover_pct": 0,
                    "temperature_c": 35,
                    "wind_speed_ms": 0.0,
                    "dhi_wm2": 100,
                },
            ]
        )

        features = prepare_features(df, 51.83, 7.28)

        # diffuse_fraction prüfen
        assert "diffuse_fraction" in features.columns
        # 200 / (800 + 1) ≈ 0.25
        assert abs(features.iloc[0]["diffuse_fraction"] - 0.25) < 0.01

        # t_module prüfen (NOCT=45)
        # t_module = temp + (ghi/800) * (45-20) - wind*2
        # = 25 + (800/800)*25 - 2*2 = 25 + 25 - 4 = 46
        assert "t_module" in features.columns
        assert abs(features.iloc[0]["t_module"] - 46) < 0.1

        # efficiency_factor prüfen
        # = 1 + (-0.004) * (46 - 25) = 1 - 0.084 = 0.916
        assert "efficiency_factor" in features.columns
        assert abs(features.iloc[0]["efficiency_factor"] - 0.916) < 0.01

    def test_dni_feature(self):
        """Test: DNI wird als Feature hinzugefügt wenn vorhanden."""
        # Ohne DNI
        df_no_dni = pd.DataFrame(
            [{"timestamp": 1704067200, "ghi_wm2": 500, "cloud_cover_pct": 20, "temperature_c": 15}]
        )
        features_no_dni = prepare_features(df_no_dni, 51.83, 7.28)
        assert features_no_dni.iloc[0]["dni"] == 0.0

        # Mit DNI
        df_with_dni = pd.DataFrame(
            [
                {
                    "timestamp": 1704067200,
                    "ghi_wm2": 500,
                    "cloud_cover_pct": 20,
                    "temperature_c": 15,
                    "dni_wm2": 700,
                }
            ]
        )
        features_with_dni = prepare_features(df_with_dni, 51.83, 7.28)
        assert features_with_dni.iloc[0]["dni"] == 700


class TestSaveLoadModel:
    """Tests für Modell-Speicherung."""

    def test_save_and_load_model(self, tmp_path):
        """Test: Modell kann gespeichert und geladen werden."""
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        # Einfaches Modell erstellen
        model = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("model", RandomForestRegressor(n_estimators=2, random_state=42)),
            ]
        )

        # Mit Dummy-Daten fitten
        X = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        y = pd.Series([10, 20, 30])
        model.fit(X, y)

        # Speichern
        model_path = tmp_path / "model.pkl"
        metrics = {"mape": 10.5, "mae": 100}
        save_model(model, model_path, metrics)

        assert model_path.exists()

        # Laden
        loaded_model, loaded_metrics = load_model(model_path)

        assert loaded_metrics["mape"] == 10.5
        assert loaded_metrics["mae"] == 100

        # Vorhersage sollte gleich sein
        pred_original = model.predict(X)
        pred_loaded = loaded_model.predict(X)

        assert list(pred_original) == list(pred_loaded)

    def test_load_nonexistent_raises(self, tmp_path):
        """Test: Laden von nicht-existentem Modell wirft Fehler."""
        with pytest.raises(ModelNotFoundError):
            load_model(tmp_path / "nonexistent.pkl")

    def test_save_creates_parent_dirs(self, tmp_path):
        """Test: Speichern erstellt Parent-Verzeichnisse."""
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        model = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("model", RandomForestRegressor(n_estimators=2, random_state=42)),
            ]
        )
        X = pd.DataFrame({"a": [1, 2, 3]})
        y = pd.Series([10, 20, 30])
        model.fit(X, y)

        model_path = tmp_path / "subdir" / "model.pkl"
        save_model(model, model_path)

        assert model_path.exists()


class TestHourlyForecast:
    """Tests für HourlyForecast Dataclass."""

    def test_create_hourly_forecast(self):
        """Test: HourlyForecast kann erstellt werden."""
        ts = datetime(2024, 1, 1, 12, 0, tzinfo=UTC_TZ)
        forecast = HourlyForecast(
            timestamp=ts,
            production_w=1500,
            ghi_wm2=400.0,
            cloud_cover_pct=30,
        )

        assert forecast.timestamp == ts
        assert forecast.production_w == 1500
        assert forecast.ghi_wm2 == 400.0
        assert forecast.cloud_cover_pct == 30


class TestXGBoostIntegration:
    """Tests für XGBoost-Integration."""

    def test_xgboost_available_constant_exists(self):
        """Test: XGBOOST_AVAILABLE Konstante existiert."""
        from pvforecast.model import XGBOOST_AVAILABLE

        assert isinstance(XGBOOST_AVAILABLE, bool)

    def test_create_rf_pipeline(self):
        """Test: RandomForest Pipeline kann erstellt werden."""
        from pvforecast.model import _create_pipeline

        pipeline = _create_pipeline("rf")
        assert pipeline is not None
        assert "scaler" in pipeline.named_steps
        assert "model" in pipeline.named_steps

    def test_create_xgb_pipeline_without_xgboost(self):
        """Test: XGBoost Pipeline wirft DependencyError wenn nicht installiert."""
        from pvforecast.model import XGBOOST_AVAILABLE, _create_pipeline
        from pvforecast.validation import DependencyError

        if not XGBOOST_AVAILABLE:
            with pytest.raises(DependencyError) as exc_info:
                _create_pipeline("xgb")
            # Prüfe dass hilfreiche Fehlermeldung vorhanden
            assert "install" in str(exc_info.value).lower()
        else:
            # Wenn XGBoost verfügbar, sollte Pipeline erstellt werden
            pipeline = _create_pipeline("xgb")
            assert pipeline is not None

    def test_reload_xgboost_function_exists(self):
        """Test: reload_xgboost Funktion existiert und ist aufrufbar."""
        from pvforecast.model import reload_xgboost

        assert callable(reload_xgboost)

    def test_reload_xgboost_returns_bool(self):
        """Test: reload_xgboost gibt boolean zurück."""
        from pvforecast.model import reload_xgboost

        result = reload_xgboost()
        assert isinstance(result, bool)

    def test_reload_xgboost_updates_globals(self):
        """Test: reload_xgboost aktualisiert XGBOOST_AVAILABLE wenn erfolgreich."""
        from pvforecast import model
        from pvforecast.model import reload_xgboost

        # Wenn XGBoost verfügbar ist, sollte reload True zurückgeben
        # und die Globals korrekt setzen
        result = reload_xgboost()
        if result:
            assert model.XGBOOST_AVAILABLE is True
            assert model.XGBOOST_ERROR is None


class TestLoadTrainingData:
    """Tests für load_training_data()."""

    def test_load_training_data_imports(self):
        """Test: load_training_data kann importiert werden."""
        assert callable(load_training_data)

    def test_load_training_data_returns_tuple(self, tmp_path):
        """Test: load_training_data gibt (X, y) Tuple zurück."""
        from pvforecast.db import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)


        # Testdaten einfügen (genug für min_samples=10)
        with db.connect() as conn:
            for i in range(20):
                ts = 1704067200 + i * 3600  # Stündlich ab 01.01.2024
                conn.execute(
                    "INSERT INTO pv_readings (timestamp, production_w, curtailed) VALUES (?, ?, 0)",
                    (ts, 500 + i * 10),
                )
                conn.execute(
                    """INSERT INTO weather_history
                    (timestamp, ghi_wm2, cloud_cover_pct, temperature_c,
                    wind_speed_ms, humidity_pct, dhi_wm2, dni_wm2)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ts, 400, 20, 15, 3, 60, 100, 300),
                )
            conn.commit()

        X, y = load_training_data(db, lat=51.83, lon=7.28, min_samples=10)

        assert isinstance(X, pd.DataFrame)
        assert isinstance(y, pd.Series)
        assert len(X) == len(y) == 20

    def test_load_training_data_min_samples(self, tmp_path):
        """Test: load_training_data wirft ValueError bei zu wenig Daten."""
        from pvforecast.db import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)


        # Nur 5 Datensätze einfügen
        with db.connect() as conn:
            for i in range(5):
                ts = 1704067200 + i * 3600
                conn.execute(
                    "INSERT INTO pv_readings (timestamp, production_w, curtailed) VALUES (?, ?, 0)",
                    (ts, 500),
                )
                conn.execute(
                    """INSERT INTO weather_history
                    (timestamp, ghi_wm2, cloud_cover_pct, temperature_c,
                    wind_speed_ms, humidity_pct, dhi_wm2, dni_wm2)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ts, 400, 20, 15, 3, 60, 100, 300),
                )
            conn.commit()

        with pytest.raises(ValueError) as exc_info:
            load_training_data(db, lat=51.83, lon=7.28, min_samples=100)

        assert "Zu wenig Trainingsdaten" in str(exc_info.value)
        assert "100" in str(exc_info.value)

    def test_load_training_data_since_year(self, tmp_path):
        """Test: since_year filtert alte Daten aus."""
        from pvforecast.db import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)


        # Daten aus 2022 und 2024
        with db.connect() as conn:
            # 10 Datensätze aus 2022
            for i in range(10):
                ts = 1640995200 + i * 3600  # 01.01.2022
                conn.execute(
                    "INSERT INTO pv_readings (timestamp, production_w, curtailed) VALUES (?, ?, 0)",
                    (ts, 500),
                )
                conn.execute(
                    """INSERT INTO weather_history
                    (timestamp, ghi_wm2, cloud_cover_pct, temperature_c,
                    wind_speed_ms, humidity_pct, dhi_wm2, dni_wm2)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ts, 400, 20, 15, 3, 60, 100, 300),
                )
            # 15 Datensätze aus 2024
            for i in range(15):
                ts = 1704067200 + i * 3600  # 01.01.2024
                conn.execute(
                    "INSERT INTO pv_readings (timestamp, production_w, curtailed) VALUES (?, ?, 0)",
                    (ts, 600),
                )
                conn.execute(
                    """INSERT INTO weather_history
                    (timestamp, ghi_wm2, cloud_cover_pct, temperature_c,
                    wind_speed_ms, humidity_pct, dhi_wm2, dni_wm2)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ts, 500, 15, 18, 2, 55, 120, 350),
                )
            conn.commit()

        # Alle Daten laden
        X_all, y_all = load_training_data(db, lat=51.83, lon=7.28, min_samples=10)
        assert len(X_all) == 25

        # Nur ab 2024
        X_2024, y_2024 = load_training_data(
            db, lat=51.83, lon=7.28, since_year=2024, min_samples=10
        )
        assert len(X_2024) == 15


class TestTune:
    """Tests für Hyperparameter-Tuning."""

    def test_tune_imports(self):
        """Test: tune Funktion kann importiert werden."""
        from pvforecast.model import tune

        assert callable(tune)

    def test_tune_requires_minimum_data(self, tmp_path):
        """Test: tune wirft Fehler bei zu wenig Daten."""
        from pvforecast.db import Database
        from pvforecast.model import tune

        # Leere Datenbank (Schema wird automatisch erstellt)
        db = Database(tmp_path / "test.db")

        with pytest.raises(ValueError) as exc_info:
            tune(db, 51.83, 7.28, n_iter=2, cv_splits=2)

        assert "Zu wenig Trainingsdaten" in str(exc_info.value)

    def test_tune_parameter_distributions(self):
        """Test: Parameter-Verteilungen sind korrekt definiert."""
        from scipy.stats import randint, uniform

        # XGBoost Parameter-Raum
        param_dist = {
            "n_estimators": randint(100, 500),
            "max_depth": randint(4, 13),
            "learning_rate": uniform(0.01, 0.29),
        }

        # Teste dass Samples im erwarteten Bereich liegen
        for _ in range(10):
            n_est = param_dist["n_estimators"].rvs()
            assert 100 <= n_est < 500

            depth = param_dist["max_depth"].rvs()
            assert 4 <= depth < 13

            lr = param_dist["learning_rate"].rvs()
            assert 0.01 <= lr <= 0.30


class TestExtendedFeatures:
    """Tests für erweiterte Wetter-Features in prepare_features."""

    def test_prepare_features_with_extended_weather(self):
        """Test: prepare_features nutzt erweiterte Wetter-Features."""
        from pvforecast.model import prepare_features

        df = pd.DataFrame(
            {
                "timestamp": [1704067200, 1704070800],  # 2 Stunden
                "ghi_wm2": [500.0, 600.0],
                "cloud_cover_pct": [30, 40],
                "temperature_c": [15.0, 16.0],
                "wind_speed_ms": [5.5, 6.0],
                "humidity_pct": [65, 70],
                "dhi_wm2": [150.0, 180.0],
            }
        )

        features = prepare_features(df, 51.83, 7.28)

        assert "wind_speed" in features.columns
        assert "humidity" in features.columns
        assert "dhi" in features.columns
        assert features["wind_speed"].iloc[0] == 5.5
        assert features["humidity"].iloc[0] == 65
        assert features["dhi"].iloc[0] == 150.0

    def test_prepare_features_without_extended_weather(self):
        """Test: prepare_features funktioniert auch ohne erweiterte Features."""
        from pvforecast.model import prepare_features

        # Nur Basis-Features (wie alte Daten)
        df = pd.DataFrame(
            {
                "timestamp": [1704067200],
                "ghi_wm2": [500.0],
                "cloud_cover_pct": [30],
                "temperature_c": [15.0],
            }
        )

        features = prepare_features(df, 51.83, 7.28)

        # Sollte Defaults verwenden
        assert features["wind_speed"].iloc[0] == 0.0
        assert features["humidity"].iloc[0] == 50
        assert features["dhi"].iloc[0] == 0.0


class TestOptunaIntegration:
    """Tests für Optuna-Integration."""

    def test_optuna_available_constant_exists(self):
        """Test: OPTUNA_AVAILABLE Konstante existiert."""
        from pvforecast.model import OPTUNA_AVAILABLE

        assert isinstance(OPTUNA_AVAILABLE, bool)

    def test_tune_optuna_imports(self):
        """Test: tune_optuna Funktion kann importiert werden."""
        from pvforecast.model import tune_optuna

        assert callable(tune_optuna)

    def test_check_optuna_available(self):
        """Test: _check_optuna_available gibt hilfreiche Fehlermeldung."""
        from pvforecast.model import OPTUNA_AVAILABLE, _check_optuna_available
        from pvforecast.validation import DependencyError

        if not OPTUNA_AVAILABLE:
            with pytest.raises(DependencyError) as exc_info:
                _check_optuna_available()
            assert "install" in str(exc_info.value).lower()
            assert "optuna" in str(exc_info.value).lower()
        else:
            # Sollte ohne Fehler durchlaufen
            _check_optuna_available()

    def test_tune_optuna_requires_minimum_data(self, tmp_path):
        """Test: tune_optuna wirft Fehler bei zu wenig Daten."""
        from pvforecast.model import OPTUNA_AVAILABLE, tune_optuna

        if not OPTUNA_AVAILABLE:
            pytest.skip("Optuna nicht installiert")

        from pvforecast.db import Database

        # Leere Datenbank
        db = Database(tmp_path / "test.db")

        with pytest.raises(ValueError) as exc_info:
            tune_optuna(db, 51.83, 7.28, n_trials=2, cv_splits=2)

        assert "Zu wenig Trainingsdaten" in str(exc_info.value)

    def test_tune_optuna_without_optuna_raises_dependency_error(self, tmp_path, monkeypatch):
        """Test: tune_optuna ohne Optuna wirft DependencyError."""
        from pvforecast import model
        from pvforecast.db import Database
        from pvforecast.validation import DependencyError

        # OPTUNA_AVAILABLE auf False setzen
        monkeypatch.setattr(model, "OPTUNA_AVAILABLE", False)

        db = Database(tmp_path / "test.db")

        with pytest.raises(DependencyError) as exc_info:
            model.tune_optuna(db, 51.83, 7.28, n_trials=2)

        assert "optuna" in str(exc_info.value).lower()

    def test_tune_optuna_xgb_without_xgboost_raises_dependency_error(self, tmp_path, monkeypatch):
        """Test: tune_optuna mit XGBoost ohne XGBoost wirft DependencyError."""
        from pvforecast import model
        from pvforecast.db import Database
        from pvforecast.validation import DependencyError

        # XGBoost deaktivieren, Optuna aktivieren
        monkeypatch.setattr(model, "XGBOOST_AVAILABLE", False)
        monkeypatch.setattr(model, "XGBOOST_ERROR", "not_installed")

        # Optuna muss verfügbar sein für diesen Test
        if not model.OPTUNA_AVAILABLE:
            pytest.skip("Optuna nicht installiert")

        db = Database(tmp_path / "test.db")

        with pytest.raises(DependencyError) as exc_info:
            model.tune_optuna(db, 51.83, 7.28, model_type="xgb", n_trials=2)

        assert "xgboost" in str(exc_info.value).lower()


class TestEvaluate:
    """Tests für evaluate() Funktion."""

    def test_evaluate_returns_evaluation_result(self, tmp_path):
        """Test: evaluate gibt EvaluationResult zurück."""
        from unittest.mock import MagicMock, patch

        import pandas as pd

        from pvforecast.model import (
            EvaluationResult,
            WeatherBreakdown,
            evaluate,
        )

        # Mock Database mit Testdaten
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connect.return_value.__exit__ = MagicMock(return_value=False)

        # Simuliere Daten für ein Jahr (vereinfacht: 100 Datenpunkte)
        test_data = pd.DataFrame(
            {
                "timestamp": [1704067200 + i * 3600 for i in range(100)],  # Stündlich
                "production_w": [500 + i * 10 for i in range(100)],
                "ghi_wm2": [300 + i * 5 for i in range(100)],
                "cloud_cover_pct": [20 + (i % 60) for i in range(100)],
                "temperature_c": [10 + (i % 20) for i in range(100)],
                "wind_speed_ms": [5.0] * 100,
                "humidity_pct": [60] * 100,
                "dhi_wm2": [100.0] * 100,
                "dni_wm2": [200.0] * 100,
            }
        )

        with patch("pandas.read_sql_query", return_value=test_data):
            # Mock Modell
            mock_model = MagicMock()
            mock_model.predict.return_value = test_data["production_w"].values + 50

            result = evaluate(
                model=mock_model,
                db=mock_db,
                lat=51.0,
                lon=7.0,
                peak_kwp=10.0,
                year=2024,
            )

        assert isinstance(result, EvaluationResult)
        assert result.year == 2024
        assert result.data_points == 100
        assert result.mae >= 0
        assert result.rmse >= 0
        # R² kann < -1 sein bei sehr schlechten Vorhersagen (mathematisch korrekt)
        assert isinstance(result.r2, float)
        assert len(result.weather_breakdown) > 0
        assert all(isinstance(wb, WeatherBreakdown) for wb in result.weather_breakdown)

    def test_evaluate_raises_on_no_data(self, tmp_path):
        """Test: evaluate wirft ValueError wenn keine Daten."""
        from unittest.mock import MagicMock, patch

        import pandas as pd
        import pytest

        from pvforecast.model import evaluate

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connect.return_value.__exit__ = MagicMock(return_value=False)

        # Leeres DataFrame
        empty_df = pd.DataFrame()

        with patch("pandas.read_sql_query", return_value=empty_df):
            mock_model = MagicMock()

            with pytest.raises(ValueError, match="Keine Daten"):
                evaluate(mock_model, mock_db, 51.0, 7.0, year=2024)

    def test_evaluate_default_year(self):
        """Test: evaluate verwendet letztes Jahr als Default."""
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        import pandas as pd

        from pvforecast.model import evaluate

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connect.return_value.__exit__ = MagicMock(return_value=False)

        test_data = pd.DataFrame(
            {
                "timestamp": [1704067200 + i * 3600 for i in range(50)],
                "production_w": [500] * 50,
                "ghi_wm2": [300] * 50,
                "cloud_cover_pct": [30] * 50,
                "temperature_c": [15] * 50,
                "wind_speed_ms": [5.0] * 50,
                "humidity_pct": [60] * 50,
                "dhi_wm2": [100.0] * 50,
                "dni_wm2": [200.0] * 50,
            }
        )

        with patch("pandas.read_sql_query", return_value=test_data):
            mock_model = MagicMock()
            mock_model.predict.return_value = [500] * 50

            result = evaluate(mock_model, mock_db, 51.0, 7.0)

        expected_year = datetime.now().year - 1
        assert result.year == expected_year
