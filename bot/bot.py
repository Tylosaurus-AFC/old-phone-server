#!/opt/bot/venv/bin/python3
"""Bot de Telegram: recibe un enlace de cualquier red social, descarga el
video/fotos, los publica en el mismo chat con el titulo enlazado al original
y borra el mensaje que traia el enlace.

Corre dentro de un Debian en un movil Android viejo (chroot con root, o proot sin
root; ver docs/).
  /opt/bot/token   -> token de @BotFather
  /opt/bot/owners  -> 1a linea: ID del dueño; resto: chats/grupos autorizados

Las funciones extra (camaras, Alexa, scrobbler, stickers, likes...) son plugins opcionales:
cada .py que se copie a /opt/bot/plugins/ se carga al arrancar (ver extras/ y
docs/*/09-plugins.md).
"""
import html
import importlib.util
import json
import logging
import mimetypes
import re
import shutil
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests

import alerts
import bigupload
import db
import diag
import health
import pending
import stt
import thumbs

BASE = Path("/opt/bot")
VENV_BIN = BASE / "venv" / "bin"
JOBS = Path("/tmp/botjobs")
TOKEN = (BASE / "token").read_text().strip()
API = f"https://api.telegram.org/bot{TOKEN}"
OWNERS_FILE = BASE / "owners"
COOKIES = BASE / "cookies.txt"        # formato Netscape; se sube por Telegram
SESSION_COOKIES = {"instagram.com": ["sessionid"], "facebook.com": ["c_user", "xs"]}
MAX_BYTES = 49 * 1024 * 1024          # limite de la Bot API: 50 MB
MAX_FILES = 20
URL_RE = re.compile(r"https?://\S+")
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VID_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

class _NoToken(logging.Formatter):
    """Los errores de red de requests incluyen la URL de la Bot API, que lleva el token."""
    def format(self, record):
        return super().format(record).replace(TOKEN, "<token>")


_log_file = RotatingFileHandler(BASE / "bot.log", maxBytes=1_000_000, backupCount=2)
_log_file.setFormatter(_NoToken("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_log_file])
logging.getLogger("telethon").setLevel(logging.WARNING)
log = logging.getLogger("bot")
http = requests.Session()
jobs = pending.PersistentJobs(BASE / "pending_downloads.json")   # sobrevive a reinicios
BOT = {}
STARTED = time.time()
VERSION = (BASE / "VERSION").read_text().strip() if (BASE / "VERSION").exists() else "?"
# Textos del equipo (/estado, /bateria, /acerca). Se personalizan con
# /opt/bot/device.json (ver phone/device.example.json). Claves opcionales: "root" (texto
# tras la version de Android), "remote" (como se entra: "adb en :5555", "SSH en :8022"...),
# "wifi_note" (false: no mostrar el aviso del Wi-Fi viejo en /velocidad) y "charge_note"
# (texto de /bateria; {range} = rango de carga).
DEVICE = {"name": "Móvil Android",
          "intro": "Un móvil Android viejo reconvertido en servidor",
          "cpu": "CPU del móvil", "android": "Android",
          "battery": "la batería original"}
try:
    DEVICE.update(json.loads((BASE / "device.json").read_text()))
except (OSError, ValueError):
    pass
LAST_OK = {}        # "download": (epoch, red) del ultimo enlace que salio bien


# ---------------------------------------------------------------- Plugins

# Un plugin es un .py en /opt/bot/plugins/ con una funcion setup(api), donde `api` es
# este modulo (say, edit, delete, tg, send_file, publish, alert, jobs, JOBS, BASE, log...).
# setup() devuelve un diccionario con lo que aporta (todo opcional):
#   "commands": {"nombre": {"fn": f(msg, chat, user, arg), "help": "texto HTML",
#                           "menu": "descripcion corta", "owner": True,
#                           "anywhere": False, "thread": True}}
#   "health":   [f() -> linea de /salud]          (usa api._check)
#   "loops":    [f()]                              (cada una en su hilo)
#   "documents": [f(msg, doc, text) -> True si lo atendio]   (.txt que manda el dueño)
#   "job_done": [f(job, ok, error)]                (al acabar cada trabajo con job["bulk"])
#   "channel_roles": {"canciones": "descripcion del uso"}   (usos de canales de Telegram)
#   "about":    ["linea de /acerca", ...]          (solo se muestran al dueño)
PLUGIN_COMMANDS = {}   # "/nombre" -> opciones
PLUGIN_HEALTH, PLUGIN_LOOPS, PLUGIN_DOCS, PLUGIN_ABOUT, PLUGIN_JOB_DONE = [], [], [], [], []
PLUGINS_DIR = BASE / "plugins"


def load_plugins():
    for coll in (PLUGIN_COMMANDS, PLUGIN_HEALTH, PLUGIN_LOOPS, PLUGIN_DOCS, PLUGIN_ABOUT,
                 PLUGIN_JOB_DONE):
        coll.clear()          # asi se puede llamar otra vez (pruebas)
    for role in list(ROLE_INFO):
        if role != "videos":
            ROLE_INFO.pop(role)
    for f in sorted(PLUGINS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"plugin_{f.stem}", f)
            mod = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(PLUGINS_DIR))
            spec.loader.exec_module(mod)
            info = mod.setup(sys.modules[__name__]) or {}
        except Exception:
            log.exception("plugin %s no se pudo cargar", f.name)
            continue
        for name, opts in info.get("commands", {}).items():
            PLUGIN_COMMANDS["/" + name] = {"owner": True, "anywhere": False, "thread": True,
                                           **opts}
        PLUGIN_HEALTH.extend(info.get("health", []))
        PLUGIN_LOOPS.extend(info.get("loops", []))
        PLUGIN_DOCS.extend(info.get("documents", []))
        PLUGIN_ABOUT.extend(info.get("about", []))
        PLUGIN_JOB_DONE.extend(info.get("job_done", []))
        ROLE_INFO.update(info.get("channel_roles", {}))
        log.info("plugin cargado: %s (%s)", f.name,
                 ", ".join("/" + c for c in info.get("commands", {})) or "sin comandos")


# ---------------------------------------------------------------- Telegram

class TelegramError(RuntimeError):
    """Telegram SI contestó, pero con un error: la conexión de este móvil va bien.
    `code` es el código HTTP (409 otra instancia, 429 demasiadas peticiones, 5xx fallo
    de su servidor) y `retry_after` los segundos que pide esperar. Es un RuntimeError
    con el mismo texto de siempre, así que lo que ya lo captura sigue igual."""

    def __init__(self, method, description, code, retry_after=None):
        super().__init__(f"{method}: {description}")
        self.code, self.retry_after = code, retry_after


def tg(method, _timeout=60, files=None, **params):
    for attempt in range(3):
        r = http.post(f"{API}/{method}", data=params, files=files, timeout=_timeout)
        try:
            data = r.json()
        except ValueError:   # p. ej. un 502 del servidor de Telegram con una página HTML
            raise TelegramError(method, f"respuesta no válida (HTTP {r.status_code})",
                                r.status_code)
        if data.get("ok"):
            return data["result"]
        code = data.get("error_code") or r.status_code
        wait = (data.get("parameters") or {}).get("retry_after")
        # 429: Telegram pide esperar unos segundos. Se espera y se repite (el mensaje no
        # llegó a procesarse). getUpdates lo gestiona el bucle principal; con archivos
        # no se reintenta, porque ya se habrían consumido.
        if code == 429 and wait and wait <= 30 and attempt < 2 \
                and files is None and method != "getUpdates":
            log.info("%s: Telegram pide esperar %s s, reintento", method, wait)
            time.sleep(wait + 1)
            continue
        raise TelegramError(method, data.get("description"), code, wait)


def keyboard(buttons):
    """[[("texto", "/orden"), ...], ...] -> teclado en linea. Cada boton manda la orden
    como si se escribiera (pasa por los mismos permisos): ver on_button."""
    return json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row]
                                           for row in buttons]})


def say(chat, text, reply_to=None, parse_mode=None, buttons=None):
    try:
        params = {"chat_id": chat, "text": text, "disable_web_page_preview": "true"}
        if buttons:
            params["reply_markup"] = keyboard(buttons)
        if reply_to:
            params["reply_to_message_id"] = reply_to
            params["allow_sending_without_reply"] = "true"
        if parse_mode:
            params["parse_mode"] = parse_mode
        return tg("sendMessage", **params)["message_id"]
    except Exception as e:
        log.warning("sendMessage: %s", e)


def edit(chat, msg_id, text, parse_mode=None):
    if not msg_id:
        return
    try:
        tg("editMessageText", chat_id=chat, message_id=msg_id, text=text,
           **({"parse_mode": parse_mode} if parse_mode else {}))
    except Exception:
        pass


def delete(chat, msg_id):
    if not msg_id:
        return True
    try:
        tg("deleteMessage", chat_id=chat, message_id=msg_id)
        return True
    except Exception as e:
        log.info("deleteMessage %s: %s", msg_id, e)
        return False


def kind(path: Path):
    ext = path.suffix.lower()
    if ext in IMG_EXT and path.stat().st_size < 10 * 1024 * 1024:
        return "photo"
    if ext in VID_EXT:
        return "video"
    if ext == ".gif":
        return "animation"
    if ext in {".mp3", ".m4a", ".opus", ".ogg"}:
        return "audio"
    return "document"


def mime(path: Path):
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def file_id_of(msg):
    """(tipo, file_id) del medio de un mensaje enviado por la Bot API."""
    if getattr(_tl, "sent_msgs", None) is not None:    # para el archivo (ver archive_put)
        _tl.sent_msgs.append([msg["chat"]["id"], msg["message_id"]])
    if msg.get("photo"):
        return "photo", msg["photo"][-1]["file_id"]
    for k in ("video", "animation", "audio", "document"):
        if msg.get(k):
            return k, msg[k]["file_id"]
    return None


def reply_args(reply_to):
    """Responder a un mensaje (si ya no existe, se envia igual sin responder)."""
    return {"reply_to_message_id": reply_to, "allow_sending_without_reply": "true"} \
        if reply_to else {}


def send_file(chat, path: Path, caption=None, extra=None, reply_to=None, as_doc=False):
    for attempt in range(4):
        try:
            return _send_file(chat, path, caption, extra, reply_to, as_doc)
        except TelegramError as e:
            if e.code != 429 or not e.retry_after or e.retry_after > 90 or attempt == 3:
                raise
            log.info("sendFile: Telegram pide esperar %s s", e.retry_after)
            time.sleep(e.retry_after + 1)


def _send_file(chat, path: Path, caption=None, extra=None, reply_to=None, as_doc=False):
    k = "document" if as_doc else kind(path)
    params = {"chat_id": chat, **(extra or {}), **reply_args(reply_to)}
    if caption:
        params.update(caption=caption, parse_mode="HTML")
    files = {}
    cover = thumbs.make(path) if k == "video" else         thumbs.audio_cover(path) if k == "audio" else None
    if k == "video":
        params["supports_streaming"] = "true"
    if cover:
        params["thumbnail"] = "attach://cover"
        files["cover"] = (cover.name, cover.read_bytes(), "image/jpeg")
        cover.unlink(missing_ok=True)
    with path.open("rb") as fh:
        try:
            msg = tg(f"send{k.capitalize()}", _timeout=600,
                     files={k: (path.name, fh, mime(path)), **files}, **params)
        except RuntimeError as e:
            if isinstance(e, TelegramError) and e.code == 429:
                raise
            # p.ej. una foto con dimensiones raras: se manda como documento
            log.info("reintento como documento: %s", e)
            fh.seek(0)
            params = {p: v for p, v in params.items()
                      if p in ("chat_id", "caption", "parse_mode", *reply_args(1))}
            msg = tg("sendDocument", _timeout=600,
                     files={"document": (path.name, fh, mime(path))}, **params)
    return file_id_of(msg)


def send_album(chat, paths, caption, reply_to=None, as_doc=False):
    """Fotos/videos (o archivos, con as_doc) en grupos de 10; el pie va en el primero."""
    sent = []
    for i in range(0, len(paths), 10):
        chunk = paths[i:i + 10]
        for attempt in range(4):
            media, files, handles = [], {}, []
            try:
                for n, p in enumerate(chunk):
                    fh = p.open("rb")
                    handles.append(fh)
                    files[f"f{n}"] = (p.name, fh, mime(p))
                    item = {"type": "document" if as_doc else kind(p),
                            "media": f"attach://f{n}"}
                    if i == 0 and n == 0 and caption:
                        item.update(caption=caption, parse_mode="HTML")
                    if item["type"] == "video":
                        item["supports_streaming"] = True
                    media.append(item)
                msgs = tg("sendMediaGroup", _timeout=900, files=files, chat_id=chat,
                          media=json.dumps(media), **reply_args(reply_to if i == 0 else None))
                sent += [file_id_of(m) for m in msgs]
                break
            except TelegramError as e:
                # Muchos albumes seguidos: Telegram pide esperar. Se reabren los archivos
                if e.code != 429 or not e.retry_after or e.retry_after > 120 or attempt == 3:
                    raise
                log.info("sendMediaGroup: Telegram pide esperar %s s", e.retry_after)
                time.sleep(e.retry_after + 1)
            finally:
                for fh in handles:
                    fh.close()
    return sent


def size_limit():
    """50 MB por la Bot API; hasta 2 GB si hay credenciales MTProto."""
    return bigupload.MAX_BYTES if bigupload.available() else MAX_BYTES


class ChatAction:
    """Lo que Telegram muestra bajo el nombre del bot mientras se trabaja: «escribiendo…»,
    «enviando vídeo…». Cada aviso dura ~5 s: se repite cada 4 s hasta stop()."""

    def __init__(self, chat, action="typing"):
        self.chat, self.action, self._stop = chat, action, threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        return self

    def _loop(self):
        while not self._stop.is_set():
            try:
                tg("sendChatAction", _timeout=10, chat_id=self.chat, action=self.action)
            except Exception:
                pass
            self._stop.wait(4)

    def stop(self):
        self._stop.set()


def acting(action, fn):
    """fn(chat, ...) con la accion de chat puesta mientras dura (comandos en hilo)."""
    def run(chat, *args):
        act = ChatAction(chat, action).start()
        try:
            fn(chat, *args)
        finally:
            act.stop()
    return run


def upload_action(files, mode):
    if mode == "file":
        return "upload_document"
    if mode in ("mp3", "song"):
        return "upload_voice"
    return "upload_video" if any(kind(f) == "video" for f in files) else "upload_photo"


def publish(chat, files, caption, status=None, extra=None, reply_to=None, as_doc=False,
            status_chat=None):
    """Envia los archivos y devuelve lo enviado para la cache:
    [("photo"|"video"|..., file_id)] o [("copy", chat, message_id)] si fue por MTProto.
    Si reply_to, el primer envio responde a ese mensaje. Con as_doc todo va como
    archivo: Telegram no lo recomprime (las fotos llegan en calidad original)."""
    big = [f for f in files if f.stat().st_size > MAX_BYTES]
    small = [f for f in files if f not in big]
    albumable = [f for f in small if as_doc or kind(f) in ("photo", "video")]
    sent = None
    if len(small) > 1 and len(albumable) == len(small):
        try:
            sent = send_album(chat, small, caption, reply_to, as_doc)
        except RuntimeError as e:
            log.info("album fallo, envio uno a uno: %s", e)
    if sent is None:
        sent = [send_file(chat, f, caption if n == 0 else None, extra,
                          reply_to if n == 0 else None, as_doc)
                for n, f in enumerate(small)]
    for n, f in enumerate(big):
        first = not small and n == 0
        mb = f.stat().st_size / 2**20
        mid = bigupload.send(chat, f, caption if first else None,
                             progress=lambda p: edit(status_chat or chat, status,
                                                     f"📤 Subiendo {mb:.0f} MB… {p}%"),
                             reply_to=reply_to if first else None, as_doc=as_doc)
        sent.append(("copy", chat, mid))
        if getattr(_tl, "sent_msgs", None) is not None:
            _tl.sent_msgs.append([chat, mid])
    return [s for s in sent if s]


def send_cached(chat, items, caption, reply_to=None):
    """Reenvia algo ya subido antes, sin descargar ni subir nada."""
    types = {t for t, *_ in items}
    if len(items) > 1 and (types <= {"photo", "video"} or types == {"document"}):
        for i in range(0, len(items), 10):
            media = []
            for n, (t, fid) in enumerate(items[i:i + 10]):
                item = {"type": t, "media": fid}
                if i == 0 and n == 0:
                    item.update(caption=caption, parse_mode="HTML")
                media.append(item)
            res = tg("sendMediaGroup", chat_id=chat, media=json.dumps(media),
                     **reply_args(reply_to if i == 0 else None))
            _note_sent(chat, *(m["message_id"] for m in res))
        return
    for n, it in enumerate(items):
        first = {"caption": caption, "parse_mode": "HTML", **reply_args(reply_to)} if n == 0 else {}
        if it[0] == "copy":
            res = tg("copyMessage", chat_id=chat, from_chat_id=it[1], message_id=it[2], **first)
        else:
            res = tg(f"send{it[0].capitalize()}", chat_id=chat, **{it[0]: it[1]}, **first)
        _note_sent(chat, res["message_id"])


def _note_sent(chat, *mids):
    """Apunta los mensajes enviados en este hilo (archivo y botones bajo el video)."""
    if getattr(_tl, "sent_msgs", None) is not None:
        _tl.sent_msgs += [[chat, m] for m in mids]


def media_buttons(chat, mode):
    """En un privado, botones bajo lo recien enviado (si fue un solo mensaje: los albumes
    no admiten botones): MP3, original y, para el dueño con NAS, guardar."""
    mids = [m for c, m in (getattr(_tl, "sent_msgs", None) or []) if c == chat]
    if chat < 0 or len(mids) != 1 or mode not in ("video", "file"):
        return
    owner, _ = load_owners()
    row = [("🎵 MP3", "/mp3"), ("📁 Original", "/original")]
    if chat == owner and ARCH_DAYS:
        row.append(("💾 NAS", "/guardar"))
    try:
        tg("editMessageReplyMarkup", chat_id=chat, message_id=mids[0], reply_markup=keyboard([row]))
    except Exception as e:
        log.info("botones bajo el video: %s", e)


# ---------------------------------------------------------------- Cache de enlaces

CACHE_FILE = BASE / "cache.json"
CACHE_MAX = 3000
cache_lock = threading.Lock()
TRACKING = re.compile(r"^(utm_\w+|si|igsh|igshid|feature|xmt|fbclid|mibextid|ref|ref_src|"
                      r"s|t|share_id|rdt|_r|is_from_webapp|sender_device|img_index|vrfl|psln|igsh\w*|"
                      r"story_media_id|hl|ssr|__a|__d)$")
# Redes donde el enlace de una publicacion nunca necesita parametros: se quitan todos
NO_QUERY_HOSTS = ("instagram.com", "tiktok.com", "threads.com", "threads.net")


