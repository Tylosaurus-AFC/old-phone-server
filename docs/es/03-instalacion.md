# 03 · Instalación: busybox, Debian y los scripts

Supone: el móvil ya tiene root ([02](02-root.md)), la depuración USB funciona y `config.sh` está
rellenado ([01](01-preparacion.md)). Todos los comandos se ejecutan en tu **PC**, desde la
carpeta del repositorio, en bash.

El instalador está dividido en pasos para que puedas repetir solo el que falló.

```bash
tools/fetch-assets.sh              # 1. descargar Debian (+ busybox en ARM de 32 bits)
tools/install.sh check             # 2. ¿qué móvil conecté?
tools/install.sh busybox           # 3. busybox en el móvil
tools/install.sh rootfs            # 4. descomprimir Debian en el móvil
tools/install.sh scripts           # 5. enter.sh, bot.sh, charge.sh, start.sh, server.conf
tools/install.sh provision         # 6. paquetes + entorno Python dentro de Debian
```

## 1. Descarga

`tools/fetch-assets.sh` descarga en `downloads/` (ignorada por git):

* El **sistema de archivos raíz de Debian 13 «trixie»** para tu `ARCH`, desde
  <https://images.linuxcontainers.org/images/debian/trixie/> (la compilación más reciente), y lo
  verifica con el `SHA256SUMS` publicado.
* **busybox** (solo ARM de 32 bits) desde <https://busybox.net/downloads/binaries/>.

> ¿Prefieres otra distribución o versión? Cualquier rootfs de la arquitectura correcta sirve para
> el chroot; los scripts suponen Debian/apt en `provision`.

## 2. Revisar

`tools/install.sh check` muestra el modelo, la versión de Android, las ABI de la CPU, la RAM, el
espacio libre, el modo de SELinux y —importante— qué **archivos de control de batería** existen.
Lo que te diga va a `config.sh` (`ARCH`) y luego a `server.conf` (`BATT_CTRL`, ver
[06](06-bateria-y-calor.md)).

## 3. busybox

El chroot se entra con el `chroot` y el `mount` de busybox; la «toolbox» de Android no tiene
ninguno. Necesitas un busybox **estático** que incluya el applet `chroot` (`install.sh busybox`
lo verifica).

**Dónde debe vivir** — esto decide `BB_PATH` en `config.sh`:

| Situación | `BB_PATH` |
|---|---|
| La mayoría de móviles, Magisk, ROMs personalizadas | `/data/debian/busybox-deb` (por defecto) |
| **Kernels Samsung viejos** con `sec_restrict_fork` (época del Galaxy S4, Android 4.4–5): a root se le prohíbe ejecutar binarios guardados en `/data`, sale *Permission denied* / *Operation not permitted* | `/system/xbin/busybox-deb` (el script remonta `/system` en escritura y lo vuelve a dejar) |

Cómo saberlo: sube busybox a `/data/local/tmp` y ejecuta
`adb shell su -c /data/local/tmp/busybox true`. Si lo rechaza, usa `/system/xbin`.
(Dentro del chroot esta restricción no aplica.)

* **ARM de 32 bits:** `tools/fetch-assets.sh` trae `busybox-armv7l`.
* **arm64:** busybox.net no tiene compilación aarch64. Si usas Magisk, ya trae una:
  `adb shell su -c "cp /data/adb/magisk/busybox /data/local/tmp/busybox-arm64"`, bájala con `adb pull` y
  ejecuta `tools/install.sh busybox ruta/a/busybox-arm64`.

## 4. Debian

`tools/install.sh rootfs` recomprime el `.tar.xz` como `.tar.gz` en el PC (a busybox casi siempre
le falta xz), lo sube y lo descomprime en `/data/debian/fs` **conservando los permisos**
(`tar -p`). Se niega a correr si `/data/debian/fs` ya tiene un Debian: muévelo o bórralo tú.

## 5. Scripts

`tools/install.sh scripts` copia a `/data/debian/`:

