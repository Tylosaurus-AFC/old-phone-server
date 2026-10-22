"""Portada (miniatura) de los videos que se envian.

Telegram pide JPEG de 320 px como maximo por lado y menos de 200 KB. Si yt-dlp dejo
un <id>.info.json junto al video, se usa la miniatura original (la de YouTube); si no,
un fotograma del video tomado al ~10 % de su duracion (los primeros segundos suelen
ser negros o un logo).
"""
import json
import logging
import subprocess
import urllib.request
from pathlib import Path

log = logging.getLogger("bot")
FIT = "scale='if(gt(iw,ih),320,-2)':'if(gt(iw,ih),-2,320)'"
MAX_BYTES = 200 * 1024


def _duration(video: Path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0


def _ffmpeg(args, out: Path):
    for q in (3, 6, 10):        # subir la compresion si pasa de 200 KB
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args, "-frames:v", "1",
                        "-vf", FIT, "-q:v", str(q), str(out)], timeout=120)
        if out.exists() and out.stat().st_size <= MAX_BYTES:
            return out
    out.unlink(missing_ok=True)
    return None


def _original(video: Path, out: Path):
    info = video.with_suffix(".info.json")
    try:
        url = json.loads(info.read_text()).get("thumbnail")
    except (OSError, ValueError):
        return None
    if not url:
        return None
    raw = out.with_suffix(".orig")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw.write_bytes(r.read(5 * 2**20))
        return _ffmpeg(["-i", str(raw)], out)
    except Exception as e:
        log.info("miniatura original: %s", e)
        return None
    finally:
        raw.unlink(missing_ok=True)


def make(video: Path):
    """Crea <video>.thumb.jpg y lo devuelve (o None). Quien la pide la borra."""
    out = video.with_suffix(".thumb.jpg")
    try:
        return _original(video, out) or \
            _ffmpeg(["-ss", f"{_duration(video) * 0.1:.1f}", "-i", str(video)], out)
    except Exception as e:
        log.info("miniatura: %s", e)
        return None


def audio_cover(audio: Path):
    """Miniatura para Telegram (sendAudio) a partir de la portada incrustada."""
    out = audio.with_suffix(".thumb.jpg")
    try:
        return _ffmpeg(["-i", str(audio)], out)
    except Exception as e:
        log.info("miniatura de audio: %s", e)
        return None