def cache_key(url, mode):
    """Misma publicacion -> misma clave, aunque el enlace traiga basura de rastreo."""
    from urllib.parse import parse_qsl, urlencode, urlsplit
    u = urlsplit(url.strip())
    host = re.sub(r"^(www\.|m\.|mobile\.)", "", u.netloc.lower())
    q = dict(parse_qsl(u.query))
    if host.endswith(NO_QUERY_HOSTS):
        q = {}
    yt = None
    if host == "youtu.be":
        yt = u.path.strip("/")
    elif host.endswith("youtube.com"):
        yt = q.get("v") or (re.search(r"/(?:shorts|live|embed)/([\w-]+)", u.path) or [None, None])[1]
    if yt:
        return f"{mode}:youtube:{yt}"
    q = {k: v for k, v in q.items() if not TRACKING.match(k)}
    return f"{mode}:{host}{u.path.rstrip('/')}" + (f"?{urlencode(sorted(q.items()))}" if q else "")


# device.json "sqlite": true -> cache e indice del archivo en bot.db; sin el ajuste
# siguen los JSON. La primera vez se importan y los JSON quedan como *.importado.
SQL = bool(DEVICE.get("sqlite"))
CACHE_MAX_SQL = 50000          # en SQLite no se reescribe todo en cada cambio: cabe mas


def migrate_to_sqlite():
    if not SQL:
        return
    for path, fn, what in ((CACHE_FILE, db.import_cache, "caché"),
                           (ARCH_INDEX, db.import_archivo, "índice del archivo")):
        if path.exists():
            try:
                n = fn(path)
                log.info("sqlite: importadas %d entradas de %s", n, path.name)
                health.event("actualizacion", f"{what} pasado a SQLite ({n} entradas)")
            except Exception:
                log.exception("importar %s", path.name)


def cache_get(key):
    if SQL:
        try:
            return db.cache_get(key)
        except Exception:
            log.exception("cache_get")
            return None
    with cache_lock:
        try:
            return json.loads(CACHE_FILE.read_text()).get(key)
        except (OSError, ValueError):
            return None


def cache_put(keys, items, title):
    if SQL:
        try:
            db.cache_put(keys, items, title, CACHE_MAX_SQL)
        except Exception:
            log.exception("cache_put")
        return
    with cache_lock:
        try:
            cache = json.loads(CACHE_FILE.read_text())
        except (OSError, ValueError):
            cache = {}
        for k in keys:
            cache[k] = {"items": items, "title": title, "t": int(time.time())}
        if len(cache) > CACHE_MAX:
            cache = dict(sorted(cache.items(), key=lambda kv: kv[1]["t"])[-CACHE_MAX:])
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False))


def cache_drop(key):
    if SQL:
        try:
            db.cache_drop(key)
        except Exception:
            log.exception("cache_drop")
        return
    with cache_lock:
        try:
            cache = json.loads(CACHE_FILE.read_text())
            cache.pop(key, None)
            CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False))
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------- Descargas

_tl = threading.local()   # ultimo error de cada hilo, para los avisos


# ---------------------------------------------------------------- Archivo local y NAS
# Lo que el bot descarga y envia se queda unos dias en el movil (device.json
# "archivo_dias"; en un movil con poco espacio, mejor no activarlo). /guardar lo copia al NAS (el disco
# USB), donde no se borra. Indice: [{t, chat, msgs: [[chat, message_id]], url, title,
# dir, files}], para encontrar los archivos al responder a un mensaje del bot.
ARCH_DAYS = DEVICE.get("archivo_dias", 0)
ARCH = BASE / "archivo"
ARCH_INDEX = ARCH / "indice.json"
NAS = Path(DEVICE.get("nas", "/mnt/disk/Guardado"))
arch_lock = threading.Lock()


def _arch_load():
    try:
        return json.loads(ARCH_INDEX.read_text())
    except (OSError, ValueError):
        return []


def archive_put(files, chat, msgs, url, title, mode="video"):
    """Mueve los archivos ya enviados al archivo (si esta activado)."""
    if not ARCH_DAYS or not files:
        return
    try:
        with arch_lock:
            d = ARCH / time.strftime("%Y%m%d") / f"{abs(chat)}_{int(time.time() * 1000)}"
            d.mkdir(parents=True, exist_ok=True)
            names = []
            for f in files:
                if f.exists():
                    shutil.move(str(f), d / f.name)
                    names.append(f.name)
            if SQL:
                db.archivo_put(int(time.time()), chat, msgs, url, title, mode,
                               str(d.relative_to(ARCH)), names)
            else:
                idx = _arch_load()
                idx.append({"t": int(time.time()), "chat": chat, "msgs": msgs, "url": url,
                            "title": title, "mode": mode, "dir": str(d.relative_to(ARCH)),
                            "files": names})
                ARCH_INDEX.write_text(json.dumps(idx, ensure_ascii=False))
    except Exception:
        log.exception("archive_put")


def archive_find(chat, msg_id=None, url=None, audio=False):
    """La entrada mas reciente de ese mensaje del bot (o de ese enlace, del mismo tipo:
    audio o video) cuyos archivos sigan en el movil."""
    entries = db.archivo_buscar(chat, msg_id, url) if SQL else reversed(_arch_load())
    for e in entries:
        is_audio = e.get("mode") in ("mp3", "song") if e.get("mode") else \
            all(n.lower().endswith((".mp3", ".m4a", ".opus", ".ogg")) for n in e["files"])
        same_kind = is_audio == audio
        if (msg_id and [chat, msg_id] in e["msgs"]) or (url and url == e.get("url") and same_kind):
            if all((ARCH / e["dir"] / n).exists() for n in e["files"]):
                return e
    return None


def archive_clean():
    """Borra lo que tiene mas de ARCH_DAYS dias (se llama cada hora)."""
    if not ARCH_DAYS:
        return
    limit = time.time() - ARCH_DAYS * 86400
    if SQL:
        with arch_lock:
            dirs = db.archivo_viejos(limit)
            for d in dirs:
                shutil.rmtree(ARCH / d, ignore_errors=True)
            if dirs:
                log.info("archivo: %d entrada(s) de más de %d días borradas", len(dirs), ARCH_DAYS)
            _clean_days(limit)
        return
    with arch_lock:
        idx = _arch_load()
        keep = [e for e in idx if e["t"] >= limit]
        for e in idx:
            if e["t"] < limit:
                shutil.rmtree(ARCH / e["dir"], ignore_errors=True)
        if len(keep) != len(idx):
            ARCH_INDEX.write_text(json.dumps(keep, ensure_ascii=False))
            log.info("archivo: %d entrada(s) de más de %d días borradas", len(idx) - len(keep),
                     ARCH_DAYS)
        _clean_days(limit)


def _clean_days(limit):
    """Carpetas de dias vacias o anteriores al limite (por su nombre AAAAMMDD), aunque no
    esten en el indice: p. ej. tras restaurar un bot.db de otro equipo."""
    cut = time.strftime("%Y%m%d", time.localtime(limit))
    for day in ARCH.glob("2*"):
        if day.is_dir() and (day.name < cut or not any(day.iterdir())):
            shutil.rmtree(day, ignore_errors=True)


def nas_save(files, title):
    """Copia los archivos al NAS como «AAAA-MM-DD - titulo.ext». -> lista de nombres."""
    # La marca .nas esta en la raiz del disco: sin ella, /mnt/disk seria una carpeta vacia
    # dentro del Debian (disco desconectado) y lo guardado no llegaria al disco
    if not (NAS.parent / ".nas").exists():
        raise RuntimeError("no hay disco USB conectado (el NAS está apagado)")
    NAS.mkdir(parents=True, exist_ok=True)
    base = re.sub(r'[\\/:*?"<>|\n]+', " ", title or "sin titulo").strip()[:100] or "sin titulo"
    out = []
    for n, f in enumerate(files, 1):
        name = f"{time.strftime('%Y-%m-%d')} - {base}" + (f" ({n})" if len(files) > 1 else "")
        dest = NAS / f"{name}{f.suffix}"
        i = 2
        while dest.exists():
            dest = NAS / f"{name} [{i}]{f.suffix}"
            i += 1
        shutil.copyfile(f, dest)
        out.append(dest.name)
    return out


def cola_command(chat, uid):
    """/cola: descargas en curso y en espera, con un boton para cancelar cada una. El
    dueño ve todas; los demas, las de su chat."""
    owner, _ = load_owners()
    mine = [j for j in list(jobs.items.values()) if uid == owner or j["chat"] == chat]
    mine.sort(key=lambda j: (not j.get("_start"), j.get("_t", 0)))
    voces = stt_jobs.qsize()
    if not mine:
        say(chat, "📭 No hay descargas en cola." + (f"\n🎙️ Notas de voz en cola: {voces}" if voces else ""))
        return
    lines, buttons = [], []
    for i, j in enumerate(mine, 1):
        if j.get("_cancel"):
            state = "🚫 cancelando"
        elif j.get("_start"):
            state = f"⏳ descargando ({health.ago(time.time() - j['_start'])})"
        else:
            state = "🕒 en espera"
        what = {"mp3": "🎵 ", "file": "📁 ", "song": "🎵 "}.get(j.get("mode"), "")
        lines.append(f"{i}. {state} · {what}{site_of(j['url'])}: {j['url'][:60]}")
        if not j.get("_cancel"):
            buttons.append([(f"❌ Cancelar {i}", f"/cancelar {j['_id']}")])
    say(chat, "📥 Cola de descargas:\n" + "\n".join(lines)
              + (f"\n\n🎙️ Notas de voz en cola: {voces}" if voces else ""), buttons=buttons)


def cancelar_command(chat, uid, arg):
    owner, _ = load_owners()
    j = jobs.items.get(arg.strip())
    if not j or (uid != owner and j["chat"] != chat):
        say(chat, "Esa descarga ya no está en la cola.")
        return
    j["_cancel"] = True
    proc = RUNNING.get(j.get("_thread")) if j.get("_start") else None
    if proc:
        proc.kill()                       # corta la descarga en marcha (yt-dlp, gallery-dl...)
    say(chat, f"🚫 Cancelada: {j['url'][:80]}")


YT_ID = re.compile(r"[\w-]{11}")


def buscar_command(msg, chat, arg):
    """/buscar texto: los primeros resultados de YouTube, con botones para bajar el video
    o solo el MP3."""
    q = arg.strip()
    if not q:
        say(chat, "🔎 Uso: /buscar texto (p. ej. /buscar documental ballenas)")
        return
    p = run([VENV_BIN / "yt-dlp", "--js-runtimes", "node", "--flat-playlist", "--print",
             "%(id)s\t%(duration_string)s\t%(title)s", f"ytsearch8:{q}"], "/", timeout=120)
    rows = [l.split("\t", 2) for l in p.stdout.splitlines() if l.count("\t") >= 2]
    rows = [r for r in rows if YT_ID.fullmatch(r[0])]
    if not rows:
        say(chat, "🔎 No encontré nada.")
        return
    text = [f"🔎 <b>{html.escape(q)}</b>"] + [
        f"{i}. {html.escape(t[:80])} <i>({d if d != 'NA' else 'directo'})</i>"
        for i, (vid, d, t) in enumerate(rows, 1)]
    say(chat, "\n".join(text) + "\n\n▶️ el vídeo · 🎵 solo el audio", parse_mode="HTML",
        buttons=[[(f"{i}. ▶️ {t[:24]}", f"/yt {vid}"), (f"🎵 {i}", f"/ytmp3 {vid}")]
                 for i, (vid, d, t) in enumerate(rows, 1)])


PERIODOS = {"hoy": "hoy", "semana": "últimos 7 días", "mes": "últimos 30 días", "todo": "desde el principio"}


def stats_text(arg):
    """/stats [hoy|semana|mes|todo]: lo que ha hecho el bot (de bot.db)."""
    p = arg.strip().lower() or "semana"
    p = p if p in PERIODOS else "semana"
    now = time.time()
    since = {"hoy": time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1)),
             "semana": now - 7 * 86400, "mes": now - 30 * 86400, "todo": 0}[p]
    q = lambda sql, *a: db.query(sql, (since, *a))
    first = db.query("SELECT MIN(t) FROM descargas")[0][0]
    if not first:
        return "📊 Aún no hay nada registrado (se apunta desde que se activó /stats)."
    gb = lambda b: f"{(b or 0) / 2**30:.1f} GB" if (b or 0) >= 2**30 else f"{(b or 0) / 2**20:.0f} MB"
    res = {r: (n, b) for r, n, b in q("SELECT resultado, COUNT(*), SUM(bytes) FROM descargas "
                                       "WHERE t >= ? GROUP BY resultado")}
    total = sum(n for n, _ in res.values())
    get = lambda k: res.get(k, (0, 0))
    out = [f"📊 <b>Estadísticas</b> · {PERIODOS[p]}",
           f"⬇️ Enlaces: <b>{total}</b> (✅ {get('ok')[0]} nuevos · ⚡ {get('cache')[0]} de caché"
           f" · ❌ {get('fallo')[0]} fallos"
           + (f" · 🚫 {get('cancelado')[0]} cancelados" if get('cancelado')[0] else "")
           + (f" · 💾 {get('nas')[0]} al NAS" if get('nas')[0] else "") + ")",
           f"📦 Descargado: {gb(get('ok')[1] + get('nas')[1])}"]
    avg = q("SELECT AVG(segundos) FROM descargas WHERE t >= ? AND resultado = 'ok'")[0][0]
    if avg:
        out.append(f"⏱️ Tiempo medio de una descarga nueva: {avg:.0f} s")
    redes = q("SELECT red, COUNT(*) FROM descargas WHERE t >= ? AND resultado IN ('ok','cache','nas') "
              "GROUP BY red ORDER BY 2 DESC LIMIT 8")
    if redes:
        out.append("🌐 Por red: " + " · ".join(f"{r} {n}" for r, n in redes))
    gente = q("SELECT COALESCE(quien, '—'), COUNT(*) FROM descargas WHERE t >= ? AND resultado "
              "IN ('ok','cache','nas') GROUP BY 1 ORDER BY 2 DESC LIMIT 6")
    if gente:
        out.append("👥 Quién: " + " · ".join(f"{html.escape(w)} {n}" for w, n in gente))
    fallos = q("SELECT red, COUNT(*), error FROM descargas WHERE t >= ? AND resultado = 'fallo' "
               "GROUP BY red ORDER BY 2 DESC LIMIT 4")
    if fallos:
        out.append("❌ Fallos: " + " · ".join(f"{r} {n}" for r, n, _ in fallos))
        if fallos[0][2]:
            out.append(f"   <i>último de {fallos[0][0]}: {html.escape(fallos[0][2][:120])}</i>")
    if p != "hoy":
        dia = q("SELECT strftime('%d/%m', t, 'unixepoch', 'localtime'), COUNT(*) FROM descargas "
                "WHERE t >= ? GROUP BY 1 ORDER BY 2 DESC LIMIT 1")
        if dia:
            out.append(f"📅 Día con más: {dia[0][0]} ({dia[0][1]} enlaces)")
    n, aud, ratio = q("SELECT COUNT(*), SUM(audio_seg), AVG(tardo_seg / NULLIF(audio_seg, 0)) "
                      "FROM voz WHERE t >= ? AND ok = 1")[0]
    if n:
        out.append(f"🎙️ Notas de voz: {n} ({aud / 60:.0f} min de audio; transcritas a "
                   f"{ratio or 0:.1f}× su duración)")
    out.append(f"\n<i>Registros desde el {time.strftime('%d/%m/%Y', time.localtime(first))}.</i>")
    return "\n".join(out)


def link_of(m):
    """Primer enlace de un mensaje: el del titulo enlazado (text_link) o uno escrito."""
    for e in (m.get("caption_entities") or m.get("entities") or []):
        if e.get("type") == "text_link":
            return e["url"]
    urls = URL_RE.findall(m.get("caption") or m.get("text") or "")
    return urls[0] if urls else None


def guardar_command(msg, chat, arg):
    """/guardar respondiendo a algo que mando el bot (o con un enlace): al NAS."""
    if not ARCH_DAYS:
        say(chat, "💾 Este equipo no tiene NAS.", reply_to=msg["message_id"])
        return
    r = msg.get("reply_to_message") or {}
    urls = URL_RE.findall(arg)
    url = urls[0] if urls else (link_of(r) if r else None)
    if not r and not url:
        say(chat, "💾 Responde con /guardar a un vídeo, foto o enlace que te haya mandado, "
                  "o escribe /guardar <enlace>. Se copia al NAS y ahí no se borra.")
        return
    e = archive_find(chat, r.get("message_id"), url, audio=bool(r.get("audio"))) if ARCH_DAYS else None
    try:
        if e:
            names = nas_save([ARCH / e["dir"] / n for n in e["files"]], e.get("title"))
            say(chat, "💾 Guardado en el NAS:\n" + "\n".join(names), reply_to=msg["message_id"])
            health.event("nas", f"guardado {e.get('title') or e['files'][0]}"[:150])
        elif url:
            # Ya no esta en el movil (o nunca lo estuvo): se baja directo al NAS
            jobs.put({"chat": chat, "msg_id": msg["message_id"], "url": url,
                      "mode": "mp3" if r.get("audio") else "video",
                      "sender": "", "only_link": False, "reply_to": msg["message_id"],
                      "save_only": True})
        else:
            say(chat, "💾 Eso ya no está en el móvil y no tiene enlace del que volver a "
                      "bajarlo.", reply_to=msg["message_id"])
    except Exception as ex:
        say(chat, f"❌ No pude guardarlo: {ex}", reply_to=msg["message_id"])


RUNNING = {}   # hilo -> proceso que esta ejecutando (para cortarlo con /cola)


def run(cmd, cwd, timeout=900):
    log.info("run: %s", " ".join(map(str, cmd)))
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    RUNNING[threading.get_ident()] = proc
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    finally:
        RUNNING.pop(threading.get_ident(), None)
    p = subprocess.CompletedProcess(cmd, proc.returncode, out, err)
    if p.returncode:
        log.info("rc=%s stderr=%s", p.returncode, p.stderr[-800:])
        _tl.last_err = p.stderr.strip().splitlines()[-1][:300] if p.stderr.strip() else ""
    return p


# ---------------------------------------------------------------- Avisos al dueño

_alert_last = {}
_fails = {}
AUTH_ERR = re.compile(r"redirect to login|login required|log ?in to|logged.in|sign in to confirm|"
                      r"use --cookies|cookies.+(expired|invalid)|checkpoint|rate.?limit|"
                      r"requires authentication|not logged", re.I)


def alert(key, text, cooldown):
    """Mensaje privado al dueño, como mucho una vez por `cooldown` segundos por tipo."""
    owner, _ = load_owners()
    now = time.time()
    if not owner or now - _alert_last.get(key, 0) < cooldown:
        return
    _alert_last[key] = now
    log.info("aviso %s", key)
    if not key.startswith(("red-", "boot")):       # esos ya tienen su propio evento
        health.event("aviso", text.splitlines()[0])
    say(owner, text)


