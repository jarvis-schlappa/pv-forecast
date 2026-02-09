"""Tests for forecast accuracy analysis."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from pvforecast.db import Database
from pvforecast.forecast_accuracy import (
    AccuracyReport,
    HorizonMetrics,
    SourceMetrics,
    analyze_forecast_accuracy,
    format_accuracy_report,
    get_horizon_bucket,
)


class TestHorizonBuckets:
    """Tests for horizon bucket assignment."""

    def test_bucket_0_1h(self):
        assert get_horizon_bucket(0) == "0-1h"
        assert get_horizon_bucket(0.5) == "0-1h"
        assert get_horizon_bucket(0.99) == "0-1h"

    def test_bucket_1_6h(self):
        assert get_horizon_bucket(1) == "1-6h"
        assert get_horizon_bucket(3) == "1-6h"
        assert get_horizon_bucket(5.99) == "1-6h"

    def test_bucket_6_24h(self):
        assert get_horizon_bucket(6) == "6-24h"
        assert get_horizon_bucket(12) == "6-24h"
        assert get_horizon_bucket(23.99) == "6-24h"

    def test_bucket_24_48h(self):
        assert get_horizon_bucket(24) == "24-48h"
        assert get_horizon_bucket(36) == "24-48h"
        assert get_horizon_bucket(47.99) == "24-48h"

    def test_bucket_48_72h(self):
        assert get_horizon_bucket(48) == "48-72h"
        assert get_horizon_bucket(60) == "48-72h"
        assert get_horizon_bucket(71.99) == "48-72h"

    def test_bucket_beyond_72h(self):
        assert get_horizon_bucket(72) == ">72h"
        assert get_horizon_bucket(100) == ">72h"
        assert get_horizon_bucket(168) == ">72h"


class TestAnalyzeForecastAccuracy:
    """Tests for the main analysis function."""

    @pytest.fixture
    def db_with_data(self, tmp_path):
        """Create a database with test data."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)

        # Insert weather history (ground truth)
        with db.connect() as conn:
            # Hours 0-5 on day 1 (timestamps: 1000, 4600, 8200, ...)
            base_ts = 1704067200  # 2024-01-01 00:00:00 UTC
            for hour in range(24):
                ts = base_ts + hour * 3600
                # Simulated GHI: peaks at noon
                ghi = max(0, 500 * math.sin(math.pi * hour / 12) if 6 <= hour <= 18 else 0)
                conn.execute(
                    "INSERT INTO weather_history (timestamp, ghi_wm2, cloud_cover_pct, temperature_c) VALUES (?, ?, ?, ?)",
                    (ts, ghi, 20, 10),
                )

            # Insert forecasts - slightly off from actual
            issued_at = base_ts - 3600  # Issued 1 hour before day starts
            for hour in range(24):
                target_ts = base_ts + hour * 3600
                actual_ghi = max(0, 500 * math.sin(math.pi * hour / 12) if 6 <= hour <= 18 else 0)
                # Open-meteo: +10% bias
                forecast_ghi_om = actual_ghi * 1.1
                # MOSMIX: -5% bias
                forecast_ghi_mosmix = actual_ghi * 0.95

                conn.execute(
                    """INSERT INTO forecast_history 
                       (issued_at, target_time, source, ghi_wm2, cloud_cover_pct, temperature_c)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (issued_at, target_ts, "open-meteo", forecast_ghi_om, 18, 11),
                )
                conn.execute(
                    """INSERT INTO forecast_history 
                       (issued_at, target_time, source, ghi_wm2, cloud_cover_pct, temperature_c)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (issued_at, target_ts, "mosmix", forecast_ghi_mosmix, 22, 9),
                )

        return db

    @pytest.fixture
    def empty_db(self, tmp_path):
        """Create an empty database."""
        db_path = tmp_path / "empty.db"
        return Database(db_path)

    def test_empty_database(self, empty_db):
        """Test with no data."""
        report = analyze_forecast_accuracy(empty_db)
        assert report.total_forecasts == 0
        assert report.matched_forecasts == 0
        assert len(report.sources) == 0
        assert len(report.correlations) == 0

    def test_basic_analysis(self, db_with_data):
        """Test basic analysis with test data."""
        report = analyze_forecast_accuracy(db_with_data)

        assert report.matched_forecasts > 0
        assert len(report.sources) == 2

        # Check we have both sources
        source_names = {s.source for s in report.sources}
        assert "open-meteo" in source_names
        assert "mosmix" in source_names

    def test_source_metrics(self, db_with_data):
        """Test that metrics are calculated correctly."""
        report = analyze_forecast_accuracy(db_with_data)

        for src in report.sources:
            # MAE should be positive
            assert src.overall_mae >= 0
            # RMSE should be >= MAE
            assert src.overall_rmse >= src.overall_mae
            # Count should be positive
            assert src.total_count > 0

        # Open-meteo has positive bias (overforecast)
        om = next(s for s in report.sources if s.source == "open-meteo")
        assert om.overall_bias > 0

        # MOSMIX has negative bias (underforecast)
        mosmix = next(s for s in report.sources if s.source == "mosmix")
        assert mosmix.overall_bias < 0

    def test_horizon_buckets(self, db_with_data):
        """Test horizon bucket breakdown."""
        report = analyze_forecast_accuracy(db_with_data)

        for src in report.sources:
            assert len(src.by_horizon) == 6  # All 6 buckets
            # At least one bucket should have data
            assert any(h.count > 0 for h in src.by_horizon)

    def test_source_filter(self, db_with_data):
        """Test filtering by source."""
        report = analyze_forecast_accuracy(db_with_data, source_filter="open-meteo")

        assert len(report.sources) == 1
        assert report.sources[0].source == "open-meteo"

    def test_days_filter(self, db_with_data):
        """Test filtering by days."""
        # With days=0, should get no results (data is from fixed date)
        report = analyze_forecast_accuracy(db_with_data, days=0)
        # Should still run without error
        assert report is not None

    def test_correlation_calculated(self, db_with_data):
        """Test that correlation is calculated when multiple sources exist."""
        report = analyze_forecast_accuracy(db_with_data)

        # Should have correlation between open-meteo and mosmix
        assert len(report.correlations) == 1
        corr = report.correlations[0]
        assert {corr.source_a, corr.source_b} == {"open-meteo", "mosmix"}
        # Allow small floating point error
        assert -1.01 <= corr.pearson_r <= 1.01
        assert corr.common_points > 0


