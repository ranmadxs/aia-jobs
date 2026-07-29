"""Bucle principal del listener: espera correos nuevos y los guarda en Mongo."""

import email as email_lib
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from listener.imap_client import YahooIMAPClient
from listener.email_parser import parse_email
from listener.store import get_collection, save_email
from listener.bci.filter import is_bci_cartola, process_bci_cartola
from listener.bci.store import save_cartola
from listener.bci.api_server import start_api_server

logger = logging.getLogger("aia-jobs.listener")

# Directorio de logs (montado como volumen en Docker: /app/logs)
_LOGS_DIR = Path(os.getenv("AIA_JOBS_LOGS_DIR", "/app/logs"))


def setup_logging() -> None:
    """Configura logging a consola + archivo rotado por día en _LOGS_DIR."""
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOGS_DIR / f"aia-jobs_{time.strftime('%Y%m%d')}.log"

    fmt = logging.Formatter(
        "%(asctime)s [aia-jobs] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=7, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)

    # Silenciar el ruido de DEBUG de las librerías (pymongo/motor emiten
    # heartbeats y traces que enturbian los logs de los correos nuevos).
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

# Variable global para manejo de señales de apagado
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Señal %s recibida, apagando listener...", signum)
    _shutdown = True


def run_once(client: YahooIMAPClient, col) -> int:
    """Procesa los correos no leídos actuales. Devuelve cuántos guardó."""
def _process_message(client: YahooIMAPClient, col, msg_id: bytes) -> str:
    """Descarga, guarda y loguea un correo. Devuelve el resultado del save."""
    raw = client.fetch_message(msg_id)
    if raw is None:
        return "error"
    doc = parse_email(email_lib.message_from_bytes(raw))
    result = save_email(col, doc)
    subject = doc.get("subject", "(sin asunto)")
    from_addr = doc.get("from_addr", "")
    date_str = doc.get("date_str", "")
    if result == "inserted":
        # Log explícito cada vez que llega un correo nuevo, con su asunto
        # y la fecha real del correo (no la del procesamiento).
        logger.info(
            "📥 Nuevo correo | Fecha: %s | Asunto: %s | De: %s",
            date_str, subject, from_addr,
        )
        # Marcar como leído en el servidor, SALVO si es de la última semana
        # (para no tocar correos recientes en la bandeja de Yahoo).
        _maybe_mark_seen(client, msg_id, doc)
    elif result == "skipped":
        logger.debug("Correo ya existente (omitido) | Asunto: %s", subject)
    if is_bci_cartola(doc):
        _process_bci_cartola(doc)
    return result


# No marcar como leídos los correos de los últimos 7 días.
_SEEN_GRACE_DAYS = 7


def _maybe_mark_seen(client: YahooIMAPClient, msg_id: bytes, doc: dict) -> None:
    """Marca el correo como \\Seen en IMAP solo si es anterior a la ventana de gracia."""
    fecha = doc.get("fecha_remitente")
    if fecha is None:
        return
    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=_SEEN_GRACE_DAYS)
    if fecha < limite:
        client.mark_seen(msg_id)
        logger.debug("Correo antiguo marcado como leído (fuera de %d días): %s",
                     _SEEN_GRACE_DAYS, doc.get("subject", ""))


def _process_bci_cartola(doc: dict) -> None:
    """Si el correo es una cartola BCI, la guarda en la colección cartolas."""
    cartola = process_bci_cartola(doc)
    if cartola is None:
        return
    result = save_cartola(cartola)
    if result in ("inserted", "updated"):
        col.update_one(
            {"message_id": doc.get("message_id")},
            {"$set": {"kind": "bci_cartola", "bci_cartola_transformed_at": datetime.now(timezone.utc).isoformat()}},
        )
    subject = doc.get("subject", "(sin asunto)")
    period = cartola.get("period", "")
    logger.info(
        "🏦 BCI Cartola | Periodo: %s | Asunto: %s | Resultado: %s",
        period, subject, result,
    )


def run_once(client: YahooIMAPClient, col) -> int:
    """Procesa los correos no leídos actuales. Devuelve cuántos guardó."""
    saved = 0
    for msg_id in client.search_unseen():
        result = _process_message(client, col, msg_id)
        if result == "inserted":
            saved += 1
    return saved


def run_forever(poll_interval: int = 60) -> None:
    """Loop principal del listener."""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    client = YahooIMAPClient(
        email=os.getenv("YAHOO_EMAIL", ""),
        app_password=os.getenv("YAHOO_APP_PASSWORD", ""),
    )
    col = get_collection()
    if col is None:
        logger.error("MongoDB no disponible. Abortando listener.")
        sys.exit(1)

    client.connect()

    # Primera pasada: procesa lo que ya está en el INBOX como no leído.
    try:
        n = run_once(client, col)
        logger.info("Pasada inicial: %d correos nuevos guardados", n)
    except Exception as e:
        logger.exception("Error en pasada inicial: %s", e)

    # Loop de espera de novedades (IDLE o polling).
    while not _shutdown:
        try:
            new_ids = client.wait_for_new(poll_interval=poll_interval)
            if new_ids:
                logger.info("%d correo(s) nuevo(s) detectados", len(new_ids))
                for msg_id in new_ids:
                    _process_message(client, col, msg_id)
        except Exception as e:
            logger.exception("Error en loop de espera: %s", e)
            time.sleep(5)
            try:
                client.connect()
            except Exception:
                pass

    client.logout()
    logger.info("Listener detenido.")


def main() -> None:
    setup_logging()
    poll = int(os.getenv("LISTENER_POLL_INTERVAL", "60"))
    start_api_server()
    run_forever(poll_interval=poll)


if __name__ == "__main__":
    main()
