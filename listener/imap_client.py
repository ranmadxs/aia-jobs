"""Cliente IMAP para Yahoo con soporte de polling y notificaciones IDLE."""

import imaplib
import logging
import select
import time

logger = logging.getLogger("aia-jobs.imap")


class YahooIMAPClient:
    """Conexión IMAP a Yahoo con reconexión y soporte IDLE.

    Yahoo soporta IDLE (RFC 2177), lo que permite recibir notificaciones
    push del servidor cuando llega un correo nuevo, sin tener que hacer
    polling constante. Si el servidor no soporta IDLE, se hace polling con
    `poll_interval` segundos.
    """

    IMAP_SERVER = "imap.mail.yahoo.com"
    IMAP_PORT = 993

    def __init__(self, email: str, app_password: str, mailbox: str = "INBOX"):
        self.email = email
        self.app_password = app_password
        self.mailbox = mailbox
        self.conn: imaplib.IMAP4_SSL | None = None
        self.supports_idle = False

    # ── Conexión ──────────────────────────────────────────────────────────
    def connect(self) -> None:
        if not self.email or not self.app_password:
            raise ValueError("YAHOO_EMAIL y YAHOO_APP_PASSWORD deben estar en .env")
        self.conn = imaplib.IMAP4_SSL(self.IMAP_SERVER, self.IMAP_PORT)
        self.conn.login(self.email, self.app_password)
        self.conn.select(self.mailbox)
        # Detectar soporte de IDLE
        try:
            typ, _ = self.conn.capability()
            caps = b" ".join(typ) if isinstance(typ, (list, tuple)) else typ
            self.supports_idle = b"IDLE" in caps.upper()
        except Exception:
            self.supports_idle = False
        logger.info("IMAP conectado a %s (IDLE=%s)", self.IMAP_SERVER, self.supports_idle)

    def _ensure_connected(self) -> None:
        if self.conn is None:
            self.connect()
            return
        try:
            self.conn.noop()
        except Exception:
            logger.warning("Conexión IMAP caída, reconectando...")
            self.connect()

    def logout(self) -> None:
        try:
            if self.conn:
                self.conn.logout()
        except Exception:
            pass
        self.conn = None

    # ── Lectura de mensajes ───────────────────────────────────────────────
    def fetch_message(self, msg_id: bytes) -> bytes | None:
        """Descarga los bytes RFC822 de un mensaje (con reintentos)."""
        for _ in range(3):
            try:
                self._ensure_connected()
                _, data = self.conn.fetch(msg_id, "(RFC822)")
                if data and data[0] is not None:
                    return data[0][1]
            except Exception as e:
                logger.warning("fetch falló (%s), reconectando", e)
                self.connect()
        return None

    def search_all(self) -> list[bytes]:
        self._ensure_connected()
        _, msgs = self.conn.search(None, "ALL")
        return msgs[0].split() if msgs[0] else []

    def search_unseen(self) -> list[bytes]:
        self._ensure_connected()
        _, msgs = self.conn.search(None, "UNSEEN")
        return msgs[0].split() if msgs[0] else []

    # ── Espera de nuevos correos ──────────────────────────────────────────
    def wait_for_new(self, poll_interval: int = 60, idle_timeout: int = 29 * 60):
        """Bloquea hasta que haya un correo nuevo.

        Usa IDLE si el servidor lo soporta (espera push del servidor con
        timeout de ~29 min, el máximo recomendado por RFC 2177), si no hace
        polling cada `poll_interval` segundos. Devuelve la lista de UIDs nuevos.
        """
        if self.supports_idle:
            return self._wait_idle(idle_timeout)
        return self._wait_poll(poll_interval)

    def _wait_idle(self, timeout: int) -> list[bytes]:
        self._ensure_connected()
        # Guarda el set actual para detectar novedades
        before = set(self.search_all())
        try:
            self.conn.send(b"%s IDLE\r\n" % self.conn.tag_preauth.encode()
                           if hasattr(self.conn, "tag_preauth") else b"")
        except Exception:
            pass
        # En la práctica usamos la API de imaplib con un tag manual
        tag = self.conn._new_tag()
        self.conn.send(f"{tag} IDLE\r\n".encode())
        # Leer la respuesta inicial "+ idling"
        try:
            self.conn.readline()
        except Exception:
            pass
        deadline = time.time() + timeout
        new_ids: list[bytes] = []
        try:
            while time.time() < deadline:
                r, _, _ = select.select([self.conn.socket()], [], [], deadline - time.time())
                if r:
                    # El servidor envió algo (exists/expunge). Salir del IDLE.
                    try:
                        self.conn.send(f"{tag} DONE\r\n".encode())
                        self.conn.readline()
                    except Exception:
                        pass
                    after = set(self.search_all())
                    new_ids = sorted(after - before)
                    break
        finally:
            try:
                self.conn.send(f"{tag} DONE\r\n".encode())
                self.conn.readline()
            except Exception:
                pass
        return new_ids

    def _wait_poll(self, poll_interval: int) -> list[bytes]:
        before = set(self.search_all())
        while True:
            time.sleep(poll_interval)
            after = set(self.search_all())
            new_ids = sorted(after - before)
            if new_ids:
                return new_ids
