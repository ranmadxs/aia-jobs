"""Persistencia en MongoDB (mismo esquema/colección que aia-mcp)."""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("aia-jobs.store")

DB_NAME = "email"
COLLECTION = "emails"


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

    Devuelve "inserted", "updated" o "skipped".
    """
    mid = doc.get("message_id")
    if not mid:
        col.insert_one(doc)
        return "inserted"
    existing = col.find_one({"message_id": mid})
    if existing:
        # Ya existe: actualiza campos que puedan faltar, pero no duplica.
        col.update_one({"message_id": mid}, {"$setOnInsert": doc})
        return "skipped"
    col.update_one({"message_id": mid}, {"$set": doc}, upsert=True)
    return "inserted"


def mark_seen(col, msg_id: str) -> None:
    """Marca el correo como procesado (campo de control del listener)."""
    col.update_one(
        {"message_id": msg_id},
        {"$set": {"listener_processed_at": datetime.now(timezone.utc).isoformat()}},
        upsert=False,
    )
