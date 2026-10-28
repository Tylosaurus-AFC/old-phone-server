# old-phone-server

**Convierte un móvil Android viejo en un servidor Linux 24/7 — con root (incluso un móvil de 2013) o sin él.**

🇬🇧 [English README](README.md)

Un Debian en tu móvil (un chroot si lo puedes rootear, Termux + proot si no), un par de vigilantes que lo mantienen
todo vivo, límite de carga que protege la batería, y una aplicación real encima: un **bot de Telegram que descarga vídeos y fotos
de redes sociales** (subidas de hasta 2 GB, transcripción de notas de voz en el propio móvil, seguimiento
de canales de YouTube, informes de salud). Se construyó en un **Galaxy S4 mini (2013, Android 4.4)** que
lleva trabajando 24/7, y luego se reprodujo en un **Moto X2 (Android 11)**, una **Galaxy Tab A7 (Android 16)** y, **sin
root**, un **Realme 12+ 5G (Android 16)**.

```
 Android (root) ─► start.sh ─┬─► bot.sh     mantiene vivo el bot (espera creciente tras caídas)
   lanzador de arranque      └─► charge.sh  vigilante: bot colgado · Wi-Fi/Internet · batería 40–60 %
 /data/debian/fs = Debian 13 (chroot)  ─►  /opt/bot: bot.py + plugins  ◄──►  Telegram
```

## ¿Es para ti?

