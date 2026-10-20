# 09 · Plugins

El bot base hace un solo trabajo (descargar, más salud y administración). Todo lo que solo le sirve
a algunos vive en **plugins**: un archivo `.py` puesto en `/opt/bot/plugins/` se carga al arrancar.
En [`extras/plugins/`](../../extras/plugins/) vienen cuatro ejemplos reales; son las
funciones privadas de la instalación original, generalizadas.

## Activar los ejemplos

Pon en `config.sh` los que quieras y despliega:

```bash
PLUGINS="cameras alexa stickers lastfm_scrobbler"
tools/deploy.sh
```

`deploy.sh` deja `/opt/bot/plugins/` con **exactamente** esos (más los módulos auxiliares cuyo
nombre empieza por `_`). Un plugin que falla al cargar se anota en el log y se omite; el resto sigue.

| Plugin | Comandos | Necesita | Notas |
|---|---|---|---|
| `cameras` | `/foto_camaras [cam]`, `/clip_camaras cam [fecha] inicio fin` | `camaras.json`: `{"host","user","password"}` | grabadores **Dahua** XVR/NVR (CGI + RTSP). Crea en el grabador un usuario solo de lectura para el bot, nunca el administrador. Otras marcas necesitan adaptar `_camaras.py` |
| `alexa` | `/alexa [@altavoz] texto` | `voicemonkey.json`: `{"token","device","language"}` | con [Voice Monkey](https://voicemonkey.io) (plan gratis: 200 llamadas/mes) |
| `stickers` | `/sticker [emoji]` | `ffmpeg` con VP9 | convierte un vídeo/GIF en sticker de vídeo de Telegram en el pack del propio usuario. Abierto a todo usuario autorizado |
| `lastfm_scrobbler` | `/scrobble`, `/lastfm` | cookies de music.youtube.com (se mandan como `.txt` cuyo nombre contenga `youtube`), clave de API de Last.fm | manda a Last.fm el historial de YouTube Music cada 3 min; el ejemplo más completo (bucle en segundo plano, línea de salud, manejo de archivos) |

Pon el archivo de configuración de cada plugin en `/opt/bot/` del móvil (dentro del chroot:
`/data/debian/fs/opt/bot/`), con `chmod 600`. Llevan contraseñas y `make-image.sh` los deja fuera;
`backup.sh` sí los guarda.

## Escribir el tuyo

Un plugin es un archivo con una función `setup(api)`. `api` es el propio módulo del bot: puedes usar
`api.say`, `api.edit`, `api.delete`, `api.tg` (llamada directa a la Bot API), `api.send_file`,
`api.publish` (maneja álbumes y la vía de 2 GB), `api.alert` (mensaje privado al dueño, con límite
de frecuencia), `api.JOBS` (carpeta temporal), `api.BASE`, `api.log`, `api.load_owners`, `api.BOT`,
`api.health.event`, `api._check` (da formato a una línea de `/salud`).

```python
# /opt/bot/plugins/hola.py   — /hola → "hola, <nombre>"
def setup(api):
    def hola(msg, chat, user, arg):
        api.say(chat, f"hola, {user.get('first_name', '')} {arg}".strip())

    return {
        "commands": {"hola": {
            "fn": hola,                      # fn(msg, chat, user, arg)
            "owner": False,                  # por defecto True: solo el dueño puede llamarlo
            "anywhere": True,                # por defecto False: los de dueño solo van por privado
            "thread": True,                  # por defecto True: corre en su propio hilo
            "help": "/hola – saluda",        # línea añadida al /help del dueño (HTML)
            "menu": "Saludar"}},             # descripción en el menú «/» de Telegram
    }
```

`setup()` también puede devolver:

| Clave | Tipo | Para qué |
|---|---|---|
| `health` | lista de `f() → str` | una línea cada una para `/salud` (`api._check(nombre, True/None/False, detalle)`) |
| `loops` | lista de `f()` | tareas en segundo plano, cada una en su hilo daemon (deben hacer `while True` + `sleep`) |
| `documents` | lista de `f(msg, doc, texto) → bool` | se llama cuando el dueño manda un `.txt` por privado; devuelve `True` si lo atendiste |
| `about` | lista de str | viñetas para el `/acerca` del dueño |

Reglas del juego:

* Un plugin corre **con los privilegios del bot**. Instala solo código que hayas leído.
* Los archivos que empiezan con `_` son módulos auxiliares: los plugins pueden importarlos
  (`import _milib`), pero nunca se cargan como plugins.
* Mantén los secretos fuera de los logs y de Telegram. El núcleo sustituye el token del bot por
  `<token>` en las líneas de log; haz lo mismo con los tuyos.
* Prueba sin móvil: `tests/test_bot.py` muestra cómo cargar plugins en una copia desechable del
  bot y mandar mensajes falsos a `on_message`.
* Las reglas de acceso del núcleo se aplican primero: los chats no autorizados nunca llegan a un
  plugin; `owner` se comprueba contra el primer usuario que ejecutó `/start`.
