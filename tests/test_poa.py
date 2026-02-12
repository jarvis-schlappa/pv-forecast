"""Tests für POA (Plane of Array) Multi-Array Features."""

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from pvforecast.config import Config, PVArrayConfig
from pvforecast.model import calculate_poa_features, prepare_features

UTC_TZ = ZoneInfo("UTC")

# Standard-Arrays (Dülmen)
ARRAYS = [
    PVArrayConfig(name="Wohnhaus SO", azimuth=140, tilt=43, kwp=6.08),
    PVArrayConfig(name="Wohnhaus NW", azimuth=320, tilt=43, kwp=2.56),
    PVArrayConfig(name="Gauben SW", azimuth=229, tilt=43, kwp=1.28),
]

LAT, LON = 51.8472166, 7.2891113


def _make_df(hours_utc: list[int], month: int = 6, day: int = 21,
             ghi: float = 500, dhi: float = 150, dni: float = 350) -> pd.DataFrame:
    """Helper: DataFrame mit Wetterdaten für bestimmte Stunden."""
    rows = []
    for h in hours_utc:
        ts = int(datetime(2025, month, day, h, 0, tzinfo=UTC_TZ).timestamp())
        rows.append({
            "timestamp": ts,
            "ghi_wm2": ghi,
            "cloud_cover_pct": 20,
            "temperature_c": 20.0,
            "wind_speed_ms": 2.0,
            "humidity_pct": 50,
            "dhi_wm2": dhi,
            "dni_wm2": dni,
        })
    return pd.DataFrame(rows)


class TestPOAFeatures:
    """Tests für POA-Berechnung."""

    def test_poa_total_positive_daytime(self):
        """POA should be positive during daytime."""
        df = _make_df([6, 8, 10, 12, 14, 16])
        features = prepare_features(df, LAT, LON, pv_arrays=ARRAYS)
        # Daytime POA should be > 0
        assert (features["poa_total"] > 0).any()

    def test_poa_ratio_reasonable(self):
        """POA/GHI ratio should be in reasonable range."""
        df = _make_df([8, 10, 12, 14, 16])
        features = prepare_features(df, LAT, LON, pv_arrays=ARRAYS)
        mask = features["poa_total"] > 0
        ratios = features.loc[mask, "poa_ratio"]
        assert (ratios >= 0).all()
        assert (ratios <= 3).all()

    def test_so_array_better_morning(self):
        """SO (140°) array should get more POA in the morning than NW (320°)."""
        # Morning: 7 UTC = 9 MESZ
        morning_hours = [6, 7, 8]
        df = _make_df(morning_hours)
        timestamps = pd.DatetimeIndex(
            pd.to_datetime(df["timestamp"], unit="s", utc=True)
        )
        ghi = df["ghi_wm2"].clip(lower=0)
        dhi = df["dhi_wm2"].clip(lower=0)
        dni = df["dni_wm2"].clip(lower=0)

        from pvforecast.model import calculate_sun_elevation
        sun_elev = df["timestamp"].apply(
            lambda ts: calculate_sun_elevation(int(ts), LAT, LON)
        )

        so_only = [PVArrayConfig(name="SO", azimuth=140, tilt=43, kwp=1.0)]
        nw_only = [PVArrayConfig(name="NW", azimuth=320, tilt=43, kwp=1.0)]

        poa_so = calculate_poa_features(timestamps, ghi, dhi, dni, sun_elev, LAT, LON, so_only)
        poa_nw = calculate_poa_features(timestamps, ghi, dhi, dni, sun_elev, LAT, LON, nw_only)

        assert poa_so["poa_total"].sum() > poa_nw["poa_total"].sum()

    def test_no_arrays_zeros(self):
        """Without arrays, POA features should be 0."""
        df = _make_df([10, 12, 14])
        features = prepare_features(df, LAT, LON, pv_arrays=None)
        assert (features["poa_total"] == 0).all()
        assert (features["poa_ratio"] == 0).all()

    def test_empty_arrays_zeros(self):
        """Empty array list should produce 0 POA features."""
        df = _make_df([10, 12, 14])
        features = prepare_features(df, LAT, LON, pv_arrays=[])
        assert (features["poa_total"] == 0).all()

    def test_backward_compatible_feature_count(self):
        """With arrays, features should have poa_total and poa_ratio columns."""
        df = _make_df([10, 12])
        features_no_poa = prepare_features(df, LAT, LON, pv_arrays=None)
        features_with_poa = prepare_features(df, LAT, LON, pv_arrays=ARRAYS)
        # Both should have poa_total and poa_ratio
        assert "poa_total" in features_no_poa.columns
        assert "poa_total" in features_with_poa.columns
        # Without arrays, values are 0; with arrays, at least some > 0
        assert features_no_poa["poa_total"].sum() == 0
        assert features_with_poa["poa_total"].sum() > 0


class TestPVArrayConfig:
    """Tests für PV-Array Config Parsing."""

    def test_config_with_arrays(self):
        """Config with pv_system.arrays should parse correctly."""
        data = {
            "location": {"latitude": 51.85, "longitude": 7.29},
            "system": {"peak_kwp": 9.92, "name": "Test"},
            "pv_system": {
                "arrays": [
                    {"name": "SO", "azimuth": 140, "tilt": 43, "kwp": 6.08},
                    {"name": "NW", "azimuth": 320, "tilt": 43, "kwp": 2.56},
                ]
            },
        }
        config = Config.from_dict(data)
        assert len(config.pv_arrays) == 2
        assert config.pv_arrays[0].azimuth == 140
        assert config.pv_arrays[1].kwp == 2.56

    def test_config_without_arrays(self):
        """Config without pv_system should have empty arrays."""
        data = {
            "location": {"latitude": 51.85, "longitude": 7.29},
            "system": {"peak_kwp": 9.92, "name": "Test"},
        }
        config = Config.from_dict(data)
        assert config.pv_arrays == []

    def test_config_roundtrip(self):
        """Config with arrays should survive to_dict/from_dict roundtrip."""
        config = Config(
            pv_arrays=[
                PVArrayConfig(name="Test", azimuth=180, tilt=30, kwp=5.0),
            ]
        )
        d = config.to_dict()
        config2 = Config.from_dict(d)
        assert len(config2.pv_arrays) == 1
        assert config2.pv_arrays[0].azimuth == 180
