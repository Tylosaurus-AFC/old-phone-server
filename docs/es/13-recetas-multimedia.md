# 13 · Recetas de servidor multimedia (opcional)

Un móvil viejo con un disco USB es un **NAS y servidor multimedia** perfectamente válido junto al bot. Estas son
recetas de la instalación del Realme 12+ ([12 · Modo sin root](12-modo-sin-root.md)), aparte porque son opcionales
y dependen del equipo. Viven en [`phone/noroot/extras/`](../../phone/noroot/extras/) y el `charge.sh` sin root las
arranca y vigila con dos ajustes de `~/server/server.conf`:

```sh
SERVICES="webdav dlna jellyfin"      # se arrancan si hay disco USB montado y se relanzan si caen
NIGHTLY="youtube-mirror.sh 3"        # una vez al día, a las 4:00
WEEKLY_BACKUP=1                      # domingos a las 4:00: extras/backup.sh
```

`touch ~/server/no-<nombre>` apaga uno sin editar nada (`no-nightly` para el trabajo nocturno). Registros:
`~/server/svc/<nombre>.log`. Un móvil en modo root puede hacer lo mismo a mano; no hay supervisión automática
para esto en modo root.

> **Solo en tu red local.** WebDAV es HTTP plano con una contraseña compartida. No redirijas estos puertos en el router.

## El disco USB

* Un móvil con USB-OTG y un hub con alimentación (o un disco autoalimentado). Android lo monta como almacenamiento
  *público*; Termux lo ve en `/storage/<UUID>` y `enter.sh` lo monta dentro de Debian en **`/mnt/disk`**
  (`charge.sh` encuentra el UUID con `sm list-volumes public`). `charge.sh` deja además un archivo `.nas` en la
  raíz del disco: el espejo, el respaldo y el `/guardar` del bot solo escriben si está, así con el disco
  desconectado nunca llenan el almacenamiento del propio móvil. No lo borres.
* **Fórmatealo en exFAT**, no NTFS: Android monta exFAT con el controlador del kernel (NTFS va por
  `ntfs-3g`/FUSE) y lo leen Windows, macOS, TVs y casi todo. Desde el usuario shell
  (`~/server/sa.sh "sm list-disks; sm partition disk:<id> public"` — **esto borra el disco**).
* Medido en un disco de 2,5" tras un adaptador USB 2.0: exFAT escritura **38 MB/s** (el techo de USB 2.0),
  lectura ~57 MB/s, ~850 archivos pequeños/s al escribir; NTFS por FUSE escribía 36,5 MB/s; el almacenamiento
  interno del móvil, 548 MB/s.

## NAS: WebDAV

`extras/webdav.sh` sirve el disco con `rclone serve webdav` en el puerto **8080**.

```bash
pkg install rclone                                   # en Termux
mkdir -p ~/.config/server && echo 'una-clave-larga' > ~/.config/server/webdav.pass
# server.conf:  SERVICES="webdav"      (usuario: WEBDAV_USER, por defecto «webdav»)
```

Desde tu PC: *Conectar unidad de red* de Windows con `http://<ip-del-móvil>:8080`, o cualquier cliente WebDAV.
Medido por Wi-Fi: **~19 MB/s subiendo, ~12 MB/s bajando** (SFTP por `ssh phone`: 10–16 MB/s).

## DLNA

`extras/dlna.sh` (`rclone serve dlna`, nombre `DLNA_NAME`, por defecto «Phone server», puerto HTTP 7879, descubrimiento
SSDP por UDP 1900, solo lectura). Responde por HTTP. **No se confirmó que una TV/VLC lo descubra**: desde el PC no
llegó ninguna respuesta SSDP (de ningún aparato), probablemente el firewall de Windows. Pruébalo desde la propia TV.

## Jellyfin

`extras/jellyfin.sh` corre Jellyfin (web + apps, puerto **8096**) *dentro del contenedor Debian*, con datos y caché
en la memoria interna (`/opt/jellyfin`). Instálalo en el contenedor siguiendo las instrucciones de Jellyfin para
Debian (su repositorio apt: `jellyfin` + `jellyfin-ffmpeg`); en el Realme fue Jellyfin 12.2 en arm64.

* Arranca en ~20 s. La primera vez: abre `http://<ip-del-móvil>:8096`, haz el asistente y añade una biblioteca
  apuntando a `/mnt/disk`.
* Recodificar 1080p → 720p fue a 1,2× tiempo real: un vídeo a la vez. Mejor reproducción directa (H.264, que es lo
  que produce el espejo de abajo).

## Respaldo semanal

`WEEKLY_BACKUP=1` lanza `extras/backup.sh` los domingos a las 4:00 (o a mano): los ajustes y secretos del bot
(token, cookies, dueños, canales seguidos, `bot.db`…) a `/mnt/disk/Backups/bot-AAAAMMDD.tgz`, conservando los 8
últimos. Lleva el token, así que las recetas de WebDAV y DLNA **no** sirven `Backups/`.

## Espejo de YouTube

`extras/youtube-mirror.sh [N]` baja los N vídeos más nuevos de cada canal que sigue el bot (`/opt/bot/subs.json`) a
`/mnt/disk/YouTube/<canal>/<fecha> - <título> [<id>].mp4` (+ miniatura): H.264 ≤ 1080p ≤ 30 fps (un Apple TV 3 no
reproduce 60 fps), sin Shorts ni directos. Conserva los 10 más nuevos por canal (`KEEP=N`) y borra los anteriores;
siguen en `.archive.txt`, así que no se vuelven a bajar. Prueba con tres canales, 2 vídeos cada uno: **6 vídeos,
9,6 GB en 48 minutos**. Lánzalo a mano o con `NIGHTLY="youtube-mirror.sh 3"`.

## AirPlay a un Apple TV viejo (sin probar con un Apple TV real)

`extras/airplay.sh scan` / `airplay.sh <ip-del-apple-tv> <ruta-en-el-disco>` sirve una carpeta por HTTP y la reproduce
con [pyatv](https://pyatv.dev) (`python3 -m venv /opt/airplay && /opt/airplay/bin/pip install pyatv` dentro del
contenedor). pyatv 0.18 se instaló y corrió; el Apple TV de las pruebas estaba apagado, así que la reproducción en sí
no está verificada.

## Hubs USB: qué salió mal

Un hub USB-C cargaba el móvil en modo anfitrión (`power_role=sink`, `data_role=host`), pero con **Ethernet + disco +
carga a la vez se cayó dos veces** (una entero, otra solo los datos) y el **adaptador Ethernet negoció solo 10 Mbit/s**
(8 Mbit/s reales, 350 ms de ping). Android prefiere el cable, así que el bot salía a Internet a 8 Mbit/s hasta que se
quitó el Ethernet. Sin el Ethernet, el disco y la carga se mantuvieron estables. Arreglos sin probar: otro cable o
puerto del switch, un disco autoalimentado, o un hub con fuente propia. Lección: mide `/velocidad` tras enchufar
cualquier cosa que se apodere de la ruta por defecto.
