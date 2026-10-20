"""Hacer hablar a las Alexa de casa con Voice Monkey (API v3).

  /opt/bot/voicemonkey.json  {"token": "...", "device": "id opcional", "language": "es-ES"}
  (secreto: no lo subas a git)

Cada altavoz de Voice Monkey dispara una rutina de Alexa ("abre Mono de Voz") en el
Echo elegido. Para que suene en varios Echo con una sola llamada basta con duplicar la
rutina en la app de Alexa cambiando solo "Desde". El plan gratis da 200 llamadas al mes.
"""
import json
import time
import unicodedata
from pathlib import Path

import requests

CONFIG = Path("/opt/bot/voicemonkey.json")
API = "https://api-v3.voicemonkey.io"
MAX_CHARS = 400
_devices = {"t": 0, "list": []}


class AlexaError(Exception):
    pass


def config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        raise AlexaError("Voice Monkey no está configurado (falta voicemonkey.json)")


def _call(path, method="GET", **params):
    cfg = config()
    params["token"] = cfg["token"]
    try:
        r = (requests.get(f"{API}/{path}", params=params, timeout=20) if method == "GET"
             else requests.post(f"{API}/{path}", json=params, timeout=20))
    except requests.RequestException as e:
        raise AlexaError(f"no pude hablar con Voice Monkey: {e}")
    if r.status_code == 429:
        raise AlexaError("se acabaron las llamadas del mes del plan gratis de Voice Monkey"
                         if "QUOTA" in r.text else "Voice Monkey pide esperar un momento")
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code != 200 or data.get("success") is False:
        raise AlexaError(f"Voice Monkey respondió {r.status_code}: {r.text[:200]}")
    return data


def devices():
    """[{id, name}] de los altavoces (Speakers) de Voice Monkey."""
    if time.time() - _devices["t"] > 3600 or not _devices["list"]:
        lst = [d for d in _call("devices").get("data", []) if d.get("capability") == "speakers"]
        _devices.update(t=time.time(), list=lst)
    return _devices["list"]


def _norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def resolve(name=None):
    devs = devices()
    if not devs:
        raise AlexaError("no hay altavoces en Voice Monkey (app.voicemonkey.io/speakers)")
    if name:
        hits = [d for d in devs if _norm(name) in _norm(d["name"])]
        if len(hits) != 1:
            raise AlexaError(f"no sé qué Alexa es «{name}». Hay: "
                             + ", ".join(d["name"] for d in devs))
        return hits[0]
    want = config().get("device")
    return next((d for d in devs if d["id"] == want), devs[0])


def speak(text, name=None):
    """Dice `text` en el altavoz `name` (o el de por defecto). Devuelve su nombre."""
    text = " ".join(text.split())[:MAX_CHARS]
    if not text:
        raise AlexaError("¿qué digo?")
    dev = resolve(name)
    _call("announce", "POST", device=dev["id"], speech=text, language=config().get("language", "es-ES"))
    return dev["name"]
