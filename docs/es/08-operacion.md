# 08 · Operación: actualizar, respaldar, restaurar, arreglar

Comandos del día a día, desde el repositorio en tu PC.

| Tarea | Comando |
|---|---|
| Subir código / ajustes / plugins nuevos y reiniciar | `tools/deploy.sh` |
| Activar / desactivar el bot en este móvil | `tools/enable-bot.sh` · `tools/enable-bot.sh off` |
| Editar los ajustes del móvil | `tools/edit-conf.sh` |
| Respaldar configuración + secretos (a `backup/`, nunca lo subas) | `tools/backup.sh` |
| Restaurar esa configuración | `tools/restore-config.sh backup/<fecha>` |
| Copiar todo el Debian (sin secretos) | `tools/make-image.sh` |
| Restaurar todo el Debian (móvil nuevo/dañado) | `tools/restore-full.sh backup/image-<fecha> [--force]` |
| Ver qué pasa | `/salud`, `/historial`, `/bateria`, `/estado` en Telegram |
| Informe para pedir ayuda (sin secretos) | `/diagnostico` en Telegram (ver abajo) |

## Equivalentes del modo sin root

| Modo root | Modo sin root |
|---|---|
| `tools/deploy.sh` | `tools/noroot-deploy.sh` |
| `tools/enable-bot.sh [off]` | `tools/noroot-bot.sh enable\|disable` |
| `tools/set-token.sh`, `tools/set-api.sh` | `tools/noroot-bot.sh token\|api` |
| `tools/edit-conf.sh` | `ssh phone nano ~/server/server.conf` |
| `tools/backup.sh` / `restore-config.sh` | `tools/noroot-backup.sh` / `noroot-restore.sh` |
| `tools/make-image.sh` / `restore-full.sh` | `proot-distro backup bot` / `proot-distro restore` (en Termux) |
| `adb connect <ip>:5555` | `ssh phone`, y `tools/noroot-adb.sh` para adb inalámbrico |

Los respaldos son intercambiables entre modos. **Migrar** (p. ej. de un móvil viejo con root a uno moderno sin root):
haz un respaldo fresco en el viejo mientras sigue funcionando → apaga el bot **allí** → `tools/noroot-restore.sh
backup/<fecha>` en el nuevo (copia token, claves de API, cookies, dueños, canales seguidos, caché, sesión MTProto,
estado de likes/Last.fm… y arranca el bot) → comprueba `/estado`, `/salud` y un enlace.

## Actualizar

* **yt-dlp / gallery-dl** se actualizan solos cada 24 h y con `/actualizar`. Los sitios cambian
  seguido; la mayoría de los «dejó de descargar» terminan aquí. Antes de actualizar el bot
  comprueba que queden al menos 300 MB libres y apunta las versiones instaladas; si `pip` falla o
  `yt-dlp`/`gallery-dl` dejan de arrancar, reinstala esas versiones y deja un `aviso` en
  `/historial`. `bot/requirements.txt` tiene las versiones con las que se probó el proyecto (las
  usa una instalación nueva). Si una versión nueva que *arranca* rompe un sitio, fija la anterior a mano:
  `adb shell su -c "/data/debian/enter.sh '/opt/bot/venv/bin/pip install yt-dlp==<versión>'"`.
* **Este proyecto:** `git pull` y luego `tools/deploy.sh`. Copia los archivos, los compila
  **en el móvil** (un error de sintaxis detiene el despliegue antes de tocar el bot) y mata
  `bot.sh` y `charge.sh` para que cada uno relance al otro con el código nuevo (~30–60 s).
* **Debian:** `adb shell su -c "/data/debian/enter.sh 'apt-get update && apt-get -y upgrade'"`.
  Hazlo de vez en cuando; haz una imagen antes si te da miedo.

## Respaldos: qué, por qué, cada cuánto

| Qué | Comando | Contiene | Guárdalo… |
|---|---|---|---|
| Configuración | `tools/backup.sh` | token, claves de API, cookies, dueños, canales de YouTube seguidos, tus canales de Telegram (`channels.json`), caché y estadísticas (`bot.db`), estado de los plugins, `server.conf`, los archivos de Android que cambiaste, la lista de apps desactivadas | **en privado** — lleva secretos |
| Todo el Debian | `tools/make-image.sh` | el chroot completo (bot, venv, Whisper…) **sin** secretos | compartible; ~1–1,5 GB |
| Código | git | este repositorio | público |

Repite `backup.sh` tras renovar cookies o cambiar algo, y la imagen tras cambios grandes.
`/salud` avisa si el último respaldo tiene más de 30 días.

### Restaurar

* **Configuración perdida:** `tools/restore-config.sh backup/<fecha>` y luego `tools/deploy.sh`.
* **Debian dañado:** `tools/restore-full.sh backup/image-<fecha> --force` (aparta el roto a
  `fs.old`), luego `tools/install.sh scripts`, `tools/restore-config.sh …`, `tools/deploy.sh`.
