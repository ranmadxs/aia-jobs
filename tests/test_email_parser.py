"""Tests del parser de emails (sin red, sin Mongo)."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from listener.email_parser import parse_email


def _build_sample() -> bytes:
    msg = MIMEMultipart()
    msg["Subject"] = "Prueba aia-jobs"
    msg["From"] = "remitente@yahoo.com"
    msg["To"] = "destino@yahoo.com"
    msg["Message-ID"] = "<test-123@yahoo.com>"
    msg["Date"] = "Tue, 16 Jul 2026 10:00:00 +0000"
    msg.attach(MIMEText("Cuerpo de prueba", "plain"))
    return msg.as_bytes()


def test_parse_email_basic_fields():
    doc = parse_email(__import__("email").message_from_bytes(_build_sample()))
    assert doc["subject"] == "Prueba aia-jobs"
    assert doc["from_addr"] == "remitente@yahoo.com"
    assert doc["message_id"] == "<test-123@yahoo.com>"
    assert "Cuerpo de prueba" in doc["body_text"]
    assert doc["kind"] == "email"
    assert doc["period"] == "2026-07"


def test_parse_email_attachment():
    msg = MIMEMultipart()
    msg["Subject"] = "Con adjunto"
    msg["Message-ID"] = "<att-1@yahoo.com>"
    msg.attach(MIMEText("texto", "plain"))
    att = MIMEText("contenido pdf falso", "plain")
    att.replace_header("Content-Type", "application/pdf")
    att.add_header("Content-Disposition", "attachment", filename="doc.pdf")
    msg.attach(att)
    doc = parse_email(__import__("email").message_from_bytes(msg.as_bytes()))
    assert len(doc["attachments"]) == 1
    assert doc["attachments"][0]["filename"] == "doc.pdf"
