"""Salud del servidor: registro de eventos, señal de vida y cortes de Internet.

  /opt/bot/events.jsonl  {"t": epoch, "k": tipo, "x": texto} por linea. Tambien lo
                         escriben bot.sh y charge.sh (lado Android).
  /opt/bot/heartbeat     epoch de la ultima vuelta del bucle principal; si se queda
                         viejo, charge.sh reinicia el bot (colgado).
"""
import json
import threading
import time
from pathlib import Path

BASE = Path("/opt/bot")
EVENTS = BASE / "events.jsonl"
HEARTBEAT = BASE / "heartbeat"
KEEP = 400
_lock = threading.Lock()

ICONS = {"arranque": "🔌", "inicio": "▶️", "caida": "💥", "colgado": "🧊", "red": "🌐", "telegram": "📡",
         "wifi": "📶", "carga": "🔋", "aviso": "⚠️", "fallo": "❌", "reinicio": "🔄",
         "adb": "🔧", "actualizacion": "⬆️", "respaldo": "💾", "cookies": "🍪"}


def event(kind, text):
    line = json.dumps({"t": int(time.time()), "k": kind, "x": str(text)[:300]},
                      ensure_ascii=False)
    with _lock:
        with EVENTS.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        try:   # recortar de vez en cuando
            lines = EVENTS.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > KEEP + 100:
                EVENTS.write_text("\n".join(lines[-KEEP:]) + "\n", encoding="utf-8")
        except OSError:
            pass


def recent(n=None, since=None, kinds=None):
    try:
        lines = EVENTS.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for l in lines:
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if since and e["t"] < since:
            continue
        if kinds and e["k"] not in kinds:
            continue
        out.append(e)
    return out[-n:] if n else out


def fmt(e):
    when = time.strftime("%d/%m %H:%M", time.localtime(e["t"]))
    return f"{ICONS.get(e['k'], '•')} {when} {e['x']}"


def beat():
    try:
        HEARTBEAT.write_text(str(int(time.time())))
    except OSError:
        pass


def ago(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds} s"
    if seconds < 5400:
        return f"{seconds // 60} min"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds // 86400} días"


def internet_ok(timeout=4):
    """(True, "") si este movil tiene salida a Internet y resuelve nombres; si no,
    (False, motivo). Prueba TCP directo a IPs conocidas y despues el DNS, para no
    confundir «Internet caido» con «Telegram con problemas»."""
    import socket
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            socket.create_connection((host, 443), timeout).close()
            break
        except OSError:
            continue
    else:
        return False, "sin salida a Internet"
    try:
        socket.getaddrinfo("api.telegram.org", 443)
    except OSError:
        return False, "no resuelve nombres (DNS)"
    return True, ""


def backoff(errors, retry_after=None, cap=60):
    """Segundos de espera tras `errors` fallos seguidos: 5, 10, 20, 40... hasta `cap`.
    Si Telegram pide esperar (`retry_after`), se espera al menos eso (+1 s)."""
    import random
    delay = min(cap, 5 * 2 ** min(max(errors, 1) - 1, 5))
    if retry_after:
        delay = max(delay, min(int(retry_after) + 1, 120))
    return delay + random.uniform(0, 1)


class Outage:
    """Lleva la cuenta de los cortes vistos por el bucle de Telegram. Distingue dos
    tipos: "internet" (este movil no tiene salida) y "telegram" (Internet va bien pero
    Telegram da errores 429/5xx o no responde)."""
    MIN_SECS = 60      # cortes mas cortos no se avisan

    def __init__(self):
        self.since = None
        self.last_ok = time.time()
        self.kind = None
        self.detail = set()

    def failed(self, kind="internet", detail=None, late=True):
        # `late`: el bucle tiene abierta una peticion larga (hasta 70 s) y el fallo se
        # nota tarde; el corte empezo, como pronto, tras la ultima respuesta buena.
        # Con un error HTTP de Telegram se sabe en el momento (late=False).
        if self.since is None:
            self.since = self.last_ok if late else time.time()
            self.kind = kind
        elif kind == "internet":
            self.kind = "internet"      # si hubo corte de Internet, manda sobre Telegram
        if detail:
            self.detail.add(str(detail))

    def ok(self):
        """Devuelve (inicio, fin, tipo, detalles) si acaba de terminar un corte que
        merece aviso."""
        now = time.time()
        self.last_ok = now
        if self.since is None:
            return None
        start, kind, detail = self.since, self.kind, sorted(self.detail)
        self.since, self.kind, self.detail = None, None, set()
        return (start, now, kind, detail) if now - start >= self.MIN_SECS else None


def describe(start, end, kind, detail):
    """(tipo de evento, texto para /historial, mensaje al dueño) de un corte."""
    span = (f"de {time.strftime('%H:%M', time.localtime(start))} a "
            f"{time.strftime('%H:%M', time.localtime(end))} ({ago(end - start)})")
    if kind == "telegram":
        why = f" ({', '.join(detail)})" if detail else ""
        txt = f"Telegram con fallos {span}{why}; Internet iba bien"
        return "telegram", txt, (f"📡 Telegram tuvo problemas {span}{why}. "
                                 "Es cosa de su servidor: la conexión de este móvil iba bien.")
    own = [d for d in detail if not d.isdigit()]     # sin los códigos HTTP de Telegram
    why = f": {', '.join(own)}" if own else ""
    txt = f"sin conexión {span}{why}"
    return "red", txt, f"🌐 Internet volvió: estuve {txt}."
