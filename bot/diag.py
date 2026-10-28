"""Informe de diagnostico para pedir ayuda: solo lectura y sin secretos.

Lo manda el bot con /diagnostico (al dueño, por privado) y tambien se puede generar a mano
dentro del Debian:

    /opt/bot/venv/bin/python3 /opt/bot/diag.py > /tmp/diagnostico.txt

Recoge versiones, recursos (RAM, disco, bateria), eventos recientes y el final de los logs.
Antes de devolverlo quita el token, el api_id/api_hash, los IDs de owners, las IPs y deja
los enlaces solo con su dominio. NUNCA lee cookies.txt ni las sesiones. Aun asi, revisa el
texto antes de publicarlo.
"""
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path("/opt/bot")
VENV_BIN = BASE / "venv" / "bin"
BAT = Path("/sys/class/power_supply/battery")
LOG_LINES = 60

_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_URL_RE = re.compile(r"(https?://[^/\s\"'<>]+)[^\s\"'<>]*")
_LONG_ID_RE = re.compile(r"(?<![\w.])-?\d{7,}(?![\w.])")    # IDs de Telegram, numeros de serie...


def _read(path, default=""):
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return default


def _secrets():
    """Textos exactos que no deben salir nunca en el informe."""
    out = [_read(BASE / "token")]
    out += _read(BASE / "api.txt").split()
    out += [l.split()[0] for l in _read(BASE / "owners").splitlines() if l.split()]
    return sorted({s for s in out if len(s) >= 4}, key=len, reverse=True)


def redact(text, secrets=None):
    for s in (secrets if secrets is not None else _secrets()):
        text = text.replace(s, "<oculto>")
    text = _TOKEN_RE.sub("<token>", text)
    text = _URL_RE.sub(r"\1/…", text)          # el dominio sirve; la ruta dice que se bajo
    text = _IP_RE.sub("<ip>", text)
    return _LONG_ID_RE.sub("<id>", text)


def _num(text, default=None):
    """float del texto, o `default`: los archivos los escriben otros procesos y pueden venir
    vacios, a medias o con "null"; el informe tiene que salir igual."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _cmd_version(*cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "no disponible"
    first = (p.stdout or p.stderr).strip().splitlines()
    return first[0][:120] if p.returncode == 0 and first else "no disponible"


def _tail(path, n=LOG_LINES):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 64 * 1024))     # basta con el final; no cargar 1 MB
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ["(no existe)"]
    return lines[-n:]


def _meminfo():
    m = {}
    for line in _read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        if v.split():
            m[k] = int(v.split()[0]) // 1024        # MB
    if "MemTotal" not in m:
        return "no disponible"
    return (f"{m.get('MemAvailable', m.get('MemFree', 0))} MB libres de {m['MemTotal']} MB; "
            f"swap {m.get('SwapFree', 0)}/{m.get('SwapTotal', 0)} MB libres")


def _disk(path):
    try:
        u = shutil.disk_usage(path)
    except OSError:
        return "no disponible"
    return f"{u.free / 2**30:.1f} GB libres de {u.total / 2**30:.1f} GB"


def report():
    now = time.time()
    up = _read("/proc/uptime", "0").split()
    lines = [
        "== old-phone-server: informe de diagnóstico ==",
        f"generado: {time.strftime('%Y-%m-%d %H:%M:%S %z', time.localtime(now))}",
        f"versión del bot: {_read(BASE / 'VERSION', '?')}",
        f"python: {sys.version.split()[0]} · {platform.machine()} · kernel {platform.release()}",
        f"modo: {'sin root (proot)' if (BASE / 'sys').is_dir() else 'root (chroot) o desconocido'}",
        f"encendido hace: {int(_num(up[0] if up else 0, 0)) // 3600} h",
        f"carga: {_read('/proc/loadavg', 'no disponible')}",
        f"RAM: {_meminfo()}",
        f"disco /: {_disk('/')}",
        f"disco /tmp: {_disk('/tmp')}",
        f"batería: {_read(BAT / 'capacity', '?')}% · {_read(BAT / 'status', '?')} · "
        f"{_num(_read(BAT / 'temp'), 0) / 10:.1f} °C",
        "",
        "== herramientas ==",
        f"yt-dlp: {_cmd_version(str(VENV_BIN / 'yt-dlp'), '--version')}",
        f"gallery-dl: {_cmd_version(str(VENV_BIN / 'gallery-dl'), '--version')}",
        f"ffmpeg: {_cmd_version('ffmpeg', '-version')}",
        "",
        "== configuración (solo si existe, nunca el contenido) ==",
    ]
    for f in ("token", "owners", "api.txt", "cookies.txt", "device.json", "stt.json"):
        lines.append(f"{f}: {'sí' if (BASE / f).exists() else 'no'}")
    plugins = sorted(p.name for p in (BASE / "plugins").glob("*.py")) \
        if (BASE / "plugins").is_dir() else []
    lines.append(f"plugins: {', '.join(plugins) or 'ninguno'}")
    hb = _read(BASE / "heartbeat")
    lines.append(f"señal de vida: hace {int(now - _num(hb))} s" if _num(hb) is not None
                 else "señal de vida: no consta")
    try:
        pend = len(json.loads(_read(BASE / "pending_downloads.json", "[]") or "[]"))
    except (ValueError, TypeError):
        pend = "ilegible"
    lines += [f"descargas pendientes: {pend}", "", "== últimos eventos =="]
    for raw in _read(BASE / "events.jsonl").splitlines()[-30:]:
        try:
            e = json.loads(raw)
            lines.append(f"{time.strftime('%d/%m %H:%M', time.localtime(e['t']))} "
                         f"[{e['k']}] {e['x']}")
        except (ValueError, KeyError, TypeError):
            continue
    doc = _read(BASE / "sys" / "doctor.txt")
    if doc:
        lines += ["", "== modo sin root: ~/server/doctor.sh (última hora) =="] + doc.splitlines()
    for name in ("bot.log", "service.log"):
        lines += ["", f"== final de {name} =="] + _tail(BASE / name)
    return redact("\n".join(lines)) + "\n"


if __name__ == "__main__":
    sys.stdout.write(report())
