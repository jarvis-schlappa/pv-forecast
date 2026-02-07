"""
PV-Forecast: Ertragsprognose für Photovoltaik-Anlagen.

Verwendet historische PV-Daten und Wettervorhersagen für 48h-Prognosen.
"""

# urllib3 v2 Warnung auf macOS unterdrücken (LibreSSL statt OpenSSL)
import warnings

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

__version__ = "0.2.2-dev"