def site_of(url):
    from urllib.parse import urlsplit
    host = urlsplit(url).netloc.lower()
    for s in ("instagram", "facebook", "youtube", "tiktok", "threads", "twitter", "x.com", "reddit"):
        if s in host or (s == "youtube" and "youtu.be" in host):
            return s.replace(".com", "")
    return re.sub(r"^www\.", "", host)


def check_auth(url, p):
    """Si una descarga falla por falta de sesion, avisar para renovar cookies."""
    if p.returncode == 0 and "login" not in p.stderr.lower():
        return
    if not AUTH_ERR.search(p.stderr):
        return
    site = site_of(url)
    if site in ("instagram", "facebook"):
        alert(f"cookies-{site}", f"🍪 Las cookies de {site.capitalize()} parecen caducadas o "
              "bloqueadas: está pidiendo iniciar sesión.\n\nExporta unas nuevas de la cuenta "
              "secundaria y mándamelas aquí como archivo .txt.", 12 * 3600)
    elif site == "youtube":
        alert("auth-youtube", "▶️ YouTube está pidiendo verificar que no soy un robot. "
              "Si se repite, mándame cookies de YouTube de una cuenta secundaria.", 12 * 3600)


def record_failure(url):
    """3 fallos de la misma red en 1 hora -> aviso."""
    site, now = site_of(url), time.time()
    hits = [t for t in _fails.get(site, []) if now - t < 3600] + [now]
    _fails[site] = hits
    health.event("fallo", f"{site}: {getattr(_tl, 'last_err', '') or 'sin detalle'}"[:200])
    if len(hits) >= 3:
        err = getattr(_tl, "last_err", "") or "sin detalle"
        alert(f"fails-{site}", f"⚠️ {len(hits)} fallos con {site} en la última hora.\n"
              f"Último error: {err}\n\nPrueba /actualizar; si sigue, puede que "
              f"{site} haya cambiado algo.", 6 * 3600)


def charge_paused():
    """"1" si charge.sh tiene la carga en pausa (movil viviendo del cargador), "0" si no.
    Lo escribe charge.sh en /opt/bot/charge_paused, sea cual sea el driver de la bateria."""
    return read_sys(BASE / "charge_paused", "0")


def monitor_loop():
    """Vigila temperatura, bateria y disco cada minuto (y limpia el archivo cada hora)."""
    bat = "/sys/class/power_supply/battery"
    n = 0
    while True:
        if n % 60 == 0:
            try:
                archive_clean()
            except Exception:
                log.exception("archive_clean")
        n += 1
        try:
            temp = int(read_sys(f"{bat}/temp", "0")) / 10
            cap = int(read_sys(f"{bat}/capacity", "100"))
            status = read_sys(f"{bat}/status")
            watch_power(cap, status, charge_paused())
            if temp >= 42:
                alert("temp", f"🌡️ La batería está a {temp:.1f} °C. He parado la carga; "
                      "si sigue subiendo, ponlo en un sitio más fresco.", 3600)
            if cap <= 15 and status != "Charging":
                alert("lowbat", f"🪫 Batería al {cap}% y no está cargando. "
                      "¿Se desconectó el cargador?", 6 * 3600)
        except Exception:
            log.exception("monitor")
        time.sleep(60)


def clear(d: Path):
    for f in sorted(d.rglob("*"), reverse=True):
        f.unlink() if f.is_file() else f.rmdir()


def media_files(d: Path):
    return [f for f in sorted(d.rglob("*"))
            if f.is_file() and not f.name.endswith((".part", ".json", ".ytdl", ".txt"))]


def meta_title(d: Path):
    """Saca un titulo de los .json de metadatos de yt-dlp / gallery-dl."""
    for j in sorted(d.rglob("*.json")):
        try:
            m = json.loads(j.read_text())
        except Exception:
            continue
        title = m.get("title") or m.get("fulltitle") or ""
        desc = (m.get("description") or m.get("content") or m.get("caption")
                or m.get("selftext") or "")
        if isinstance(desc, dict):
            desc = desc.get("text", "")
        # Titulos genericos tipo "Video by fulano" -> mejor la descripcion
        if desc and (not title or re.match(r"^(Video|Post|Photo|Reel) by ", title)
                     or title.startswith(("Instagram", "Facebook"))):
            title = desc
        if title:
            return title
    return ""


def page_title(url):
    try:
        r = http.get(url, timeout=15, headers={"User-Agent": UA})
        m = (re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', r.text)
             or re.search(r"<title[^>]*>([^<]+)</title>", r.text))
        return html.unescape(m.group(1)) if m else ""
    except Exception:
        return ""


_cookie_lock = threading.Lock()


def cookie_args(d: Path):
    """Las herramientas reciben una copia de las cookies: yt-dlp y gallery-dl reescriben
    el archivo al terminar y, si la web cierra la sesion, la borran (asi se perdio la
    sessionid de Instagram). Lo nuevo que traigan lo pasa keep_cookies() al original."""
    if not COOKIES.exists():
        return []
    tmp = d / ".cookies.txt"
    shutil.copyfile(COOKIES, tmp)
    return ["--cookies", str(tmp)]


def _cookie_lines(text):
    out = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 7 and (not line.startswith("#") or line.startswith("#HttpOnly_")):
            out[(parts[0].removeprefix("#HttpOnly_").lstrip("."), parts[2], parts[5])] = line
    return out


def keep_cookies(d: Path):
    """Copia al original las cookies nuevas o renovadas, sin borrar ninguna."""
    tmp = d / ".cookies.txt"
    if not tmp.exists() or not COOKIES.exists():
        return
    with _cookie_lock:
        cur = _cookie_lines(COOKIES.read_text(errors="replace"))
        new = {k: v for k, v in _cookie_lines(tmp.read_text(errors="replace")).items()
               if cur.get(k) != v}
        if not new:
            return
        cur.update(new)
        part = COOKIES.with_suffix(".tmp")
        part.write_text("# Netscape HTTP Cookie File\n" + "\n".join(cur.values()) + "\n")
        part.chmod(0o640)
        part.replace(COOKIES)


def try_ytdlp(url, d: Path, heights=(720, 480, 360), cookies=True):
    # De mejor a peor calidad. A igual resolucion, H.264/MP4 primero para que Telegram
    # lo reproduzca dentro del chat (la resolucion manda sobre el codec).
    limit = size_limit()
    for height in heights:
        clear(d)
        p = run([
            VENV_BIN / "yt-dlp", "--js-runtimes", "node", "--no-playlist",
            "--no-progress", "--restrict-filenames", "--write-info-json",
            "-f", f"bv*[height<={height}]+ba/b[height<={height}]/b",
            "-S", f"res:{height},vcodec:h264,acodec:m4a",
            "--merge-output-format", "mp4",
            "--max-filesize", str(int(limit * 1.5)),
            *(cookie_args(d) if cookies else []),
            "-o", "%(id)s.%(ext)s", url,
        ], d, timeout=3600)
        if cookies:
            keep_cookies(d)
            check_auth(url, p)
        if p.returncode:
            return None
        files = media_files(d)
        if files and all(f.stat().st_size <= limit for f in files):
            return files
        # demasiado grande (o descartado por --max-filesize): menos resolucion
    return media_files(d)


THREADS_RE = re.compile(r"^https?://(www\.)?threads\.(com|net)/", re.I)
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def download_to(url, out_stem: Path):
    """Descarga un medio; la extension sale del content-type. None si es muy grande."""
    r = http.get(url, stream=True, timeout=60, headers={"User-Agent": MOBILE_UA})
    r.raise_for_status()
    ctype = r.headers.get("content-type", "").split(";")[0]
    ext = {"image/jpeg": ".jpg", "image/webp": ".webp", "image/png": ".png",
           "video/mp4": ".mp4"}.get(ctype) or mimetypes.guess_extension(ctype) or ".bin"
    out = out_stem.with_suffix(ext)
    total = 0
    with out.open("wb") as fh:
        for chunk in r.iter_content(256 * 1024):
            total += len(chunk)
            if total > MAX_BYTES:
                fh.close()
                out.unlink()
                return None
            fh.write(chunk)
    if ext == ".webp":  # los albumes de Telegram prefieren JPG
        jpg = out.with_suffix(".jpg")
        if run(["ffmpeg", "-loglevel", "error", "-y", "-i", out, jpg], out.parent).returncode == 0:
            out.unlink()
            out = jpg
    return out


def try_threads(url, d: Path):
    """Threads no tiene extractor en yt-dlp/gallery-dl: se usa la pagina /embed,
    que viene renderizada con las fotos y videos del post en orden."""
    if not THREADS_RE.match(url):
        return None
    clear(d)
    # Los enlaces /share/ redirigen al post real con un User-Agent movil
    r = http.get(url, timeout=30, headers={"User-Agent": MOBILE_UA})
    m = re.search(r"threads\.(?:com|net)/(@[\w.]+)/post/([\w-]+)", r.url) \
        or re.search(r"/(@[\w.]+)/post/([\w-]+)", url)
    if not m:
        log.info("threads: no encuentro el post en %s", r.url)
        return None
    user, code = m.groups()
    page = http.get(f"https://www.threads.com/{user}/post/{code}/embed", timeout=30,
                    headers={"User-Agent": MOBILE_UA}).text

    media = []
    for tag in re.finditer(r"<(img|source)\b[^>]*>", page):
        t = tag.group(0)
        src = re.search(r'src="([^"]+)"', t)
        if not src:
            continue
        src = html.unescape(src.group(1))
        if tag.group(1) == "img":
            alt = re.search(r'alt="([^"]*)"', t)
            if (alt and alt.group(1)) or "Favicon" in t or "s100x100" in src \
                    or not re.search(r"(cdninstagram|fbcdn)\.", src):
                continue  # foto de perfil, iconos de comunidad, etc.
        if src not in media:
            media.append(src)

    files = []
    for n, src in enumerate(media[:MAX_FILES]):
        try:
            f = download_to(src, d / f"{code}_{n:02d}")
            if f:
                files.append(f)
        except Exception as e:
            log.info("threads: fallo medio %d: %s", n, e)

    body = re.search(r'class="[^"]*BodyTextContainer[^"]*"[^>]*>(.*?)</div>', page, re.S)
    caption = html.unescape(re.sub(r"<[^>]+>", " ", body.group(1))).strip() if body else ""
    (d / "_threads.json").write_text(json.dumps({"title": caption or f"{user} en Threads"}))
    log.info("threads %s/%s: %d medio(s)", user, code, len(files))
    return files or None


def try_gallerydl(url, d: Path, cookies=True):
    clear(d)
    p = run([VENV_BIN / "gallery-dl", "--write-metadata", "--range", f"1-{MAX_FILES}",
             *(cookie_args(d) if cookies else []), "-D", ".", url], d)
    if cookies:
        keep_cookies(d)
        check_auth(url, p)
    files = media_files(d)
    return files if p.returncode in (0, 4) and files else None


INSTAGRAM_RE = re.compile(r"^https?://(www\.)?instagram\.com/(p|reels?|tv)/", re.I)


def try_instagram(url, d: Path):
    """Post de Instagram sin sesion. yt-dlp solo baja videos y gallery-dl exige sesion,
    pero el JSON que yt-dlp saca sin cookies trae cada foto del carrusel a tamaño
    original (`thumbnail`); los videos del carrusel se bajan con yt-dlp, uno a uno."""
    if not INSTAGRAM_RE.match(url):
        return None
    clear(d)
    p = run([VENV_BIN / "yt-dlp", "--ignore-no-formats-error", "-J", url], d)
    try:
        info = json.loads(p.stdout)
    except ValueError:
        return None
    files = []
    for n, e in enumerate((info.get("entries") or [info])[:MAX_FILES], 1):
        try:
            if e.get("formats"):
                run([VENV_BIN / "yt-dlp", "--no-progress", "--playlist-items", str(n),
                     "-f", "b[ext=mp4]/bv*+ba/b", "--merge-output-format", "mp4",
                     "-o", f"{n:02d}_%(id)s.%(ext)s", url], d, timeout=1800)
                files += sorted(d.glob(f"{n:02d}_*.mp4"))
            elif e.get("thumbnail"):
                f = download_to(e["thumbnail"], d / f"{n:02d}_{e.get('id') or 'foto'}")
                if f:
                    files.append(f)
        except Exception as ex:
            log.info("instagram: fallo medio %d: %s", n, ex)
    (d / "_instagram.json").write_text(json.dumps({
        "title": info.get("title") or "", "description": info.get("description") or "",
        "webpage_url": info.get("webpage_url") or url}))
    log.info("instagram sin sesion: %d medio(s)", len(files))
    return files or None


def try_audio(url, d: Path):
    """/mp3: solo el audio, MP3 192 kbps con portada y etiquetas."""
    clear(d)
    p = run([VENV_BIN / "yt-dlp", "--js-runtimes", "node", "--no-playlist", "--no-progress",
             "--restrict-filenames", "--write-info-json", "-x", "--audio-format", "mp3",
             "--audio-quality", "192K", "--embed-thumbnail", "--embed-metadata",
             *cookie_args(d), "-o", "%(title).80B.%(ext)s", url], d, timeout=3600)
    keep_cookies(d)
    check_auth(url, p)
    files = [f for f in media_files(d) if f.suffix == ".mp3"]
    return files if p.returncode == 0 and files else None


def song_cover(song: Path, info: dict):
    """Portada cuadrada para la cancion. Los temas de catalogo (los que traen album) tienen
    la tapa del disco cuadrada y centrada en una imagen 16:9 con barras de color a los
    lados: se recorta al cuadrado central. Los videos subidos por usuarios se dejan enteros.
    Se incrusta en el m4a sin tocar el audio."""
    vid = info.get("id") or song.stem
    raw = song.with_suffix(".cover.jpg")
    for name in ("maxresdefault", "hq720", "sddefault", "hqdefault"):
        r = http.get(f"https://i.ytimg.com/vi/{vid}/{name}.jpg", timeout=30)
        if r.status_code == 200 and len(r.content) > 5000:
            raw.write_bytes(r.content)
            break
    else:
        return
    vf = ["-vf", "crop='min(iw,ih)':'min(iw,ih)'"] if info.get("album") else []
    out = song.with_suffix(".tmp.m4a")
    q = run(["ffmpeg", "-loglevel", "error", "-y", "-i", song, "-i", raw, "-map", "0:a",
             "-map", "1:v", "-c:a", "copy", "-c:v", "mjpeg", *vf, "-q:v", "2",
             "-disposition:v:0", "attached_pic", "-movflags", "+faststart", out], song.parent)
    raw.unlink(missing_ok=True)
    if q.returncode == 0 and out.exists() and out.stat().st_size > song.stat().st_size:
        out.replace(song)
    else:
        out.unlink(missing_ok=True)


def try_song(url, d: Path):
    """Like de YouTube Music: el mejor audio disponible (AAC ~130 kbps, o Opus pasado a
    m4a si no hay AAC) con portada cuadrada y etiquetas. Sin recodificar a MP3."""
    clear(d)
    p = run([VENV_BIN / "yt-dlp", "--js-runtimes", "node", "--no-playlist", "--no-progress",
             "--restrict-filenames", "--write-info-json",
             "-f", "bestaudio[ext=m4a]/bestaudio", "-x", "--audio-format", "m4a",
             "--embed-metadata", *cookie_args(d), "-o", "%(id)s.%(ext)s", url], d, timeout=1800)
    keep_cookies(d)
    check_auth(url, p)
    files = [f for f in media_files(d) if f.suffix == ".m4a"]
    if p.returncode or not files:
        return None
    try:
        info = json.loads(next(d.glob("*.info.json")).read_text())
        song_cover(files[0], info)
    except Exception as e:
        log.info("portada: %s", e)      # sin portada es mejor que sin cancion
    return files


def audio_tags(d: Path):
    for j in d.glob("*.info.json"):
        try:
            m = json.loads(j.read_text())
        except ValueError:
            continue
        tags = {"title": (m.get("track") or m.get("title") or "")[:200],
                "performer": (m.get("artist") or m.get("uploader") or m.get("channel") or "")[:100]}
        if m.get("duration"):
            tags["duration"] = int(m["duration"])
        return {k: v for k, v in tags.items() if v}
    return {}


def try_direct(url, d: Path):
    clear(d)
    r = http.get(url, stream=True, timeout=30, headers={"User-Agent": UA})
    ctype = r.headers.get("content-type", "").split(";")[0]
    if not ctype.startswith(("image/", "video/", "audio/")):
        return None
    ext = mimetypes.guess_extension(ctype) or ""
    out = d / ((Path(url.split("?")[0]).stem or "archivo")[:60] + ext)
    total = 0
    with out.open("wb") as fh:
        for chunk in r.iter_content(256 * 1024):
            total += len(chunk)
            if total > MAX_BYTES:
                return None
            fh.write(chunk)
    return [out]


def clean_url(url):
    """Enlace del pie sin rastreadores (?si=, igsh, fbclid…, que dicen quien lo compartio).
    YouTube se deja en su forma canonica; de lo demas solo se quitan los rastreadores."""
    from urllib.parse import parse_qsl, urlencode, urlsplit
    try:
        u = urlsplit(url.strip())
        host = u.netloc.lower()
        q = dict(parse_qsl(u.query))
        vid = None
        if host in ("youtu.be", "www.youtu.be"):
            vid = u.path.strip("/")
        elif host.endswith("youtube.com") and not host.startswith("music."):
            m = re.match(r"/(shorts|live|embed)/([\w-]+)", u.path)
            if m and m.group(1) == "shorts":
                return f"https://www.youtube.com/shorts/{m.group(2)}"
            vid = q.get("v") or (m.group(2) if m else None)
        if vid:
            t = q.get("t") or q.get("start")       # el minuto del vídeo sí es útil
            return f"https://www.youtube.com/watch?v={vid}" + (f"&t={t}" if t else "")
        keep = {} if host.lstrip("w.").endswith(NO_QUERY_HOSTS) else             {k: v for k, v in q.items() if not TRACKING.match(k)}
        return u._replace(query=urlencode(keep), fragment="").geturl()
    except ValueError:
        return url


def build_caption(title, url, sender):
    url = clean_url(url)
    title = " ".join((title or "").split()) or "Ver original"
    if len(title) > 200:
        title = title[:197].rstrip() + "…"
    cap = f'<a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>'
    if sender:
        cap += f"\nvía {html.escape(sender)}"
    return cap


DEFAULT_HEIGHTS = (1080, 720, 480, 360)   # 1080p; si pasa de 2 GB, 720p y asi


