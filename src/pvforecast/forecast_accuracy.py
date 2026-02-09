"""Forecast accuracy analysis module.

Compares forecast_history against weather_history (HOSTRADA) to evaluate
forecast quality by source and horizon.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pvforecast.db import Database


@dataclass
class HorizonMetrics:
    """Metrics for a specific forecast horizon bucket."""

    horizon_label: str  # e.g., "0-1h", "1-6h"
    count: int
    mae: float  # Mean Absolute Error (W/m²)
    rmse: float  # Root Mean Square Error (W/m²)
    bias: float  # Mean error (positive = overforecast)


@dataclass
class SourceMetrics:
    """Aggregated metrics for one forecast source."""

    source: str
    total_count: int
    overall_mae: float
    overall_rmse: float
    overall_bias: float
    by_horizon: list[HorizonMetrics]


@dataclass
class CorrelationResult:
    """Correlation between two forecast sources' errors."""

    source_a: str
    source_b: str
    pearson_r: float
    common_points: int


@dataclass
class AccuracyReport:
    """Complete forecast accuracy report."""

    sources: list[SourceMetrics]
    correlations: list[CorrelationResult]
    analysis_start: int  # Unix timestamp
    analysis_end: int
    total_forecasts: int
    matched_forecasts: int  # How many had ground truth


# Horizon buckets in hours: (min_hours, max_hours, label)
HORIZON_BUCKETS = [
    (0, 1, "0-1h"),
    (1, 6, "1-6h"),
    (6, 24, "6-24h"),
    (24, 48, "24-48h"),
    (48, 72, "48-72h"),
    (72, float("inf"), ">72h"),
]


def get_horizon_bucket(horizon_hours: float) -> str:
    """Map horizon in hours to bucket label."""
    for min_h, max_h, label in HORIZON_BUCKETS:
        if min_h <= horizon_hours < max_h:
            return label
    return ">72h"


def analyze_forecast_accuracy(
    db: Database,
    days: int | None = None,
    source_filter: str | None = None,
) -> AccuracyReport:
    """
    Analyze forecast accuracy by comparing forecasts to ground truth.

    Args:
        db: Database instance
        days: Limit analysis to last N days (None = all available)
        source_filter: Only analyze this source (None = all sources)

    Returns:
        AccuracyReport with per-source and per-horizon metrics
    """
    import time

    with db.connect() as conn:
        # Build time constraint
        time_constraint = ""
        params: list = []
        if days:
            cutoff = int(time.time()) - (days * 86400)
            time_constraint = "AND f.target_time >= ?"
            params.append(cutoff)

        # Source filter
        source_constraint = ""
        if source_filter:
            source_constraint = "AND f.source = ?"
            params.append(source_filter)

        # Main query: join forecasts with ground truth weather
        query = f"""
            SELECT
                f.source,
                f.issued_at,
                f.target_time,
                f.ghi_wm2 as forecast_ghi,
                w.ghi_wm2 as actual_ghi,
                (f.target_time - f.issued_at) / 3600.0 as horizon_hours
            FROM forecast_history f
            INNER JOIN weather_history w ON f.target_time = w.timestamp
            WHERE f.ghi_wm2 IS NOT NULL
              AND w.ghi_wm2 IS NOT NULL
              {time_constraint}
              {source_constraint}
            ORDER BY f.source, f.target_time
        """

        rows = conn.execute(query, params).fetchall()

        # Get total forecast count for stats
        total_count = conn.execute(
            f"SELECT COUNT(*) FROM forecast_history WHERE 1=1 {time_constraint}",
            params[:1] if days else [],
        ).fetchone()[0]

        # Get time range
        range_query = "SELECT MIN(target_time), MAX(target_time) FROM forecast_history"
        range_result = conn.execute(range_query).fetchone()
        analysis_start = range_result[0] or 0
        analysis_end = range_result[1] or 0

    if not rows:
        return AccuracyReport(
            sources=[],
            correlations=[],
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            total_forecasts=total_count,
            matched_forecasts=0,
        )

    # Group by source
    source_data: dict[str, list[dict]] = {}
    for row in rows:
        source = row["source"]
        if source not in source_data:
            source_data[source] = []
        source_data[source].append(
            {
                "target_time": row["target_time"],
                "forecast_ghi": row["forecast_ghi"],
                "actual_ghi": row["actual_ghi"],
                "horizon_hours": row["horizon_hours"],
                "error": row["forecast_ghi"] - row["actual_ghi"],
            }
        )

    # Calculate metrics per source
    source_metrics: list[SourceMetrics] = []
    for source, data in source_data.items():
        errors = [d["error"] for d in data]
        abs_errors = [abs(e) for e in errors]
        sq_errors = [e**2 for e in errors]

        overall_mae = sum(abs_errors) / len(abs_errors)
        overall_rmse = math.sqrt(sum(sq_errors) / len(sq_errors))
        overall_bias = sum(errors) / len(errors)

        # Group by horizon
        horizon_data: dict[str, list[float]] = {label: [] for _, _, label in HORIZON_BUCKETS}
        for d in data:
            bucket = get_horizon_bucket(d["horizon_hours"])
            horizon_data[bucket].append(d["error"])

        horizon_metrics: list[HorizonMetrics] = []
        for _, _, label in HORIZON_BUCKETS:
            bucket_errors = horizon_data[label]
            if bucket_errors:
                abs_err = [abs(e) for e in bucket_errors]
                sq_err = [e**2 for e in bucket_errors]
                horizon_metrics.append(
                    HorizonMetrics(
                        horizon_label=label,
                        count=len(bucket_errors),
                        mae=sum(abs_err) / len(abs_err),
                        rmse=math.sqrt(sum(sq_err) / len(sq_err)),
                        bias=sum(bucket_errors) / len(bucket_errors),
                    )
                )
            else:
                horizon_metrics.append(
                    HorizonMetrics(
                        horizon_label=label,
                        count=0,
                        mae=0.0,
                        rmse=0.0,
                        bias=0.0,
                    )
                )

        source_metrics.append(
            SourceMetrics(
                source=source,
                total_count=len(data),
                overall_mae=overall_mae,
                overall_rmse=overall_rmse,
                overall_bias=overall_bias,
                by_horizon=horizon_metrics,
            )
        )

    # Calculate correlations between sources
    correlations: list[CorrelationResult] = []
    sources = list(source_data.keys())
    for i, source_a in enumerate(sources):
        for source_b in sources[i + 1 :]:
            corr = _calculate_error_correlation(
                source_a, source_b, source_data[source_a], source_data[source_b]
            )
            if corr:
                correlations.append(corr)

    return AccuracyReport(
        sources=source_metrics,
        correlations=correlations,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        total_forecasts=total_count,
        matched_forecasts=len(rows),
    )


