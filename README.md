# aia-jobs

Listener de correo **Yahoo** (vía IMAP `IDLE`) que guarda automáticamente los
correos nuevos en **MongoDB Atlas**, reutilizando el mismo esquema de base de
datos que [`aia-mcp`](https://github.com/ranmadxs/aia-mcp) (`DB=email`,
`collection=emails`, upsert por `Message-ID`).

## Qué hace

- Se conecta a `imap.mail.yahoo.com` con una **app password** (no la clave de la cuenta).
- Espera correos nuevos usando **IMAP IDLE** (push del servidor, sin polling constante).
  Si el servidor no soporta IDLE, hace polling cada `LISTENER_POLL_INTERVAL` segundos.
- Al llegar un correo nuevo, lo parsea (asunto, remitente, cuerpo, adjuntos en base64)
  y lo guarda en MongoDB con **upsert por `message_id`** (sin duplicar).
- En el arranque procesa los correos no leídos que ya estén en el INBOX.

## Estructura

```
listener/
  cli.py          # Entry point (aia-jobs listen)
  listener.py     # Bucle principal (IDLE/polling + guardado)
  imap_client.py  # Cliente IMAP Yahoo con soporte IDLE y reconexión
  email_parser.py # Parser de mensajes (mismo esquema que aia-mcp)
  store.py        # Persistencia en MongoDB (misma DB/colección que aia-mcp)
```

## Uso local

```bash
poetry install
cp .env.example .env   # completa YAHOO_EMAIL, YAHOO_APP_PASSWORD, MONGODB_URI
poetry run aia-jobs listen
```

## Docker

La imagen reutiliza la base del ecosistema aia (`keitarodxs/aia-utils-base`),
igual que `aia-mcp`:

```bash
docker build -t aia-jobs .
docker run -d --name aia-jobs \
  -e YAHOO_EMAIL=... -e YAHOO_APP_PASSWORD=... -e MONGODB_URI=... \
  -v $(pwd)/logs:/app/logs \
  aia-jobs
```

## CI/CD

El workflow `.github/workflows/docker-image.yml` tiene dos modos:

- **Pull Request a `main`**: corre tests y hace un **build de prueba** de la
  imagen (sin push) para validar que compila. No despliega.
- **Push de un tag `vX.Y.Z`**: corre tests, construye y **publica** la imagen en
  Docker Hub (`keitarodxs/aia-jobs:vX.Y.Z` + `:latest`) y despliega en `nara`.

El tag del release se deriva del tag del git (`vX.Y.Z`), por eso **toda
modificación relevante debe subir la versión en `pyproject.toml`**, crear el tag
y registrarse en el `CHANGELOG.md`.

Flujo recomendado para un cambio:
1. Rama feature → PR a `main` (valida build).
2. Merge del PR.
3. `poetry version patch` + actualizar `CHANGELOG.md`.
4. `git tag vX.Y.Z && git push origin vX.Y.Z` → build + push + deploy.