| Archivo | Función |
|---|---|
| `enter.sh` | monta `/proc`, `/sys`, `/dev`… y entra al chroot. `enter.sh` abre una shell; `enter.sh "comando"` ejecuta un comando |
| `bot.sh` | mantiene el bot corriendo, reiniciando con esperas crecientes |
| `charge.sh` | el vigilante de cada minuto |
| `start.sh` | corre al arrancar: wake-lock, Wi-Fi, adb, y luego `bot.sh` y `charge.sh` |
| `server.conf` | **tus ajustes** (se crea desde `phone/server.conf.example` y nunca se sobrescribe) |

**Edita `server.conf` ahora**, sobre todo el driver de batería
([06](06-bateria-y-calor.md)). La referencia de cada ajuste está en
[`phone/server.conf.example`](../../phone/server.conf.example). Para editar la copia del móvil:

```bash
tools/edit-conf.sh        # la baja, abre tu $EDITOR y la sube si cambiaste algo
```

(`charge.sh` la relee cada minuto, así que las ediciones posteriores no necesitan reinicio.)

## 6. Preparar Debian

`tools/install.sh provision` ejecuta `phone/setup-debian.sh` **dentro** del chroot. Tarda
10–30 minutos en un móvil lento y necesita Internet en el móvil. Hace:

* escribe `resolv.conf` y ajusta tu zona horaria;
* crea los grupos `aid_inet` (3003) y `aid_net_raw` (3004) —Android solo deja usar la red a los
  procesos del grupo *inet*, y apt normalmente baja sus privilegios a un usuario que no está en
  él— y le dice a apt que corra como root y solo con IPv4;
* instala Python, ffmpeg, Node.js (yt-dlp necesita un runtime de JS para YouTube), `iw`,
  poppler-utils y las bibliotecas de Python que existen como paquetes precompilados de Debian;
* crea un entorno virtual en `/opt/bot/venv` e instala `bot/requirements.txt` (yt-dlp,
  gallery-dl, Telethon + TgCrypto…); el compilador que necesita TgCrypto se elimina después.

Al terminar imprime las versiones de Python y yt-dlp.

### Comprobación manual rápida

```bash
adb shell su -c "/data/debian/enter.sh 'cat /etc/debian_version; python3 --version; ping -c1 1.1.1.1'"
```

## Si algo falla

| Síntoma | Causa / solución |
|---|---|
| `exec format error` al entrar al chroot | `ARCH` equivocada: un móvil de 32 bits necesita `armhf` |
| `chroot: not found` / sin applet `chroot` | ese busybox no lo trae; usa otro (`busybox --list \| grep chroot`) |
| `Permission denied` al ejecutar busybox desde `/data` | `sec_restrict_fork`: usa `BB_PATH=/system/xbin/busybox-deb` |
| `mount: Operation not permitted` | no es root de verdad, o SELinux en modo enforcing lo bloquea: prueba una vez `su -c 'setenforce 0'` para confirmarlo; algunas ROMs necesitan la vía de SELinux permisivo de Magisk |
| apt: *Temporary failure resolving* | `/etc/resolv.conf` vacío (el paso `provision` lo escribe), o el móvil no tiene Internet |
| apt: *Could not create temporary file* / red inaccesible | falta el grupo `aid_inet` o el ajuste `Sandbox::User root`; repite `provision` |
| *No space left on device* | `/data` lleno; libera espacio o quita los modelos de voz |
| Android 11+: `Network is unreachable` como root | pon `FIX_ROUTE=1` en `server.conf` ([07](07-red.md)) |

## Lo que hace el instalador, a mano

Si prefieres hacerlo manualmente: sube busybox a su sitio (`chmod 755`; `chcon
u:object_r:system_file:s0` si está en `/system`); crea `/data/debian/fs` y haz `tar -xzpf` del
rootfs dentro; copia los scripts de `phone/` a `/data/debian/` con `chmod 755`; copia
`bot/requirements.txt` a `/data/debian/fs/opt/bot/`; y ejecuta `phone/setup-debian.sh` a través de
`enter.sh`.

Siguiente: [04 · Bot de Telegram](04-bot-telegram.md).
