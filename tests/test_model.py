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

        assert "hour" in features.columns
        assert "month" in features.columns
        assert "day_of_year" in features.columns
        assert "ghi" in features.columns
        assert "cloud_cover" in features.columns
        assert "temperature" in features.columns
        assert "sun_elevation" in features.columns

        assert len(features) == 2

    def test_hour_feature_correct(self):
        """Test: Stunden-Feature ist korrekt."""
        # 2024-01-01 00:00 UTC and 12:00 UTC
        df = pd.DataFrame([
            {"timestamp": 1704067200, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 0},
            {"timestamp": 1704110400, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 0},
        ])

        features = prepare_features(df, 51.83, 7.28)

        assert features.iloc[0]["hour"] == 0
        assert features.iloc[1]["hour"] == 12

    def test_month_feature_correct(self):
        """Test: Monat-Feature ist korrekt."""
        # January and July 2024
        df = pd.DataFrame([
            {"timestamp": 1704067200, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 0},
            {"timestamp": 1719792000, "ghi_wm2": 0, "cloud_cover_pct": 0, "temperature_c": 0},
        ])

        features = prepare_features(df, 51.83, 7.28)

        assert features.iloc[0]["month"] == 1
        assert features.iloc[1]["month"] == 7


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
