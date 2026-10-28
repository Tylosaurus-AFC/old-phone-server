# 00 · Resumen: qué es y si es para ti

**old-phone-server** convierte un móvil Android viejo en un servidor Linux pequeño, silencioso y
siempre encendido, e incluye una aplicación real para correr en él: un bot de Telegram que
descarga vídeos y fotos de redes sociales. Nació para rescatar móviles que ya no sirven para
nada más (un Galaxy S4 mini de 2013 con Android 4.4 lleva trabajando 24/7), luego se reprodujo en un
Moto X2 y una Galaxy Tab A7, y por último —**sin root**— en un Realme 12+ moderno.

Todo lo que hay en este repositorio viene de equipos que funcionaron de verdad, con los
problemas que fueron saliendo anotados. Las guías no se quedan en «funciona»: dicen qué se
rompe, por qué y cómo recuperarlo.

## Por qué un móvil viejo es un buen servidor

| | |
|---|---|
| **UPS incluido** | La batería mantiene el servidor vivo en un apagón (el bot incluso avisa cuándo se fue la luz y cuánto aguantó la batería). |
| **Pequeño y silencioso** | Sin ventilador ni piezas móviles, unos pocos watts. |
| **Gratis** | Ya está en un cajón. |
| **Wi-Fi + CPU + RAM + almacenamiento** | Un móvil de 2013 tiene más que una Raspberry Pi 1. |
| **Solo conexiones de salida** | Un bot de Telegram solo hace conexiones hacia fuera: sin abrir puertos, sin DNS dinámico, sin exponerse a Internet. |

## Cómo funciona

```
 Android (con root, pantalla apagada, enchufado)
  │
  ├─ lanzador de arranque ──► start.sh   wake-lock, Wi-Fi siempre activo, adb por Wi-Fi
  │   (Magisk service.d,                 │
  │    gancho de KingRoot, o init.rc)    ├─► bot.sh     mantiene vivo el bot; reintenta con
  │                                      │              esperas crecientes (10 s, 20 s … 10 min)
  │                                      └─► charge.sh  vigilante, cada minuto:
  │                                                     bot colgado · Wi-Fi/Internet · batería
  │                                                     entre 40 y 60 % · peticiones /reiniciar
  │
  └─ /data/debian/fs  =  Debian 13 en un chroot  (se entra con enter.sh)
       └─ /opt/bot/   bot.py + plugins opcionales  ◄──►  Telegram
```

* **¿Por qué un chroot y no Termux/proot?** Un chroot corre a velocidad nativa, no necesita
  capa de emulación y te da un Debian *completo* (apt, Python, ffmpeg, compiladores). El precio
  es que necesita **root**. Abajo hay proyectos que no lo necesitan.
* **¿Por qué dos vigilantes?** `bot.sh` y `charge.sh` se vigilan entre sí: si uno muere, el otro
  lo relanza en un minuto. `charge.sh` además detecta un bot que sigue vivo pero *congelado*
  (deja de escribir su señal de vida) y lo mata para que `bot.sh` levante uno nuevo.
* **¿Y sin root?** Una segunda variante corre el mismo Debian y bot dentro de **Termux** (proot) y usa **Shizuku**
  para los pocos poderes de sistema que necesita el vigilante. Mismo bot, mismos plugins, mismas ideas; el cargador
  no se puede conmutar, solo informar. Ver [12 · Modo sin root](12-modo-sin-root.md).
* **¿Por qué cuidar la batería?** Un móvil al 100 % en el cargador durante años se hincha y
  puede volverse peligroso. `charge.sh` enciende y apaga el cargador para mantener 40–60 %
  (ver [06 · Batería y calor](06-bateria-y-calor.md)).

## Qué hace la aplicación de ejemplo

Un bot de Telegram, en español (los textos son fáciles de traducir; ver [FAQ](11-faq-y-seguridad.md)):

* Mándale un enlace de TikTok, Instagram, Facebook, Threads, YouTube, X, Reddit… (yt-dlp y
  gallery-dl cubren más de 1000 sitios). Publica el vídeo o las fotos en el mismo chat con el
  título enlazado al original y borra tu mensaje.
* Vídeo en 1080p (menos si pasa de 2 GB), subidas **de hasta 2 GB** por archivo, caché que
  reenvía un enlace al instante, `/mp3`, `/original`, PDF → imágenes, seguimiento de canales de YouTube.
* **Notas de voz a texto**, íntegramente en el móvil (whisper.cpp + Vosk), sin mandar nada a la nube.
* Salud: `/estado`, `/salud`, `/historial`, `/bateria`, `/velocidad` y avisos automáticos
  (cookies caducadas, batería caliente, poco disco, cortes de Internet o de Telegram, apagones).
* **Canales de Telegram como destino:** los canales de YouTube seguidos pueden publicarse en tu chat privado, en un
  canal de Telegram tuyo, o en ambos (`/canal`, `/destino`).
* **Plugins** para lo que solo le sirve a algunos: fotos de cámaras de seguridad, avisos por
  Alexa, scrobbling a Last.fm, likes de YouTube Music → canal, creador de stickers ([09 · Plugins](09-plugins.md)).
