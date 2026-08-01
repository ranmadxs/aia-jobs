"""Tests unitarios para sync_job y api_server del filtro BCI."""

from unittest.mock import patch, MagicMock

from listener.bci.sync_job import (
    _JOB_STATUS,
    _filter_by_months,
    _needs_transform,
    sync_historical_cartolas,
    sync_trx,
)


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
        assert _OPENAPI_SPEC["info"]["version"] != "0.0.0"

class TestTrxKey:
    def test_same_movements_same_key(self):
        from listener.bci.sync_job import _trx_key
        m1 = {
            "fecha": "2026-07-29",
            "sucursal": "001",
            "descripcion": "测试",
            "abono": 1000,
            "cargo": 0,
            "saldo": 5000,
        }
        m2 = {
            "fecha": "2026-07-29",
            "sucursal": "001",
            "descripcion": "测试",
            "abono": 1000,
            "cargo": 0,
            "saldo": 5000,
        }
        assert _trx_key(m1) == _trx_key(m2)

    def test_different_movements_different_key(self):
        from listener.bci.sync_job import _trx_key
        m1 = {
            "fecha": "2026-07-29",
            "sucursal": "001",
            "descripcion": "测试",
            "abono": 1000,
            "cargo": 0,
            "saldo": 5000,
        }
        m2 = {
            "fecha": "2026-07-30",
            "sucursal": "001",
            "descripcion": "测试",
            "abono": 1000,
            "cargo": 0,
            "saldo": 5000,
        }
        assert _trx_key(m1) != _trx_key(m2)


class TestApiServerSyncTrx:
    def test_openapi_spec_has_sync_trx_path(self):
        from listener.bci.api_server import _OPENAPI_SPEC
        assert "/api/jobs/sync-trx" in _OPENAPI_SPEC["paths"]

    def test_sync_trx_endpoint_is_post(self):
        from listener.bci.api_server import _OPENAPI_SPEC
        path = _OPENAPI_SPEC["paths"]["/api/jobs/sync-trx"]
        assert "post" in path

    def test_sync_trx_endpoint_summary(self):
        from listener.bci.api_server import _OPENAPI_SPEC
        spec = _OPENAPI_SPEC["paths"]["/api/jobs/sync-trx"]["post"]
        assert "bci.transacciones" in spec["description"] or "Sincronizar movimientos" in spec["summary"]

    def test_handle_sync_trx_exists(self):
        from listener.bci.api_server import handle_sync_trx
        assert callable(handle_sync_trx)