"""Tests für das Konfidenz-Modul."""

from pathlib import Path

import pytest

from pvforecast.confidence import (
    ConfidenceResult,
    classify_weather,
    compute_error_bands,
    parse_observation_log,
)


@pytest.fixture
def sample_log(tmp_path: Path) -> Path:
    """Erstellt ein minimales Observation Log für Tests."""
    log = tmp_path / "observation-log.md"
    log.write_text(
        """# PV-Forecast Observation Log

---

## 2026-02-15

- **Ertrag:** 22.41 kWh
- **Modell-Prognose:** 24.7 kWh
- **Abweichung:** -9%

## 2026-02-16

- **Ertrag:** 5.83 kWh
- **Modell-Prognose:** 5.6 kWh
- **Abweichung:** 4%

## 2026-02-17

- **Ertrag:** 8.65 kWh
- **Modell-Prognose:** 6.4 kWh
- **Abweichung:** 35%

## 2026-02-22

- **Ertrag:** 2.33 kWh
- **Modell-Prognose:** 0.7 kWh
- **Abweichung:** 233%
""",
        encoding="utf-8",
    )
    return log


class TestParseObservationLog:
    def test_parse_entries(self, sample_log: Path):
        entries = parse_observation_log(sample_log)
        assert len(entries) == 4
        assert entries[0]["date"] == "2026-02-15"
        assert entries[0]["actual_kwh"] == 22.41
        assert entries[0]["forecast_kwh"] == 24.7

    def test_relative_error(self, sample_log: Path):
        entries = parse_observation_log(sample_log)
        # (22.41 - 24.7) / 24.7 ≈ -0.0927
        assert abs(entries[0]["rel_error"] - (-0.0927)) < 0.01

    def test_empty_file(self, tmp_path: Path):
        log = tmp_path / "empty.md"
        log.write_text("# Empty Log\n")
        entries = parse_observation_log(log)
        assert entries == []

    def test_nonexistent_file(self, tmp_path: Path):
        log = tmp_path / "nonexistent.md"
        entries = parse_observation_log(log)
        assert entries == []

    def test_skips_entries_without_forecast(self, tmp_path: Path):
        """Einträge ohne Modell-Prognose werden übersprungen."""
        log = tmp_path / "partial.md"
        log.write_text(
            """# Log

## 2026-02-12

- **Ertrag:** 3.93 kWh
- **Hinweis:** Modell-Prognose nicht verfügbar
""",
            encoding="utf-8",
        )
        entries = parse_observation_log(log)
        assert entries == []


class TestClassifyWeather:
    def test_clear(self):
        name, emoji = classify_weather(10.0)
        assert name == "klar"
        assert emoji == "☀️"

    def test_partly_cloudy(self):
        name, emoji = classify_weather(50.0)
        assert name == "teilbewölkt"
        assert emoji == "⛅"

    def test_overcast(self):
        name, emoji = classify_weather(85.0)
        assert name == "bedeckt"
        assert emoji == "☁️"

    def test_boundary_clear_partly(self):
        name, _ = classify_weather(30.0)
        assert name == "teilbewölkt"  # 30% ist Grenze → teilbewölkt

    def test_boundary_partly_overcast(self):
        name, _ = classify_weather(70.0)
        assert name == "bedeckt"  # 70% ist Grenze → bedeckt


class TestComputeErrorBands:
    def test_fallback_without_log(self, tmp_path: Path):
        """Ohne Observation Log → Fallback-Bänder."""
        log = tmp_path / "nonexistent.md"
        db = tmp_path / "nonexistent.db"
        bands = compute_error_bands(log, db)
        assert "klar" in bands
        assert "teilbewölkt" in bands
        assert "bedeckt" in bands
        # Fallback: N=0
        assert bands["klar"].n_days == 0


class TestConfidenceResult:
    def test_range_str(self):
        conf = ConfidenceResult(
            forecast_kwh=28.2,
            p10_kwh=23.0,
            p90_kwh=33.0,
            weather_class="klar",
            weather_emoji="☀️",
            uncertainty="gering",
            uncertainty_emoji="🟢",
            n_days=10,
            avg_cloud_cover=15.0,
        )
        assert conf.range_str == "23–33 kWh"

    def test_p10_less_than_p90(self):
        """P10 sollte immer <= P90 sein."""
        conf = ConfidenceResult(
            forecast_kwh=10.0,
            p10_kwh=8.0,
            p90_kwh=12.0,
            weather_class="bedeckt",
            weather_emoji="☁️",
            uncertainty="mittel",
            uncertainty_emoji="🟡",
            n_days=5,
            avg_cloud_cover=85.0,
        )
        assert conf.p10_kwh <= conf.p90_kwh
