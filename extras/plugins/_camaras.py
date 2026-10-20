"""Camaras de un grabador (XVR/NVR) Dahua o compatible: fotos al momento y clips.

  /opt/bot/camaras.json  {"host": "192.168.1.10", "user": "...", "password": "..."}
  (crea en el grabador un usuario solo para el bot, con permisos de ver y reproducir;
  nunca el administrador)

Usa la API CGI de Dahua (snapshot.cgi, loadfile.cgi, RTSP). Otras marcas hablan otro
protocolo: hay que adaptar _http(), snapshot() y clip().

Fotos: snapshot.cgi por HTTP (autenticacion digest); si falla, un fotograma del
directo por RTSP. Clips: RTSP de reproduccion del grabador, copiado sin recodificar.
"""
import datetime as dt
import json
import logging
import re
import subprocess
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote

import requests
from requests.auth import HTTPDigestAuth

BASE = Path("/opt/bot")
CONFIG = BASE / "camaras.json"
MAX_CLIP_MIN = 60
log = logging.getLogger("bot")
_names = {"t": 0, "list": []}


class CamError(Exception):
    pass


def config():
    try:
        cfg = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        raise CamError("las cámaras no están configuradas")
    return cfg


def _http(path, cfg=None, timeout=15):
    cfg = cfg or config()
    r = requests.get(f"http://{cfg['host']}{path}", timeout=timeout,
                     auth=HTTPDigestAuth(cfg["user"], cfg["password"]))
    if r.status_code == 401:
        raise CamError("el grabador rechaza el usuario o la contraseña del bot")
    r.raise_for_status()
    return r


def _rtsp(path, cfg):
    return (f"rtsp://{quote(cfg['user'], safe='')}:{quote(cfg['password'], safe='')}"
            f"@{cfg['host']}:554{path}")


def channels():
    """[(numero, nombre)] de las camaras, con los nombres que tiene el grabador."""
    if time.time() - _names["t"] < 3600 and _names["list"]:
        return _names["list"]
    text = _http("/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle").text
    found = {}
    for idx, name in re.findall(r"table\.ChannelTitle\[(\d+)\]\.Name=(.*)", text):
        found[int(idx) + 1] = name.strip()
    lst = sorted(found.items()) or [(n, f"Cámara {n}") for n in range(1, 5)]
    _names.update(t=time.time(), list=lst)
    return lst


def _norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def resolve(arg):
    """'3' o parte del nombre ('patio') -> (numero, nombre)."""
    chans = channels()
    if arg.isdigit():
        n = int(arg)
        for c in chans:
            if c[0] == n:
                return c
        raise CamError(f"no hay cámara {n} (hay {len(chans)})")
    hits = [c for c in chans if _norm(arg) in _norm(c[1])]
    if len(hits) == 1:
        return hits[0]
    names = ", ".join(f"{n} {name}" for n, name in chans)
    raise CamError(f"no sé qué cámara es «{arg}». Cámaras: {names}")


def snapshot(ch, out: Path):
    """Foto actual de la camara `ch` en `out` (JPEG)."""
    cfg = config()
    try:
        r = _http(f"/cgi-bin/snapshot.cgi?channel={ch}", cfg)
        if r.headers.get("content-type", "").startswith("image") and len(r.content) > 1000:
            out.write_bytes(r.content)
            return out
    except CamError:
        raise
    except requests.RequestException as e:
        log.info("snapshot.cgi canal %s: %s", ch, e)
    # Plan B: un fotograma del directo
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-rtsp_transport", "tcp",
                        "-i", _rtsp(f"/cam/realmonitor?channel={ch}&subtype=0", cfg),
                        "-frames:v", "1", "-q:v", "2", str(out)],
                       capture_output=True, text=True, timeout=40)
    if p.returncode or not out.exists():
        raise CamError(f"no pude sacar la foto de la cámara {ch}")
    return out


# ---------------------------------------------------------------- Clips

