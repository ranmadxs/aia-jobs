# ─────────────────────────────────────────────────────────────────────────────
# aia-jobs — imagen Docker
# Listener de correo Yahoo (IMAP IDLE) que guarda nuevos emails en MongoDB.
#
# Reutiliza la imagen base del ecosistema aia (aia-utils), que ya trae:
#   Python 3.13-slim, git, curl, ca-certificates, build-essential/gcc,
#   Poetry (para `poetry export`), uv (instalador rápido) y
#   Node.js 20 + drawio-mcp-server@2.2.0.
# Ver: https://github.com/ranmadxs/aia-utils (PR #1, imagen keitarodxs/aia-utils-base)
# ─────────────────────────────────────────────────────────────────────────────

FROM keitarodxs/aia-utils-base:v1.0.0

WORKDIR /app

# ── Dependencias Python (capa cacheable) ─────────────────────────────────────
# Se copia SOLO pyproject.toml + poetry.lock ANTES del código fuente, así la
# capa de dependencias solo se reconstruye si cambian las deps, no el código.
# Se exporta a requirements.txt (respeta poetry.lock) y se instala con `uv pip
# install --system`, que es 10-100x más rápido que `pip install`.
COPY pyproject.toml poetry.lock ./
# Poetry 1.8.x no incluye `export` por defecto: instala el plugin con el mismo
# pip que instaló poetry, para que lo detecte en el mismo entorno.
RUN pip install --no-cache-dir poetry-plugin-export \
    && poetry export -f requirements.txt --without-hashes --with dev -o /tmp/requirements.txt 2>/dev/null \
    || poetry export -f requirements.txt --without-hashes -o /tmp/requirements.txt \
    && uv pip install --system -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# ── Código fuente (capa NO cacheable, va DESPUÉS de las deps) ───────
COPY listener ./listener
# README.md es requerido por pyproject.toml (readme = "README.md") para
# que pip install . genere los metadatos sin error.
COPY README.md ./README.md
# Instala el paquete propio (registra el entry point `aia-jobs`).
RUN pip install --no-cache-dir .

# ── Variables de entorno por defecto ──────────────────────────────────────────
ENV FASTMCP_LOG_LEVEL=INFO

# MongoDB (donde se guardan los emails)
ENV MONGODB_URI=

# Email (IMAP Yahoo)
ENV YAHOO_EMAIL=
ENV YAHOO_APP_PASSWORD=

# Listener
ENV LISTENER_POLL_INTERVAL=60
ENV AIA_JOBS_LOGS_DIR=/app/logs

# ── Directorios de datos persistentes ─────────────────────────────────────────
RUN mkdir -p /app/logs \
    && chmod -R 777 /app/logs

VOLUME ["/app/logs"]

# Entry point: arranca el listener en primer plano.
# Para un solo servidor MCP: docker run ... aia-mcp aia-mcp temperatura --http
ENTRYPOINT ["aia-jobs", "listen"]