def handle(job):
    chat, msg_id, url = job["chat"], job["msg_id"], job["url"]
    _tl.ok = False                              # el worker lo lee (colas masivas de plugins)
    targets = job.get("targets") or [chat]     # donde se publica; `chat` lleva el aviso
    mode = job.get("mode", "video")
    key = cache_key(url, mode)

    # 1) Ya enviado antes: reenviar al instante sin descargar (salvo /guardar, que necesita
    # el archivo para el NAS)
    hit = None if job.get("save_only") else cache_get(key)
    if hit:
        try:
            _tl.sent_msgs = []
            for t in targets:
                send_cached(t, hit["items"],
                            "" if mode == "song" else build_caption(hit["title"], url, job["sender"]),
                            job.get("reply_to") if t == chat else None)
            if not job.get("quiet") and not job.get("bulk"):
                media_buttons(chat, mode)
            _tl.sent_msgs = None
            log.info("cache %s", key)
            _tl.reg = {"res": "cache"}
            _tl.ok = True
            bump("links")
            if job["only_link"]:
                delete(chat, msg_id)
            return
        except Exception as e:
            log.info("cache invalida %s: %s", key, e)
            cache_drop(key)

    # 2) Descargar
    quiet = job.get("quiet")      # trabajos automaticos: al privado solo si algo falla
    status = None if quiet else say(
        chat, "🎵 Sacando el audio…" if mode in ("mp3", "song") else "⏳ Descargando…",
        reply_to=msg_id)

    def note(text):
        if job.get("bulk"):
            return                    # la cola masiva avisa una sola vez, al terminar
        if status:
            edit(chat, status, text)
        else:
            say(chat, f"{url}\n{text}")
    act = ChatAction(chat, "typing")
    if not quiet and not job.get("bulk"):
        act.start()                   # «escribiendo…» mientras descarga
    if "_id" in job:
        jobs.update(job, _status=status,    # para borrarlo si el bot se reinicia a medias
                    _start=int(time.time()), _thread=threading.get_ident())   # para /cola
    d = JOBS / f"{abs(chat)}_{msg_id}_{job.get('_id') or abs(hash(url)) % 10000}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    t0 = time.time()
    _tl.last_err = ""
    try:
        files, extra = None, None
        if mode == "mp3":
            files = try_audio(url, d)
            extra = audio_tags(d)
        elif mode == "song":
            files = try_song(url, d)
            extra = audio_tags(d)
        else:
            heights = job.get("heights", DEFAULT_HEIGHTS)
            ytdlp = lambda u, dd: try_ytdlp(u, dd, heights)
            steps = [("threads", try_threads)]
            if site_of(url) in ("instagram", "facebook"):
                # Primero lo publico, sin sesion; las cookies solo si no hay otra forma
                steps += [("yt-dlp público", lambda u, dd: try_ytdlp(u, dd, heights, False)),
                          ("instagram público", try_instagram),
                          ("gallery-dl público", lambda u, dd: try_gallerydl(u, dd, False))]
            steps += [("yt-dlp", ytdlp), ("gallery-dl", try_gallerydl), ("directo", try_direct)]
            for name, fn in steps:
                if job.get("_cancel"):
                    break
                try:
                    files = fn(url, d)
                except Exception as e:
                    log.info("%s fallo: %s", name, e)
                    _tl.last_err = str(e)[:300]
                if files:
                    log.info("%s -> %d archivo(s)", name, len(files))
                    break
        if job.get("_cancel"):
            note("🚫 Cancelado.")
            _tl.reg = {"res": "cancelado"}
            return
        if not files:
            record_failure(url)
            note("❌ No he podido sacar nada de ese enlace.\n"
                 "Puede ser privado, necesitar sesión o no estar soportado.")
            return
        title = meta_title(d) or page_title(url)
        if job.get("save_only"):               # /guardar de algo que ya no estaba en el movil
            names = nas_save(files, title)     # al NAS va todo: sin el limite de Telegram
            delete(chat, status)
            say(chat, "💾 Guardado en el NAS:\n" + "\n".join(names), reply_to=msg_id)
            health.event("nas", f"guardado {title or url}"[:150])
            _tl.reg = {"res": "nas", "bytes": sum(f.stat().st_size for f in files)}
            _tl.ok = True
            return
        limit = size_limit()
        ok = [f for f in files if f.stat().st_size <= limit][:MAX_FILES]
        nbytes = sum(f.stat().st_size for f in ok)      # antes de que pasen al archivo
        if not ok:
            note(f"❌ El archivo pasa de {limit // 2**20} MB (límite de Telegram para bots).")
            return
        edit(chat, status, f"📤 Enviando {len(ok)} archivo(s)…")
        act.action = upload_action(ok, mode)   # «enviando vídeo…», «enviando foto…»
        _tl.sent_msgs = []                     # mensajes que se envian: para el archivo
        cap = "" if mode == "song" else build_caption(title, url, job["sender"])
        try:
            sent = publish(targets[0], ok, cap, status, extra,
                           job.get("reply_to") if targets[0] == chat else None,
                           as_doc=(mode == "file"), status_chat=chat)
        except Exception as e:
            if targets[0] == chat or job.get("bulk"):
                raise
            # No llego al canal: avisar y dejar el video en el privado para no perderlo
            log.warning("publicar en %s: %s", targets[0], e)
            say(chat, f"⚠️ No pude publicar en el canal ({str(e).replace(TOKEN, '…')[:200]}). "
                      "Te lo dejo aquí:")
            targets = [chat]
            sent = publish(chat, ok, cap, status, extra, None, as_doc=(mode == "file"))
        for t in targets[1:]:          # el resto de destinos: reenviar lo ya subido
            try:
                send_cached(t, sent, cap)
            except Exception as e:
                log.warning("destino %s: %s", t, e)
                say(chat, f"⚠️ No pude publicar en {t}: {str(e).replace(TOKEN, '…')}")
        if sent:
            # Guardar tambien con la URL canonica (p.ej. el enlace corto de TikTok)
            keys = {key}
            for j in d.glob("*.json"):
                try:
                    canon = json.loads(j.read_text()).get("webpage_url")
                except ValueError:
                    canon = None
                if canon:
                    keys.add(cache_key(canon, mode))
            cache_put(sorted(keys), sent, title)
            archive_put(ok, chat, list(_tl.sent_msgs), url, title, mode)
            if not quiet and not job.get("bulk"):
                media_buttons(chat, mode)
        log.info("ok %s en %.0fs", url, time.time() - t0)
        _tl.reg = {"res": "ok", "bytes": nbytes}
        _tl.ok = True
        LAST_OK["download"] = (time.time(), site_of(url))
        bump("links")
        delete(chat, status)
        if job["only_link"]:
            delete(chat, msg_id)
    except Exception as e:
        log.exception("handle")
        _tl.last_err = str(e)[:300]
        record_failure(url)
        note(f"❌ Error: {e}")
    finally:
        act.stop()
        _tl.sent_msgs = None
        shutil.rmtree(d, ignore_errors=True)


WORKERS = 3   # peticiones simultaneas; casi todo es esperar a la red, no CPU


def worker():
    while True:
        job = jobs.get()
        if job.get("_cancel"):                  # cancelado con /cola antes de empezar
            jobs.done(job)
            db.descarga(job["chat"], job.get("uid"), job.get("quien"), site_of(job["url"]),
                        job["url"], job.get("mode"), "cancelado")
            continue
        _tl.reg = {"res": "fallo"}             # handle lo cambia en cada salida
        t_job = time.time()
        try:
            handle(job)
        finally:
            jobs.done(job)
            r = _tl.reg
            db.descarga(job["chat"], job.get("uid"),
                        job.get("quien") or ("likes" if job.get("bulk") else
                                             "canal seguido" if job.get("quiet") else None),
                        site_of(job["url"]), job["url"], job.get("mode"), r["res"],
                        r.get("bytes", 0), time.time() - t_job,
                        None if r["res"] in ("ok", "cache", "nas") else
                        r.get("err") or getattr(_tl, "last_err", ""))
            if job.get("bulk"):
                for hook in PLUGIN_JOB_DONE:
                    try:
                        hook(job, getattr(_tl, "ok", False), getattr(_tl, "last_err", ""))
                    except Exception:
                        log.exception("job_done")


# ---------------------------------------------------------------- Canales de YouTube

SUBS_FILE = BASE / "subs.json"
SUBS_EVERY = 5 * 60
subs_lock = threading.Lock()
YT_NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
         "media": "http://search.yahoo.com/mrss/"}


def load_subs():
    try:
        return json.loads(SUBS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_subs(subs):
    tmp = SUBS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(subs, ensure_ascii=False, indent=1))
    tmp.replace(SUBS_FILE)


def rss_entries(channel_id):
    """[(video_id, titulo, es_short)] del feed RSS del canal (los ~15 ultimos)."""
    # El RSS de YouTube falla a rachas (404/500 con el canal intacto): reintentar
    for attempt in range(3):
        r = http.get("https://www.youtube.com/feeds/videos.xml",
                     params={"channel_id": channel_id}, timeout=30)
        if r.status_code < 400 or attempt == 2:
            break
        time.sleep(5 * (attempt + 1))
    r.raise_for_status()
    out = []
    for e in ET.fromstring(r.content).findall("a:entry", YT_NS):
        vid = e.findtext("yt:videoId", namespaces=YT_NS)
        link = e.find("a:link", YT_NS)
        href = link.get("href", "") if link is not None else ""
        out.append((vid, e.findtext("a:title", namespaces=YT_NS) or "", "/shorts/" in href))
    return out


CHANNELS_FILE = BASE / "channels.json"      # canales de Telegram donde publico y su uso
POSTCH_FILE = BASE / "postchannel.json"     # formato viejo (un solo canal): se migra
DESTS = {"privado": "👤", "canal": "📢", "ambos": "👤📢"}
# Usos de un canal de Telegram. "videos": canales de YouTube seguidos. Los plugins
# anaden los suyos (p. ej. "canciones" el plugin de likes de YouTube Music).
ROLE_INFO = {"videos": "los vídeos de los canales de YouTube que sigas"}


def load_channels():
    try:
        return json.loads(CHANNELS_FILE.read_text())
    except (OSError, ValueError):
        pass
    d = {"list": [], "roles": {}}
    try:
        old = json.loads(POSTCH_FILE.read_text())
        d["list"].append(old)
        d["roles"]["videos"] = old["id"]
        save_channels(d)
    except (OSError, ValueError, KeyError):
        pass
    return d


def save_channels(d):
    tmp = CHANNELS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    tmp.replace(CHANNELS_FILE)


def role_channel(role):
    d = load_channels()
    return next((c for c in d["list"] if c["id"] == d["roles"].get(role)), None)


def post_channel():
    return role_channel("videos")


def sub_targets(dest, owner):
    """Chats donde publicar los vídeos de un canal seguido. Si el canal de vídeos no
    está configurado, todo va al privado."""
    pc = post_channel()
    priv = dest in (None, "privado", "ambos") or not pc
    return ([owner] if priv else []) + ([pc["id"]] if pc and dest in ("canal", "ambos") else [])


def _norm_title(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower())
                   if not unicodedata.combining(c))


def channel_event(ev):
    """my_chat_member: el bot entra a un canal como administrador (o sale de él)."""
    c, new = ev["chat"], ev["new_chat_member"]
    if c.get("type") != "channel":
        return
    owner, _ = load_owners()
    d = load_channels()
    title = c.get("title", "")
    if new["status"] == "administrator":
        if ev["from"]["id"] != owner:
            log.info("me añadieron al canal %s alguien que no es el dueño", c["id"])
            try:
                tg("leaveChat", chat_id=c["id"])
            except Exception:
                pass
            return
        d["list"] = [x for x in d["list"] if x["id"] != c["id"]] + [{"id": c["id"], "title": title}]
        role = None
        for r in ROLE_INFO:       # el titulo menciona el uso: «Canciones», «Videos»...
            if r != "videos" and _norm_title(r)[:6] in _norm_title(title) \
                    and d["roles"].get(r) != c["id"]:
                role = r
        if role is None and not d["roles"].get("videos") and not any(
                v == c["id"] for v in d["roles"].values()):
            role = "videos"
        if role:
            d["roles"][role] = c["id"]
        save_channels(d)
        warn = "" if new.get("can_post_messages", True) else \
            "\n⚠️ Me falta el permiso «Publicar mensajes»: actívalo en los administradores."
        uso = ROLE_INFO.get(role) or ("nada todavía: /canal " + "|".join(ROLE_INFO) + " N")
        say(owner, f"📢 Canal «{title}» conectado. Publicaré ahí: {uso}.{warn}")
    elif new["status"] in ("left", "kicked") and any(x["id"] == c["id"] for x in d["list"]):
        d["list"] = [x for x in d["list"] if x["id"] != c["id"]]
        d["roles"] = {r: v for r, v in d["roles"].items() if v != c["id"]}
        save_channels(d)
        say(owner, f"📢 Salí del canal «{title}»; lo que iba ahí vuelve a tu privado.")


def channel_command(chat, arg):
    """/canal: canales de Telegram donde publico. /canal videos N · /canal canciones N ·
    /canal quitar N · /canal @usuario (conectar uno que no se detectó solo)."""
    d = load_channels()
    words = arg.split()
    ROLES = tuple(ROLE_INFO)
    uso = lambda cid: ", ".join(r for r in ROLES if d["roles"].get(r) == cid) or "sin uso"
    if len(words) == 2 and words[0].lower() in ROLES + ("quitar",) and words[1].isdigit() \
            and 1 <= int(words[1]) <= len(d["list"]):
        ch = d["list"][int(words[1]) - 1]
        if words[0].lower() == "quitar":
            d["list"].remove(ch)
            d["roles"] = {r: v for r, v in d["roles"].items() if v != ch["id"]}
            say(chat, f"📢 «{ch['title']}» desconectado (sigo de administrador ahí hasta que "
                      "me quites tú).")
        else:
            d["roles"][words[0].lower()] = ch["id"]
            say(chat, f"📢 {words[0].lower()} → «{ch['title']}».")
        save_channels(d)
        return
    if arg and not words[0].lower() in ROLES + ("quitar",):
        try:
            info = tg("getChat", chat_id=int(arg) if arg.lstrip("-").isdigit() else arg)
            me = tg("getChatMember", chat_id=info["id"], user_id=BOT["id"])
            if info.get("type") != "channel" or me["status"] != "administrator":
                raise RuntimeError("tiene que ser un canal y yo administrador")
            if not me.get("can_post_messages", True):
                raise RuntimeError("me falta el permiso «Publicar mensajes»")
        except Exception as e:
            say(chat, f"❌ No pude usar ese canal: {str(e).replace(TOKEN, '…')}")
            return
        d["list"] = [x for x in d["list"] if x["id"] != info["id"]] + \
            [{"id": info["id"], "title": info.get("title", "")}]
        save_channels(d)
        say(chat, f"📢 Canal «{info.get('title', '')}» conectado. Dime su uso con "
                  "/canal " + "|".join(ROLES) + " N.")
        return
    if not d["list"]:
        say(chat, "📢 Sin canales de publicación.\n\nCrea un canal, añádeme como administrador "
                  "(solo con «Publicar mensajes»; desactiva «Firmar mensajes» para que no "
                  "salga mi nombre) y lo detecto solo. Si no, /canal @usuario_del_canal")
        return
    lines = [f"{i}. «{c['title']}» — {uso(c['id'])}" for i, c in enumerate(d["list"], 1)]
    say(chat, "📢 Canales donde publico:\n" + "\n".join(lines)
        + "\n\n" + "\n".join(f"/canal {r} N – {u}" for r, u in ROLE_INFO.items())
        + "\n/canal quitar N – desconectar")


def follow_channel(url, dest="privado"):
    """Resuelve un enlace de canal (@handle, /channel/UC..., video) -> (id, nombre)."""
    if not url.startswith("http"):
        url = "https://www.youtube.com/" + (url if url.startswith("@") else "@" + url)
    p = run([VENV_BIN / "yt-dlp", "--js-runtimes", "node", "--flat-playlist",
             "--playlist-end", "1", "-J", url], "/tmp", timeout=180)
    if p.returncode:
        raise RuntimeError("no encuentro ese canal")
    info = json.loads(p.stdout)
    cid = info.get("channel_id") or (info.get("id") if str(info.get("id", "")).startswith("UC") else None)
    name = info.get("channel") or info.get("uploader") or info.get("title") or cid
    if not cid:
        raise RuntimeError("no encuentro el ID del canal")
    seen = [v for v, _, _ in rss_entries(cid)]
    with subs_lock:
        subs = load_subs()
        subs[cid] = {"name": name, "seen": seen, "pending": {}, "dest": dest}
        save_subs(subs)
    return cid, name, len(seen)


def live_status(video_id):
    p = run([VENV_BIN / "yt-dlp", "--js-runtimes", "node", "--skip-download",
             "--print", "%(live_status)s", f"https://www.youtube.com/watch?v={video_id}"],
            "/tmp", timeout=180)
    return p.stdout.strip() if p.returncode == 0 else "error"


def check_subs():
    owner, _ = load_owners()
    if not owner:
        return
    with subs_lock:
        subs = load_subs()
    for cid, ch in subs.items():
        try:
            entries = rss_entries(cid)
        except Exception as e:
            log.info("rss %s: %s", ch["name"], e)
            continue
        for vid, title, is_short in reversed(entries):   # de mas antiguo a mas nuevo
            if vid in ch["seen"]:
                continue
            st = "short" if is_short else live_status(vid)
            if st in ("is_upcoming", "is_live", "error"):
                # estreno/directo aun no disponible: reintentar en la siguiente vuelta
                tries = ch.setdefault("pending", {}).get(vid, 0) + 1
                ch["pending"][vid] = tries
                if tries < 24 * 3600 // SUBS_EVERY:      # ~24 h, luego se descarta
                    continue
            elif st != "short":
                log.info("nuevo video de %s: %s", ch["name"], title)
                jobs.put({"chat": owner, "msg_id": None, "only_link": False,
                          "targets": sub_targets(ch.get("dest"), owner), "quiet": True,
                          "url": f"https://www.youtube.com/watch?v={vid}",
                          "sender": "",      # sin «vía …»: solo el título enlazado
                          # mismo orden que DEFAULT_HEIGHTS, explicito por claridad
                          "heights": (1080, 720, 480, 360)})
            ch["seen"] = (ch["seen"] + [vid])[-60:]
            ch.get("pending", {}).pop(vid, None)
    with subs_lock:
        current = load_subs()
        for cid in current:          # conservar altas/bajas hechas mientras tanto
            if cid in subs:
                current[cid]["seen"] = subs[cid]["seen"]
                current[cid]["pending"] = subs[cid].get("pending", {})
        save_subs(current)




def subs_loop():
    time.sleep(60)
    while True:
        try:
            check_subs()
        except Exception:
            log.exception("check_subs")
        time.sleep(SUBS_EVERY)