* Recetas de **NAS y servidor multimedia** para un móvil con disco USB: WebDAV, DLNA, Jellyfin, espejo de YouTube
  ([13 · Recetas multimedia](13-recetas-multimedia.md)).

Puedes ignorar el bot por completo y usar el móvil como servidor Debian para otra cosa: todo
hasta la [05](05-servicios-y-arranque.md) es independiente de la aplicación.

## ¿Sirve tu móvil?

Necesitas **todo** esto:

1. **Root** para el modo chroot —conseguirlo depende del modelo y es el paso más arriesgado
   ([02 · Root](02-root.md))— **o** un móvil razonablemente moderno (se recomienda Android 11+) para el modo
   sin root ([12](12-modo-sin-root.md)).
2. **≥ 3 GB libres de almacenamiento** (Debian + bot ≈ 1,3 GB, modelos de voz ≈ 0,3 GB y espacio
   de trabajo para descargas: un vídeo largo pueden ser varios GB) y **≥ 1 GB de RAM** (el S4 mini
   tiene 1,3 GB y corre tres descargas a la vez).
3. Una CPU ARM: 32 bits (`armeabi-v7a`) o 64 bits (`arm64-v8a`). Los móviles x86 no se han probado.
4. Un móvil que ya no necesites como móvil, un cargador y Wi-Fi.

### Otros proyectos, para otros móviles

Este proyecto tiene dos modos: **root + chroot** (la única opción para los móviles más viejos) y **sin root +
Termux/proot** (para los modernos). Si lo que quieres no es un servidor 24/7 tipo bot, estos proyectos independientes
(sin relación con este) pueden encajar mejor:

| Tu móvil | Prueba |
|---|---|
| Android 10+, 64 bits, sin root, quiere apps ya hechas | [homedroid](https://github.com/sudiptacmd/homedroid): una APK (SSH, Jellyfin, Immich, AdGuard…) con su propio proot |
| 64 bits, sin root, quiere escritorio o Home Assistant | [mayukh4/linux-android](https://github.com/mayukh4/linux-android): Termux + Termux-X11 + proot |
| Con root (Magisk), quiere una guía sencilla con Termux | [MultiX0/old-phone-to-server](https://github.com/MultiX0/old-phone-to-server) y [Nikhil-Richhariya/Android-Phone-as-Server](https://github.com/Nikhil-Richhariya/Android-Phone-as-Server) |
| **Android 4.4–10, 32 o 64 bits, se puede rootear, debe funcionar 24/7** | **este proyecto, modo root** |
| **Android 11+, sin root, un servicio 24/7 con vigilantes, un bot de Telegram y NAS opcional** | **este proyecto, modo sin root** |

Lo que lo distingue: soporta móviles donde el Termux actual ni se puede instalar (Termux pide
Android 7+), ofrece un chroot nativo además del modo proot, e incluye la parte poco vistosa de operar
24/7: vigilantes, esperas ante caídas, recuperación del Wi-Fi, límites de carga de la batería,
respaldos y restauración, y un procedimiento documentado para cada fallo que nos tocó.

## Ruta por las guías

| # | Guía | Harás |
|---|---|---|
| 01 | [Preparación](01-preparacion.md) | instalar adb, revisar tu móvil, rellenar `config.sh` |
| 02 | [Root](02-root.md) | elegir cómo rootear (y entender sus riesgos) |
| 03 | [Instalación](03-instalacion.md) | busybox, chroot de Debian, scripts, paquetes |
| 04 | [Bot de Telegram](04-bot-telegram.md) | crear el bot, poner el token, ser el dueño |
| 05 | [Servicios y arranque](05-servicios-y-arranque.md) | que arranque solo y se mantenga |
| 06 | [Batería y calor](06-bateria-y-calor.md) | proteger la batería (**no te lo saltes**) |
| 07 | [Red](07-red.md) | IP fija, adb por Wi-Fi, problemas de Wi-Fi, Ethernet |
| 08 | [Operación](08-operacion.md) | actualizar, respaldar, restaurar, resolver problemas |
| 09 | [Plugins](09-plugins.md) | extras opcionales y cómo escribir los tuyos |
| 10 | [Móviles probados](10-moviles-probados.md) | medidas y manías de cuatro equipos reales |
| 11 | [FAQ y seguridad](11-faq-y-seguridad.md) | legal, seguridad, riesgos, preguntas frecuentes |
| 12 | [Modo sin root](12-modo-sin-root.md) | el mismo servidor con Termux + proot + Shizuku, sin root |
| 14 | [Sin root 24/7](14-sin-root-fiabilidad.md) | límites del modo sin root, defensas, `doctor.sh`, recuperación de Shizuku, avisos, matriz de compatibilidad |
| 16 | [Auditoría de Shizuku](16-shizuku-auditoria.md) | oficial frente al fork, matriz de recuperación por versión de Android |
| 15 | [Evaluación de WhatsApp](15-whatsapp-evaluacion.md) | un segundo canal: opciones, costes, riesgos (sin implementar) |
| 13 | [Recetas multimedia](13-recetas-multimedia.md) | NAS / DLNA / Jellyfin / espejo de YouTube opcionales en un disco USB |
