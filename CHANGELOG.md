# Changelog

Todos los cambios relevantes de este proyecto se documentan aquí.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y el versionado sigue [SemVer](https://semver.org/lang/es/).

## [0.1.0a1] - 2026-07-16

### Añadido
- Listener de correo Yahoo vía IMAP `IDLE` que guarda correos nuevos en MongoDB.
- Cliente IMAP con reconexión automática y fallback a polling si no hay IDLE.
- Parser de mensajes reutilizando el esquema de `aia-mcp` (DB `email`, colección `emails`).
- Persistencia con upsert por `Message-ID` (sin duplicados).
- Dockerfile basado en `keitarodxs/aia-utils-base` (misma base que `aia-mcp`).
- Workflow `docker-image.yml`: build de PR (sin push) + release por tag `vX.Y.Z`
  con push a Docker Hub y despliegue best-effort en `nara`.