* **Mudarse a otro móvil:**
  1. rootéalo, prepara `config.sh`, instala busybox (`tools/install.sh busybox`), instala el lanzador de
     arranque (`tools/install.sh boot`), y luego `tools/restore-full.sh` (misma arquitectura de CPU) —
     o haz una instalación nueva ([03](03-instalacion.md)) si la arquitectura difiere (el bot es Python
     puro y corre sin cambios en arm64; solo hay que recompilar whisper.cpp);
  2. `tools/restore-config.sh backup/<fecha>`, ajusta `server.conf` (el driver de batería cambia de móvil a móvil);
  3. **primero el móvil viejo:** `tools/enable-bot.sh off`, *después* `tools/enable-bot.sh` en el nuevo.

## Informe de diagnóstico (para pedir ayuda)

`/diagnostico` (dueño, por privado) manda un archivo de texto con: versión del bot,
Python/arquitectura/kernel, tiempo encendido, carga, RAM y disco libres, batería, versiones de
yt-dlp/gallery-dl/ffmpeg, qué archivos de configuración existen (nunca su contenido), plugins,
antigüedad de la señal de vida, descargas pendientes, los últimos 30 eventos y las últimas 60
líneas de `bot.log` y `service.log`. Es de solo lectura. Antes de mandarlo oculta el token,
`api.txt`, los IDs de `owners`, cualquier número largo (IDs de chats), las IPs y la ruta de cada
enlace (solo queda el dominio). Nunca lee `cookies.txt` ni las sesiones. **Revísalo antes de
publicarlo.**

Sin Telegram, se genera dentro del Debian:
`/opt/bot/venv/bin/python3 /opt/bot/diag.py > /tmp/diagnostico.txt`
(modo root: a través de `/data/debian/enter.sh '…'`; sin root: `~/server/enter.sh '…'`).

## Resolver problemas

**El bot no contesta en Telegram.** Primero, lo automático: un bot congelado se mata a los 5 min,
uno caído se relanza con esperas crecientes, un `bot.sh` muerto lo relanza `charge.sh` en menos
de un minuto. Mira `/historial` cuando vuelva. Si sigue en silencio:

1. ¿El móvil está encendido, con batería y en el Wi-Fi? `ping <IP del móvil>`
2. `adb connect <IP del móvil>:5555` (o USB).
3. `adb shell su -c "tail -n 40 /data/debian/fs/opt/bot/service.log"`
4. Reiniciar solo el bot: `adb shell su -c "<busybox> pkill -f opt/bot/bot.py"` (`bot.sh` lo relanza en 10 s).
   Si no hay `bot.sh`: `tools/enable-bot.sh`.
5. Reiniciar el móvil: `/reiniciar confirmar`, o `adb reboot`.

**Error 409 de Telegram en `bot.log`.** Dos instancias usan el mismo token (otro móvil, o un
proceso sobrante). Desactiva el bot en todas partes menos una.

**No puedo conectar por adb Wi-Fi.** [07 · Red](07-red.md), «Escalera de recuperación».

**Un cambio rompió el bot.** `git log --oneline` → `git checkout <commit bueno> -- bot/ phone/` →
`tools/deploy.sh`. Paquetes de Python: reinstala las versiones de `bot/requirements.txt`.

**El móvil no arranca el servidor tras reiniciar.** Lee `/data/debian/boot.log` (¿corrió
`start.sh`?). KingRoot: comprueba que `grep server-boot /system/bin/ddexe` siga mostrando el gancho.
Magisk: comprueba que `/data/adb/service.d/server.sh` exista y sea ejecutable, y que ningún
gestor de módulos haya desactivado `service.d`. Una actualización de la ROM puede borrar todo eso.

**La RAM se va achicando.** Mira `/estado`: el RSS del bot debe estar entre 20 y 230 MB (más de
~100 MB sostenidos en reposo sugiere una fuga). Linux usa la RAM sobrante como caché de archivos;
importa la «disponible», no la «libre».

**Una app o la ROM se actualizó sola.** Actualizar Android en un móvil con root suele quitar el root.
En uno con bootloader bloqueado puede ser irrecuperable. Desactiva las actualizaciones automáticas
del sistema y no instales ninguna OTA.

**Perder el root.** Con KingRoot y bootloader bloqueado: da por hecho que es definitivo. Con
bootloader desbloqueable: vuelve a parchear la imagen de arranque con Magisk. Reflashear el firmware
de fábrica siempre devuelve el móvil en sí.

**Deshacerlo todo:** `tools/enable-bot.sh off`, quita el lanzador de arranque, borra `/data/debian`
(desmonta antes `/data/debian/fs/{proc,sys,dev,dev/pts,dev/shm,sdcard}` o reinicia —¡`rm -rf`
sigue los montajes bind: borraría el contenido del almacenamiento real del móvil!—),
reactiva las apps que desactivaste (`pm enable <paquete>`; la lista está en
`backup/<fecha>/android/disabled-apps.txt`).

Siguiente: [09 · Plugins](09-plugins.md).
