"""Persistencia de cartolas BCI en MongoDB."""

import logging
import os

from pymongo import MongoClient

from listener.bci.config import BCI_PDF_PASSWORD, DB_NAME, COLLECTION

logger = logging.getLogger("aia-jobs.bci")


def get_bci_collection():
    uri = os.getenv("MONGODB_URI", "")
    if not uri:
        return None
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return client[DB_NAME][COLLECTION]
    except Exception as e:
        logger.error("No se pudo conectar a MongoDB: %s", e)
        return None


def save_cartola(cartola: dict) -> str:
    col = get_bci_collection()
    if col is None:
        return "error"
    mid = cartola.get("message_id", "")
    period = cartola.get("period", "")
    if not mid or not period:
        col.insert_one(cartola)
        return "inserted"
    existing = col.find_one({"message_id": mid, "period": period})
    if existing:
        col.update_one(
            {"message_id": mid, "period": period}, {"$set": cartola},
        )
        return "updated"
    col.update_one(
        {"message_id": mid, "period": period}, {"$set": cartola}, upsert=True,
    )
    return "inserted"