def subs_command(chat, cmd, arg):
    if cmd == "/seguir":
        if not arg:
            say(chat, "Uso: /seguir https://www.youtube.com/@canal [privado|canal|ambos]")
            return
        words = arg.split()
        dest = words.pop().lower() if words and words[-1].lower() in DESTS else "privado"
        arg = " ".join(words)
        say(chat, "🔎 Buscando el canal…")
        try:
            cid, name, n = follow_channel(arg, dest)
            where = {"privado": "a tu privado", "canal": "al canal", "ambos": "a tu privado y al canal"}[dest]
            say(chat, f"✅ Siguiendo «{name}». Sus vídeos nuevos irán {where} en 1080p "
                      f"(revisado cada {SUBS_EVERY // 60} min; sin Shorts)."
                      + ("" if post_channel() or dest == "privado" else
                         "\n⚠️ Aún no hay canal conectado (/canal): irán a tu privado."))
        except Exception as e:
            say(chat, f"❌ {e}")
    elif cmd == "/canales":
        subs = load_subs()
        if not subs:
            say(chat, "No sigues ningún canal. Usa /seguir <enlace del canal>.")
            return
        lines = [f"{i}. {DESTS.get(c.get('dest'), DESTS['privado'])} {c['name']}"
                 for i, c in enumerate(subs.values(), 1)]
        pc = post_channel()
        say(chat, "📺 Canales seguidos (👤 privado · 📢 canal"
                  + (f" «{pc['title']}»" if pc else " sin conectar") + "):\n" + "\n".join(lines)
                  + "\n\n/destino N privado|canal|ambos\n/dejar N – dejar de seguir"
                  + "\n\nBotones: a dónde van los vídeos de cada canal, o dejar de seguirlo.",
            buttons=[[(f"{i}. 👤", f"/destino {i} privado"), ("📢", f"/destino {i} canal"),
                      ("👤+📢", f"/destino {i} ambos"), ("🗑️", f"/dejar {i}")]
                     for i in range(1, len(subs) + 1)])
    elif cmd == "/destino":
        words = arg.split()
        with subs_lock:
            subs = load_subs()
            keys = list(subs)
            if len(words) != 2 or not words[0].isdigit() or words[1].lower() not in DESTS \
                    or not 1 <= int(words[0]) <= len(keys):
                say(chat, "Uso: /destino N privado|canal|ambos (N = número de /canales)")
                return
            subs[keys[int(words[0]) - 1]]["dest"] = words[1].lower()
            name = subs[keys[int(words[0]) - 1]]["name"]
            save_subs(subs)
        say(chat, f"{DESTS[words[1].lower()]} «{name}» → {words[1].lower()}"
                  + ("" if post_channel() or words[1].lower() == "privado" else
                     "\n⚠️ Aún no hay canal conectado (/canal): irá a tu privado."))
    elif cmd == "/dejar":
        with subs_lock:
            subs = load_subs()
            keys = list(subs)
            if not arg.isdigit() or not 1 <= int(arg) <= len(keys):
                say(chat, "Uso: /dejar N (el número de /canales)")
                return
            name = subs.pop(keys[int(arg) - 1])["name"]
            save_subs(subs)
        say(chat, f"🗑️ Ya no sigo «{name}».")


# ---------------------------------------------------------------- Permisos

def load_owners():
    if not OWNERS_FILE.exists():
        return None, set()
    ids = [int(x) for x in OWNERS_FILE.read_text().split() if x.strip()]
    return (ids[0] if ids else None), set(ids)


USERS_FILE = BASE / "users.json"      # nombres de usuarios/grupos autorizados


def authorize(chat_id, name=None):
    owner, chats = load_owners()
    if chat_id not in chats:
        with OWNERS_FILE.open("a") as fh:
            fh.write(f"{chat_id}\n")
        log.info("chat autorizado: %s", chat_id)
    if name:
        names = load_names()
        names[str(chat_id)] = name
        USERS_FILE.write_text(json.dumps(names, ensure_ascii=False, indent=1))


def deauthorize(chat_id):
    owner, chats = load_owners()
    if chat_id == owner or chat_id not in chats:
        return False
    ids = [i for i in OWNERS_FILE.read_text().split() if i.strip() and int(i) != chat_id]
    OWNERS_FILE.write_text("\n".join(ids) + "\n")
    log.info("chat desautorizado: %s", chat_id)
    return True


def load_names():
    try:
        return json.loads(USERS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def display_name(user):
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
    if user.get("username"):
        name += f" (@{user['username']})"
    return name or str(user.get("id"))


def access_command(chat, cmd, arg):
    owner, chats = load_owners()
    names = load_names()
    if cmd == "/usuarios":
        lines = []
        for c in sorted(chats - {owner}):
            label = names.get(str(c), "sin nombre")
            lines.append(f"{'👥 Grupo' if c < 0 else '👤'} {label} — ID {c}")
        say(chat, ("🔐 Con acceso:\n" + "\n".join(lines) + "\n\n/quitar ID – retirar acceso")
            if lines else "Nadie más tiene acceso todavía.")
    elif cmd == "/permitir":
        if not arg.lstrip("-").isdigit():
            say(chat, "Uso: /permitir ID (te llega el ID cuando alguien me escribe por privado)")
            return
        uid = int(arg)
        authorize(uid, names.get(f"pending:{uid}"))
        say(chat, f"✅ {names.get(f'pending:{uid}', uid)} ya puede usarme por privado.")
        say(uid, "✅ Ya tienes acceso. Mándame un enlace o escribe /help.")
    elif cmd == "/quitar":
        if not arg.lstrip("-").isdigit():
            say(chat, "Uso: /quitar ID (míralo en /usuarios)")
            return
        uid = int(arg)
        if deauthorize(uid):
            say(chat, f"🗑️ Acceso retirado a {names.get(str(uid), uid)}.")
        else:
            say(chat, "Ese ID no tenía acceso (y al dueño no se le puede quitar).")


def request_access(user):
    """Alguien sin permiso escribe por privado: avisar al dueño (1 vez al dia)."""
    uid, name = user.get("id"), display_name(user)
    names = load_names()
    names[f"pending:{uid}"] = name
    USERS_FILE.write_text(json.dumps(names, ensure_ascii=False, indent=1))
    alert(f"req-{uid}", f"👤 {name} quiere usar el bot por privado.\n\n"
          f"Para darle acceso: /permitir {uid}", 24 * 3600)


# ---------------------------------------------------------------- Comandos

def read_sys(path, default="?"):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def status_text():
    bat = "/sys/class/power_supply/battery"
    temp = read_sys(f"{bat}/temp")
    temp = f"{int(temp) / 10:.1f}°C" if temp.lstrip("-").isdigit() else "?"
    du = shutil.disk_usage("/")
    up = float(read_sys("/proc/uptime", "0").split()[0])
    load = read_sys("/proc/loadavg").split()[:3]
    mem = dict(l.split(":", 1) for l in read_sys("/proc/meminfo", "").splitlines() if ":" in l)
    kb = lambda k: int(mem.get(k, "0 kB").split()[0]) // 1024
    # Este kernel (3.4) no da MemAvailable: libre + cache recuperable es lo disponible
    # de verdad. MemFree a secas baja durante el dia porque Linux usa la RAM sobrante
    # como cache de archivos y la suelta al instante si hace falta.
    free = kb("MemFree")
    cache = kb("Buffers") + kb("Cached") - kb("Shmem")
    if "MemAvailable" in mem:   # kernels modernos: el calculo del propio kernel
        cache = kb("MemAvailable") - free
    me = dict(l.split(":", 1) for l in read_sys("/proc/self/status", "").splitlines() if ":" in l)
    bot_mb = int(me.get("VmRSS", "0 kB").split()[0]) // 1024
    ver = run([VENV_BIN / "yt-dlp", "--version"], "/").stdout.strip()
    slate = charge_paused()
    mode = "en pausa, vive del cargador" if slate == "1" else "cargando"
    try:   # IP local: la que usaria para salir a Internet (no envia nada)
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("1.1.1.1", 53))
            ip = s.getsockname()[0]
    except OSError:
        ip = "sin red"
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    now = time.localtime()
    fecha = f"{dias[now.tm_wday]} {time.strftime('%d/%m/%Y %H:%M', now)}"
    return (f"📱 {DEVICE['name']} · {fecha}\n"
            f"🔋 Batería: {read_sys(bat + '/capacity')}% ({battery_label()}), {temp}\n"
            f"⚡ Carga {mode} · ciclo {read_sys(BASE / 'charge_range', '?')} %\n"
            f"💾 Libre: {du.free / 2**30:.1f} GB\n"
            f"🧠 RAM disponible: {free + cache} MB (libre {free} + caché {cache}) · "
            f"bot {bot_mb} MB\n"
            f"📊 Carga: {' '.join(load)}\n"
            f"⏱️ Encendido: {up / 3600:.1f} h\n"
            f"🌐 IP: {ip} ({'Ethernet' if eth_link()[0] else 'Wi-Fi'}; {DEVICE.get('remote', 'adb en :5555')})\n"
            f"⬇️ yt-dlp {ver} · en cola: {jobs.qsize()}")


# ---------------------------------------------------------------- Prueba de velocidad

SPEED_URL = "https://speed.cloudflare.com"
speed_lock = threading.Lock()


def eth_link():
    """(interfaz, Mbit/s) del cable si hay un adaptador USB-Ethernet conectado y con
    enlace (p. ej. un adaptador USB-Ethernet); (None, None) si no."""
    for d in sorted(Path("/sys/class/net").glob("*")):
        if re.match(r"(eth|usb)\d+$", d.name) and read_sys(d / "operstate") == "up":
            speed = read_sys(d / "speed")
            return d.name, (int(speed) if speed.isdigit() else None)
    return None, None


def wifi_link():
    """(señal dBm, velocidad del enlace Mbit/s, banda) de wlan0 con `iw`.
    /proc/net/wireless sale a ceros con este driver y dumpsys no va desde root."""
    try:
        out = subprocess.run(["iw", "dev", "wlan0", "link"], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    if not out:   # sin root (proot): lo deja cada minuto charge.sh
        try:
            w = json.loads((BASE / "sys" / "wifi.json").read_text())
            band = ("5 GHz" if w["freq"] > 4000 else "2.4 GHz") if w.get("freq") else None
            return w.get("rssi"), w.get("link"), band
        except (OSError, ValueError, KeyError, TypeError):
            return None, None, None
    sig = re.search(r"signal:\s*(-?\d+)", out)
    rate = re.search(r"tx bitrate:\s*([\d.]+)", out)
    freq = re.search(r"freq:\s*(\d+)", out)
    band = ("5 GHz" if int(freq.group(1)) > 4000 else "2.4 GHz") if freq else None
    return (int(sig.group(1)) if sig else None,
            float(rate.group(1)) if rate else None, band)


def _transfer(kind, seconds, streams=2):
    """Mbps bajando o subiendo con varias conexiones a la vez durante `seconds`."""
    total, stop_at = [0], time.time() + seconds
    payload = bytes(1024 * 1024) * 4          # 4 MB de ceros (Cloudflare no comprime)

    def one():
        s = requests.Session()
        while time.time() < stop_at:
            try:
                if kind == "down":
                    r = s.get(f"{SPEED_URL}/__down?bytes=50000000", stream=True, timeout=15)
                    for chunk in r.iter_content(64 * 1024):
                        total[0] += len(chunk)
                        if time.time() >= stop_at:
                            r.close()
                            break
                else:
                    s.post(f"{SPEED_URL}/__up", data=payload, timeout=15)
                    if time.time() < stop_at + 2:      # contar solo lo que entro en el plazo
                        total[0] += len(payload)
            except requests.RequestException:
                time.sleep(0.5)

    t0 = time.time()
    threads = [threading.Thread(target=one, daemon=True) for _ in range(streams)]
    [t.start() for t in threads]
    [t.join(seconds + 20) for t in threads]
    return total[0] * 8 / (time.time() - t0) / 1e6


def speedtest(chat, status):
    """Ping, bajada y subida contra Cloudflare, editando el mensaje de estado."""
    s = requests.Session()
    meta = {}
    try:   # proveedor y ciudad (el /meta de Cloudflare devuelve vacio desde aqui)
        meta = s.get("https://ipinfo.io/json", timeout=10).json()
        meta["colo"] = dict(l.split("=", 1) for l in s.get(
            f"{SPEED_URL}/cdn-cgi/trace", timeout=10).text.splitlines() if "=" in l).get("colo")
    except (requests.RequestException, ValueError):
        pass
    edit(chat, status, "📶 Midiendo ping…")
    pings = []
    for i in range(8):
        t = time.time()
        try:
            s.get(f"{SPEED_URL}/__down?bytes=0", timeout=5)
            if i:                                  # la 1a incluye abrir la conexion TLS
                pings.append((time.time() - t) * 1000)
        except requests.RequestException:
            pass
    if not pings:
        return "❌ No hay conexión a Internet desde el móvil (Cloudflare no responde)."
    jitter = sum(abs(a - b) for a, b in zip(pings, pings[1:])) / max(len(pings) - 1, 1)
    edit(chat, status, "⬇️ Midiendo bajada…")
    down = _transfer("down", 10)
    edit(chat, status, "⬆️ Midiendo subida…")
    up = _transfer("up", 8)

    eth, eth_speed = eth_link()
    dbm, rate, band = wifi_link()
    if dbm is None:
        senal = "?"
    else:
        calidad = ("excelente" if dbm >= -55 else "buena" if dbm >= -67
                   else "regular" if dbm >= -75 else "mala")
        senal = f"{dbm} dBm ({calidad})" + (f", {band}" if band else "") \
            + (f", enlace {rate:.0f} Mbit/s" if rate else "")
    lines = ["🌐 <b>Prueba de velocidad</b>",
             f"⬇️ Bajada: <b>{down:.1f} Mbps</b>",
             f"⬆️ Subida: <b>{up:.1f} Mbps</b>",
             f"📶 Ping: {min(pings):.0f} ms (media {sum(pings) / len(pings):.0f}, "
             f"jitter {jitter:.0f} ms)",
             f"🔌 Conectado por cable ({eth}, {eth_speed or '?'} Mbit/s)" if eth
             else f"📡 Señal Wi-Fi del móvil: {senal}"]
    if meta.get("org"):
        isp = re.sub(r"^AS\d+\s+", "", meta["org"])
        lines.append(f"🏢 {html.escape(isp)} ({html.escape(meta.get('city') or '?')})"
                     + (f" · servidor Cloudflare {html.escape(meta['colo'])}"
                        if meta.get("colo") else ""))
    if not eth and DEVICE.get("wifi_note", True):
        lines.append("\n<i>Mide hasta lo que da el Wi-Fi de este móvil (antiguo, ~100 Mbps "
                     "reales como mucho): si tu plan es mayor, la red de la casa puede ir "
                     "más rápido que esto.</i>")
    log.info("velocidad: %.1f/%.1f Mbps, ping %.0f ms, %s", down, up, min(pings),
             f"cable {eth}" if eth else senal)
    return "\n".join(lines)


def speed_command(chat):
    if not speed_lock.acquire(blocking=False):
        say(chat, "⏳ Ya hay una prueba de velocidad en marcha, espera un momento.")
        return
    try:
        status = say(chat, "🌐 Preparando la prueba de velocidad (~25 s)…")
        try:
            result = speedtest(chat, status)
        except Exception as e:
            log.exception("speedtest")
            result = f"❌ Error en la prueba: {e}"
        delete(chat, status)
        say(chat, result, parse_mode="HTML")
    finally:
        speed_lock.release()




# ---------------------------------------------------------------- PDF a imagenes

PDF_MAX_PAGES = 500
PDF_MAX_BYTES = 300 * 2**20   # por MTProto; sin el, la Bot API solo baja 20 MB
PDF_SIDE = 2160               # px del lado mayor: de sobra para redes sociales
PDF_BATCH = 10                # paginas por album: se convierten y envian de 10 en 10


def pdf_of(m):
    doc = (m or {}).get("document") or {}
    if doc.get("mime_type") == "application/pdf" or \
            doc.get("file_name", "").lower().endswith(".pdf"):
        return doc
    return None


def pdf_zip_path(d: Path, name):
    """Ruta del .zip de /pdf zip: el nombre del PDF sin caracteres raros (o "pdf")."""
    return d / ((re.sub(r"[^\w.-]+", "_", name)[:60] or "pdf") + ".zip")


def pdf_command(msg, chat, arg):
    """/pdf en el pie de un PDF o respondiendo a uno: cada pagina como imagen.
    Opciones (se combinan): 'archivo' -> JPG como archivo, sin recomprimir; 'png';
    'zip' -> todas en un ZIP; '5-20' -> solo esas paginas. Va de 10 en 10 paginas
    para que lleguen desde el principio y no llenar el disco con catalogos enteros."""
    src_msg = msg if pdf_of(msg) else msg.get("reply_to_message")
    doc = pdf_of(src_msg)
    if not doc:
        say(chat, "Uso: mándame el PDF con /pdf como pie, o responde a un PDF con /pdf.\n"
                  "Opciones: archivo (sin comprimir) · png · zip (todo en un archivo) · "
                  "10-25 (solo esas páginas)", reply_to=msg["message_id"])
        return
    size = doc.get("file_size", 0)
    big = size > 20 * 2**20
    if (big and not bigupload.available()) or size > PDF_MAX_BYTES:
        limit = PDF_MAX_BYTES if bigupload.available() else 20 * 2**20
        say(chat, f"📄 Ese PDF pesa {size / 2**20:.0f} MB; el máximo es "
                  f"{limit // 2**20} MB.", reply_to=msg["message_id"])
        return
    opts = arg.lower().split()
    png = "png" in opts
    as_zip = "zip" in opts
    as_doc = png or "archivo" in opts
    rng = next((re.fullmatch(r"(\d+)(?:-(\d+))?", o) for o in opts
                if re.fullmatch(r"\d+(-\d+)?", o)), None)
    status = say(chat, f"📄 Bajando el PDF ({size / 2**20:.1f} MB)…", reply_to=msg["message_id"])
    d = JOBS / f"pdf_{abs(chat)}_{msg['message_id']}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    try:
        src = d / "doc.pdf"
        if big:
            bigupload.download(chat, src_msg["message_id"], src)
        else:
            path = tg("getFile", file_id=doc["file_id"])["file_path"]
            r = http.get(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=300)
            r.raise_for_status()
            src.write_bytes(r.content)
        info = run(["pdfinfo", src], d)
        m = re.search(r"^Pages:\s+(\d+)", info.stdout, re.M)
        if not m:
            err = (info.stderr.strip().splitlines() or [""])[-1]
            edit(chat, status, "❌ No pude leer ese PDF"
                 + (" (tiene contraseña)." if "password" in err.lower() else f": {err}"[:200]))
            return
        pages = int(m.group(1))
        first = max(1, int(rng.group(1))) if rng else 1
        last = min(pages, int(rng.group(2) or rng.group(1))) if rng else pages
        cut = last - first + 1 > PDF_MAX_PAGES
        last = min(last, first + PDF_MAX_PAGES - 1)
        if first > last:
            edit(chat, status, f"📄 Ese PDF solo tiene {pages} páginas.")
            return
        total = last - first + 1
        name = Path(doc.get("file_name") or "PDF").stem
        ext = "png" if png else "jpg"
        fmt = ["-png"] if png else ["-jpeg", "-jpegopt", "quality=92"]
        note = f" (de {pages})" if (first, last) != (1, pages) else ""
        note += f"; máximo {PDF_MAX_PAGES} por vez" if cut else ""
        t0 = time.time()
        zf = None
        if as_zip:
            import zipfile
            zpath = pdf_zip_path(d, name)
            zf = zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED)   # JPG/PNG ya van comprimidos
        for a in range(first, last + 1, PDF_BATCH):
            b = min(a + PDF_BATCH - 1, last)
            edit(chat, status, f"📄 Convirtiendo páginas {a}–{b} de {last}…"
                 if total > PDF_BATCH else "📄 Convirtiendo…")
            run(["pdftoppm", "-scale-to", str(PDF_SIDE), "-f", str(a), "-l", str(b), *fmt,
                 src, d / "p"], d)
            files = sorted(d.glob(f"p-*.{ext}"))
            if zf:
                for f in files:
                    zf.write(f, f"{name[:60]}_{int(f.stem.split('-')[-1]):03d}.{ext}")
                    f.unlink()
                continue
            if not files:
                raise RuntimeError(f"pdftoppm no sacó las páginas {a}–{b}")
            pag = f"pág. {a}" if a == b else f"págs. {a}–{b}"
            cap = html.escape(f"📄 {name} · {pag} de {pages}" if total > PDF_BATCH or note
                              else f"📄 {name} · {len(files)} página"
                                   f"{'s' if len(files) != 1 else ''}")
            publish(chat, files, cap, status,
                    reply_to=msg["message_id"] if a == first else None, as_doc=as_doc)
            for f in files:
                f.unlink()
            if b < last:
                time.sleep(2)     # que Telegram no frene por tantos albumes seguidos
        if zf:
            zf.close()
            mb = zpath.stat().st_size / 2**20
            edit(chat, status, f"📤 Enviando ZIP de {total} páginas ({mb:.0f} MB)…")
            publish(chat, [zpath], html.escape(f"📄 {name} · {total} páginas{note}"), status,
                    reply_to=msg["message_id"], as_doc=True)
        log.info("pdf %d página(s) en %.0fs", total, time.time() - t0)
        delete(chat, status)
        if cut:
            say(chat, f"📄 Solo convertí hasta la página {last}. Para seguir: responde al PDF "
                      f"con /pdf {last + 1}-{pages}")
    except Exception as e:
        log.exception("pdf")
        edit(chat, status, f"❌ Error con el PDF: {str(e).replace(TOKEN, '…')}")
    finally:
        shutil.rmtree(d, ignore_errors=True)




