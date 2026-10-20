# old-phone-server

**Convierte un móvil Android viejo en un servidor Linux 24/7 — incluso un móvil de 2013 donde nada más corre.**

🇬🇧 [English README](README.md)

Un móvil con root, un chroot de Debian, un par de vigilantes que lo mantienen todo vivo, límites de carga
que protegen la batería, y una aplicación real encima: un **bot de Telegram que descarga vídeos y fotos
de redes sociales** (subidas de hasta 2 GB, transcripción de notas de voz en el propio móvil, seguimiento
de canales de YouTube, informes de salud). Se construyó en un **Galaxy S4 mini (2013, Android 4.4)** que
lleva trabajando 24/7, y luego se reprodujo en un **Moto X2 (Android 11)** y en una **Galaxy Tab A7 (Android 16)**.

```
 Android (root) ─► start.sh ─┬─► bot.sh     mantiene vivo el bot (espera creciente tras caídas)
   lanzador de arranque      └─► charge.sh  vigilante: bot colgado · Wi-Fi/Internet · batería 40–60 %
 /data/debian/fs = Debian 13 (chroot)  ─►  /opt/bot: bot.py + plugins  ◄──►  Telegram
```

## ¿Es para ti?

| Tu móvil | Usa |
|---|---|
| **Android 4.4–9, 32 o 64 bits, se puede rootear, debe funcionar 24/7** | **este proyecto** |
| Android 10+, 64 bits, sin root | [homedroid](https://github.com/sudiptacmd/homedroid) |
| 64 bits, sin root, quiere escritorio / Home Assistant | [mayukh4/linux-android](https://github.com/mayukh4/linux-android) |
| Con root, quiere una guía sencilla con Termux | [MultiX0/old-phone-to-server](https://github.com/MultiX0/old-phone-to-server), [Android-Phone-as-Server](https://github.com/Nikhil-Richhariya/Android-Phone-as-Server) |

Son proyectos independientes. Lo que añade este: soporte para móviles donde el Termux actual no se puede
instalar, un chroot nativo (sin la lentitud de proot) y la parte poco vistosa de operar 24/7 — vigilantes,
esperas ante caídas, recuperación del Wi-Fi, **límite de carga de la batería**, respaldos/restauración y
un procedimiento de recuperación para cada fallo que de verdad ocurrió.

## Inicio rápido

Necesitas: el móvil **ya con root** ([guía](docs/es/02-root.md)), un PC con `adb` y bash
(Git Bash en Windows) y una cuenta de Telegram. Los detalles y explicaciones están en las [guías](#guías).

```bash
git clone https://github.com/Tylosaurus-AFC/old-phone-server.git && cd old-phone-server
cp config.example.sh config.sh && $EDITOR config.sh      # ARCH, PHONE_IP, ROOT_MODE, BOOT_MODE, BB_PATH…

tools/fetch-assets.sh          # Debian 13 para tu CPU (+ busybox) → downloads/
tools/install.sh check         # ¿qué móvil es? (también muestra los archivos de control de batería)
tools/install.sh busybox       # busybox en el móvil
tools/install.sh rootfs        # descomprimir Debian
tools/install.sh scripts       # enter.sh, bot.sh, charge.sh, start.sh, server.conf
tools/edit-conf.sh             # ← pon tu driver de batería (docs/es/06-bateria-y-calor.md)
tools/install.sh provision     # paquetes + entorno Python dentro de Debian (10–30 min)
tools/install.sh boot          # que arranque al encender (sigue las notas impresas para KingRoot)

tools/set-token.sh             # token de @BotFather
tools/deploy.sh                # subir el bot
tools/enable-bot.sh            # ¡a andar!  luego manda /start a tu bot — la primera persona queda como dueña
```

## Qué obtienes

* **Lo básico de un servidor, en un móvil:** wake-lock, Wi-Fi que nunca duerme, adb por Wi-Fi, reinicio
  tras caídas con espera exponencial, detección de procesos congelados con señal de vida, recuperación del
  Wi-Fi y de Internet, persistencia al arrancar para tres tipos de root (Magisk, KingRoot, init.rc).
* **Cuidado de la batería:** mantiene la carga al 40–60 %, para por encima de 42 °C, nunca la deja morir,
  detecta apagones y cuenta cuánto aguantó. Soporta `batt_slate_mode` de Samsung, `charging_enabled`, o ninguno.
* **El bot de Telegram** (mensajes en español): descargas de más de 1000 sitios con yt-dlp/gallery-dl, 1080p,
  subidas de 2 GB por MTProto, caché instantánea, MP3, PDF → imágenes, canales de YouTube seguidos, control
  de acceso por usuario, manejo de cookies, actualización diaria automática, `/salud` `/historial` `/bateria`,
  voz a texto local.
* **Plugins:** extras que se enchufan — fotos de cámaras de seguridad (Dahua), avisos por Alexa,
  scrobbling de YouTube Music a Last.fm, stickers de vídeo — y una API sencilla para los tuyos.
* **Operación:** despliegue, respaldo/restauración de la configuración y de todo el Debian, mudanza a otro móvil.
* **Pruebas que no necesitan móvil:** `tests/run.sh` (lógica de batería contra una batería falsa, carga de
  plugins, despacho de comandos, utilidades).

## Guías

English: [docs/en](docs/en/) · Español: [docs/es](docs/es/)

| | |
|---|---|
| [00 Resumen](docs/es/00-resumen.md) | qué es, por qué, cómo funciona, otros proyectos |
| [01 Preparación](docs/es/01-preparacion.md) | herramientas del PC, adb, `config.sh` |
| [02 Root](docs/es/02-root.md) | elegir cómo rootear, con honestidad |
| [03 Instalación](docs/es/03-instalacion.md) | busybox, Debian, scripts, paquetes, problemas |
| [04 Bot de Telegram](docs/es/04-bot-telegram.md) | token, dueño, comandos, cookies, voz |
| [05 Servicios y arranque](docs/es/05-servicios-y-arranque.md) | cadena de arranque, vigilantes, `server.conf` |
| [06 Batería y calor](docs/es/06-bateria-y-calor.md) | **seguridad**, límite de carga, drivers |
| [07 Red](docs/es/07-red.md) | IP fija, adb por Wi-Fi, puntos de acceso pegajosos, Ethernet |
| [08 Operación](docs/es/08-operacion.md) | actualizar, respaldar, restaurar, resolver problemas |
| [09 Plugins](docs/es/09-plugins.md) | usar y escribir plugins |
| [10 Móviles probados](docs/es/10-moviles-probados.md) | S4 mini, Moto X2, Tab A7: manías y medidas |
| [11 FAQ y seguridad](docs/es/11-faq-y-seguridad.md) | legal, seguridad, créditos |

## Estado — léelo

* El diseño viene de tres equipos que corrieron en producción o en el banco de pruebas. Los scripts
  **unificados** de este repositorio (un solo `charge.sh`/`start.sh`/`server.conf` para todos, que sustituye
  a tres copias específicas de cada equipo) se armaron después: pasan las pruebas automáticas
  (`tests/run.sh`: 47 comprobaciones) pero **todavía no se han revalidado en cada dispositivo físico** —
  trata tu primera instalación como una validación, empieza con el bot desactivado y
  [cuéntanos qué encuentras](CONTRIBUTING.md).
* Sin probar con hardware real: adaptadores USB-Ethernet, scripts de voz en arm64 en otras CPU,
  cámaras que no sean Dahua, móviles x86.
* Rootear es arriesgado y depende del modelo; este repositorio no lo hace por ti.
  Descargar contenido puede infringir los términos de los sitios o los derechos de autor: **tú** eres
  responsable de para qué lo usas ([FAQ](docs/es/11-faq-y-seguridad.md)).

## Estructura

```
bot/            el bot de Telegram (bot.py, bigupload, health, pending, stt, thumbs)
extras/plugins/ plugins opcionales: cameras, alexa, stickers, lastfm_scrobbler
phone/          scripts que corren en el móvil (enter, bot, charge, start, lanzadores de arranque, extras)
tools/          scripts que corren en tu PC (fetch-assets, install, deploy, backup, restore…)
tests/          pruebas que no necesitan móvil
docs/{en,es}/   las guías
```

## Contribuir

Añade tu móvil a [Móviles probados](docs/es/10-moviles-probados.md), cuenta qué se rompió, traduce los
textos del bot o escribe un plugin. Ver [CONTRIBUTING.md](CONTRIBUTING.md). El código tiene licencia MIT
([LICENSE](LICENSE)); las herramientas de terceros que instala tienen sus propias licencias.
