"""Filtro que detecta cartolas BCI en correos procesados."""

from typing import Optional

from listener.bci.config import BCI_SENDER
from listener.bci.transform import transform_cartola


def is_bci_cartola(doc: dict) -> bool:
    from_addr = doc.get("from_addr", "")
    subject = doc.get("subject", "").upper()
    return BCI_SENDER in from_addr and (
        "CUENTA CORRIENTE" in subject or "CARTOLA" in subject
    )


def process_bci_cartola(doc: dict) -> Optional[dict]:
    if not is_bci_cartola(doc):
        return None
    return transform_cartola(doc)