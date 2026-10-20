"""Stickers de video: cualquier video -> el WEBM que acepta Telegram.

Requisitos de Telegram para un sticker de video: VP9 en WEBM, sin audio, lado mayor
de 512 px, como mucho 3 s, 30 fps y 256 KB. Se recorta a los primeros 3 s (o desde
`start`) y se baja la tasa de bits hasta que quepa.
"""
import subprocess
from pathlib import Path

MAX_SECS = 3
MAX_BYTES = 256 * 1024
MAX_INPUT = 20 * 1024 * 1024          # la Bot API no deja bajar archivos mas grandes


class StickerError(Exception):
    pass


def convert(src: Path, out: Path, start=0.0):
    err = ""
    for kbps in (500, 330, 200, 120):
        p = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", str(start), "-i", str(src),
             "-t", str(MAX_SECS), "-an",
             "-vf", "scale=512:512:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                    "fps=30",
             "-c:v", "libvpx-vp9", "-b:v", f"{kbps}k", "-deadline", "good", "-cpu-used", "5",
             "-row-mt", "1", "-pix_fmt", "yuva420p", "-f", "webm", str(out)],
            capture_output=True, text=True, timeout=600)
        if p.returncode:
            err = (p.stderr.strip().splitlines() or [""])[-1][:200]
            break
        if out.stat().st_size <= MAX_BYTES:
            return out
    raise StickerError(f"no pude convertir el vídeo: {err}" if err else
                       "no consigo dejarlo en menos de 256 KB")