def _calculate_error_correlation(
    source_a_name: str,
    source_b_name: str,
    data_a: list[dict],
    data_b: list[dict],
) -> CorrelationResult | None:
    """Calculate Pearson correlation of errors between two sources."""
    # Build lookup by target_time
    errors_a = {d["target_time"]: d["error"] for d in data_a}
    errors_b = {d["target_time"]: d["error"] for d in data_b}

    # Find common timestamps
    common_times = set(errors_a.keys()) & set(errors_b.keys())
    if len(common_times) < 10:
        return None  # Not enough data for meaningful correlation

    # Extract paired errors
    paired_a = [errors_a[t] for t in common_times]
    paired_b = [errors_b[t] for t in common_times]

    # Pearson correlation
    n = len(paired_a)
    mean_a = sum(paired_a) / n
    mean_b = sum(paired_b) / n

    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(paired_a, paired_b)) / n
    std_a = math.sqrt(sum((a - mean_a) ** 2 for a in paired_a) / n)
    std_b = math.sqrt(sum((b - mean_b) ** 2 for b in paired_b) / n)

    if std_a == 0 or std_b == 0:
        return None

    pearson_r = cov / (std_a * std_b)

    return CorrelationResult(
        source_a=source_a_name,
        source_b=source_b_name,
        pearson_r=pearson_r,
        common_points=n,
    )


def format_accuracy_report(report: AccuracyReport) -> str:
    """Format accuracy report as human-readable text."""
    from datetime import datetime

    lines = []
    lines.append("Forecast Accuracy Report")
    lines.append("=" * 60)
    lines.append("")

    # Time range
    if report.analysis_start and report.analysis_end:
        start = datetime.fromtimestamp(report.analysis_start).strftime("%Y-%m-%d")
        end = datetime.fromtimestamp(report.analysis_end).strftime("%Y-%m-%d")
        lines.append(f"📅 Zeitraum: {start} bis {end}")

    lines.append(
        f"📊 Forecasts: {report.total_forecasts} gesamt, "
        f"{report.matched_forecasts} mit Ground Truth"
    )
    lines.append("")

    if not report.sources:
        lines.append("⚠️  Keine auswertbaren Daten gefunden.")
        lines.append("   Mögliche Ursachen:")
        lines.append("   - Noch keine Forecasts gesammelt")
        lines.append("   - Keine überlappenden Zeitstempel mit weather_history")
        return "\n".join(lines)

    # GHI comparison per source
    lines.append("📊 GHI-Vergleich (Forecast vs. HOSTRADA)")
    lines.append("-" * 60)

    # Header
    lines.append(f"{'Quelle':<12} | {'N':>6} | {'MAE':>8} | {'RMSE':>8} | {'Bias':>8}")
    lines.append(f"{'':<12} | {'':<6} | {'(W/m²)':>8} | {'(W/m²)':>8} | {'(W/m²)':>8}")
    lines.append("-" * 60)

    for src in report.sources:
        bias_sign = "+" if src.overall_bias >= 0 else ""
        lines.append(
            f"{src.source:<12} | {src.total_count:>6} | {src.overall_mae:>8.1f} | "
            f"{src.overall_rmse:>8.1f} | {bias_sign}{src.overall_bias:>7.1f}"
        )

    lines.append("")
    lines.append("📈 Nach Forecast-Horizont (MAE in W/m²)")
    lines.append("-" * 60)

    # Horizon table header
    horizons = [h.horizon_label for h in report.sources[0].by_horizon]
    header = f"{'Quelle':<12} |" + "|".join(f"{h:>8}" for h in horizons)
    lines.append(header)
    lines.append("-" * 60)

    for src in report.sources:
        row = f"{src.source:<12} |"
        for hm in src.by_horizon:
            if hm.count > 0:
                row += f"{hm.mae:>8.1f}"
            else:
                row += f"{'--':>8}"
            row += "|"
        lines.append(row.rstrip("|"))

    # Correlations
    if report.correlations:
        lines.append("")
        lines.append("🔗 Fehler-Korrelation zwischen Quellen")
        lines.append("-" * 60)
        for corr in report.correlations:
            interpretation = ""
            if corr.pearson_r > 0.7:
                interpretation = " (hohe Korrelation → gleiche Fehlerquellen)"
            elif corr.pearson_r < 0.3:
                interpretation = " (niedrige Korrelation → Ensemble-Potenzial)"
            lines.append(
                f"   {corr.source_a} ↔ {corr.source_b}: r={corr.pearson_r:.2f} "
                f"(n={corr.common_points}){interpretation}"
            )

    return "\n".join(lines)
