"""Persistencia de cartolas BCI y transacciones en MongoDB."""

import logging
import os

from pymongo import MongoClient

from listener.bci.config import COLLECTION, DB_NAME, MONGODB_URI_MAIN

logger = logging.getLogger("aia-jobs.bci")


def _get_client(uri: str, timeout_ms: int = 5000):
    if not uri:
        return None
    try:
        return MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
    except Exception as e:
        logger.error("No se pudo conectar a MongoDB: %s", e)
        return None


def get_bci_collection():
    uri = os.getenv("MONGODB_URI", "")
    client = _get_client(uri)
    if client is None:
        return None
    return client[DB_NAME][COLLECTION]


def get_transacciones_collection_main():
    client = _get_client(MONGODB_URI_MAIN)
    if client is None:
        return None
    return client["bci"]["transacciones"]


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


def save_transaccion(trx: dict) -> str:
    col = get_transacciones_collection_main()
    if col is None:
        return "error"
    tkey = trx.get("trx_key", "")
    if not tkey:
        col.insert_one(trx)
        return "inserted"
    existing = col.find_one({"trx_key": tkey})
    if existing:
        return "skipped"
    col.insert_one(trx)
    return "inserted"


def _trx_key(mov: dict) -> str:
    from hashlib import sha256
    parts = [
        mov.get("fecha", ""),
        mov.get("sucursal", ""),
        mov.get("descripcion", ""),
        str(mov.get("abono", 0)),
        str(mov.get("cargo", 0)),
        str(mov.get("saldo", 0)),
    ]
    return sha256("|".join(parts).encode()).hexdigest()
