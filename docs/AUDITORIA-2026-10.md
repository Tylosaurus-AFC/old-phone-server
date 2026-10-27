# Auditoría de mantenimiento — octubre de 2026

Versión en español de [`AUDIT-2026-10.md`](AUDIT-2026-10.md) (si difieren, manda la inglesa, que
tiene el detalle). Revisión hecha **sin teléfono**: todo sale de leer el código y de ejecutar
`tests/run.sh` en un PC Linux (x86_64, Python 3.11, sin red). Nada se ha comprobado en hardware real.

## Arquitectura encontrada

* **PC** `tools/*.sh` (bash): instalar, desplegar, respaldar/restaurar por adb (root) o SSH (sin root).
* **Modo root** `phone/*.sh` (sh de Android + busybox): Debian en chroot en `/data/debian`;
  `start.sh` al arrancar → `charge.sh` (vigilante cada minuto, límite de carga) y `bot.sh`
  (supervisor con esperas crecientes).
* **Modo sin root** `phone/noroot/*.sh` (bash de Termux): Debian en proot-distro; Shizuku para el
  acceso a Android; `guard.sh` reabre Termux si Android lo cierra. El límite de carga lo pone el
  fabricante: los scripts solo lo leen.
* **Bot** `bot/` (Python): Telegram, descargas con yt-dlp/gallery-dl, ffmpeg, plugins.

## Problemas y estado

| # | Prioridad | Problema | Estado |
|---|-----------|----------|--------|
| 1 | Alta | El hilo de actualización diaria moría con cualquier excepción (p. ej. timeout de pip). | Corregido |
| 2 | Alta | `pip install -U` sin mirar el espacio ni poder volver atrás. | Corregido: ≥300 MB, versiones anotadas, reversión |
| 3 | Media | Sin forma de pedir ayuda sin exponer secretos. | Corregido: `/diagnostico` (`bot/diag.py`) |
| 4 | Media | Sin root, la comprobación de Internet estaba fija en 1.1.1.1/8.8.8.8. | Corregido: `NET_HOSTS` |
| 5 | Baja | Sin CI ni búsqueda de secretos. | Corregido |
| 6 | Baja | `service.log` solo se recorta al reiniciar el bot. | Abierto (riesgo bajo) |
| 7 | Baja | En root, `bot.sh` espera a que responda un ping (`PING_HOST`). | Documentado |
| 9 | Alta | Faltaba `on_button`: ningún botón del bot funcionaba. | Corregido |
| 10 | Alta | Las listas de respaldo/restauración no coincidían y se perdía configuración (`channels.json`, `likes.json`, `bot.db`, `device.json`). | Corregido + test |
| 11 | Media | `restore-config.sh` sobrescribía archivos con el bot en marcha. | Corregido: copia temporal + `mv` |
| 12 | Media | Sin `USB_SERIAL` ni `PHONE_IP` se intentaba conectar a `:5555`; sin `adb` el mensaje era confuso. | Corregido: `check_config()` |
| 13 | Media | Sin root, la comprobación de SSH se tragaba la entrada: un token pasado por tubería se perdía. | Corregido: `</dev/null` |
| 14 | Baja | `noroot-bot.sh api` no validaba `api_hash`; `set-api.sh` solo el primer carácter. | Corregido: 32 hexadecimales |
| 15 | Baja | `fetch-assets.sh` con `ARCH` incorrecto o ausente descargaba de una URL inexistente. | Corregido |
| 16 | Baja | `noroot-adb.sh` con `NOROOT_IP` vacío aceptaba cualquier dispositivo. | Corregido |
| 17 | Alta | Las exenciones anti-cierre (batería, segundo plano, grupo de espera, phantom killer de Android 12+) se hacían a mano una vez; Android, el fabricante o Google Play Services pueden deshacerlas sin que nada lo note. | Corregido: `charge.sh` las reaplica por Shizuku al aparecer y cada 30 min (`KEEPALIVE=0` para no tocarlas) |
| 18 | Alta | No había forma de saber si el móvil está preparado para sobrevivir (p. ej. Termux:Boot nunca abierto o forzado a detenerse). | Corregido: `doctor.sh`, `tools/noroot-doctor.sh`, en `/salud` y `/diagnostico` |
| 19 | Media | `boot.sh` se ejecuta también al reabrir Termux y lanzaba otro bucle vigilante cada vez. | Corregido: `loop.pid` |

Análisis completo, perfiles por fabricante y matriz: [`docs/es/14-sin-root-fiabilidad.md`](es/14-sin-root-fiabilidad.md).
Lo que `doctor.sh` lee de Android (`dumpsys`, `am`, etiqueta del wake lock) sale de la documentación y
del código de Android/Termux, **no de un móvil**: un formato distinto saldría como aviso, nunca como fallo del script.

Se mantiene a propósito: un `ROOT_MODE` desconocido (p. ej. `magisk`) sigue funcionando como `su`
y un `BOOT_MODE` desconocido significa «instálalo a mano»; `ROOT_MODE` y `ARCH` solo **avisan**.

## Pruebas (entorno de desarrollo)

`tests/run.sh` completo, ~27 s, todo en verde: sintaxis, búsqueda de secretos, `ruff`, listas de
respaldo 5/5, herramientas del PC 46/46, `test_charge` 17/17, `test_noroot` 20/20,
`test_services` 9/9, `test_bot` 42/42, `test_doctor` 31/31 (`test_noroot` 26/26, herramientas 48/48 tras la cuarta tanda).

`tests/test_tools.sh` usa `adb`, `ssh`, `curl` y `sleep` falsos que registran lo que se ejecutaría
en el móvil sin ejecutarlo. Con las herramientas antiguas da 11 fallos.

**Límites de la simulación:** los falsos aceptan todo; no reproducen errores reales de adb/ssh,
las rutas de Windows/Git Bash, los shells del móvil (mksh, busybox, Termux) ni los tiempos. Los
scripts que corren en el móvil solo se comprueban con `sh -n`, no se ejecutan.

## Pendiente de validar en un teléfono real

1. Desplegar y comprobar `/salud` y un enlace.
2. `/diagnostico`: que llegue y no contenga token, IDs, IPs ni rutas de enlaces.
3. `/actualizar` y la reversión cuando pip falla.
4. Botones MP3/Original/NAS, `/help`, `/stats`, `/cola`; un usuario que no es el dueño no puede usar los del dueño.
5. Respaldo y restauración reales en ambos modos con `channels.json`, `likes.json`, `bot.db`, `device.json`.
6. Herramientas del PC en Windows (Git Bash) y Linux con `config.sh` correcto e incorrecto.
7. `printf 'TOKEN\n' | tools/noroot-bot.sh token` guarda el token.
8. `NET_HOSTS` en Termux.
9. `tools/noroot-doctor.sh` en un móvil sano y tras forzar la detención de Termux:Boot; las pruebas prolongadas de `docs/es/14-sin-root-fiabilidad.md`.

No hay compatibilidad nueva verificada con ningún dispositivo ni versión de Android.

## Actualizar y revertir

`git pull` y el script de despliegue de siempre; no hay migraciones. Para revertir, desplegar el
commit anterior. `NET_HOSTS` en `server.conf` lo ignoran los scripts antiguos.