| Tu móvil | Usa |
|---|---|
| **Android 4.4–10, 32 o 64 bits, se puede rootear, debe funcionar 24/7** | **este proyecto — modo root** |
| **Android 11+, no puedes / no quieres rootear, un servicio 24/7** | **este proyecto — [modo sin root](docs/es/12-modo-sin-root.md)** (Termux + proot + Shizuku) |
| Android 10+, 64 bits, sin root, quiere apps ya hechas | [homedroid](https://github.com/sudiptacmd/homedroid) |
| 64 bits, sin root, quiere escritorio / Home Assistant | [mayukh4/linux-android](https://github.com/mayukh4/linux-android) |
| Con root, quiere una guía sencilla con Termux | [MultiX0/old-phone-to-server](https://github.com/MultiX0/old-phone-to-server), [Android-Phone-as-Server](https://github.com/Nikhil-Richhariya/Android-Phone-as-Server) |

Son proyectos independientes. Lo que añade este: soporte para móviles donde el Termux actual no se puede
instalar, un chroot nativo *y* un modo sin root, y la parte poco vistosa de operar 24/7 — vigilantes,
esperas ante caídas, recuperación del Wi-Fi, **límite de carga de la batería**, respaldos/restauración y
un procedimiento de recuperación para cada fallo que de verdad ocurrió.

## Inicio rápido — modo root

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

## Inicio rápido — modo sin root

Necesitas: un móvil moderno (se recomienda Android 13+; en 11–12 hay que pulsar *Permitir* tras cada reinicio), un PC con `adb`, `ssh` y bash. Primero, a mano (la
[guía](docs/es/12-modo-sin-root.md) te lleva): instala Termux, Termux:Boot y Termux:API desde GitHub/F-Droid, quítales
las restricciones de batería, prepara SSH a Termux y Shizuku (fork de thedjchi) + `rish`. Luego:

```bash
cp config.example.sh config.sh && $EDITOR config.sh      # NOROOT_SSH, NOROOT_IP, TZ_NAME…
tools/noroot-install.sh check        # ¿puede este móvil?
tools/noroot-install.sh packages     # proot-distro, openssh, termux-api, jq
tools/noroot-install.sh container    # contenedor Debian 13 «bot» (desde Docker Hub)
tools/noroot-install.sh provision    # entorno Python, yt-dlp, ffmpeg…
tools/noroot-install.sh scripts      # ~/server/*.sh + gancho de Termux:Boot
tools/noroot-install.sh rish <dir>   # archivos rish exportados de la app Shizuku
tools/noroot-bot.sh token            # token de @BotFather
tools/noroot-deploy.sh               # bot + plugins
tools/noroot-bot.sh enable           # ¡a andar!
```

## Qué obtienes

* **Lo básico de un servidor, en un móvil:** wake-lock, Wi-Fi que nunca duerme, adb por Wi-Fi (o SSH en modo sin
  root), reinicio tras caídas con espera exponencial, detección de procesos congelados con señal de vida,
  recuperación del Wi-Fi y de Internet, persistencia al arrancar para tres tipos de root (Magisk, KingRoot, init.rc) y
  para Termux:Boot.
* **Cuidado de la batería:** el modo root mantiene la carga al 40–60 %, para por encima de 42 °C y nunca la deja
  morir; soporta `batt_slate_mode` de Samsung, `charging_enabled`, o ninguno. El modo sin root informa del límite del
  propio fabricante. Ambos detectan apagones y cuentan cuánto aguantó la batería.
* **El bot de Telegram** (mensajes en español): descargas de más de 1000 sitios con yt-dlp/gallery-dl, 1080p,
  subidas de 2 GB por MTProto, caché instantánea, MP3, PDF → imágenes, canales de YouTube seguidos, control
  de acceso por usuario, manejo de cookies, actualización diaria automática, `/salud` `/historial` `/bateria`,
  voz a texto local, canales de YouTube seguidos publicados en un chat privado y/o un canal de Telegram,
  Instagram/Facebook primero sin sesión y con enlaces limpios, botones (MP3 / original / guardar en el disco bajo cada
  vídeo), búsqueda en YouTube con `/buscar`, cola con cancelación (`/cola`), `/stats` desde un registro SQLite y un
  archivo opcional de 7 días con `/guardar` al disco USB.
* **Plugins:** extras que se enchufan — fotos de cámaras de seguridad (Dahua), avisos por Alexa,
  scrobbling de YouTube Music a Last.fm, likes de YouTube Music → canal de Telegram, stickers de vídeo — y una API
  sencilla para los tuyos.
* **Recetas de NAS / servidor multimedia** para un móvil con disco USB: WebDAV, DLNA, Jellyfin, espejo de YouTube, respaldo semanal.
* **Operación:** despliegue, respaldo/restauración de la configuración y de todo el Debian, mudanza a otro móvil.
* **Pruebas que no necesitan móvil:** `tests/run.sh` (72 comprobaciones: lógica de batería contra una batería falsa,
  el vigilante sin root contra un Shizuku falso, esperas tras caídas y secuencia de arranque, carga de plugins,
  despacho de comandos, utilidades).

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
| [10 Móviles probados](docs/es/10-moviles-probados.md) | S4 mini, Moto X2, Tab A7, Realme 12+: manías y medidas |
| [11 FAQ y seguridad](docs/es/11-faq-y-seguridad.md) | legal, seguridad, créditos |
| [12 Modo sin root](docs/es/12-modo-sin-root.md) | Termux + proot + Shizuku, paso a paso, con supervisión probada |
| [14 Sin root 24/7](docs/es/14-sin-root-fiabilidad.md) | qué puede parar un servidor sin root, las defensas, `doctor.sh`, recuperación de Shizuku, avisos automáticos, perfiles por fabricante, matriz de compatibilidad |
| [15 Evaluación de WhatsApp](docs/es/15-whatsapp-evaluacion.md) | ¿puede WhatsApp ser un segundo canal? opciones, costes, riesgos, recomendación (sin implementar) |
| [13 Recetas multimedia](docs/es/13-recetas-multimedia.md) | disco USB, WebDAV, DLNA, Jellyfin, espejo de YouTube, trampas de hubs |

## Estado

* **Modo root (chroot):** el diseño y cada script vienen de tres equipos reales —un Galaxy S4 mini (producción,
  24/7), un Moto X2 (repuesto en frío) y una Galaxy Tab A7 (banco de pruebas)— que corrieron los scripts originales de
  cada equipo. Este repositorio los une en un solo conjunto parametrizado (`server.conf`), cubierto por las
  comprobaciones automáticas y a la espera de informes de instalaciones nuevas en otros móviles.
* **Modo sin root:** probado de punta a punta en un Realme 12+ 5G: todas las funciones del bot, cinco escenarios de
  supervisión, recuperación tras reinicio, servicios del disco USB. Los pasos de contenedor y preparación del
  instalador se repitieron desde cero en ese móvil para esta versión.
* **Sin cubrir todavía:** un corte de luz real en modo sin root, grupos, varios días seguidos sin intervención
  ahí; adaptadores USB-Ethernet (un primer intento fue poco fiable); AirPlay con un Apple TV real; cámaras que no sean
  Dahua; móviles x86.
* Rootear es arriesgado y depende del modelo; este repositorio no lo hace por ti.
  Descargar contenido puede infringir los términos de los sitios o los derechos de autor: **tú** eres
  responsable de para qué lo usas ([FAQ](docs/es/11-faq-y-seguridad.md)).

## Estructura

```
bot/            el bot de Telegram (bot.py, bigupload, health, pending, stt, thumbs)
extras/plugins/ plugins opcionales: cameras, alexa, stickers, lastfm_scrobbler, youtube_music_likes
phone/          scripts que corren en el móvil (modo root: enter, bot, charge, start, lanzadores de arranque, extras)
phone/noroot/   lo mismo para el modo sin root (Termux): boot, bot, charge, enter, sa (Shizuku), guard, recetas extras/
tools/          scripts que corren en tu PC (root: fetch-assets, install, deploy…; sin root: noroot-*.sh)
tests/          pruebas que no necesitan móvil
docs/{en,es}/   las guías
```

## Contribuir

Añade tu móvil a [Móviles probados](docs/es/10-moviles-probados.md), cuenta qué se rompió, traduce los
textos del bot o escribe un plugin. Ver [CONTRIBUTING.md](CONTRIBUTING.md). El código tiene licencia MIT
([LICENSE](LICENSE)); las herramientas de terceros que instala tienen sus propias licencias.
