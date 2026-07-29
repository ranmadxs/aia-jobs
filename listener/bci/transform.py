"""Transformación de PDF de cartola BCI a estructura de documento."""

import re
from io import BytesIO

import pdfplumber

from listener.bci.config import BCI_PDF_PASSWORD

_PERIOD_RANGE_RE = re.compile(r"PERIODO\s*:\s*(\d{2}-\d{2}-\d{4})\s*al\s*(\d{2}-\d{2}-\d{4})")
_CUENTA_RE = re.compile(r"Nº\s*CUENTA\s*:\s*(\d+)")
_MONEDA_RE = re.compile(r"MONEDA\s*:\s*(\w+)")
_OFICINA_RE = re.compile(r"OFICINA\s*:\s*(.+)")

_AMOUNT_RE = re.compile(r"[\d.]{2,}")


def _parse_amount(token: str) -> float:
    return float(token.replace(".", "").replace(",", "."))


def extract_period_from_pdf(pdf_bytes: bytes, password: str = "") -> str | None:
    try:
        with pdfplumber.open(BytesIO(pdf_bytes), password=password or "") as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                m = _PERIOD_RANGE_RE.search(text)
                if m:
                    return f"{m.group(1)} al {m.group(2)}"
    except Exception:
        return None
    return None


def extract_header_from_pdf(pdf_bytes: bytes, password: str = "") -> dict:
    header = {}
    try:
        with pdfplumber.open(BytesIO(pdf_bytes), password=password or "") as pdf:
            text = pdf.pages[0].extract_text() or ""
            m = _CUENTA_RE.search(text)
            if m:
                header["n_cuenta"] = m.group(1)
            m = _MONEDA_RE.search(text)
            if m:
                header["moneda"] = m.group(1)
            m = _OFICINA_RE.search(text)
            if m:
                header["oficina"] = m.group(1).strip()
    except Exception:
        pass
    return header


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
                rest = txt[10:]
                descripcion_full = rest.split(nums[0])[0].strip()
                parts = descripcion_full.split(None, 1)
                sucursal = parts[0] if parts else ""
                descripcion = parts[1] if len(parts) > 1 else descripcion_full
                monto = _parse_amount(nums[-2])
                saldo = _parse_amount(nums[-1])
                is_ingreso = False
                if prev_saldo is None:
                    is_ingreso = False
                elif saldo > prev_saldo:
                    is_ingreso = True
                movements.append({
                    "fecha": fecha,
                    "sucursal": sucursal,
                    "descripcion": descripcion,
                    "saldo": saldo,
                })
                if is_ingreso:
                    movements[-1]["abono"] = monto
                    movements[-1]["cargo"] = 0
                else:
                    movements[-1]["cargo"] = monto
                    movements[-1]["abono"] = 0
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
    header = extract_header_from_pdf(pdf_bytes, password)
    movements = extract_movements(pdf_bytes, password)
    resultado = {
        "message_id": doc.get("message_id", ""),
        "subject": doc.get("subject", ""),
        "from_addr": doc.get("from_addr", ""),
        "fecha_remitente": doc.get("fecha_remitente"),
        "date_str": doc.get("date_str", ""),
        "period": period,
        "kind": "bci_cartola",
        "n_cuenta": header.get("n_cuenta", ""),
        "moneda": header.get("moneda", ""),
        "oficina": header.get("oficina", ""),
        "total_movimientos": len(movements),
        "movimientos": movements,
        "fetched_at": doc.get("fetched_at", ""),
        "pdf": atts[0],
    }
    return resultado