def parse_clip(args, now=None):
    """'2 [hoy|ayer|17/10[/2026]] 14:59 15:02' -> (camara, inicio, fin)."""
    now = now or dt.datetime.now()
    toks = args.split()
    if len(toks) < 3:
        raise CamError("uso: /clip_camaras cámara [fecha] inicio fin\n"
                       "p.ej. /clip_camaras 2 14:59 15:02 · /clip_camaras 2 ayer 23:50 23:58 · "
                       "/clip_camaras patio 17/10 2:59 3:02")
    cam, rest = toks[0], toks[1:]
    day, explicit = now.date(), False
    if len(rest) == 3:
        d = rest.pop(0).lower()
        explicit = True
        if d == "hoy":
            pass
        elif d == "ayer":
            day -= dt.timedelta(days=1)
        else:
            m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", d)
            if not m:
                raise CamError(f"no entiendo la fecha «{d}» (usa hoy, ayer o dd/mm[/aaaa])")
            y = int(m.group(3)) if m.group(3) else now.year
            y = y + 2000 if y < 100 else y
            day = dt.date(y, int(m.group(2)), int(m.group(1)))
    elif len(rest) != 2:
        raise CamError("necesito una hora de inicio y otra de fin, p.ej. 14:59 15:02")

    def hhmm(s):
        m = re.fullmatch(r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?", s)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise CamError(f"no entiendo la hora «{s}» (usa HH:MM, p.ej. 14:59)")
        return dt.time(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))

    start = dt.datetime.combine(day, hhmm(rest[0]))
    end = dt.datetime.combine(day, hhmm(rest[1]))
    if end <= start:                      # p.ej. 23:58 00:03 -> cruza medianoche
        end += dt.timedelta(days=1)
    if not explicit and start > now:      # sin fecha y aun no ha pasado hoy -> ayer
        start -= dt.timedelta(days=1)
        end -= dt.timedelta(days=1)
    if end > now:
        raise CamError("ese fragmento todavía no ha terminado de grabarse")
    if end - start > dt.timedelta(minutes=MAX_CLIP_MIN):
        raise CamError(f"máximo {MAX_CLIP_MIN} minutos por clip")
    return cam, start, end


def last_minute(now=None):
    """(inicio, fin) del ultimo minuto ya grabado; unos segundos de margen porque el
    grabador escribe el disco con algo de retraso."""
    end = (now or dt.datetime.now()).replace(microsecond=0) - dt.timedelta(seconds=10)
    return end - dt.timedelta(minutes=1), end


def _to_mp4(src, out: Path, secs, timeout):
    """Remux a MP4 sin recodificar el video; el audio del grabador (G.711) a AAC."""
    return subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-rtsp_transport", "tcp",
                           "-i", src, "-t", str(secs), "-map", "0:v:0", "-map", "0:a?",
                           "-c:v", "copy", "-c:a", "aac", "-b:a", "64k",
                           "-movflags", "+faststart", str(out)]
                          if src.startswith("rtsp") else
                          ["ffmpeg", "-loglevel", "error", "-y", "-i", src,
                           "-map", "0:v:0", "-map", "0:a?", "-c:v", "copy", "-c:a", "aac",
                           "-b:a", "64k", "-movflags", "+faststart", str(out)],
                          capture_output=True, text=True, timeout=timeout)


def clip(ch, start, end, out: Path):
    """Saca del grabador el tramo [start, end] de la camara `ch` a `out` (MP4).

    Primero descarga directa del archivo (loadfile.cgi, formato DHAV): ~30x mas
    rapido que el RTSP de reproduccion, que va a menos de tiempo real."""
    cfg = config()
    secs = int((end - start).total_seconds())
    raw = out.with_suffix(".dav")
    try:
        f = lambda t: t.strftime("%Y-%m-%d %H:%M:%S")
        r = _http(f"/cgi-bin/loadfile.cgi?action=startLoad&channel={ch}&startTime={f(start)}"
                  f"&endTime={f(end)}&subtype=0", cfg, timeout=60)
        with raw.open("wb") as fh:
            for chunk in r.iter_content(256 * 1024):
                fh.write(chunk)
        if raw.stat().st_size > 10_000:
            p = _to_mp4(str(raw), out, secs, timeout=600)
            if p.returncode == 0 and out.exists() and out.stat().st_size > 10_000:
                return out
            log.info("clip loadfile canal %s: ffmpeg %s", ch, p.stderr[-200:])
    except CamError:
        raise
    except requests.RequestException as e:
        log.info("clip loadfile canal %s: %s", ch, e)
    finally:
        raw.unlink(missing_ok=True)
    return _clip_rtsp(ch, start, end, out, cfg)


def _clip_rtsp(ch, start, end, out: Path, cfg):
    """Plan B: RTSP de reproduccion (lento, va a menos de tiempo real)."""
    f = lambda t: t.strftime("%Y_%m_%d_%H_%M_%S")
    url = _rtsp(f"/cam/playback?channel={ch}&starttime={f(start)}&endtime={f(end)}", cfg)
    secs = int((end - start).total_seconds())
    p = _to_mp4(url, out, secs, timeout=secs * 3 + 120)
    if p.returncode or not out.exists() or out.stat().st_size < 10_000:
        err = (p.stderr.strip().splitlines() or [""])[-1][:200]
        log.info("clip canal %s: rc=%s %s", ch, p.returncode, err)
        raise CamError("no hay grabación en ese horario o el grabador no la entregó")
    return out


def video_codec(path: Path):
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return p.stdout.strip()
