"""Job de transformación de cartolas BCI existentes en MongoDB."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from listener.bci.config import BCI_SENDER, COLLECTION, DB_NAME
from listener.bci.store import get_bci_collection, save_cartola
from listener.bci.transform import transform_cartola
from listener.email_parser import parse_email
from listener.store import save_email

logger = logging.getLogger("aia-jobs.bci.sync")

_JOB_STATUS = {
    "running": False,
    "current_job": None,
    "last_run": None,
    "last_result": None,
}


def _get_imap_client():
    import os
    from listener.imap_client import YahooIMAPClient

    email = os.getenv("YAHOO_EMAIL", "")
    app_password = os.getenv("YAHOO_APP_PASSWORD", "")
    client = YahooIMAPClient(email=email, app_password=app_password)
    client.connect()
    return client


def _get_email_collection():
    from pymongo import MongoClient
    import os as _os
    uri = _os.getenv("MONGODB_URI", "")
    if not uri:
        return None
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return client["email"]["emails"]
    except Exception as e:
        logger.error("No se pudo conectar a MongoDB (email): %s", e)
        return None


def _get_bci_collection():
    from pymongo import MongoClient
    import os as _os
    from listener.bci.config import DB_NAME, COLLECTION
    uri = _os.getenv("MONGODB_URI", "")
    if not uri:
        return None
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return client[DB_NAME][COLLECTION]
    except Exception as e:
        logger.error("No se pudo conectar a MongoDB (bci): %s", e)
        return None


def _needs_transform(doc: dict) -> bool:
    return doc.get("bci_cartola_transformed_at") is None


def _filter_by_months(docs: list, months_back: Optional[int]) -> list:
    if months_back is None or months_back <= 0:
        return docs
    cutoff = datetime.now() - timedelta(days=30 * months_back)
    return [d for d in docs if d.get("fecha_remitente") and d["fecha_remitente"] >= cutoff]


def sync_historical_cartolas(months_back: Optional[int] = None) -> dict:
    """Transforma cartolas BCI pendientes de email.emails → bci.cartolas.

    Lee de MongoDB (DB=email, colección=emails) los documentos con
    kind="bci_cartola" que aún no han sido transformados.
    No consulta Yahoo, no lee disco. Solo transforma PDFs ya almacenados.

    Args:
        months_back: Cuántos meses hacia atrás procesar.
                     None o 0 = todos los pendientes sin filtro de fecha.

    Returns:
        Dict con resumen del procesamiento.
    """
    _JOB_STATUS["running"] = True
    _JOB_STATUS["current_job"] = "sync_historical_cartolas"
    _JOB_STATUS["last_run"] = datetime.now(timezone.utc).isoformat()

    email_col = _get_email_collection()
    bci_col = get_bci_collection()

    if email_col is None:
        _JOB_STATUS["running"] = False
        _JOB_STATUS["last_result"] = {"error": "email collection unavailable"}
        return _JOB_STATUS["last_result"]

    if bci_col is None:
        _JOB_STATUS["running"] = False
        _JOB_STATUS["last_result"] = {"error": "bci collection unavailable"}
        return _JOB_STATUS["last_result"]

    query = {
        "from_addr": {"$regex": BCI_SENDER, "$options": "i"},
        "subject": {"$regex": "CUENTA CORRIENTE", "$options": "i"},
    }
    all_docs = list(email_col.find(query))
    pending = [d for d in all_docs if _needs_transform(d)]
    filtered = _filter_by_months(pending, months_back)

    transformed = 0
    skipped = 0
    errors = 0

    for doc in filtered:
        try:
            cartola = transform_cartola(doc)
            if cartola is None:
                skipped += 1
                email_col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"bci_cartola_transformed_at": datetime.now(timezone.utc).isoformat()}},
                )
                continue
            result = save_cartola(cartola)
            if result in ("inserted", "updated"):
                email_col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"bci_cartola_transformed_at": datetime.now(timezone.utc).isoformat()}},
                )
                transformed += 1
            else:
                errors += 1
        except Exception as e:
            logger.exception("Error transformando cartola %s: %s", doc.get("message_id", "unknown"), e)
            errors += 1

    summary = {
        "transformed": transformed,
        "skipped": skipped,
        "errors": errors,
        "total_pending": len(pending),
        "total_filtered": len(filtered),
    }
    _JOB_STATUS["running"] = False
    _JOB_STATUS["current_job"] = None
    _JOB_STATUS["last_result"] = summary
    return summary


def sync_bci_emails(sender: str, year: int, month: int) -> dict:
    """Descarga emails de un remitente en un mes dado desde Yahoo IMAP
    y los guarda en MongoDB (email.emails). Idempotente: no re-descarga
    emails ya existentes (verifica por message_id).

    Args:
        sender: Dirección de correo del remitente a buscar (ej: "bcimail@bci.cl").
        year: Año (ej: 2026).
        month: Mes (1-12).

    Returns:
        Dict con resumen del procesamiento.
    """
    since = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
       直到 = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        hasta = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    _JOB_STATUS["running"] = True
    _JOB_STATUS["current_job"] = "sync_bci_emails"
    _JOB_STATUS["last_run"] = datetime.now(timezone.utc).isoformat()

    email_col = _get_email_collection()
    if email_col is None:
        _JOB_STATUS["running"] = False
        return {"error": "email collection unavailable", "downloaded": 0, "already_existed": 0}

    try:
        client = _get_imap_client()
    except Exception as e:
        _JOB_STATUS["running"] = False
        return {"error": f"IMAP connect failed: {e}", "downloaded": 0, "already_existed": 0}

    try:
        _date_since = since.strftime("%d-%b-%Y")
        _date_hasta = hasta.strftime("%d-%b-%Y")
        _, raw_ids = client.conn.uid("SEARCH", None, "FROM", sender, "SINCE", _date_since, "BEFORE", _date_hasta)
        if not raw_ids or not raw_ids[0]:
            return {"downloaded": 0, "already_existed": 0, "sender": sender, "period": f"{year}-{month:02d}"}
        uid_list = raw_ids[0].split()
    except Exception as e:
        _JOB_STATUS["running"] = False
        return {"error": f"IMAP search failed: {e}", "downloaded": 0, "already_existed": 0}

    downloaded = 0
    already_existed = 0
    for uid_b in uid_list:
        try:
            uid = int(uid_b)
            raw = client.fetch_message_uid(uid)
            if raw is None:
                continue
            import email as email_lib
            doc = parse_email(email_lib.message_from_bytes(raw))
            result = save_email(email_col, doc)
            if result == "inserted":
                downloaded += 1
            else:
                already_existed += 1
        except Exception as e:
            logger.exception("Error procesando UID %s: %s", uid_b, e)

    _JOB_STATUS["running"] = False
    _JOB_STATUS["current_job"] = None
    _JOB_STATUS["last_result"] = {"downloaded": downloaded, "already_existed": already_existed}
    return {
        "downloaded": downloaded,
        "already_existed": already_existed,
        "sender": sender,
        "period": f"{year}-{month:02d}",
        "total_searched": len(uid_list),
    }