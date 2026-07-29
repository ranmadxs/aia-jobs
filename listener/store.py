"""Persistencia en MongoDB (mismo esquema/colección que aia-mcp)."""

import base64
import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("aia-jobs.store")

DB_NAME = "email"
COLLECTION = "emails"
SYNC_STATE_COLLECTION = "_sync_state"

_attachments_dir = Path(os.getenv("AIA_ATTACHMENTS_DIR", "/app/attachments"))


def get_sync_state_col():
    uri = os.getenv("MONGODB_URI", "")
    if not uri:
        return None
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return client[DB_NAME][SYNC_STATE_COLLECTION]
    except Exception:
        return None


def get_last_uid() -> int:
    col = get_sync_state_col()
    if col is None:
        return 0
    try:
        doc = col.find_one({})
        return int(doc.get("last_uid", 0)) if doc else 0
    except Exception:
        return 0


def set_last_uid(uid: int) -> None:
    col = get_sync_state_col()
    if col is None:
        return
    try:
        col.update_one({}, {"$setOnInsert": {"_id": "uid_tracker"}}, upsert=True)
        col.update_one({}, {"$set": {"last_uid": uid}})
    except Exception:
        pass


def get_collection():
    uri = os.getenv("MONGODB_URI", "")
    if not uri:
        return None
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return client[DB_NAME][COLLECTION]
    except Exception as e:
        logger.error("No se pudo conectar a MongoDB: %s", e)
        return None


def save_email(col, doc: dict) -> str:
    """Guarda un correo con upsert por message_id (sin duplicar).

    Los adjuntos se guardan sin campo 'data_b64' para evitar
    documentos mayores a 16 MB en MongoDB.

    Devuelve "inserted", "updated" o "skipped".
    """
    mid = doc.get("message_id")
    clean = _strip_attachment_data(doc)
    if not mid:
        col.insert_one(clean)
        return "inserted"
    existing = col.find_one({"message_id": mid})
    if existing:
        col.update_one({"message_id": mid}, {"$setOnInsert": clean})
        return "skipped"
    col.update_one({"message_id": mid}, {"$set": clean}, upsert=True)
    return "inserted"


def _strip_attachment_data(doc: dict) -> dict:
    """Guarda adjuntos > 2 MB en disco; los chicos quedan como data_b64 en MongoDB."""
    clean = doc.copy()
    attachments = doc.get("attachments") or []
    cleaned_attachments = []
    _attachments_dir.mkdir(parents=True, exist_ok=True)
    for a in attachments:
        data_b64 = a.get("data_b64")
        if data_b64 is None:
            cleaned_attachments.append(a)
            continue
        size = len(base64.b64decode(data_b64))
        if size < 2 * 1024 * 1024:
            cleaned_attachments.append(a)
            continue
        filename = a.get("filename") or "unknown"
        ext = os.path.splitext(filename)[1] or ""
        content_hash = hashlib.sha256(base64.b64decode(data_b64)).hexdigest()
        safe_name = f"{content_hash}{ext}"
        filepath = _attachments_dir / safe_name
        if not filepath.exists():
            filepath.write_bytes(base64.b64decode(data_b64))
        cleaned_attachments.append({k: v for k, v in a.items() if k != "data_b64"} | {"path": str(filepath)})
    clean["attachments"] = cleaned_attachments
    return clean


def mark_seen(col, msg_id: str) -> None:
    """Marca el correo como procesado (campo de control del listener)."""
    col.update_one(
        {"message_id": msg_id},
        {"$set": {"listener_processed_at": datetime.now(timezone.utc).isoformat()}},
        upsert=False,
    )
