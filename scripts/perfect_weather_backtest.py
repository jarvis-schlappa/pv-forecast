#!/usr/bin/env python3
"""
Perfect Weather Backtest

Testet das PV-Modell mit HOSTRADA-Messdaten statt Forecast-Daten.
Zeigt die theoretische Untergrenze des MAPE bei perfekter Wettervorhersage.
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_percentage_error

# pvforecast imports
from pvforecast.model import prepare_features, load_model
from pvforecast.config import load_config

# Paths
DB_PATH = Path.home() / ".local/share/pvforecast/data.db"
MODEL_PATH = Path.home() / ".local/share/pvforecast/model.pkl"


def load_data() -> pd.DataFrame:
    """Lädt HOSTRADA-Wetter und PV-Produktionsdaten (wie beim Training)."""
    conn = sqlite3.connect(DB_PATH)
    
    # Exakt gleiche Query wie load_training_data() in model.py
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
        ORDER BY p.timestamp
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"✓ Daten geladen: {len(df):,} Einträge (non-curtailed)")
    return df


def calculate_mape(y_true: np.ndarray, y_pred: np.ndarray, threshold: float = 100.0) -> float:
    """Berechnet MAPE, ignoriert Werte unter threshold (wie Training: >100W)."""
    mask = y_true > threshold
    if mask.sum() == 0:
        return float('nan')
    
    errors = np.abs(y_true[mask] - y_pred[mask]) / y_true[mask]
    return float(np.mean(errors) * 100)


def main():
    print("=" * 60)
    print("Perfect Weather Backtest")
    print("=" * 60)
    print()
    
    # Config laden
    config = load_config()
    lat = config.latitude
    lon = config.longitude
    peak_kwp = config.peak_kwp
    print(f"✓ Config: {lat:.2f}°N, {lon:.2f}°E, {peak_kwp} kWp")
    print()
    
    # Daten laden
    print("Lade Daten...")
    data = load_data()
    print()
    
    # Features erstellen
    print("Erstelle Features aus HOSTRADA-Messdaten...")
    X = prepare_features(data, lat, lon, peak_kwp, mode="train")
    y = data["production_w"].values
    print(f"✓ Features: {X.shape[1]} Spalten")
    print()
    
    # Model laden
    print("Lade trainiertes Modell...")
    model, metrics = load_model(MODEL_PATH)
    print(f"✓ Modell geladen")
    if metrics:
        print(f"  Training MAPE: {metrics.get('mape', 'N/A'):.1f}%")
    print()
    
    # Predict
    print("Berechne Vorhersagen...")
    y_pred = model.predict(X)
    y_pred = np.clip(y_pred, 0, None)  # Keine negativen Werte
    print(f"✓ {len(y_pred):,} Vorhersagen")
    print()
    
    # Metriken
    print("=" * 60)
    print("Ergebnisse")
    print("=" * 60)
    
    mape_perfect = calculate_mape(y, y_pred)
    mae = np.mean(np.abs(y - y_pred))
    rmse = np.sqrt(np.mean((y - y_pred) ** 2))
    
    print(f"  MAPE (perfektes Wetter):  {mape_perfect:.1f}%")
    print(f"  MAE:                      {mae:.0f} W")
    print(f"  RMSE:                     {rmse:.0f} W")
    print()
    
    # Vergleich
    if metrics and 'mape' in metrics:
        forecast_mape = metrics['mape']
        gap = forecast_mape - mape_perfect
        print("Vergleich:")
        print(f"  MAPE mit Forecast-Daten:  {forecast_mape:.1f}%")
        print(f"  MAPE mit perfektem Wetter: {mape_perfect:.1f}%")
        print(f"  ────────────────────────────")
        print(f"  Forecast-Gap:             {gap:.1f}%")
        print(f"  → {gap:.1f}% Verbesserung möglich durch bessere Wettervorhersage")
    
    print()


if __name__ == "__main__":
    main()