class TestFormatAccuracyReport:
    """Tests for report formatting."""

    def test_format_empty_report(self):
        """Test formatting empty report."""
        report = AccuracyReport(
            sources=[],
            correlations=[],
            analysis_start=0,
            analysis_end=0,
            total_forecasts=0,
            matched_forecasts=0,
        )
        output = format_accuracy_report(report)
        assert "Keine auswertbaren Daten" in output

    def test_format_with_data(self):
        """Test formatting report with data."""
        report = AccuracyReport(
            sources=[
                SourceMetrics(
                    source="open-meteo",
                    total_count=100,
                    overall_mae=50.0,
                    overall_rmse=65.0,
                    overall_bias=10.0,
                    by_horizon=[
                        HorizonMetrics("0-1h", 10, 30.0, 40.0, 5.0),
                        HorizonMetrics("1-6h", 20, 40.0, 50.0, 8.0),
                        HorizonMetrics("6-24h", 30, 50.0, 60.0, 10.0),
                        HorizonMetrics("24-48h", 25, 55.0, 70.0, 12.0),
                        HorizonMetrics("48-72h", 15, 60.0, 75.0, 15.0),
                        HorizonMetrics(">72h", 0, 0.0, 0.0, 0.0),
                    ],
                )
            ],
            correlations=[],
            analysis_start=1704067200,
            analysis_end=1704153600,
            total_forecasts=150,
            matched_forecasts=100,
        )
        output = format_accuracy_report(report)

        assert "Forecast Accuracy Report" in output
        assert "open-meteo" in output
        assert "50.0" in output  # MAE
        assert "65.0" in output  # RMSE

    def test_format_with_correlation(self):
        """Test formatting report with correlation data."""
        from pvforecast.forecast_accuracy import CorrelationResult

        report = AccuracyReport(
            sources=[
                SourceMetrics(
                    source="open-meteo",
                    total_count=100,
                    overall_mae=50.0,
                    overall_rmse=65.0,
                    overall_bias=10.0,
                    by_horizon=[HorizonMetrics(f"bucket{i}", 10, 40.0, 50.0, 5.0) for i in range(6)],
                ),
                SourceMetrics(
                    source="mosmix",
                    total_count=100,
                    overall_mae=45.0,
                    overall_rmse=60.0,
                    overall_bias=-5.0,
                    by_horizon=[HorizonMetrics(f"bucket{i}", 10, 35.0, 45.0, -3.0) for i in range(6)],
                ),
            ],
            correlations=[
                CorrelationResult(
                    source_a="open-meteo",
                    source_b="mosmix",
                    pearson_r=0.85,
                    common_points=100,
                )
            ],
            analysis_start=1704067200,
            analysis_end=1704153600,
            total_forecasts=200,
            matched_forecasts=200,
        )
        output = format_accuracy_report(report)

        assert "Fehler-Korrelation" in output
        assert "r=0.85" in output
        assert "hohe Korrelation" in output
