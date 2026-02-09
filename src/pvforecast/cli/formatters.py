"""Output formatters for pvforecast CLI."""

from __future__ import annotations

import json
import math
from zoneinfo import ZoneInfo

from pvforecast.config import Config
from pvforecast.model import EvaluationResult, Forecast

# Wetter-Emojis für Ausgabe
WEATHER_EMOJI = {
    (0, 10): "☀️",  # klar
    (10, 30): "🌤️",  # leicht bewölkt
    (30, 60): "⛅",  # teilweise bewölkt
    (60, 85): "🌥️",  # überwiegend bewölkt
    (85, 101): "☁️",  # bedeckt
}


def get_weather_emoji(cloud_cover: int) -> str:
    """Gibt Wetter-Emoji basierend auf Bewölkung zurück."""
    for (low, high), emoji in WEATHER_EMOJI.items():
        if low <= cloud_cover < high:
            return emoji
    return "☁️"


def format_duration(seconds: float) -> str:
    """Formatiert Sekunden als lesbare Dauer."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if secs == 0:
        return f"{minutes}m"
    return f"{minutes}m {secs}s"


def format_forecast_table(forecast: Forecast, config: Config) -> str:
    """Formatiert Prognose als Tabelle."""
    tz = ZoneInfo(config.timezone)
    lines = []

    lines.append("")
    lines.append(f"PV-Ertragsprognose für {config.system_name} ({config.peak_kwp} kWp)")
    lines.append(f"Erstellt: {forecast.generated_at.astimezone(tz).strftime('%d.%m.%Y %H:%M')}")
    lines.append("")
    lines.append("═" * 60)
    lines.append("Zusammenfassung")
    lines.append("─" * 60)

    # Tages-Summen berechnen
    daily_kwh: dict[str, float] = {}
    for h in forecast.hourly:
        day_key = h.timestamp.astimezone(tz).strftime("%d.%m.")
        daily_kwh[day_key] = daily_kwh.get(day_key, 0) + h.production_w / 1000

    for day, kwh in daily_kwh.items():
        lines.append(f"  {day}:  {kwh:>6.1f} kWh")

    lines.append("  " + "─" * 20)
    lines.append(f"  Gesamt:  {forecast.total_kwh:>6.1f} kWh")
    lines.append("")
    lines.append("═" * 60)
    lines.append("Stundenwerte")
    lines.append("─" * 60)
    lines.append("  Zeit           Ertrag   Wetter")
    lines.append("  " + "─" * 35)

    for h in forecast.hourly:
        local_time = h.timestamp.astimezone(tz)
        time_str = local_time.strftime("%d.%m. %H:%M")
        emoji = get_weather_emoji(h.cloud_cover_pct)

        # Nur Stunden mit Produktion anzeigen (oder Tagesstunden)
        if h.production_w > 0 or 6 <= local_time.hour <= 20:
            lines.append(f"  {time_str}   {h.production_w:>5} W   {emoji}")

    lines.append("")
    return "\n".join(lines)


def format_forecast_json(forecast: Forecast) -> str:
    """Formatiert Prognose als JSON."""
    data = {
        "generated_at": forecast.generated_at.isoformat(),
        "total_kwh": forecast.total_kwh,
        "model_version": forecast.model_version,
        "hourly": [
            {
                "timestamp": h.timestamp.isoformat(),
                "production_w": h.production_w,
                "ghi_wm2": h.ghi_wm2,
                "cloud_cover_pct": h.cloud_cover_pct,
            }
            for h in forecast.hourly
        ],
    }
    return json.dumps(data, indent=2)


def print_evaluation_result(result: EvaluationResult) -> None:
    """Formatiert und gibt EvaluationResult aus."""
    print(f"📊 Backtesting für {result.year}")
    print("=" * 50)
    print(f"📈 Datenpunkte: {result.data_points:,}")

    print()
    print("📉 Gesamtmetriken:")
    print(f"   MAE:  {result.mae:.0f} W")
    print(f"   RMSE: {result.rmse:.0f} W")
    print(f"   R²:   {result.r2:.3f}")
    print(f"   MAPE: {result.mape:.1f}% (nur Stunden > 100W)")

    # Skill Score vs Persistence
    if result.skill_score is not None and result.mae_persistence is not None:
        print()
        print("🎯 Skill Score (vs. Persistence):")
        # Berechne ML MAE aus Skill Score für Anzeige
        ml_mae = result.mae_persistence * (1 - result.skill_score / 100)
        print(f"   ML-Modell MAE:      {ml_mae:.0f} W")
        print(f"   Persistence MAE:    {result.mae_persistence:.0f} W")
        if result.skill_score > 0:
            print(f"   Skill Score:        +{result.skill_score:.1f}% (ML ist besser)")
        else:
            print(f"   Skill Score:        {result.skill_score:.1f}% (Persistence ist besser)")

    # Performance nach Wetterbedingungen
    print()
    print("🌤️  Performance nach Wetter:")
    for wb in result.weather_breakdown:
        print(f"   {wb.label:22} MAE {wb.mae:5.0f}W, MAPE {wb.mape:5.1f}%")
    print()

    # Jahresübersicht
    print(f"☀️  Jahresertrag {result.year}:")
    print(f"   Tatsächlich:  {result.total_actual_kwh:,.0f} kWh")
    print(f"   Vorhersage:   {result.total_predicted_kwh:,.0f} kWh")
    print(f"   Abweichung:   {result.total_error_kwh:+,.0f} kWh ({result.total_error_pct:+.1f}%)")
    print()

    # Monatsübersicht
    print("📅 Monatliche Abweichung:")
    month_names = [
        "Jan",
        "Feb",
        "Mär",
        "Apr",
        "Mai",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Okt",
        "Nov",
        "Dez",
    ]

    for month in range(1, 13):
        month_data = result.monthly[result.monthly["month"] == month]
        if len(month_data) > 0:
            err = month_data.iloc[0]["error_pct"]
            if math.isnan(err):
                print(f"   {month_names[month - 1]}: keine Daten")
            else:
                bar = "█" * min(10, int(abs(err) / 2))
                sign = "+" if err > 0 else "-" if err < 0 else " "
                print(f"   {month_names[month - 1]}: {sign}{abs(err):5.1f}% {bar}")
        else:
            print(f"   {month_names[month - 1]}: keine Daten")
