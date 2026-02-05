"""Tests für Dependency-Checks (XGBoost/libomp)."""

from unittest.mock import patch

import pytest

from pvforecast.validation import DependencyError


class TestXGBoostDependencyCheck:
    """Tests für XGBoost Dependency-Prüfung."""

    def test_check_xgboost_when_available(self):
        """Test: Kein Fehler wenn XGBoost verfügbar."""
        # Dieser Test läuft nur wenn XGBoost tatsächlich installiert ist
        pytest.importorskip("xgboost")

        from pvforecast.model import _check_xgboost_available

        # Sollte ohne Exception durchlaufen
        _check_xgboost_available()

    def test_check_xgboost_not_installed(self):
        """Test: Klare Fehlermeldung wenn XGBoost nicht installiert."""
        from pvforecast import model

        # Mock: XGBoost nicht verfügbar, Grund: nicht installiert
        with patch.object(model, "XGBOOST_AVAILABLE", False):
            with patch.object(model, "XGBOOST_ERROR", "not_installed"):
                with pytest.raises(DependencyError) as exc_info:
                    model._check_xgboost_available()

                error_msg = str(exc_info.value)
                assert "nicht installiert" in error_msg.lower()
                assert "pip install" in error_msg

    def test_check_xgboost_libomp_missing(self):
        """Test: Klare Fehlermeldung wenn libomp fehlt."""
        from pvforecast import model

        # Mock: XGBoost nicht verfügbar, Grund: libomp fehlt
        with patch.object(model, "XGBOOST_AVAILABLE", False):
            with patch.object(model, "XGBOOST_ERROR", "libomp_missing"):
                with pytest.raises(DependencyError) as exc_info:
                    model._check_xgboost_available()

                error_msg = str(exc_info.value)
                assert "openmp" in error_msg.lower() or "libomp" in error_msg.lower()
                assert "brew install" in error_msg  # macOS Hinweis
                assert "apt" in error_msg  # Linux Hinweis

    def test_check_xgboost_unknown_error(self):
        """Test: Generische Fehlermeldung bei unbekanntem Fehler."""
        from pvforecast import model

        with patch.object(model, "XGBOOST_AVAILABLE", False):
            with patch.object(model, "XGBOOST_ERROR", "unknown: some weird error"):
                with pytest.raises(DependencyError) as exc_info:
                    model._check_xgboost_available()

                error_msg = str(exc_info.value)
                assert "some weird error" in error_msg

    def test_create_pipeline_xgb_raises_dependency_error(self):
        """Test: _create_pipeline('xgb') wirft DependencyError wenn nicht verfügbar."""
        from pvforecast import model

        with patch.object(model, "XGBOOST_AVAILABLE", False):
            with patch.object(model, "XGBOOST_ERROR", "not_installed"):
                with pytest.raises(DependencyError):
                    model._create_pipeline("xgb")

    def test_create_pipeline_rf_works_without_xgboost(self):
        """Test: RandomForest funktioniert auch ohne XGBoost."""
        from pvforecast import model

        # Auch wenn XGBoost nicht verfügbar ist
        with patch.object(model, "XGBOOST_AVAILABLE", False):
            with patch.object(model, "XGBOOST_ERROR", "not_installed"):
                # RF sollte trotzdem funktionieren
                pipeline = model._create_pipeline("rf")
                assert pipeline is not None
                assert "RandomForestRegressor" in str(type(pipeline.named_steps["model"]))


class TestDependencyErrorInCLI:
    """Tests für DependencyError Behandlung in CLI."""

    def test_dependency_error_handler_exists(self):
        """Test: CLI hat Handler für DependencyError."""
        import inspect

        from pvforecast.cli import main
        from pvforecast.validation import DependencyError  # noqa: F401

        # Prüfe dass main() DependencyError im Source erwähnt
        source = inspect.getsource(main)
        assert "DependencyError" in source

    def test_dependency_error_message_format(self):
        """Test: DependencyError Nachricht ist benutzerfreundlich formatiert."""
        from pvforecast.validation import DependencyError

        # Erstelle eine DependencyError wie sie vom Code erzeugt wird
        error = DependencyError(
            "XGBoost benötigt OpenMP (libomp), das auf diesem System fehlt.\n"
            "\n"
            "Installation:\n"
            "  macOS:  brew install libomp\n"
        )

        msg = str(error)
        # Prüfe dass alle wichtigen Infos enthalten sind
        assert "libomp" in msg
        assert "brew install" in msg
        assert "macOS" in msg
