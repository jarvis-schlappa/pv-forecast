"""Tests für das Doctor-Modul."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from pvforecast.doctor import CheckResult, Doctor


class TestCheckResult:
    """Tests für CheckResult Dataclass."""

    def test_creation_ok(self):
        """Test: OK-Status."""
        result = CheckResult(
            name="Test",
            status="ok",
            message="Alles gut",
        )
        assert result.name == "Test"
        assert result.status == "ok"
        assert result.detail is None

    def test_creation_with_detail(self):
        """Test: Mit Detail."""
        result = CheckResult(
            name="Test",
            status="warning",
            message="Warnung",
            detail="Mehr Info",
        )
        assert result.detail == "Mehr Info"


class TestDoctorChecks:
    """Tests für einzelne Doctor-Checks."""

    def test_check_python(self):
        """Test: Python-Version wird geprüft."""
        outputs = []
        doctor = Doctor(output_func=lambda x: outputs.append(x))
        doctor._check_python()

        assert len(doctor.results) == 1
        result = doctor.results[0]
        assert result.name == "Python"
        assert result.status == "ok"  # Wir laufen auf Python 3.9+

    def test_check_pvforecast(self):
        """Test: pvforecast Version wird angezeigt."""
        doctor = Doctor(output_func=lambda x: None)
        doctor._check_pvforecast()

        assert len(doctor.results) == 1
        result = doctor.results[0]
        assert result.name == "pvforecast"
        assert result.status == "ok"

    @patch("pvforecast.doctor.get_config_path")
    def test_check_config_missing(self, mock_path):
        """Test: Fehlende Config wird erkannt."""
        mock_path.return_value = Path("/nonexistent/config.yaml")

        doctor = Doctor(output_func=lambda x: None)
        doctor._check_config()

        assert len(doctor.results) == 1
        result = doctor.results[0]
        assert result.name == "Config"
        assert result.status == "warning"
        assert "Nicht vorhanden" in result.message

    def test_check_config_exists(self):
        """Test: Vorhandene Config wird erkannt."""
        from pvforecast import doctor as doctor_module

        mock_config = MagicMock()
        mock_config.system_name = "Test PV"
        mock_config.peak_kwp = 9.92
        mock_config.latitude = 51.83
        mock_config.longitude = 7.28

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch.object(doctor_module, "get_config_path", return_value=mock_path):
            with patch.object(doctor_module, "load_config", return_value=mock_config):
                doc = Doctor(output_func=lambda x: None)
                doc._check_config()

        # Config + Standort
        assert len(doc.results) == 2
        assert doc.results[0].status == "ok"
        assert doc.results[1].name == "Standort"

    def test_check_xgboost_installed(self):
        """Test: XGBoost installiert."""
        with patch.dict("sys.modules", {"xgboost": MagicMock(__version__="2.0.0")}):
            doctor = Doctor(output_func=lambda x: None)
            doctor._check_xgboost()

        # Mindestens XGBoost-Check
        xgb_results = [r for r in doctor.results if r.name == "XGBoost"]
        assert len(xgb_results) == 1
        assert xgb_results[0].status == "ok"

    def test_check_xgboost_not_installed(self):
        """Test: XGBoost nicht installiert."""
        import sys

        # Temporär xgboost aus sys.modules entfernen
        original = sys.modules.get("xgboost")
        sys.modules["xgboost"] = None  # Simuliert nicht installiert

        doctor = Doctor(output_func=lambda x: None)

        # Mock den Import
        def mock_import(name, *args, **kwargs):
            if name == "xgboost":
                raise ImportError("No module named 'xgboost'")
            return original_import(name, *args, **kwargs)

        import builtins

        original_import = builtins.__import__

        with patch.object(builtins, "__import__", mock_import):
            doctor._check_xgboost()

        # Restore
        if original:
            sys.modules["xgboost"] = original
        elif "xgboost" in sys.modules:
            del sys.modules["xgboost"]

        xgb_results = [r for r in doctor.results if r.name == "XGBoost"]
        assert len(xgb_results) == 1
        assert xgb_results[0].status == "warning"

    def test_check_network_ok(self):
        """Test: Netzwerk OK."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch.object(httpx, "Client", return_value=mock_client):
            doctor = Doctor(output_func=lambda x: None)
            doctor._check_network()

        result = doctor.results[0]
        assert result.name == "Open-Meteo"
        assert result.status == "ok"

    def test_check_network_error(self):
        """Test: Netzwerk-Fehler."""
        import httpx

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError("Connection failed")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch.object(httpx, "Client", return_value=mock_client):
            doctor = Doctor(output_func=lambda x: None)
            doctor._check_network()

        result = doctor.results[0]
        assert result.name == "Open-Meteo"
        assert result.status == "warning"


