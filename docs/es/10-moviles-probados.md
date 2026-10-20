# 10 · Móviles probados

Tres móviles/tablets reales, con lo que necesitó cada uno y lo que midió. Úsalos como plantilla
para el tuyo. (Las cifras vienen de la instalación original, octubre de 2026.)

## De un vistazo

| | Galaxy S4 mini | Moto X2 | Galaxy Tab A7 |
|---|---|---|---|
| Modelo | Samsung SCH-I435 (Verizon) | Motorola XT1097 «victara» | Samsung SM-T500 |
| Año / Android | 2013 / **4.4.2** | 2014 / **11** (LineageOS 18.1, userdebug, microG) | 2020 / **16** (LineageOS 23) |
| CPU | Snapdragon 400, 2 núcleos 1,7 GHz, **32 bits** | Snapdragon 801, 32 bits | Snapdragon 662, 8 núcleos, **64 bits** |
| RAM | 1,3 GB + 1 GB vnswap | 2 GB + zram 1 GB | 2,7 GB + zram 2 GB |
| Libre con Debian | 7,9 GB de 11,5 | – | ~7 GB de 22 |
| Batería | 1900 mAh | 2281 mAh (sana) | 7040 mAh |
| Bootloader | **bloqueado** (Verizon) | desbloqueado | desbloqueado |
| Root | KingRoot (ruta B) | `adb root` (userdebug, ruta C) | Magisk 30.7 (ruta A) |
| `ARCH` | armhf | armhf | **arm64** |
| `ROOT_MODE` / `BOOT_MODE` | `su` / `kingroot` | `adbroot` / `initrc` | `su` / `magisk` |
| `BB_PATH` | `/system/xbin/busybox-deb` | `/data/debian/busybox-deb` | `/data/debian/busybox-deb` (busybox de Magisk) |
| `BATT_CTRL` | `slate` | `enable` | `slate` |
| Especial en `server.conf` | valores por defecto, `LOW=40 HIGH=60` | `FIX_ROUTE=1`, `ADB_TCP_PROP=persist.adb.tcp.port`, `LOW=25 HIGH=65` | `DOZE_OFF=1`, `LINEAGE_CHARGE_CTRL_OFF=1`, `WIFI_MIN=-85`, `ADB_RESTART="setprop ctl.restart adbd"` |
| Papel | producción 24/7 | repuesto en frío | banco de pruebas / candidata |

## Galaxy S4 mini (Verizon SCH-I435, Android 4.4.2) — la referencia

* Debian 13 armhf en un chroot, Python 3.13, ffmpeg 7.1, Node 20. Proceso del bot: 19–45 MB.
* Root con KingRoot; **nunca lo quites ni lo actualices** (bootloader bloqueado).
* Manías: `sec_restrict_fork` (busybox debe vivir en `/system/xbin`); SELinux bloquea
  `install-recovery.sh` (de ahí el gancho en `ddexe`); `batt_slate_mode` para el cargador;
  Android 4.4 se queda con el primer punto de acceso; adbd atiende una conexión a la vez; Android
  4.4 no trae los certificados raíz de Let's Encrypt (añade ISRG Root X1/X2 a
  `/system/etc/security/cacerts/` si hacen falta herramientas del lado Android; el chroot usa
  los de Debian).
* 195 paquetes preinstalados desactivados (quedan 50 activos) para liberar RAM; ~980 MB disponibles en reposo.
* El AES en Python de Telethon iba a 0,5 MB/s en esta CPU; **TgCrypto** (C) subió las subidas a ~3,5 MB/s.
* `libvosk.so` necesita `patchelf --clear-execstack` o glibc 2.41 se niega a cargarla.

Medido (Wi-Fi 802.11n 5 GHz, junto al router, ~50–66 Mbps de bajada / ~48–54 de subida):

| Tarea | Tiempo |
|---|---|
| Enlace de TikTok / Instagram / Threads | 5–20 s |
| Vídeo de YouTube de 154 MB (descarga + subida por la vía de 2 GB) | ~2 min (subida ~3,5 MB/s) |
| Reenviar un enlace en caché | ~0,3 s |
| `/mp3` de 10 min de audio | ~95 s |
| Nota de voz: borrador Vosk / final Whisper `base` | segundos / ~4× la duración del audio |
| Whisper `small` | ~13× la duración del audio (demasiado lento aquí) |
| 3 descargas simultáneas de YouTube | sin swap; RAM disponible mínima 886 MB |

