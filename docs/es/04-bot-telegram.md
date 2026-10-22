# 04 · El bot de Telegram

La aplicación de ejemplo. Con Debian ya preparado ([03](03-instalacion.md)), el bot necesita un
token, un despliegue y un dueño.

> Los mensajes y comandos del bot están **en español** (`/estado`, `/seguir`, `/permitir`…). La
> lógica no depende del idioma; traducir es editar los textos de `bot/bot.py`. Una capa i18n
> de verdad sería una contribución muy bienvenida ([CONTRIBUTING](../../CONTRIBUTING.md)).

## 1. Crea el bot y dale el token al móvil

1. En Telegram abre **@BotFather**, manda `/newbot`, elige un nombre y un usuario.
2. BotFather responde con un **token** (`123456789:AA…`). Es una contraseña: quien lo tenga controla
   el bot.
3. Ponlo en el móvil (se pide en silencio y se guarda con `chmod 600`):

```bash
tools/set-token.sh              # modo sin root: tools/noroot-bot.sh token
```

## 2. Opcional: subidas de hasta 2 GB

La Bot API normal no deja subir más de 50 MB. Un bot llega a 2 GB por MTProto si le das una clave
de aplicación de Telegram:

1. Entra en <https://my.telegram.org> → *API development tools* → crea una aplicación.
2. Ejecuta `tools/set-api.sh` e introduce el `api_id` y el `api_hash`.

Sin esto todo funciona, pero los archivos de más de 50 MB fallan (el bot prueba antes con
resoluciones menores).

## 3. Despliega y activa

```bash
tools/deploy.sh          # copia bot/, plugins y scripts del móvil; revisa la sintaxis en el móvil
tools/enable-bot.sh      # crea /data/debian/BOT_ENABLED y arranca bot.sh
# modo sin root:  tools/noroot-deploy.sh  y  tools/noroot-bot.sh enable
```

El bot **solo corre donde existe `BOT_ENABLED`.** Ese archivo es un seguro: el mismo token no
puede estar en dos móviles a la vez (Telegram responde *409 Conflict* y cada descarga se hace
dos veces). Mudar el servidor a otro móvil = primero `tools/enable-bot.sh off` en el viejo.

## 4. Hazte dueño — *hazlo de inmediato*

Abre un **chat privado con tu bot** y manda `/start`. **La primera persona que lo haga queda
como dueña** y es la única que puede usar los comandos de dueño. Hazlo antes de compartir el
usuario del bot con nadie.

Después:

| Para… | Haz |
|---|---|
| usarlo en un grupo | añade el bot al grupo **siendo el dueño** (si lo añade otro, el bot se va). Hazlo administrador con permiso de *borrar mensajes* para que pueda quitar el mensaje del enlace |
| que un amigo lo use por privado | le escribe al bot; te llega una solicitud con su id; manda `/permitir ID` (`/quitar ID`, `/usuarios`) |
| seguir un canal de YouTube | `/seguir <enlace del canal> [privado\|canal\|ambos]`; los vídeos nuevos se publican en 1080p, sin Shorts, revisados cada 5 min (`/canales`, `/destino N …`, `/dejar N`) |
| publicarlos en un **canal** de Telegram | crea un canal, añade el bot como administrador solo con *Publicar mensajes* (desactiva *Firmar mensajes* para que no salga su nombre) — el bot lo detecta solo y te avisa; `/canal` lista y asigna canales. Si falla la publicación en el canal, el vídeo se deja en tu chat privado con un aviso |

## 5. Uso

Basta con mandar un enlace. Comandos:

| Comando | Quién | Qué hace |
|---|---|---|
| *enlace* | todos | descarga y publica; borra el mensaje del enlace |
| `/mp3 enlace` | todos | solo el audio, MP3 a 192 kbps con portada y etiquetas (o respondiendo a un vídeo del bot) |
| `/original enlace` | todos | fotos/vídeos como archivo, sin comprimir (o respondiendo a un vídeo del bot) |
| `/buscar palabras` | todos | busca en YouTube: 5 resultados con botones de vídeo o MP3 |
| `/cola` | todos | tus descargas en espera o en curso, con botón para cancelar (`/cancelar N`) |
| `/pdf` | todos | manda un PDF con `/pdf` como pie (o responde a uno): una imagen por página; opciones `archivo`, `png`, `zip`, `10-25` |
| `/estado` `/velocidad` `/acerca` `/help` | todos | estado, prueba de velocidad, acerca de, ayuda |
| `/cookies` (+ mandar un `.txt`) | dueño | estado/renovación de cookies de Instagram y Facebook |
| `/actualizar` | dueño | actualizar yt-dlp y gallery-dl ya (también automático cada 24 h) |
| `/seguir` `/canales` `/destino` `/dejar` | dueño | canales de YouTube y adónde se publica cada uno (privado, canal o ambos) |
| `/canal` | dueño | canales de Telegram donde publica el bot y para qué sirve cada uno (`/canal videos N`, `/canal quitar N`; los plugins añaden más usos) |
| `/permitir` `/quitar` `/usuarios` | dueño | quién puede usarlo por privado |
| `/salud` `/historial [N]` `/bateria` | dueño | comprobaciones, registro de eventos, detalle de batería y cortes de luz |
| `/reiniciar confirmar` · `adb` · `wifi` | dueño | reiniciar el móvil · solo adb · reconectar el Wi-Fi |
| `/transcribir on\|off\|modelo X` | dueño | transcripción de notas de voz en este chat (`modelo auto`: ver abajo) |
| `/stats [hoy\|semana\|mes\|todo]` | dueño | descargas, fallos, datos y notas de voz por periodo (necesita `"sqlite": true`) |
| `/guardar` (respondiendo, o `/guardar enlace`) | dueño | copia un vídeo al disco USB, donde no se borra (solo con `archivo_dias`) |

