"""Parser de mensajes de correo (reutilizado del esquema de aia-mcp)."""

import base64
import email as email_lib
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone


def _decode_str(s) -> str:
    if s is None:
        return ""
    if isinstance(s, bytes):
        return s.decode("utf-8", errors="replace")
    return str(s)


def parse_email(msg) -> dict:
    """Extrae campos relevantes de un mensaje IMAP, incluidos adjuntos (base64)."""
    subject = ""
    subj_raw = msg.get("Subject")
    if subj_raw:
        subject = " ".join(_decode_str(p) for p, _ in decode_header(subj_raw))

    date_str = msg.get("Date", "")
    fecha_remitente = None
    if date_str:
        try:
            dt = parsedate_to_datetime(date_str)
            fecha_remitente = dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            pass

    body_text = body_html = ""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            filename = part.get_filename()
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                payload = None
            # Adjunto (PDF, etc.) -> guardar en base64
            if filename and ctype not in ("text/plain", "text/html") and payload:
                attachments.append({
                    "filename": _decode_str(filename),
                    "content_type": ctype,
                    "size": len(payload),
                    "data_b64": base64.b64encode(payload).decode("ascii"),
                })
                continue
            if payload is None:
                continue
            decoded = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain" and not body_text:
                body_text = decoded
            elif ctype == "text/html" and not body_html:
                body_html = decoded
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                body_text = payload.decode("utf-8", errors="replace")
        except Exception:
            body_text = str(msg.get_payload())

    doc = {
        "message_id": msg.get("Message-ID", ""),
        "subject": subject,
        "from_addr": msg.get("From", ""),
        "to_addr": msg.get("To", ""),
        "date_str": date_str,
        "body_text": body_text[:50000],
        "body_html": body_html[:50000],
        "attachments": attachments,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "kind": "email",
    }
    if fecha_remitente:
        doc["fecha_remitente"] = fecha_remitente
        doc["period"] = fecha_remitente.strftime("%Y-%m")
    return doc
