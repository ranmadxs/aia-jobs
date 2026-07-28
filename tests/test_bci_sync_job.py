"""Tests unitarios para sync_job y api_server del filtro BCI."""

from unittest.mock import patch, MagicMock

from listener.bci.sync_job import sync_historical_cartolas, _JOB_STATUS, _needs_transform, _filter_by_months


class TestSyncJobStatus:
    def test_status_initially_not_running(self):
        assert _JOB_STATUS["running"] is False

    def test_status_has_keys(self):
        assert "running" in _JOB_STATUS
        assert "current_job" in _JOB_STATUS
        assert "last_run" in _JOB_STATUS
        assert "last_result" in _JOB_STATUS

    def test_status_after_sync_no_mongo(self):
        with patch("listener.bci.sync_job._get_email_collection", return_value=None):
            result = sync_historical_cartolas()
        assert "error" in result
        assert result["error"] == "email collection unavailable"


class TestFilterByMonths:
    def test_none_returns_all(self):
        from listener.bci.sync_job import _filter_by_months
        docs = [{"fecha_remitente": None}, {"fecha_remitente": "2025-01-01"}]
        assert _filter_by_months(docs, None) == docs

    def test_zero_returns_all(self):
        from listener.bci.sync_job import _filter_by_months
        docs = [{"fecha_remitente": "2025-01-01"}]
        assert _filter_by_months(docs, 0) == docs


class TestNeedsTransform:
    def test_untransformed_returns_true(self):
        assert _needs_transform({"kind": "bci_cartola"}) is True

    def test_already_transformed_returns_false(self):
        doc = {
            "kind": "bci_cartola",
            "bci_cartola_transformed_at": "2026-07-28T00:00:00+00:00",
        }
        assert _needs_transform(doc) is False

    def test_no_kind_field(self):
        assert _needs_transform({"subject": "test"}) is True


class TestApiServerImport:
    def test_start_api_server_exists(self):
        from listener.bci.api_server import start_api_server
        assert callable(start_api_server)

    def test_openapi_spec_has_required_paths(self):
        from listener.bci.api_server import _OPENAPI_SPEC
        assert "/api/jobs/sync-historical-bci" in _OPENAPI_SPEC["paths"]
        assert "/api/jobs/status" in _OPENAPI_SPEC["paths"]

    def test_openapi_spec_has_swagger_ui_path(self):
        from listener.bci.api_server import _OPENAPI_SPEC
        assert "/docs" in _OPENAPI_SPEC["paths"]
        assert "/openapi.json" in _OPENAPI_SPEC["paths"]

    def test_openapi_info(self):
        from listener.bci.api_server import _OPENAPI_SPEC
        assert _OPENAPI_SPEC["info"]["title"] == "aia-jobs API"
        assert _OPENAPI_SPEC["info"]["version"] == "0.3.0"