### Instagram / Facebook / YouTube con restricción de edad necesitan cookies

Estos sitios exigen una sesión iniciada. Usa una **cuenta secundaria**, nunca la principal:

1. Inicia sesión con esa cuenta en un navegador de escritorio.
2. Exporta sus cookies con una extensión como *Get cookies.txt LOCALLY* → un `cookies.txt` (formato Netscape).
3. Manda el archivo al bot **por privado**. Lo guarda (`chmod 600`) y **borra tu mensaje**.

El bot avisa cuando caducan o el sitio las bloquea, y `/salud` muestra la fecha de caducidad.

**Cómo consigue el bot un enlace** (para que puedas prever fallos): Instagram y Facebook se prueban **primero sin
sesión** (yt-dlp, luego el embed de la propia página, luego gallery-dl) y las cookies solo se usan si eso falla — una
publicación pública nunca toca tu cuenta. Los pies se limpian: el enlace bajo un vídeo no lleva rastreadores
(`?si=`, `igsh`, `fbclid`, `img_index`…), los enlaces de YouTube son canónicos y la caché trata la misma publicación
con distintos rastreadores como una sola. Cada trabajo tiene su propia carpeta de trabajo, así que dos descargas
nunca se pisan.

### Notas de voz a texto (opcional)

```bash
tools/install.sh voice        # compila whisper.cpp (10+ min en un móvil de 2 núcleos) + Vosk
```

Pon el idioma en `/opt/bot/stt.json` como `{"lang": "es"}` (por defecto `es`) y usa un modelo de Vosk
del mismo idioma (mira el encabezado de `phone/extras/setup-voice.sh`). Las notas de voz de los chats
autorizados se transcriben en el móvil: primero un borrador rápido de Vosk y luego el texto mejor de
Whisper lo sustituye. Con `/transcribir modelo auto` (y bajados `large-v3-turbo-q5_0` y `small-q5_1`) las
notas de hasta 2 min usan turbo y las más largas el modelo small, más rápido, para que una nota larga no
tenga el procesador ocupado mucho rato en un móvil de gama media.

### Botones, estadísticas y archivo de 7 días

* `/help` muestra botones rápidos al dueño, y cada vídeo lleva botones debajo (**MP3**, **Original** y, con
  disco USB, **NAS**). Mientras trabaja, el bot muestra «escribiendo…» / «enviando vídeo…».
* Ajustes de `/opt/bot/device.json` (mira `phone/device.example.json`):
  * `"sqlite": true` — la caché de enlaces enviados y el índice del archivo van en `/opt/bot/bot.db` (SQLite,
    viene con Python) en vez de en JSON; el `cache.json` anterior se importa una vez al arrancar. Ahí se
    registra cada descarga y nota de voz, que es lo que lee `/stats`. Sin el ajuste el bot sigue con los
    JSON y `/stats` no tiene nada que mostrar.
  * `"archivo_dias": 7` — guarda lo enviado en el móvil 7 días, para que los botones y `/guardar` funcionen
    sin volver a descargar; se limpia cada hora. No lo actives en un móvil con poco espacio.
  * `"nas": "/mnt/disk/Guardado"` — adónde copia `/guardar`. El disco debe tener un archivo `.nas` en su raíz
    (el `charge.sh` sin root lo crea); sin él no se escribe nada, así un disco desconectado nunca llena el
    almacenamiento del propio móvil.

## 6. Dónde mirar cuando algo falla

| Archivo (dentro del móvil, `/data/debian/fs/opt/bot/`) | Contenido |
|---|---|
| `bot.log` | el bot (rota a 1 MB) |
| `service.log` | `bot.sh` y `charge.sh` |
| `events.jsonl` | lo que muestra `/historial` |
| `/data/debian/boot.log` | `start.sh` al arrancar |

```bash
adb shell su -c "tail -n 40 /data/debian/fs/opt/bot/service.log"
```

Siguiente: [05 · Servicios y arranque](05-servicios-y-arranque.md).