# ---------------------------------------------------------------- Notas de voz

stt_jobs = pending.PersistentJobs(BASE / "pending_voice.json")   # sobrevive a reinicios
STT_MAX_SECS = 15 * 60


def stt_worker():
    # Una transcripcion a la vez: es lo unico que de verdad exprime la CPU
    while True:
        job = stt_jobs.get()
        chat, msg_id = job["chat"], job["msg_id"]
        status = say(chat, "✍️ Transcribiendo…", reply_to=msg_id)
        act = ChatAction(chat, "typing").start()      # «escribiendo…» mientras transcribe
        stt_jobs.update(job, _status=status)
        d = JOBS / f"stt_{msg_id}_{abs(chat)}"
        d.mkdir(parents=True, exist_ok=True)
        try:
            path = tg("getFile", file_id=job["file_id"])["file_path"]
            src = d / ("audio" + (Path(path).suffix or ".ogg"))
            r = http.get(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=120)
            r.raise_for_status()
            src.write_bytes(r.content)
            who = html.escape(job["name"])
            text, secs, took, eng = stt.transcribe(src, on_draft=lambda draft: edit(
                chat, status, f"🎙️ <b>{who}</b> dijo <i>(borrador, afinando…)</i>:\n"
                              f"{html.escape(draft)}", "HTML"))
            log.info("stt %.0fs de audio en %.0fs (%s)", secs, took, eng)
            db.voz(chat, job.get("uid"), job.get("name"), secs, took, eng, bool(text))
            if text:
                edit(chat, status, f"🎙️ <b>{who}</b> dijo:\n{html.escape(text)}", "HTML")
            else:
                edit(chat, status, f"🎙️ No entendí nada en el audio de {job['name']}.")
        except Exception as e:
            log.exception("stt")
            db.voz(chat, job.get("uid"), job.get("name"), 0, 0, "error", False)
            edit(chat, status, f"❌ No pude transcribir el audio: {e}")
        finally:
            act.stop()
            shutil.rmtree(d, ignore_errors=True)
            stt_jobs.done(job)


def resume_pending():
    """Al arrancar: retomar descargas y notas de voz que quedaron a medias."""
    total = 0
    for q, what in ((jobs, "enlace"), (stt_jobs, "nota de voz")):
        resumed, dropped = q.resume()
        for job in resumed:
            if job.get("_status"):            # el "⏳ Descargando…" de la vez anterior
                delete(job["chat"], job["_status"])
        for job in dropped:
            if job.get("_status"):
                delete(job["chat"], job["_status"])
            if job.get("_tries", 0) >= pending.MAX_TRIES:
                say(job["chat"], f"❌ No pude procesar esta {what}: el bot se reinició varias "
                                 "veces intentándolo.", reply_to=job.get("msg_id"))
                health.event("fallo", f"{what} descartada tras {job['_tries']} intentos")
        total += len(resumed)
    if total:
        health.event("reinicio", f"retomados {total} trabajo(s) pendiente(s)")
        log.info("retomados %d trabajos pendientes", total)


def transcribe_command(chat, arg):
    a = arg.lower().split()
    if a[:1] == ["on"]:
        stt.set_enabled(chat, True)
        say(chat, "🎙️ Transcripción de notas de voz activada en este chat.")
    elif a[:1] == ["off"]:
        stt.set_enabled(chat, False)
        say(chat, "🔇 Transcripción de notas de voz desactivada en este chat.")
    elif a[:1] == ["modelo"] and len(a) == 2:
        need = stt.AUTO[:2] if a[1] == "auto" else (a[1],)
        if not all((stt.STT / f"ggml-{m}.bin").exists() for m in need):
            have = sorted(p.stem[5:] for p in stt.STT.glob("ggml-*.bin"))
            say(chat, f"No tengo ese modelo. Disponibles: {', '.join(have) or 'ninguno'}")
            return
        cfg = stt.config()
        cfg["model"] = a[1]
        stt.save_config(cfg)
        say(chat, f"✅ Modelo de Whisper: {a[1]}")
    else:
        models = sorted(p.stem[5:] for p in stt.STT.glob("ggml-*.bin")) \
            + (["auto"] if all((stt.STT / f"ggml-{m}.bin").exists() for m in stt.AUTO[:2]) else [])
        say(chat, f"🎙️ Transcripción: {'activada' if stt.enabled(chat) else 'desactivada'} "
                  f"en este chat · motor: {stt.engine() or 'ninguno'}\n\n"
                  "/transcribir on | off · /transcribir modelo " + " | ".join(models),
            buttons=[[("🎙️ Activar aquí", "/transcribir on"), ("🔇 Desactivar aquí", "/transcribir off")]]
            + [[(f"🧠 {m.split('-q')[0]}", f"/transcribir modelo {m}") for m in models[i:i + 3]]
               for i in range(0, len(models), 3)])


# ---------------------------------------------------------------- Salud del servidor

def report_crashes():
    """Al arrancar: si bot.sh tuvo que relanzar el bot (caidas o cuelgues) desde el
    ultimo arranque bueno, avisar con el ultimo error."""
    evs = health.recent(kinds=["inicio", "caida", "colgado"])
    since_start = []
    for e in reversed(evs):
        if e["k"] == "inicio":
            break
        since_start.append(e)
    if not since_start:
        return
    last = since_start[0]
    n = len(since_start)
    alert(f"caidas-{last['t']}", f"💥 El bot tuvo que reiniciarse {'1 vez' if n == 1 else f'{n} veces'} "
          f"antes de volver a funcionar.\nÚltimo: {last['x']}", 0)


def _check(name, ok, detail):
    return f"{'✅' if ok is True else '⚠️' if ok is None else '❌'} <b>{name}</b>: {detail}"


def health_text():
    """/salud: comprobacion real de cada servicio, en el momento."""
    now = time.time()
    lines = [f"🩺 <b>Salud del servidor</b> · {time.strftime('%d/%m %H:%M')}"]
    day = health.recent(since=now - 86400)
    crashes = [e for e in day if e["k"] in ("caida", "colgado")]
    hb = float(read_sys(str(health.HEARTBEAT), "0") or 0)
    lines.append(_check("Bot", not crashes or None,
                        f"en marcha hace {health.ago(now - STARTED)}, versión {VERSION}, "
                        f"señal de vida hace {health.ago(now - hb)}"
                        + (f", {len(crashes)} reinicio(s) forzado(s) en 24 h" if crashes else "")))
    try:
        t = time.time()
        http.get("https://1.1.1.1/cdn-cgi/trace", timeout=5)
        ms = (time.time() - t) * 1000
        cuts = [e for e in day if e["k"] == "red"]
        lines.append(_check("Internet", True, f"responde en {ms:.0f} ms"
                            + (f"; {len(cuts)} corte(s) en 24 h, último "
                               f"{cuts[-1]['x']}" if cuts else "; sin cortes en 24 h")))
    except requests.RequestException:
        lines.append(_check("Internet", False, "no responde"))
    tgcuts = [e for e in day if e["k"] == "telegram"]
    lines.append(_check("Telegram", not tgcuts or None,
                        f"{len(tgcuts)} fallo(s) de su servidor en 24 h, último {tgcuts[-1]['x']}"
                        if tgcuts else "sin fallos en 24 h"))
    last_ok = LAST_OK.get("download")
    fails = [e for e in day if e["k"] == "fallo"]
    lines.append(_check("Descargas", not fails or None,
                        f"en cola {jobs.qsize()}"
                        + (f", último enlace bien hace {health.ago(now - last_ok[0])} ({last_ok[1]})"
                           if last_ok else "")
                        + (f", {len(fails)} fallo(s) en 24 h" if fails else "")))
    lines.append(_check("Subidas grandes (2 GB)", bigupload.available(),
                        "activas" if bigupload.available() else "sin api.txt"))
    found = parse_cookies(COOKIES.read_text(errors="replace")) if COOKIES.exists() else {}
    for site, needed in SESSION_COOKIES.items():
        have = found.get(site, {})
        ok = all(n in have for n in needed)
        exp = min((have[n] for n in needed), default=0) if ok else 0
        soon = ok and exp and exp - now < 14 * 86400
        lines.append(_check(f"Cookies {site.split('.')[0]}", (None if soon else True) if ok else False,
                            (f"caducan {time.strftime('%d/%m/%Y', time.localtime(exp))}" if exp
                             else "de sesión") if ok else "sin sesión"))
    for check in PLUGIN_HEALTH:
        try:
            lines.append(check())
        except Exception as e:
            lines.append(_check(getattr(check, "__name__", "plugin"), False, str(e)[:100]))
    eng = stt.engine()
    lines.append(_check("Notas de voz", bool(eng), f"{eng}, en cola {stt_jobs.qsize()}" if eng
                        else "sin motor"))
    bat = "/sys/class/power_supply/battery"
    temp = int(read_sys(f"{bat}/temp", "0")) / 10
    free = shutil.disk_usage("/").free / 2**30
    lines.append(_check("Batería y disco", True if temp < 40 and free > 2 else None,
                        f"{read_sys(bat + '/capacity')}% · {temp:.1f} °C · {free:.1f} GB libres"))
    doc = read_sys(str(BASE / "sys" / "doctor.txt"), "")      # solo en modo sin root
    if doc.startswith("RESULT:"):
        state = (doc.split()[1:2] or ["?"])[0]          # un archivo truncado no rompe /salud
        bad = [l[5:] for l in doc.splitlines() if l.startswith("FAIL ")] + \
              [l[5:] for l in doc.splitlines() if l.startswith("WARN ")]     # lo peor primero
        lines.append(_check("Android/Termux", {"ok": True, "degraded": None}.get(state, False),
                            "todo en orden" if state == "ok" else
                            html.escape(bad[0][:150] if bad else state) +
                            (f" (+{len(bad) - 1} más; /diagnostico)" if len(bad) > 1 else "")))
    backup = read_sys(str(BASE / "last_backup"), "")
    if backup.isdigit():
        b_age = now - int(backup)
        lines.append(_check("Último respaldo", b_age < 30 * 86400 or None,
                            f"hace {health.ago(b_age)} (tools/backup.sh)"))
    else:
        lines.append(_check("Último respaldo", None, "no consta"))
    bad = [e for e in day if e["k"] in ("fallo", "caida", "colgado", "aviso")]
    if bad:
        lines.append(f"\nÚltimo problema: {html.escape(health.fmt(bad[-1]))}")
    st = ALERTS.level()
    lines.append(_check("Avisos automáticos", {"ok": True, "degraded": None}.get(st, False), ALERTS.summary()))
    lines.append("\n/historial – eventos recientes · /diagnostico – informe para pedir ayuda")
    return "\n".join(lines)


def diag_command(chat):
    """/diagnostico: informe de solo lectura, sin secretos, para pedir ayuda (ver diag.py)."""
    path = Path("/tmp") / f"diagnostico-{time.strftime('%Y%m%d-%H%M')}.txt"
    try:
        path.write_text(diag.report(), encoding="utf-8")
        send_file(chat, path, caption="🩺 Informe de diagnóstico. Quité token, IDs, IPs y "
                                      "rutas de enlaces, pero revísalo antes de compartirlo.",
                  as_doc=True)
    except Exception as e:
        log.exception("diagnostico")
        say(chat, f"❌ No pude generar el informe: {str(e).replace(TOKEN, '…')[:200]}")
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------- Avisos por estado

SHZ_FIX = {   # que hacer segun shizuku.sh probe (modo sin root)
    "not-running": "abre Shizuku y pulsa Iniciar (con el Wi-Fi conectado)",
    "app-unreachable": "abre la app Shizuku; ponla sin restricciones de batería",
    "not-authorized": "en Shizuku > Aplicaciones autorizadas, activa Termux",
    "awaiting-permission": "desbloquea el móvil y pulsa Permitir en el aviso de Shizuku",
    "dex-writable": "en Termux: chmod 400 ~/server/rish_shizuku.dex",
    "no-rish": "tools/noroot-install.sh rish <carpeta> desde el PC",
}
_tools_ok = {"t": 0, "ok": True}


def _sysinfo(name):
    out = {}
    for line in read_sys(str(BASE / "sys" / name), "").splitlines():
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def collect_problems():
    """Problemas reales de ahora mismo, para alerts.Alerts. "broken": el servidor no puede
    hacer su trabajo (descargar, avisar, recuperarse); "degraded": lo hace, con limites.
    Cada comprobacion va aparte: si una falla, las demas siguen."""
    now, out = time.time(), []

    def add(pid, level, title, impact="", fix=""):
        out.append({"id": pid, "level": level, "title": title, "impact": impact, "fix": fix})

    def guard(fn):
        try:
            fn()
        except Exception:
            log.exception("collect_problems: %s", fn.__name__)

    def internet():
        up, why = health.internet_ok()
        if not up:
            add("internet", "broken", f"Sin conexión a Internet ({why})", "no puedo descargar nada",
                "mira el router y el Wi-Fi; el vigilante reinicia el Wi-Fi tras 5 min sin red")

    def disk():
        free = shutil.disk_usage(str(BASE)).free / 2**20
        if free < 300:
            add("disk", "broken", f"Casi sin espacio: {free:.0f} MB libres",
                "las descargas y las actualizaciones fallan", "borra archivos grandes o fotos del móvil")
        elif free < 1024:
            add("disk", "degraded", f"Poco espacio: {free:.0f} MB libres",
                "los vídeos grandes pueden fallar", "libera espacio en el móvil")

    def tools():
        if now - _tools_ok["t"] >= 1800:          # arrancar yt-dlp cuesta: cada 30 min
            _tools_ok.update(t=now, ok=tools_work())
        if not _tools_ok["ok"]:
            add("tools", "broken", "yt-dlp o gallery-dl no arrancan", "no puedo descargar",
                "/actualizar; si sigue igual, /diagnostico")

    def noroot():
        shz = _sysinfo("shizuku")
        if not shz:
            return                                  # modo root, o vigilante antiguo
        checked = int(shz.get("checked") or 0)
        if checked and now - checked > 900:
            add("watchdog", "broken", "El vigilante (charge.sh) no está funcionando",
                "si el bot se cae o se cuelga, nadie lo relanza",
                "reinicia el móvil o, desde el PC, tools/noroot-doctor.sh")
            return
        state, since, boot = shz.get("state", "ok"), int(shz.get("since") or 0), int(shz.get("boot") or 0)
        if state != "ok" and since and now - since >= 300 and now - boot >= 600:
            fix = SHZ_FIX.get(state, "abre la app Shizuku y arráncala")
            if shz.get("auth") != "1" and state in ("not-running", "app-unreachable"):
                fix += "; pon SHIZUKU_AUTH en server.conf para que se reinicie solo"
            add("shizuku", "degraded", f"Shizuku no funciona ({state})",
                "si Android cierra Termux no se reabre solo, y /reiniciar del móvil no va", fix)

    def doctor():
        doc = read_sys(str(BASE / "sys" / "doctor.txt"), "")
        path = BASE / "sys" / "doctor.txt"
        if not doc.startswith("RESULT:") or now - path.stat().st_mtime > 3 * 3600:
            return
        lines = doc.splitlines()
        have_shz = bool(_sysinfo("shizuku"))
        for i, l in enumerate(lines):
            if not l.startswith(("FAIL ", "WARN ")):
                continue
            title = l[5:]
            if (have_shz and re.search(r"shizuku|wireless debugging|SHIZUKU_AUTH", title, re.I)) \
                    or re.search(r"MB free", title):      # ya vigilados aparte
                continue
            fix = lines[i + 1].strip()[3:] if i + 1 < len(lines) and lines[i + 1].strip().startswith("->") else ""
            add("doctor:" + re.sub(r"[\d\s]+", " ", title)[:60], "broken" if l.startswith("FAIL") else "degraded",
                title, "", fix)

    def crashes():
        n = len(health.recent(since=now - 6 * 3600, kinds=["caida", "colgado"]))
        if n >= 3:
            add("crashes", "degraded", f"El bot se reinició {n} veces en 6 h", "", "/historial y /diagnostico")

    def failures():
        n = len(health.recent(since=now - 3600, kinds=["fallo"]))
        if n >= 5:
            add("failures", "degraded", f"{n} descargas fallidas en la última hora", "",
                "/actualizar; si es una sola red, puede que haya cambiado algo")

    for fn in (internet, disk, tools, noroot, doctor, crashes, failures):
        guard(fn)
    return out


def _alert_send(text):
    owner, _ = load_owners()
    return bool(owner) and say(owner, text, parse_mode="HTML") is not None


ALERTS = alerts.Alerts(BASE / "alerts.json", _alert_send, clean=lambda s: diag.redact(s))


def alerts_loop():
    """Cada 5 min: estado real del servidor -> aviso al dueño solo si cambia (alerts.py).
    Nunca deja caer el hilo: un error aqui no afecta al bot."""
    time.sleep(180)                 # que arranque todo antes de juzgar
    while True:
        try:
            ALERTS.update(collect_problems())
        except Exception:
            log.exception("alerts_loop")
        time.sleep(300)


