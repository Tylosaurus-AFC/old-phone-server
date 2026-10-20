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
tools/set-token.sh
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
| seguir un canal de YouTube | `/seguir <enlace del canal>`; los vídeos nuevos se publican en 1080p (`/canales`, `/dejar N`) |

## 5. Uso

Basta con mandar un enlace. Comandos:

| Comando | Quién | Qué hace |
|---|---|---|
| *enlace* | todos | descarga y publica; borra el mensaje del enlace |
| `/mp3 enlace` | todos | solo el audio, MP3 a 192 kbps con portada y etiquetas |
| `/original enlace` | todos | fotos/vídeos como archivo, sin comprimir |
| `/pdf` | todos | manda un PDF con `/pdf` como pie (o responde a uno): una imagen por página; opciones `archivo`, `png`, `zip`, `10-25` |
| `/estado` `/velocidad` `/acerca` `/help` | todos | estado, prueba de velocidad, acerca de, ayuda |
| `/cookies` (+ mandar un `.txt`) | dueño | estado/renovación de cookies de Instagram y Facebook |
| `/actualizar` | dueño | actualizar yt-dlp y gallery-dl ya (también automático cada 24 h) |
| `/seguir` `/canales` `/dejar` | dueño | canales de YouTube |
| `/permitir` `/quitar` `/usuarios` | dueño | quién puede usarlo por privado |
| `/salud` `/historial [N]` `/bateria` | dueño | comprobaciones, registro de eventos, detalle de batería y cortes de luz |
| `/reiniciar confirmar` · `adb` · `wifi` | dueño | reiniciar el móvil · solo adb · reconectar el Wi-Fi |
| `/transcribir on\|off\|modelo X` | dueño | transcripción de notas de voz en este chat |

### Instagram / Facebook / YouTube con restricción de edad necesitan cookies

Estos sitios exigen una sesión iniciada. Usa una **cuenta secundaria**, nunca la principal:

1. Inicia sesión con esa cuenta en un navegador de escritorio.
2. Exporta sus cookies con una extensión como *Get cookies.txt LOCALLY* → un `cookies.txt` (formato Netscape).
3. Manda el archivo al bot **por privado**. Lo guarda (`chmod 600`) y **borra tu mensaje**.

El bot avisa cuando caducan o el sitio las bloquea, y `/salud` muestra la fecha de caducidad.

### Notas de voz a texto (opcional)

```bash
tools/install.sh voice        # compila whisper.cpp (10+ min en un móvil de 2 núcleos) + Vosk
```

Pon el idioma en `/opt/bot/stt.json` como `{"lang": "es"}` (por defecto `es`) y usa un modelo de Vosk
del mismo idioma (mira el encabezado de `phone/extras/setup-voice.sh`). Las notas de voz de los chats
autorizados se transcriben en el móvil: primero un borrador rápido de Vosk y luego el texto mejor de
Whisper lo sustituye.

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
