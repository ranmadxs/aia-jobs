"""Tests unitarios del filtro de cartolas BCI."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from listener.bci.filter import is_bci_cartola, process_bci_cartola
from listener.bci.transform import extract_period_from_pdf


def _bci_doc(subject="Cuenta Corriente", from_addr="bcimail@bci.cl"):
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = "destino@yahoo.com"
    msg["Message-ID"] = "<bci-test@example.com>"
    msg["Date"] = "Tue, 16 Jul 2026 10:00:00 +0000"
    msg.attach(MIMEText("cuerpo", "plain"))
    return msg


def _parse_email(msg):
    from listener.email_parser import parse_email
    import email as _email
    return parse_email(_email.message_from_bytes(msg.as_bytes()))


class TestIsBciCartola:
    def test_bci_cartola_mensual(self):
        doc = _parse_email(_bci_doc())
        assert is_bci_cartola(doc) is True

    def test_bci_cartola_lowercase_subject(self):
        doc = _parse_email(_bci_doc(subject="cuenta corriente"))
        assert is_bci_cartola(doc) is True

    def test_wrong_sender(self):
        doc = _parse_email(_bci_doc(from_addr="otros@banco.cl"))
        assert is_bci_cartola(doc) is False

    def test_no_bci_body(self):
        doc = _parse_email(_bci_doc(from_addr="noticias@bci.cl"))
        assert is_bci_cartola(doc) is False

    def test_empty_sender(self):
        doc = _parse_email(_bci_doc(from_addr=""))
        assert is_bci_cartola(doc) is False

    def test_non_bci_sender_with_cuenta_corriente(self):
        doc = _parse_email(_bci_doc(from_addr="banco@ Otro.cl"))
        assert is_bci_cartola(doc) is False


class TestProcessBciCartola:
    def test_non_bci_returns_none(self):
        doc = _parse_email(_bci_doc(from_addr="otros@banco.cl"))
        assert process_bci_cartola(doc) is None

    def test_trimestral_returns_none(self):
        doc = _parse_email(_bci_doc(subject="Cartola Trimestral Consumo"))
        assert process_bci_cartola(doc) is None

    def test_no_attachment_returns_none(self):
        doc = _parse_email(_bci_doc())
        result = process_bci_cartola(doc)
        assert result is None or isinstance(result, dict)


class TestExtractPeriodFromPdf:
    def test_extracts_period(self):
        pdf_text = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
            b"/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 60>>stream\n"
            b"BT/F1 12 Tf 100 700 Td(PERIODO : 01-06-2026 al 30-06-2026)"
            b"Tj ET\n"
            b"endstream\nendobj\n"
            b"xref\n0 5\ntrailer<</Size 5/Root 1 0 R>>\n"
            b"%%EOF\n"
        )
        period = extract_period_from_pdf(pdf_text)
        assert period == "01-06-2026 al 30-06-2026"

    def test_no_period(self):
        pdf_text = b"%PDF-1.4\nno period here\n"
        assert extract_period_from_pdf(pdf_text) is None

    def test_no_date_in_al(self):
        pdf_text = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
            b"/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 30>>stream\n"
            b"BT/F1 12 Tf 100 700 Td(al  sin fecha)Tj ET\n"
            b"endstream\nendobj\n"
            b"xref\n0 5\ntrailer<</Size 5/Root 1 0 R>>\n"
            b"%%EOF\n"
        )
        assert extract_period_from_pdf(pdf_text) is None