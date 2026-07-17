# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y el versionado sigue [SemVer](https://semver.org/lang/es/).

## [0.1.0a5] - 2026-07-17

### Cambiado
- Logs: el `datefmt` ahora incluye fecha completa (`%Y-%m-%d %H:%M:%S`) y el
  mensaje `📥 Nuevo correo` muestra la **fecha real del correo** (`date_str`
  del header Date), no solo la hora de procesamiento.

## [0.1.0a4] - 2026-07-17

### Cambiado
- Logs: el file handler pasa de DEBUG a INFO y se silencia el logger de
  pymongo/motor (WARNING). Así los `📥 Nuevo correo` quedan visibles en
  `/app/logs` sin el ruido de los heartbeats de MongoDB.

## [0.1.0a3] - 2026-07-17

### Arreglado
- `fetch_message` en `imap_client.py`: maneja ambos formatos de respuesta de
  `IMAP.fetch` (tupla y plano) para evitar el error `'int' object has no
  attribute 'decode'` al parsear el cuerpo del correo.

## [0.1.0a2] - 2026-07-16

### Cambiado
- Workflow `pr-checks.yml` dedicado a PRs (step de test).
- Ajuste de `docker-image.yml` (triggers `main` + tags `v*.*.*`).

## [0.1.0a1] - 2026-07-16

### Añadido
- Listener de correo Yahoo vía IMAP `IDLE` que guarda correos nuevos en MongoDB.
- Cliente IMAP con reconexión automática y fallback a polling si no hay IDLE.
- Parser de mensajes reutilizando el esquema de `aia-mcp` (DB `email`, colección `emails`).
- Persistencia con upsert por `Message-ID` (sin duplicados).
- Dockerfile basado en `keitarodxs/aia-utils-base` (misma base que `aia-mcp`).
- Workflow `docker-image.yml`: build de PR (sin push) + release por tag `vX.Y.Z`
  con push a Docker Hub y despliegue best-effort en `nara`.