## Moto X2 (Android 11, LineageOS 18.1) — el repuesto en frío

* Mismo chroot y scripts; `ROOT_MODE=adbroot`. Hay que repetir `adb root` tras cada reinicio.
* Sin `su`: los archivos se instalan con `/` remontado en escritura; arranque por `init.rc`.
* Manías: Android 11 necesita `FIX_ROUTE=1`; sin lanzador ni systemui, Android se queda en
  *«Iniciando teléfono»* (`server-boot.sh` corta la animación de arranque y duerme la pantalla);
  `charging_enabled` para el cargador.
* **Nunca desactives `com.android.permissioncontroller`**: `system_server` se cae en bucle en el
  siguiente reinicio («There must be exactly one permissions manager; found []»), `sys.boot_completed`
  no llega nunca y `pm` deja de responder. Arreglo: borrar la entrada `enabled="3"` de ese paquete en
  `/data/system/users/0/package-restrictions.xml` (adb root sigue funcionando). Prueba cada lote de
  apps desactivadas con un reinicio.
* Procesos como `systemui` y `nfc` reaparecen aunque estén desactivados; RAM libre tras arrancar ~760–890 MB.
* El bot está instalado pero desactivado (sin `BOT_ENABLED`): el mismo token no debe correr dos veces.

## Galaxy Tab A7 (SM-T500, Android 16, LineageOS 23) — la opción más rápida

* Debian 13 **arm64**; whisper.cpp recompilado para la CPU (3 min 23 s frente a 10+ min en el S4).
* Busybox de Magisk (1.36.1 aarch64) en `/data/debian/busybox-deb`; arranque por `service.d`.
* Sin basura: 81 apps y 4 módulos de Magisk desactivados, Bluetooth/ubicación apagados. RAM disponible
  en reposo 698 → **1050 MB**, procesos de apps de Android 25 → 9 y —más valioso que la velocidad— los
  tiempos dejaron de variar.
* Manías descubiertas: el horario de carga de LineageOS (22:00–06:00) cortaba el cargador y la tablet
  se quedó sin batería «enchufada» → `LINEAGE_CHARGE_CTRL_OFF=1`; no actualices LineageOS sin volver a
  parchear Magisk (sin root no arranca nada); el `stop; start` del framework (que usa el script de
  fijar banda) reactiva Doze, así que se vuelve a apagar después.

Medido frente al S4 mini:

| Tarea | S4 mini | Tab A7 |
|---|---|---|
| Nota de voz, Whisper `base` | ~4× la duración | ~0,2–0,5× (8–10× más rápido) |
| Nota de voz, Whisper `small` | ~13× | ~1,2–1,4× |
| Subida grande | 3,5 MB/s | ~8 MB/s (**×2,3**) |
| `/mp3` | – | ×4 más rápido |
| YouTube de 255 MB (descarga + subida) | – | 105 s |
| 1,6 GB en 1080p (descarga + unión) | – | 6 min 42 s |
| Descarga de enlace (TikTok/X/Threads) | 5–20 s | 8–14 s (limitado por la red) |
| Prueba de velocidad Wi-Fi | 50–66 ↓ / 48–54 ↑ Mbps (junto al router, 802.11n) | 180 ↓ / 115 ↑ Mbps (5 GHz, −57 dBm, 802.11ac, repetidor cerca) |
| Autonomía en un apagón | 1900 mAh | 7040 mAh (**4×**) |
| Memoria del proceso del bot | 19–45 MB | 78 MB (pico 226 MB, 64 bits) |

Lo que **no** mejora: las descargas normales (las limita tu Internet y los sitios), y todo lo que
dependa del punto de acceso y no del móvil.

## Añade tu móvil

Si lo instalas en otro modelo, manda por favor un pull request con una sección como las de arriba:
modelo, Android, ABI, ruta de root, `BB_PATH`, `BATT_CTRL`, qué tuviste que cambiar y un par de
medidas. Los intentos fallidos valen tanto como los éxitos.