class TestDoctorExitCode:
    """Tests für Exit-Code Logik."""

    def test_exit_code_all_ok(self):
        """Test: Exit 0 wenn alles OK."""
        doctor = Doctor(output_func=lambda x: None)
        doctor.results = [
            CheckResult("A", "ok", "OK"),
            CheckResult("B", "ok", "OK"),
        ]
        assert doctor._get_exit_code() == 0

    def test_exit_code_with_warning(self):
        """Test: Exit 1 bei Warnungen."""
        doctor = Doctor(output_func=lambda x: None)
        doctor.results = [
            CheckResult("A", "ok", "OK"),
            CheckResult("B", "warning", "Warnung"),
        ]
        assert doctor._get_exit_code() == 1

    def test_exit_code_with_error(self):
        """Test: Exit 2 bei Fehlern."""
        doctor = Doctor(output_func=lambda x: None)
        doctor.results = [
            CheckResult("A", "ok", "OK"),
            CheckResult("B", "error", "Fehler"),
        ]
        assert doctor._get_exit_code() == 2

    def test_exit_code_error_over_warning(self):
        """Test: Fehler hat Priorität über Warnung."""
        doctor = Doctor(output_func=lambda x: None)
        doctor.results = [
            CheckResult("A", "warning", "Warnung"),
            CheckResult("B", "error", "Fehler"),
        ]
        assert doctor._get_exit_code() == 2


class TestDoctorOutput:
    """Tests für Ausgabe."""

    def test_print_header(self):
        """Test: Header wird ausgegeben."""
        outputs = []
        doctor = Doctor(output_func=lambda x: outputs.append(x))
        doctor._print_header()

        assert any("Systemcheck" in str(o) for o in outputs)

    def test_print_results(self):
        """Test: Ergebnisse werden ausgegeben."""
        outputs = []
        doctor = Doctor(output_func=lambda x: outputs.append(x))
        doctor.results = [
            CheckResult("Test", "ok", "Alles gut"),
        ]
        doctor._print_results()

        assert any("Test" in str(o) for o in outputs)
        assert any("Alles gut" in str(o) for o in outputs)

    def test_print_results_with_detail(self):
        """Test: Details werden ausgegeben."""
        outputs = []
        doctor = Doctor(output_func=lambda x: outputs.append(x))
        doctor.results = [
            CheckResult("Test", "warning", "Problem", detail="Mehr Info"),
        ]
        doctor._print_results()

        assert any("Mehr Info" in str(o) for o in outputs)


class TestDoctorRun:
    """Tests für run()."""

    @patch.object(Doctor, "_check_python")
    @patch.object(Doctor, "_check_pvforecast")
    @patch.object(Doctor, "_check_config")
    @patch.object(Doctor, "_check_database")
    @patch.object(Doctor, "_check_model")
    @patch.object(Doctor, "_check_xgboost")
    @patch.object(Doctor, "_check_network")
    def test_run_calls_all_checks(self, *mocks):
        """Test: run() ruft alle Checks auf."""
        doctor = Doctor(output_func=lambda x: None)
        doctor.run()

        for mock in mocks:
            mock.assert_called_once()

    def test_run_returns_exit_code(self):
        """Test: run() gibt Exit-Code zurück."""
        with patch.object(Doctor, "_check_python"):
            with patch.object(Doctor, "_check_pvforecast"):
                with patch.object(Doctor, "_check_config"):
                    with patch.object(Doctor, "_check_database"):
                        with patch.object(Doctor, "_check_model"):
                            with patch.object(Doctor, "_check_xgboost"):
                                with patch.object(Doctor, "_check_network"):
                                    doctor = Doctor(output_func=lambda x: None)
                                    result = doctor.run()
                                    assert isinstance(result, int)
