# 00 · Resumen: qué es y si es para ti

**old-phone-server** convierte un móvil Android viejo en un servidor Linux pequeño, silencioso y
siempre encendido, e incluye una aplicación real para correr en él: un bot de Telegram que
descarga vídeos y fotos de redes sociales. Nació para rescatar móviles que ya no sirven para
nada más (un Galaxy S4 mini de 2013 con Android 4.4 lleva trabajando 24/7) y luego se reprodujo
en un Moto X2 y en una Galaxy Tab A7.

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
* **Plugins** para lo que solo le sirve a algunos: fotos de cámaras de seguridad, avisos por
  Alexa, scrobbling a Last.fm, creador de stickers ([09 · Plugins](09-plugins.md)).

Puedes ignorar el bot por completo y usar el móvil como servidor Debian para otra cosa: todo
hasta la [05](05-servicios-y-arranque.md) es independiente de la aplicación.

## ¿Sirve tu móvil?

Necesitas **todo** esto:

1. **Root.** No hay forma de evitarlo para el chroot. Conseguirlo depende del modelo y es el
   paso más arriesgado ([02 · Root](02-root.md)).
2. **≥ 3 GB libres de almacenamiento** (Debian + bot ≈ 1,3 GB, modelos de voz ≈ 0,3 GB y espacio
   de trabajo para descargas: un vídeo largo pueden ser varios GB) y **≥ 1 GB de RAM** (el S4 mini
   tiene 1,3 GB y corre tres descargas a la vez).
3. Una CPU ARM: 32 bits (`armeabi-v7a`) o 64 bits (`arm64-v8a`). Los móviles x86 no se han probado.
4. Un móvil que ya no necesites como móvil, un cargador y Wi-Fi.

### Otros proyectos, para otros móviles

Este proyecto apunta a propósito a **móviles viejos con root**. Si el tuyo es más nuevo o no quieres
hacer root, estos son mejores puntos de partida (proyectos independientes, sin relación con este):

| Tu móvil | Prueba |
|---|---|
| Android 10+, 64 bits, sin root | [homedroid](https://github.com/sudiptacmd/homedroid): una APK (SSH, Jellyfin, Immich, AdGuard…) con su propio proot |
| 64 bits, sin root, quiere escritorio o Home Assistant | [mayukh4/linux-android](https://github.com/mayukh4/linux-android): Termux + Termux-X11 + proot |
| Con root (Magisk), quiere una guía sencilla con Termux | [MultiX0/old-phone-to-server](https://github.com/MultiX0/old-phone-to-server) y [Nikhil-Richhariya/Android-Phone-as-Server](https://github.com/Nikhil-Richhariya/Android-Phone-as-Server) |
| **Android 4.4–9, 32 o 64 bits, se puede rootear, debe funcionar 24/7** | **este proyecto** |

Lo que lo distingue: soporta móviles donde el Termux actual ni se puede instalar (Termux pide
Android 7+), usa un chroot nativo en vez de proot, e incluye la parte poco vistosa de operar
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
| 10 | [Móviles probados](10-moviles-probados.md) | medidas y manías de tres equipos reales |
| 11 | [FAQ y seguridad](11-faq-y-seguridad.md) | legal, seguridad, riesgos, preguntas frecuentes |
