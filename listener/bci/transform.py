"""Transformación de PDF de cartola BCI a estructura de documento."""

import re
from io import BytesIO

import pdfplumber

from listener.bci.config import BCI_PDF_PASSWORD

_PERIOD_RE = re.compile(r"al\s+(\d{2})-(\d{2})-(\d{4})")

_ABONO_KEYWORDS = (
    "TRANSFER", "ABONO", "TRASPASO FONDOS", "PAGO RECIBIDO", "DEPOSITO",
    "DEPÓSITO", "RECAUDACION", "ACREDITACION", "ACREDITACIÓN", "NOTA ABONO",
    "REINTEGRO", "DEVOLUCION", "DEVOLUCIÓN",
)

_AMOUNT_RE = re.compile(r"[\d.]{2,}")


def _parse_amount(token: str) -> float:
    return float(token.replace(".", "").replace(",", "."))


def extract_period_from_pdf(pdf_bytes: bytes, password: str = "") -> str | None:
    try:
        with pdfplumber.open(BytesIO(pdf_bytes), password=password or "") as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                m = _PERIOD_RE.search(text)
                if m:
                    d, mo, y = m.groups()
                    return f"{y}-{mo}"
    except Exception:
        return None
    return None


def extract_movements(pdf_bytes: bytes, password: str = "") -> list[dict]:
    movements: list[dict] = []
    prev_saldo = None
    with pdfplumber.open(BytesIO(pdf_bytes), password=password or "") as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            lineas: dict[int, list[str]] = {}
            for w in words:
                lineas.setdefault(round(w["top"]), []).append(w["text"])
            for y_s in sorted(lineas):
                txt = " ".join(lineas[y_s])
                if not re.match(r"^\d{2}-\d{2}-\d{4}", txt):
                    continue
                if "SALDO" in txt or "al " in txt:
                    continue
                nums = _AMOUNT_RE.findall(txt)
                if len(nums) < 2:
                    continue
                fecha = txt[:10]
                descripcion = txt[10:].split(nums[0])[0].strip()
                monto = _parse_amount(nums[-2])
                saldo = _parse_amount(nums[-1])
                is_ingreso = False
                has_abono_kw = any(k in descripcion.upper() for k in _ABONO_KEYWORDS)
                if prev_saldo is None:
                    is_ingreso = has_abono_kw
                elif saldo > prev_saldo:
                    is_ingreso = True
                elif saldo >= prev_saldo and has_abono_kw:
                    is_ingreso = True
                movements.append({
                    "fecha": fecha,
                    "descripcion": descripcion,
                    "monto": monto,
                    "saldo": saldo,
                    "is_ingreso": is_ingreso,
                })
                prev_saldo = saldo
    return movements


def transform_cartola(doc: dict) -> dict | None:
    atts = doc.get("attachments", [])
    if not atts:
        return None
    password = BCI_PDF_PASSWORD or ""
    try:
        import base64 as _b64
        pdf_bytes = _b64.b64decode(atts[0]["data_b64"])
    except Exception:
        return None
    period = extract_period_from_pdf(pdf_bytes, password) or doc.get("period", "")
    movements = extract_movements(pdf_bytes, password)
    resultado = {
        "message_id": doc.get("message_id", ""),
        "subject": doc.get("subject", ""),
        "from_addr": doc.get("from_addr", ""),
        "fecha_remitente": doc.get("fecha_remitente"),
        "date_str": doc.get("date_str", ""),
        "period": period,
        "kind": "bci_cartola",
        "total_movimientos": len(movements),
        "movimientos": movements,
        "fetched_at": doc.get("fetched_at", ""),
        "pdf": atts[0],
    }
    return resultado