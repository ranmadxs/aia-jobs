# SPEC — Instalación de GitHub Actions Self-Hosted Runners en `nara`

Propósito: documentar cómo registrar e instalar runners self-hosted de GitHub en
el servidor `nara` (Ubuntu 26.04, x86_64), de forma que **sobrevivan reinicios**
y queden disponibles para los workflows de los repos del usuario `ranmadxs`.

> Servidor: `nara` (acceso por SSH desde el Mac admin vía `ssh nara`, LAN
> `192.168.1.200`). El runner NO corre en el Mac; corre en `nara`.

---

## 1. Estado actual (al 2026-07-17)

En `nara` hay 3 runners instalados, todos con el **mismo nombre `nara`** y el
label `self-hosted,Linux,X64,nara` (el label `nara` es el que usan los workflows
con `runs-on: [self-hosted, nara]`):

| Directorio en `nara`        | Repo enlazado     | Tipo de servicio                         | Estado  |
|-----------------------------|-------------------|------------------------------------------|---------|
| `~/actions-runner`          | `ranmadxs/aia-mcp`| system service (`User=ranmadxs`, sudo)   | online  |
| `~/actions-runner-aia-device`| `ranmadxs/aia-device`| system service (`User=ranmadxs`, sudo)| online  |
| `~/actions-runner-aia-jobs` | `ranmadxs/aia-jobs`| **user service** + linger (sin sudo)     | online  |

Versión del binario de runner: **2.335.1** (linux-x64).

> Nota: los dos primeros fueron instalados como *system service* con `sudo
> ./svc.sh install`. El de `aia-jobs` se instaló como *user service* porque
> `sudo` no es usable de forma no interactiva por SSH; ambos métodos sobreviven
> al reinicio (el user service gracias a `loginctl enable-linger`).

---

## 2. Prerrequisitos en `nara`

- Acceso SSH funcionando (`ssh nara` desde el Mac admin).
- Usuario `ranmadxs` con su `$HOME` (`/home/ranmadxs`).
- `curl`, `tar`, `systemctl` (systemd) disponibles.
- El binario del runner ya descargado en `~/actions-runner` (se reutiliza para
  clonar a los otros directorios, evitando descargas lentas).

---

## 3. Obtener el token de registro (desde el Mac admin)

El token se genera desde GitHub y **expira en ~1 hora**. Se genera en el Mac
(porque `gh` NO está instalado en `nara`) y se pasa por variable de entorno al
comando remoto.

```bash
# En el Mac admin, dentro del repo:
TOKEN=$(gh api -X POST repos/ranmadxs/aia-jobs/actions/runners/registration-token \
  --jq '.token')
echo "$TOKEN"   # usarlo en el paso siguiente
```

> Sustituir `aia-jobs` por el repo destino (`aia-mcp`, `aia-device`, etc.).

---

## 4. Crear el directorio del runner (reutilizando binario existente)

Hacer `cp -r` del runner ya instalado evita volver a descargar ~100 MB.

```bash
ssh nara '
  set -e
  cd ~
  rm -rf actions-runner-aia-jobs
  cp -r actions-runner actions-runner-aia-jobs
  cd actions-runner-aia-jobs
  # limpiar estado de configuración previo (clave: borrar ANTES de configurar)
  rm -f .runner .runner_migrated .credentials .credentials_rsaparams .env
'
```

> ⚠️ Si alguna vez quedó un servicio instalado del mismo directorio, desinstalar
> primero: `./svc.sh uninstall` (requiere sudo) o, para user service,
> `systemctl --user disable --now github-runner-aia-jobs.service`.
> `config.sh` falla con *"already configured"* si existe `.runner`/`.env`.

---

## 5. Registrar el runner (config.sh)

```bash
# Desde el Mac, con el TOKEN del paso 3:
ssh nara "
  cd ~/actions-runner-aia-jobs
  ./config.sh \
    --url https://github.com/ranmadxs/aia-jobs \
    --token '$TOKEN' \
    --name nara \
    --labels self-hosted,Linux,X64,nara \
    --runnergroup default \
    --work _work \
    --unattended
"
# Salida esperada: "√ Runner successfully added"
```

Parámetros:
- `--name nara`: nombre visible en GitHub (puede repetirse entre repos).
- `--labels`: el label `nara` es obligatorio para que matchee `runs-on:
  [self-hosted, nara]`.
- `--unattended`: sin prompts interactivos.

---

## 6. Instalar como servicio PERSISTENTE (sobrevive reinicios)

### Opción A — system service (los 2 primeros runners)
Requiere `sudo` interactivo en `nara`:
```bash
cd ~/actions-runner-aia-jobs
sudo ./svc.sh install
sudo ./svc.sh start
```
Esto crea `actions.runner.ranmadxs-aia-jobs.nara.service` y lo habilita.

### Opción B — user service + linger (usado para aia-jobs, sin sudo)
Como `sudo` no es usable por SSH no interactivo, se crea el unit manualmente:
```bash
ssh nara '
  set -e
  RUNNER_DIR=$HOME/actions-runner-aia-jobs
  mkdir -p ~/.config/systemd/user
  cat > ~/.config/systemd/user/github-runner-aia-jobs.service <<EOF
[Unit]
Description=GitHub Actions Runner (aia-jobs.nara)
After=network.target

[Service]
Type=simple
WorkingDirectory=$RUNNER_DIR
ExecStart=$RUNNER_DIR/run.sh
User=ranmadxs
Restart=always
RestartSec=5
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable github-runner-aia-jobs.service
  systemctl --user start  github-runner-aia-jobs.service
  loginctl enable-linger $USER   # arranca el user service tras reiniciar
'
```

Verificar:
```bash
systemctl --user is-enabled github-runner-aia-jobs.service   # -> enabled
systemctl --user is-active  github-runner-aia-jobs.service   # -> active
loginctl show-user $USER -p Linger                           # -> Linger=yes
```

---

## 7. Verificar en GitHub

```bash
gh api repos/ranmadxs/aia-jobs/actions/runners \
  --jq '.runners[] | [.id, .name, .status, .busy] | @tsv'
# Ejemplo:  2   nara   online   false
```

---

## 8. Troubleshooting

| Síntoma | Causa | Solución |
|---------|-------|----------|
| `Cannot configure the runner because it is already configured` | Quedó `.runner`/`.env` de un intento previo | `rm -f .runner .runner_migrated .credentials .credentials_rsaparams .env` y reintentar |
| `Must run as sudo` en `svc.sh install` | `svc.sh` instala system service | Usar Opción B (user service) o correr `sudo ./svc.sh install` en sesión interactiva |
| `gh: command not found` dentro de `ssh nara` | `gh` no está en `nara` | Generar el token en el Mac y pasarlo como variable al comando remoto |
| El runner no arranca tras reinicio | Sin linger / sin enable | `systemctl --user enable` + `loginctl enable-linger $USER` |
| Descarga lenta / falla URL `.../v/...` | Versión vacía en la URL | Reutilizar binario con `cp -r` (ver paso 4) o fijar versión: `v2.335.1` |

---

## 9. Para agregar un NUEVO repo en el futuro

1. Repetir paso 3 (token para el repo nuevo).
2. `cp -r ~/actions-runner ~/actions-runner-<repo>` y limpiar estado (paso 4).
3. `config.sh` con la URL del repo nuevo (paso 5).
4. Instalar servicio (paso 6).
5. Verificar en GitHub (paso 7).
