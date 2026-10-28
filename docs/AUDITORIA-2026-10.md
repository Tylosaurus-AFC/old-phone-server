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
| 20 | Media | El instalador sin root empezaba sin comprobar si el móvil puede y no decía qué faltaba al terminar. | Corregido: `tools/noroot-install.sh check` (también al inicio de `packages`); `scripts` y `noroot-bot.sh enable` terminan con `doctor.sh` |

Análisis completo, perfiles por fabricante y matriz: [`docs/es/14-sin-root-fiabilidad.md`](es/14-sin-root-fiabilidad.md).
Lo que `doctor.sh` lee de Android (`dumpsys`, `am`, etiqueta del wake lock) sale de la documentación y
del código de Android/Termux, **no de un móvil**: un formato distinto saldría como aviso, nunca como fallo del script.

| 21 | **Crítica** | El `charge.sh` sin root abortaba cada vuelta con Shizuku caído y Termux:API sin respuesta (aritmética sobre un voltaje vacío): ni relanzaba el bot ni recuperaba el Wi-Fi, justo en el caso degradado. | Corregido, con pruebas que fallan en el código anterior |
| 22 | Alta | Shizuku caído solo se veía como «no responde»: sin causa, sin rearranque y con ~40 s de esperas en cada vuelta. | Corregido: `shizuku.sh`, aviso START con `SHIZUKU_AUTH` y esperas crecientes |
| 23 | Alta | Sin avisos proactivos; los avisos sueltos no confirmaban la entrega. | Corregido: `bot/alerts.py` |
| 24 | Alta | Nadie avisa de un bot muerto. | Corregido: mensaje del vigilante con curl |
| 25 | Alta | Con PIN/contraseña nada arranca tras un reinicio hasta desbloquear. | Documentado; doctor lo detecta si Android informa del tipo de bloqueo |
| 26 | Media | Ajustes anti-cierre aplicados a ciegas. | Corregido: se comprueban, aviso único y esperas |
| 27 | Media | El puente de WhatsApp de referencia escucha en todas las interfaces sin autenticación. | Anotado en la evaluación ([15](es/15-whatsapp-evaluacion.md)) |

Catálogo de escenarios y pruebas: [`docs/FAILURE-CATALOG.md`](FAILURE-CATALOG.md). Suite completa ~90 s.

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
10. Rearranque de Shizuku con `SHIZUKU_AUTH`, Shizuku tras reiniciar en una red nueva, avisos con el router apagado y el mensaje de bot muerto (procedimientos en `docs/es/14-sin-root-fiabilidad.md`).

No hay compatibilidad nueva verificada con ningún dispositivo ni versión de Android.

## Actualizar y revertir

`git pull` y el script de despliegue de siempre; no hay migraciones. Para revertir, desplegar el
commit anterior. `NET_HOSTS` en `server.conf` lo ignoran los scripts antiguos.

## Integración en main (28-10-2026)

`main` avanzó (fast-forward) hasta `8782efe`, conservando los hashes, y recibió con `cherry-pick -x` los
avisos por cambio de estado (`969a9c3`), la compatibilidad con Python 3.11 y la CI en 3.11/3.13 (`d7a3e64`)
y la robustez de `/diagnostico` y `/salud` (`cc88c51`), más este commit de unión. Siguen solo en
`claude/maintenance-and-tests_by_claude`, pendientes de revisión o de un móvil real: la detección del estado
de Shizuku y su rearranque con el aviso START del fork (`502cc50`), el mensaje del vigilante cuando el bot
está muerto (`2ea9b02`) y su documentación, la evaluación de WhatsApp y el catálogo de fallos (`7827800`).
La CI no pasó nunca antes de `d7a3e64` (una f-string de Python 3.12+ que ya estaba en main); los informes
anteriores no lo detectaron.

## Sexta tanda (28-10-2026): integración, auditoría de Shizuku, simulaciones largas, códigos de salida

**Correcciones a informes anteriores.** (1) La CI añadida en la primera tanda nunca pasó: una f-string de
Python 3.12+ que ya estaba en main rompía las pruebas del bot en el Python 3.11 de la CI; nadie miró las
ejecuciones. Corregido (`d7a3e64`); la CI usa 3.11 y 3.13 y está en verde. (2) «La Shizuku oficial solo
arranca al encender con root» estaba desfasado: la v13.6.0 arranca por depuración inalámbrica en Android 13+
(un intento). (3) La matriz daba como «esperado» el arranque desatendido de Shizuku en Android 11–12: falso,
esas versiones olvidan las redes permitidas en cada reinicio (corregido en Android 13). (4) Las comprobaciones
del bot del primer arnés de simulación larga no probaban nada hasta crear allí `BOT_ENABLED`.

| # | Gravedad | Hallazgo (todos reproducidos antes de corregir) | Estado |
|---|---|---|---|
| 28 | Alta | Los vigilantes (ambos modos) reiniciaban el Wi-Fi cada 5 min durante todo un corte: 288 reinicios/eventos al día | Corregido: 5, 10, 20, 40 y luego 60 min |
| 29 | Alta | El mensaje de «bot muerto» saltaba en cada reinicio (señal de vida vieja en disco) | Corregido |
| 30 | Alta | `noroot-restore.sh` decía «Done» tras fallar la extracción; `restore-config.sh` contaba copias fallidas; respaldos sin token se anunciaban como buenos | Corregido, salida 1 con explicación |
| 31 | Media | `/diagnostico` y `/salud` fallaban con archivos raros | Corregido |
| 32 | Media | El servidor mandaría START a la Shizuku oficial y pelearía con un usuario que la para a propósito | Corregido: detección de variante, `~/server/no-shizuku-restart` |
| 33 | Baja | Las pruebas dejaban procesos `sleep` huérfanos | Corregido |

Ejecución LONG=1 de `tests/test_longrun.sh` sobre una copia congelada de `41d6e11` (28-10-2026, este PC):
escenarios A (corte), B (fallos encadenados) y C (fallos aleatorios, semilla 20261028) a 12, 24, 48 y 72 horas
simuladas — 124/124 comprobaciones superadas; reinicios del Wi-Fi en el corte de 72 h: unos 74 (con la lógica
anterior, 852). Las horas simuladas prueban la lógica del vigilante; aún no hay una prueba física larga.
