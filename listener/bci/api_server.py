"""Servidor HTTP con Swagger UI y endpoints para jobs asíncronos."""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("aia-jobs.api")

API_HOST = "0.0.0.0"
API_PORT = int(os.getenv("API_PORT", "8080"))
API_BASE = "/api"

_OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "aia-jobs API",
        "description": "API para gestionar jobs y escuchar correos BCI.",
        "version": "0.3.0",
    },
    "paths": {
        f"{API_BASE}/jobs/sync-historical-bci": {
            "post": {
                "summary": "Sincronizar cartolas BCI históricas",
                "description": "Transforma correos de cartola BCI almacenados en MongoDB "
                "(email.emails) en documentos estructurados guardados en bci.cartolas. "
                "Solo procesa emails con kind=bci_cartola que aún no hayan sido transformados.",
                "operationId": "syncHistoricalBciCartolas",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "months_back": {
                                        "type": "integer",
                                        "description": "Cuántos meses hacia atrás procesar. "
                                        "0 o omitido = todos los pendientes sin filtro.",
                                        "default": 0,
                                        "minimum": 0,
                                    }
                                },
                            },
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Resumen del procesamiento",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "transformed": {"type": "integer"},
                                        "skipped": {"type": "integer"},
                                        "errors": {"type": "integer"},
                                        "total_pending": {"type": "integer"},
                                        "total_filtered": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            }
        },
        f"{API_BASE}/jobs/status": {
            "get": {
                "summary": "Estado del último job",
                "description": "Retorna el estado del job actual, si está corriendo, "
                "y el resultado del último ejecutado.",
                "operationId": "getJobStatus",
                "responses": {
                    "200": {
                        "description": "Estado del job",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "running": {"type": "boolean"},
                                        "current_job": {"type": ["string", "null"]},
                                        "last_run": {"type": ["string", "null"]},
                                        "last_result": {
                                            "type": ["object", "null"],
                                        },
                                        "total_cartolas_bci": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                },
            }
        },
        "/docs": {
            "get": {
                "summary": "Swagger UI",
                "operationId": "getSwaggerUI",
                "responses": {
                    "200": {"description": "Swagger UI HTML"},
                },
            }
        },
        "/openapi.json": {
            "get": {
                "summary": "OpenAPI spec JSON",
                "operationId": "getOpenApiSpec",
                "responses": {
                    "200": {"description": "OpenAPI spec JSON"},
                },
            }
        },
    },
}

_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>aia-jobs API</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({
  url: "/openapi.json",
  dom_id: "#swagger-ui",
  presets: [SwaggerUIBundle.presets.apis],
  layout: "BaseLayout",
});
</script>
</body>
</html>"""

# ── Thread-local para aiohttp fallback ──────────────────────────────────────
_server = None


def _build_status_total(bci_col) -> int:
    try:
        return bci_col.count_documents({}) if bci_col is not None else 0
    except Exception:
        return 0


async def handle_sync(request):
    from aiohttp import web
    try:
        data = await request.json()
    except Exception:
        data = {}
    months_back = data.get("months_back", 0) if isinstance(data, dict) else 0

    from listener.bci.sync_job import sync_historical_cartolas

    def _run():
        return sync_historical_cartolas(months_back if months_back > 0 else None)

    loop = request.app["loop"]
    try:
        result = await loop.run_in_executor(None, _run)
    except Exception as e:
        logger.exception("Error en sync_histórico BCI: %s", e)
        result = {"error": str(e), "transformed": 0, "skipped": 0, "errors": 0}
    return web.json_response(result)


async def handle_status(request):
    from aiohttp import web
    from listener.bci.sync_job import _JOB_STATUS

    from listener.bci.store import get_bci_collection
    bci_col = get_bci_collection()
    total = _build_status_total(bci_col)

    return web.json_response({
        "running": _JOB_STATUS["running"],
        "current_job": _JOB_STATUS["current_job"],
        "last_run": _JOB_STATUS["last_run"],
        "last_result": _JOB_STATUS["last_result"],
        "total_cartolas_bci": total,
    })


async def handle_swagger(request):
    from aiohttp import web
    return web.Response(text=_SWAGGER_HTML, content_type="text/html")


async def handle_openapi(request):
    from aiohttp import web
    return web.json_response(_OPENAPI_SPEC)


def start_api_server(loop=None) -> threading.Thread:
    """Arranca el servidor HTTP en un thread secundario."""
    global _server

    def _run():
        import asyncio
        from aiohttp import web

        global _server
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = web.Application()
        app["loop"] = loop

        app.router.add_post(f"{API_BASE}/jobs/sync-historical-bci", handle_sync)
        app.router.add_get(f"{API_BASE}/jobs/status", handle_status)
        app.router.add_get("/docs", handle_swagger)
        app.router.add_get("/openapi.json", handle_openapi)

        _server = web.AppRunner(app)
        loop.run_until_complete(_server.setup())
        site = web.TCPSite(_server, API_HOST, API_PORT)
        loop.run_until_complete(site.start())
        logger.info("API servidor escuchando en http://0.0.0.0:%d", API_PORT)
        loop.run_forever()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info("API server thread iniciado (puerto %d)", API_PORT)
    return thread