def history_text(arg):
    n = int(arg) if arg.isdigit() else 15
    evs = health.recent(n=min(n, 50))
    if not evs:
        return "Sin eventos todavía."
    return "📜 <b>Últimos eventos</b>\n" + "\n".join(html.escape(health.fmt(e)) for e in evs)


BAT = "/sys/class/power_supply/battery"
POWER_FILE = BASE / "power.json"      # ultimo corte de corriente: para estimar autonomia
_power = {"ref": None, "out": None, "drop": 0}


def battery_label():
    """En pausa de carga el driver dice "Discharging" aunque viva del cargador."""
    status = read_sys(f"{BAT}/status")
    if status == "Discharging" and charge_paused() == "1":
        if _power["out"]:
            return "sin corriente: tirando de la batería"
        return "en pausa, vive del cargador"
    return {"Charging": "cargando", "Discharging": "descargando", "Full": "llena",
            "Not charging": "sin cargar"}.get(status, status)


def watch_power(cap, status, slate):
    """Detecta cortes de luz (o el cargador desenchufado). En pausa el driver no dice si
    hay cargador, pero la bateria solo baja de verdad cuando falta: 2 puntos en menos
    de 1 h (en pausa normal baja ~0,1 %/h). Cargando, "Discharging" ya lo dice."""
    now, p = time.time(), _power
    charging = status in ("Charging", "Full")
    # Al reanudar la carga el driver tarda un poco en pasar a "Charging": 3 min seguidos
    p["unpl"] = p.get("unpl", 0) + 1 if status == "Discharging" and slate != "1" else 0
    unplugged = p["unpl"] >= 3
    if p["out"]:
        t0, c0 = p["out"]
        if cap < p["drop_cap"]:
            p["drop"], p["drop_cap"] = now, cap
        if charging or (not unplugged and now - p["drop"] > 2400):   # 40 min sin bajar
            end = p["drop"] if not charging else now
            hours = max((end - t0) / 3600, 0.1)
            rate = (c0 - p["drop_cap"]) / hours
            POWER_FILE.write_text(json.dumps({"t": t0, "end": end, "from": c0,
                                              "to": p["drop_cap"], "rate": round(rate, 2)}))
            health.event("carga", f"volvió la corriente: {c0}→{p['drop_cap']}% en "
                                  f"{health.ago(end - t0)} ({rate:.1f} %/h)")
            alert("power-back", f"🔌 Volvió la corriente. Estuvo {health.ago(end - t0)} con "
                  f"batería: {c0}→{p['drop_cap']}%.", 0)
            p.update(out=None, ref=(now, cap))
        return
    ref = p["ref"]
    if ref is None or charging or cap > ref[1] or now - ref[0] > 3600:
        p["ref"] = ref = (now, cap)
    if unplugged or ref[1] - cap >= 2:
        p.update(out=ref, drop=now, drop_cap=cap)
        health.event("carga", f"sin corriente del cargador: va con batería ({cap}%)")
        alert("power-out", f"🔌 Parece que se fue la luz o se desconectó el cargador: el "
              f"móvil va con batería ({cap}%). Te aviso cuando vuelva.", 0)


CHARGE_RE = re.compile(r"^(pausa|reanuda) la carga al (\d+)%")


def battery_text(arg):
    """/bateria: estado, detalles y tramos de carga (de los eventos de charge.sh)."""
    n = int(arg) if arg.isdigit() else 6
    marks = []                                    # (epoch, cargando, %)
    for e in health.recent(kinds={"carga"}):
        m = CHARGE_RE.match(e["x"])
        if m and (not marks or marks[-1][1] != (m.group(1) == "reanuda")):
            marks.append((e["t"], m.group(1) == "reanuda", int(m.group(2))))
    cap = read_sys(f"{BAT}/capacity")
    capn = int(cap) if cap.isdigit() else None
    now = (time.time(), None, capn)
    hm = lambda t: time.strftime("%d/%m %H:%M", time.localtime(t))
    lines = []
    for i, ((t0, on, p0), (t1, _, p1)) in enumerate(zip(marks, marks[1:] + [now])):
        secs = t1 - t0
        if p1 is None:
            continue
        rate = f" · {(p1 - p0) / (secs / 3600):.1f} %/h" if on and secs >= 600 and p1 > p0 else ""
        if i == len(marks) - 1:
            end = "ahora"
        else:   # mismo dia: solo la hora
            end = hm(t1)[6:] if hm(t1)[:5] == hm(t0)[:5] else hm(t1)
        lines.append(f"{'🔌 carga' if on else '⏸️ pausa'} {hm(t0)} → {end}: "
                     f"{p0}→{p1}% en {health.ago(secs)}{rate}")

    def num(f, div, digits):
        v = read_sys(f"{BAT}/{f}")
        return f"{int(v) / div:.{digits}f}" if v.lstrip("-").isdigit() else "?"
    raw = read_sys(f"{BAT}/batt_read_raw_soc")
    gauge = f" (medidor {int(raw) / 100:.2f} %)" if raw.isdigit() else ""
    health_es = {"Good": "buena", "Overheat": "sobrecalentada", "Dead": "agotada",
                 "Cold": "fría"}.get(read_sys(f"{BAT}/health"), read_sys(f"{BAT}/health"))
    maker = read_sys(f"{BAT}/batt_type").split()[0].replace("SDI", "Samsung SDI")
    out = [f"🔋 <b>Batería</b>: {cap}%{gauge} · {html.escape(battery_label())}",
           f"⚡ {num('voltage_now', 1e6, 2)} V · 🌡️ {num('temp', 10, 1)} °C · salud {health_es}",
           f"🔧 {read_sys(f'{BAT}/technology')} {maker}, {DEVICE['battery']}",
           "🎚️ " + DEVICE.get("charge_note", "Carga entre {range} %; si pasa de 42 °C deja "
                              "de cargar y por debajo del 15 % carga siempre")
           .replace("{range}", read_sys(BASE / "charge_range"))]
    try:
        last = json.loads(POWER_FILE.read_text())
        est = f" · con {cap}% aguantaría ~{capn / last['rate']:.0f} h" \
            if capn and last["rate"] > 0.5 else ""
        out.append(f"💡 Último corte: {hm(last['t'])}, {health.ago(last['end'] - last['t'])}, "
                   f"{last['from']}→{last['to']}% ({last['rate']:.1f} %/h){est}")
    except (OSError, ValueError, KeyError):
        out.append("💡 Si se va la luz la batería entra sola (te aviso). La autonomía se "
                   "mide en el primer corte.")
    if lines:
        out += ["", "<b>Últimos tramos</b>"] + [html.escape(l) for l in lines[-n:]]
    out.append("\n<i>En pausa el móvil vive del cargador: la batería ni carga ni se gasta, "
               "así que el % casi no se mueve.</i>")
    return "\n".join(out)


REBOOT_REQUEST = BASE / "reboot_request"   # lo atiende charge.sh (lado Android)


def reboot_command(chat, arg):
    if arg == "adb":
        REBOOT_REQUEST.write_text("adb")
        health.event("adb", "reinicio de adb pedido por /reiniciar")
        say(chat, "🔌 Reiniciando adb (la conexión del PC) en menos de 1 min. "
                  "El bot sigue funcionando.")
    elif arg == "wifi":
        REBOOT_REQUEST.write_text("wifi")
        health.event("wifi", "reconexión del Wi-Fi pedida por /reiniciar")
        say(chat, "📶 Reconectando el Wi-Fi en menos de 1 min (se engancha al punto de "
                  "acceso más fuerte). El bot vuelve solo en ~30 s.")
    elif arg == "confirmar":
        REBOOT_REQUEST.write_text("phone")
        health.event("reinicio", "reinicio del móvil pedido por /reiniciar")
        log.info("reinicio del movil pedido por el dueño")
        say(chat, "🔄 Reiniciando el móvil en menos de 1 min. Volveré en ~2 min y te "
                  "avisaré cuando esté en marcha.")
    else:
        say(chat, "¿Qué quieres reiniciar?\n"
                  "/reiniciar confirmar – el móvil entero (~2 min sin bot)\n"
                  "/reiniciar adb – solo la conexión del PC por Wi-Fi (el bot sigue)\n"
                  "/reiniciar wifi – reconectar el Wi-Fi (si el PC no lo ve o va lento)",
            buttons=[[("📶 Wi-Fi", "/reiniciar wifi"), ("🔌 Conexión del PC", "/reiniciar adb")],
                     [("🔄 Móvil completo", "/reiniciar confirmar")]])


UPDATE_PKGS = ("yt-dlp", "yt-dlp-ejs", "gallery-dl")
UPDATE_MIN_FREE = 300 * 2**20       # pip necesita sitio para descargar y desempaquetar


def tool_versions():
    """{paquete: version} de los descargadores instalados en el venv ({} si pip falla)."""
    try:
        p = run([VENV_BIN / "pip", "list", "--format=json"], "/", timeout=120)
        have = {d["name"].lower(): d["version"] for d in json.loads(p.stdout or "[]")}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}
    return {n: have[n] for n in UPDATE_PKGS if n in have}


def tools_work():
    """Comprobacion minima tras actualizar: los ejecutables arrancan y dicen su version."""
    for exe in ("yt-dlp", "gallery-dl"):
        try:
            if run([VENV_BIN / exe, "--version"], "/", timeout=120).returncode:
                return False
        except (OSError, subprocess.TimeoutExpired):
            return False
    return True


def update_tools(chat=None):
    """Actualiza yt-dlp/gallery-dl a lo ultimo. Antes mira que haya sitio y apunta las
    versiones que habia; si pip falla o los programas no arrancan despues, vuelve a ellas.
    Nunca lanza excepciones (lo llama un hilo que debe seguir vivo)."""
    def done(ok, text):
        health.event("actualizacion" if ok else "aviso", text)
        if chat:
            say(chat, ("🔄 " if ok else "❌ ") + text)
    try:
        free = shutil.disk_usage(str(VENV_BIN)).free
        if free < UPDATE_MIN_FREE:
            return done(False, f"no actualizo los descargadores: solo quedan "
                               f"{free // 2**20} MB libres (hacen falta {UPDATE_MIN_FREE // 2**20})")
        before = tool_versions()
        p = run([VENV_BIN / "pip", "install", "-q", "-U", *UPDATE_PKGS], "/", timeout=900)
        if p.returncode == 0 and tools_work():
            after = tool_versions()
            return done(True, "descargadores: " + ", ".join(
                f"{n} {after.get(n, '?')}" for n in UPDATE_PKGS if n != "yt-dlp-ejs"))
        why = (p.stderr.strip().splitlines() or ["los programas no arrancan"])[-1][:200] \
            if p.returncode else "los programas no arrancan tras actualizar"
        if before:
            r = run([VENV_BIN / "pip", "install", "-q", *(f"{n}=={v}" for n, v in before.items())],
                    "/", timeout=900)
            back = "vuelvo a las versiones de antes" if r.returncode == 0 and tools_work() \
                else "y TAMPOCO pude volver a las de antes (ver bot.log)"
        else:
            back = "no sé qué versiones había para volver atrás"
        done(False, f"falló la actualización de descargadores ({why}); {back}")
    except Exception as e:      # TimeoutExpired, OSError...: el hilo no debe morir
        log.exception("update_tools")
        done(False, f"falló la actualización de descargadores: {str(e)[:200]}")


def auto_update():
    while True:
        time.sleep(24 * 3600)
        update_tools()


def parse_cookies(text):
    """Devuelve {dominio: {nombre: caducidad}} de un cookies.txt Netscape."""
    found = {}
    for line in text.splitlines():
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if line.startswith("#") or len(parts) != 7:
            continue
        domain = parts[0].lstrip(".")
        for site in SESSION_COOKIES:
            if domain == site or domain.endswith("." + site):
                domain = site
        found.setdefault(domain, {})[parts[5]] = int(parts[4] or 0)
    return found


def cookies_status():
    if not COOKIES.exists():
        return ("🍪 No hay cookies guardadas.\n\nMándame por privado un archivo "
                "cookies.txt (formato Netscape) de una cuenta secundaria.")
    found = parse_cookies(COOKIES.read_text(errors="replace"))
    lines = ["🍪 Cookies guardadas:"]
    for site, needed in SESSION_COOKIES.items():
        have = found.get(site, {})
        if all(n in have for n in needed):
            exp = min(have[n] for n in needed)
            when = time.strftime("%d/%m/%Y", time.localtime(exp)) if exp else "sesión"
            lines.append(f"✅ {site} (caduca {when})")
        else:
            lines.append(f"❌ {site}: sin sesión iniciada")
    lines.append("\n/cookies borrar – eliminarlas")
    return "\n".join(lines)


def save_cookies(msg):
    chat = msg["chat"]["id"]
    doc = msg["document"]
    if doc.get("file_size", 0) > 1024 * 1024:
        say(chat, "❌ Ese archivo es demasiado grande para ser un cookies.txt.")
        return
    path = tg("getFile", file_id=doc["file_id"])["file_path"]
    text = http.get(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=60).text
    for handler in PLUGIN_DOCS:
        if handler(msg, doc, text):
            return
    found = parse_cookies(text)
    if not found:
        say(chat, "❌ No parece un cookies.txt en formato Netscape.")
        return
    # Fusionar con las que ya habia: se reemplazan solo los dominios que trae
    keep = []
    if COOKIES.exists():
        new_domains = set(found)
        for line in COOKIES.read_text(errors="replace").splitlines():
            if line.startswith("#") and not line.startswith("#HttpOnly_"):
                continue
            dom = parse_cookies(line)
            if dom and not set(dom) & new_domains:
                keep.append(line)
    body = [l for l in text.splitlines()
            if l.strip() and (not l.startswith("#") or l.startswith("#HttpOnly_"))]
    COOKIES.write_text("# Netscape HTTP Cookie File\n" + "\n".join(keep + body) + "\n")
    COOKIES.chmod(0o600)
    delete(chat, msg["message_id"])  # el archivo es una credencial: no dejarlo en el chat
    log.info("cookies actualizadas: %s", ", ".join(sorted(found)))
    health.event("cookies", "cookies renovadas: " + ", ".join(sorted(found)))
    say(chat, "Guardadas y borré tu mensaje.\n\n" + cookies_status())


HELP = ("🤖 <b>Qué hago</b>\n"
        "Mándame un enlace de TikTok, Instagram, Facebook, Threads, YouTube, X, Reddit… "
        "y publico el vídeo o las fotos con el título enlazado al original, y borro tu "
        "mensaje con el enlace. Los vídeos van en 1080p (720p si pasan de 2 GB).\n\n"
        "<b>Comandos</b>\n"
        "/mp3 <i>enlace</i> – solo el audio, en MP3 con portada\n"
        "/original <i>enlace</i> – fotos y vídeos como archivo, en calidad original "
        "(Telegram comprime las fotos normales)\n"
        "/pdf – mándame un PDF con /pdf como pie (o responde a uno) y te devuelvo cada "
        "página como imagen JPG. Opciones: <i>archivo</i> (sin comprimir), <i>png</i>, "
        "<i>zip</i> (todo en un archivo), <i>10-25</i> (solo esas páginas)\n"
        "/estado – batería, temperatura, espacio y cola de descargas\n"
        "/buscar <i>texto</i> – busca en YouTube; con botones bajas el vídeo o solo el audio\n"
        "/cola – descargas en curso y en espera (con botón para cancelar)\n"
        "/acerca – quién soy, en qué corro y todo lo que sé hacer\n"
        "/velocidad – prueba de velocidad de la red de casa (ping, bajada y subida)\n"
        "/help – esta ayuda")
OWNER_HELP = ("\n\n👑 <b>Solo tú (por privado)</b>\n"
              "/seguir <i>canal</i> [<i>privado|canal|ambos</i>] – recibir en 1080p los vídeos "
              "nuevos de un canal de YouTube (por defecto, a tu privado)\n"
              "/canales – canales que sigues y a dónde va cada uno\n"
              "/destino <i>N privado|canal|ambos</i> – cambiar a dónde va un canal seguido\n"
              "/canal – tus canales de Telegram donde publico (añádeme como administrador; "
              "<i>/canal videos N</i> · <i>/canal canciones N</i>)\n"
              "/dejar <i>N</i> – dejar de seguir el canal N\n"
              "/permitir <i>ID</i> – dar acceso por privado a alguien\n"
              "/quitar <i>ID</i> – retirar el acceso\n"
              "/usuarios – quién tiene acceso\n"
              "/cookies – estado de las sesiones de Instagram/Facebook "
              "(mándame un .txt para renovarlas; /cookies borrar las elimina)\n"
              "/actualizar – actualizar yt-dlp y gallery-dl ahora (si falla, vuelve a las versiones de antes)\n"
              "/stats [<i>hoy|semana|mes|todo</i>] – enlaces por red y por persona, GB, fallos y "
              "notas de voz\n"
              "/reiniciar – el móvil (<i>confirmar</i>), solo adb (<i>adb</i>) o el Wi-Fi (<i>wifi</i>)\n"
              + ("/guardar – respondiendo a un vídeo o foto que te mandé (o con un enlace): lo copia "
                 f"al NAS, donde no se borra (lo demás se guarda {ARCH_DAYS} días)\n" if ARCH_DAYS else "")
              +
              "/transcribir – notas de voz a texto en este chat (<i>on</i>/<i>off</i>)\n"
              "/salud – comprobación de todos los servicios, conexión, espacio y último fallo\n"
              "/historial [<i>N</i>] – últimos eventos (reinicios, cortes de Internet, avisos…)\n"
              "/diagnostico – informe sin secretos (versiones, recursos, logs) para pedir ayuda\n"
              "/bateria [<i>N</i>] – batería a detalle: voltaje, salud, cortes de luz y "
              "últimos tramos de carga\n\n"
              "Te aviso por aquí si caducan las cookies, si la batería se calienta, "
              "si una red falla varias veces o si el móvil se reinicia, y cuando el estado del "
              "servidor cambia (algo deja de funcionar o se arregla), una sola vez por cambio.")
PUBLIC_COMMANDS = [("mp3", "Solo el audio de un enlace"),
                   ("original", "Fotos/vídeos como archivo, calidad original"),
                   ("pdf", "PDF → una imagen por página"),
                   ("estado", "Estado del móvil"),
                   ("buscar", "Buscar en YouTube y bajarlo"),
                   ("cola", "Descargas en curso (y cancelarlas)"),
                   ("acerca", "Quién soy y todo lo que hago"),
                   ("velocidad", "Prueba de velocidad de la red"),
                   ("help", "Qué hago y comandos")]
OWNER_COMMANDS = PUBLIC_COMMANDS + [
    ("seguir", "Seguir un canal de YouTube"), ("canales", "Canales seguidos"),
    ("dejar", "Dejar de seguir un canal"), ("destino", "Privado o canal para un canal seguido"),
    ("canal", "Canales de Telegram donde publico"), ("permitir", "Dar acceso a alguien"),
    ("quitar", "Retirar acceso"), ("usuarios", "Quién tiene acceso"),
    ("cookies", "Sesiones de Instagram/Facebook"), ("actualizar", "Actualizar descargadores"),
    ("stats", "Estadísticas: redes, personas, GB, fallos"),
    ("reiniciar", "Reiniciar el móvil o adb"),
    *([("guardar", "Guardar en el NAS (respondiendo a un vídeo o con un enlace)")] if ARCH_DAYS else []),
    ("transcribir", "Transcripción de notas de voz"),
    ("salud", "Salud de todos los servicios"), ("historial", "Últimos eventos"),
    ("bateria", "Batería a detalle y cortes de luz")]


STATS = BASE / "stats.json"            # contadores para /acerca
_stats_lock = threading.Lock()


def bump(key, n=1):
    with _stats_lock:
        try:
            st = json.loads(STATS.read_text())
        except (OSError, ValueError):
            st = {}
        st.setdefault("since", int(time.time()))
        st[key] = st.get(key, 0) + n
        STATS.write_text(json.dumps(st))


def about_text(full=False):
    """/acerca: presentacion del servidor para presumir (sin comandos). Lo privado
    (plugins, version de Android) solo se lo ensena al dueño por privado."""
    mem = dict(l.split(":", 1) for l in read_sys("/proc/meminfo", "").splitlines() if ":" in l)
    ram = int(mem.get("MemTotal", "0 kB").split()[0]) / 2**20
    du = shutil.disk_usage("/")
    freqs = [read_sys(str(f)) for f in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/cpuinfo_max_freq")]
    ghz = max([int(f) for f in freqs if f.isdigit()] or [1728000]) / 1e6   # el nucleo mas rapido
    up = float(read_sys("/proc/uptime", "0").split()[0])
    debian = read_sys("/etc/debian_version").split(".")[0]
    try:
        st = json.loads(STATS.read_text())
    except (OSError, ValueError):
        st = {}
    eng = (stt.engine() or "whisper").split()[0].capitalize()
    lines = [
        f"🦖 <b>{html.escape(BOT.get('first_name') or 'Bot')}</b>",
        f"{DEVICE['intro']}, trabajando 24/7 "
        "con su cargador y su Wi-Fi. Nada de nube: todo corre aquí dentro.",
        "",
        "📱 <b>El fierro</b>",
        f"• {DEVICE['cpu']} a {ghz:.1f} GHz · {ram:.1f} GB de RAM · "
        f"{du.total / 2**30:.0f} GB ({du.free / 2**30:.1f} libres)",
        f"• {DEVICE['android']} {DEVICE.get('root', 'con root')} y, dentro, un Debian {debian} "
        "completo con Python" if full
        else f"• Android y, dentro, un Linux Debian {debian} completo",
        f"• Lleva {health.ago(up)} encendido sin parar · batería al "
        f"{read_sys(BAT + '/capacity')}% y a {int(read_sys(BAT + '/temp', '0')) / 10:.0f} °C",
        "",
        "🧠 <b>Lo que sabe hacer</b>",
        "• Descarga vídeos y fotos de TikTok, Instagram, Facebook, Threads, YouTube, X, "
        "Reddit y más de mil sitios, en 1080p y hasta 2 GB por archivo",
        "• Saca el audio en MP3 con portada y etiquetas",
        "• Sigue canales de YouTube y publica sus vídeos nuevos en cuanto salen",
        f"• Transcribe notas de voz con inteligencia artificial ({eng}) corriendo en el "
        "propio teléfono, sin mandar el audio a nadie",
        "• Convierte PDFs en imágenes, una por página, listas para redes sociales",
        *(PLUGIN_ABOUT if full else []),
        "• Mide la velocidad del internet de la casa",
        "",
        "🛡️ <b>Se cuida solo</b>",
        "• Si el bot se cuelga o se cae, se levanta solo: sus procesos se vigilan entre sí",
        "• Si se cae el Wi-Fi o internet, se reconecta y se cambia a la antena más fuerte",
        "• Cuida su batería: no la carga de más, deja de cargar si se calienta y si se va "
        "la luz sigue con batería y avisa",
        "• Actualiza sus descargadores cada día y avisa si una red empieza a fallar",
        "• Copias de seguridad del sistema completo",
    ]
    if st.get("links"):
        since = time.strftime("%d/%m/%Y", time.localtime(st["since"]))
        lines += ["", f"📊 {st['links']} enlaces atendidos desde el {since}"]
    return "\n".join(lines)


def help_text(owner_private):
    if not owner_private:
        return HELP
    extra = "".join("\n" + o["help"] for o in PLUGIN_COMMANDS.values() if o.get("help"))
    # los comandos de plugins van al final de la lista del dueño, antes del aviso final
    head, sep, tail = OWNER_HELP.partition("\n\nTe aviso")
    return HELP + head + extra + sep + tail


def register_commands(owner):
    """Menu de '/' en Telegram: el dueño ve tambien los suyos en su chat privado."""
    as_json = lambda cmds: json.dumps([{"command": c, "description": d} for c, d in cmds])
    mine = [(n[1:], o["menu"]) for n, o in PLUGIN_COMMANDS.items() if o.get("menu")]
    try:
        tg("setMyCommands", commands=as_json(PUBLIC_COMMANDS))
        if owner:
            tg("setMyCommands", commands=as_json(OWNER_COMMANDS + mine),
               scope=json.dumps({"type": "chat", "chat_id": owner}))
    except Exception as e:
        log.info("setMyCommands: %s", e)


def enqueue(msg, chat, user, urls, rest_text, mode="video"):
    # Solo se borra el mensaje si no traia nada mas que enlaces (y el comando)
    only_link = not URL_RE.sub("", rest_text).strip()
    # En privado no hace falta decir quien lo mando: solo el titulo enlazado
    name = "" if msg["chat"]["type"] == "private" else \
        " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) \
        or user.get("username", "")
    for n, url in enumerate(urls):
        jobs.put({"chat": chat, "msg_id": msg["message_id"], "url": url, "mode": mode,
                  "sender": name, "uid": user.get("id"),
                  "quien": " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
                           or user.get("username", ""),
                  "only_link": only_link and n == len(urls) - 1,
                  # El mensaje se queda (trae texto): la respuesta lo cita
                  "reply_to": None if only_link else msg["message_id"]})


OWNER_ONLY = {"/seguir", "/canales", "/dejar", "/destino", "/canal", "/permitir", "/quitar",
              "/usuarios", "/cookies", "/actualizar", "/reiniciar", "/transcribir", "/salud",
              "/historial", "/bateria", "/batería", "/carga", "/guardar", "/stats",
              "/diagnostico", "/diagnóstico"}
OWNER_ANYWHERE = {"/actualizar", "/transcribir", "/salud", "/historial", "/guardar",   # tambien en grupos
                  "/bateria", "/batería", "/carga"}


def on_message(msg):
    chat = msg["chat"]["id"]
    ctype = msg["chat"]["type"]
    user = msg.get("from", {})
    uid = user.get("id")
    owner, allowed = load_owners()
    owner_private = uid == owner and ctype == "private"

    # Al añadir el bot a un grupo: si lo añade el dueño, el grupo queda autorizado
    for m in msg.get("new_chat_members", []):
        if m.get("id") == BOT.get("id"):
            if uid == owner:
                authorize(chat, msg["chat"].get("title"))
                say(chat, "👋 Listo.\n\n" + help_text(False) + "\n\nHazme administrador con "
                          "permiso para borrar mensajes para que pueda limpiar los enlaces.",
                    parse_mode="HTML")
            else:
                say(chat, "🔒 Solo mi dueño puede añadirme a grupos.")
                tg("leaveChat", chat_id=chat)
            return

    # Solo el dueño, por privado, puede subir cookies
    if msg.get("document") and owner_private \
            and msg["document"].get("file_name", "").lower().endswith(".txt"):
        save_cookies(msg)
        return

    text = (msg.get("text") or msg.get("caption") or "").strip()
    cmd = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    arg = text.split(maxsplit=1)[1].strip() if cmd and len(text.split()) > 1 else ""

    if cmd == "/start":
        if owner is None and ctype == "private":
            authorize(uid, display_name(user))
            register_commands(uid)
            say(chat, "👋 Hecho, ahora eres el dueño de este bot.\n\n" + help_text(True),
                parse_mode="HTML")
            log.info("nuevo dueño: %s", uid)
        elif uid == owner:
            authorize(chat, msg["chat"].get("title"))
            say(chat, "✅ Chat autorizado.\n\n" + help_text(owner_private), parse_mode="HTML")
        elif chat in allowed:
            say(chat, help_text(False), parse_mode="HTML")
        elif ctype == "private":
            request_access(user)
            say(chat, "🔒 Este bot es privado. Le he pedido acceso a su dueño; "
                      "te avisaré aquí cuando te lo dé.")
        return

    if chat not in allowed:
        if ctype == "private" and owner:
            request_access(user)
            say(chat, "🔒 Este bot es privado. Le he pedido acceso a su dueño.")
        return

    # Notas de voz y videomensajes redondos: transcribir y responder al audio
    voice = msg.get("voice") or msg.get("video_note")
    if voice and not cmd:
        if stt.enabled(chat) and stt.engine():
            if voice.get("duration", 0) > STT_MAX_SECS:
                say(chat, f"🎙️ Ese audio dura más de {STT_MAX_SECS // 60} min; "
                          "no lo transcribo.", reply_to=msg["message_id"])
            else:
                stt_jobs.put({"chat": chat, "msg_id": msg["message_id"], "uid": uid,
                              "file_id": voice["file_id"],
                              "name": user.get("first_name") or user.get("username", "")})
        return

    plugin = PLUGIN_COMMANDS.get(cmd)
    if (cmd in OWNER_ONLY or (plugin and plugin["owner"])) and uid != owner:
        return
    if ((cmd in OWNER_ONLY - OWNER_ANYWHERE) or (plugin and plugin["owner"]
                                                 and not plugin["anywhere"])) \
            and ctype != "private":
        say(chat, "Ese comando úsalo conmigo por privado.")
        return
    if plugin:
        args = (msg, chat, user, arg)
        if plugin["thread"]:
            threading.Thread(target=plugin["fn"], args=args, daemon=True).start()
        else:
            plugin["fn"](*args)
        return

    if cmd in ("/help", "/ayuda"):
        say(chat, help_text(owner_private), parse_mode="HTML", buttons=[
            [("📱 Estado", "/estado"), ("🔋 Batería", "/bateria"), ("🌐 Velocidad", "/velocidad")],
            [("🩺 Salud", "/salud"), ("📊 Estadísticas", "/stats"), ("📥 Cola", "/cola")],
            [("📺 Canales", "/canales"), ("🎙️ Notas de voz", "/transcribir"), ("🔄 Reiniciar", "/reiniciar")],
        ] if owner_private else None)
    elif cmd == "/acerca":
        say(chat, about_text(owner_private), parse_mode="HTML")
    elif cmd == "/estado":
        say(chat, status_text())
    elif cmd == "/pdf":
        threading.Thread(target=acting("upload_photo", lambda c, m, a: pdf_command(m, c, a)),
                         args=(chat, msg, arg), daemon=True).start()
    elif cmd in ("/velocidad", "/speedtest"):
        threading.Thread(target=acting("typing", speed_command), args=(chat,), daemon=True).start()
    elif cmd in ("/mp3", "/original", "/archivo"):
        urls = URL_RE.findall(arg)
        r = msg.get("reply_to_message")
        if not urls and r and link_of(r):
            # Respondiendo a algo que mando el bot (o con su boton): el enlace de su titulo.
            # Con texto, para que enqueue no borre el mensaje al que se responde.
            enqueue(msg, chat, user, [link_of(r)], "(respuesta)",
                    mode="mp3" if cmd == "/mp3" else "file")
            return
        if not urls:
            say(chat, f"Uso: {cmd} enlace (o respondiendo a un vídeo que te mandé)")
            return
        enqueue(msg, chat, user, urls, arg, mode="mp3" if cmd == "/mp3" else "file")
    elif cmd == "/cookies":
        if "borrar" in arg.lower():
            COOKIES.unlink(missing_ok=True)
            say(chat, "🗑️ Cookies eliminadas.")
        else:
            say(chat, cookies_status())
    elif cmd == "/actualizar":
        say(chat, "🔄 Actualizando yt-dlp y gallery-dl… (si algo falla vuelvo a las versiones de ahora)")
        threading.Thread(target=update_tools, args=(chat,), daemon=True).start()
    elif cmd == "/canal":
        channel_command(chat, arg)
    elif cmd in ("/seguir", "/canales", "/dejar", "/destino"):
        threading.Thread(target=subs_command, args=(chat, cmd, arg), daemon=True).start()
    elif cmd in ("/permitir", "/quitar", "/usuarios"):
        access_command(chat, cmd, arg)
    elif cmd == "/transcribir":
        transcribe_command(chat, arg)
    elif cmd == "/salud":
        threading.Thread(target=lambda: say(chat, health_text(), parse_mode="HTML"),
                         daemon=True).start()
    elif cmd == "/historial":
        say(chat, history_text(arg), parse_mode="HTML")
    elif cmd in ("/diagnostico", "/diagnóstico"):
        threading.Thread(target=diag_command, args=(chat,), daemon=True).start()
    elif cmd in ("/bateria", "/batería", "/carga"):
        say(chat, battery_text(arg), parse_mode="HTML")
    elif cmd == "/reiniciar":
        reboot_command(chat, arg.lower())
    elif cmd == "/guardar":
        threading.Thread(target=guardar_command, args=(msg, chat, arg), daemon=True).start()
    elif cmd == "/cola":
        cola_command(chat, uid)
    elif cmd == "/stats":
        say(chat, stats_text(arg), parse_mode="HTML",
            buttons=[[(t, f"/stats {k}") for k, t in (("hoy", "Hoy"), ("semana", "Semana"),
                                                       ("mes", "Mes"), ("todo", "Todo"))]])
    elif cmd == "/cancelar":
        cancelar_command(chat, uid, arg)
    elif cmd == "/buscar":
        threading.Thread(target=acting("typing", lambda c, m, a: buscar_command(m, c, a)),
                         args=(chat, msg, arg), daemon=True).start()
    elif cmd in ("/yt", "/ytmp3"):            # los botones de /buscar
        if YT_ID.fullmatch(arg.strip()):
            enqueue(msg, chat, user, [f"https://www.youtube.com/watch?v={arg.strip()}"],
                    "(búsqueda)", mode="mp3" if cmd == "/ytmp3" else "video")
    elif not cmd:
        urls = URL_RE.findall(text)
        if urls:
            enqueue(msg, chat, user, urls, text)
        elif ctype == "private":
            say(chat, "Mándame un enlace, o escribe /help para ver qué hago.")


def on_button(cb):
    """Pulsacion de un boton en linea (ver keyboard()): su orden se trata como un mensaje
    escrito por quien pulsa, con los mismos permisos, y como respuesta al mensaje del
    boton (asi /mp3, /original y /guardar encuentran el enlace de su titulo)."""
    try:
        tg("answerCallbackQuery", callback_query_id=cb["id"])   # quita el reloj del boton
    except Exception as e:
        log.info("answerCallbackQuery: %s", e)
    m, data = cb.get("message"), cb.get("data") or ""
    if not m or not data.startswith("/"):
        return              # mensaje demasiado viejo (Telegram no lo manda) o dato ajeno
    try:
        on_message({"message_id": m["message_id"], "chat": m["chat"],
                    "from": cb.get("from", {}), "text": data, "reply_to_message": m})
    except Exception:
        log.exception("on_button")

def main():
    shutil.rmtree(JOBS, ignore_errors=True)   # restos de descargas cortadas
    migrate_to_sqlite()
    JOBS.mkdir(parents=True, exist_ok=True)
    for _ in range(WORKERS):
        threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=auto_update, daemon=True).start()
    threading.Thread(target=subs_loop, daemon=True).start()
    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=alerts_loop, daemon=True).start()
    load_plugins()
    for fn in PLUGIN_LOOPS:
        threading.Thread(target=fn, daemon=True).start()
    threading.Thread(target=stt_worker, daemon=True).start()
    health.beat()
    BOT.update(tg("getMe"))
    log.info("arrancado como @%s", BOT["username"])
    owner, _ = load_owners()
    register_commands(owner)
    # Aviso de encendido: una vez por arranque del kernel, aunque el bot se reinicie
    boot_id, marker = read_sys("/proc/sys/kernel/random/boot_id", ""), BASE / "last_boot"
    if boot_id and read_sys(marker, "") != boot_id:
        marker.write_text(boot_id)
        health.event("arranque", "el móvil se encendió")
        alert("boot", "🔌 El móvil se acaba de encender (reinicio o corte de luz). "
                      "Todo está en marcha otra vez.", 600)
    report_crashes()
    health.event("inicio", f"bot en marcha (versión {VERSION})")
    resume_pending()
    outage = health.Outage()
    offset = None
    errs = 0            # fallos seguidos del sondeo, para esperar cada vez más
    while True:
        health.beat()   # señal de vida: si deja de llegar, charge.sh reinicia el bot
        try:
            # Durante un corte, peticiones cortas: asi la vuelta se nota al momento
            wait = 1 if outage.since is not None else 50
            params = {"timeout": wait, "allowed_updates": json.dumps(["message", "my_chat_member", "callback_query"])}
            if offset:
                params["offset"] = offset
            updates = tg("getUpdates", _timeout=wait + 20, **params)
            errs = 0
            cut = outage.ok()
            if cut:
                kind, txt, msg = health.describe(*cut)
                health.event(kind, txt)
                alert(f"red-{int(cut[0])}", msg, 0)
            for upd in updates:
                offset = upd["update_id"] + 1
                if "message" in upd:
                    try:
                        on_message(upd["message"])
                    except Exception:
                        log.exception("on_message")
                elif "callback_query" in upd:
                    threading.Thread(target=on_button, args=(upd["callback_query"],),
                                     daemon=True).start()
                elif "my_chat_member" in upd:
                    try:
                        channel_event(upd["my_chat_member"])
                    except Exception:
                        log.exception("channel_event")
        except TelegramError as e:
            # Telegram contestó con un error: NO es un corte de Internet.
            errs += 1
            if e.code == 409:
                # Otra copia del bot usa el mismo token (p. ej. el móvil de respaldo).
                log.warning("poll: %s (¿hay otra instancia del bot con este token?)", e)
                delay = 15
            elif e.code == 429 or e.code >= 500:
                outage.failed("telegram", e.code, late=False)
                log.warning("poll (Telegram): %s", e)
                delay = health.backoff(errs, e.retry_after)
            else:
                log.warning("poll: %s", e)
                delay = 5
            time.sleep(delay)
        except requests.RequestException as e:
            # Sin respuesta (timeout, conexión rota). Antes de culpar a Internet se
            # comprueba la salida a Internet y el DNS: si van bien, el fallo es de Telegram.
            errs += 1
            up, why = health.internet_ok()
            outage.failed("telegram" if up else "internet", None if up else why)
            log.warning("poll (%s): %s", "Telegram sin respuesta" if up else "red: " + why, e)
            time.sleep(health.backoff(errs, cap=60 if up else 15))
        except Exception as e:
            log.warning("poll: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
