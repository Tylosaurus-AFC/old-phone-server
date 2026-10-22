"""Scrobbler YouTube Music -> Last.fm.

En iPhone no hay forma de scrobblear YouTube Music, asi que el servidor lee el
historial de la cuenta (ytmusicapi, con las cookies del navegador) cada pocos
minutos y manda a Last.fm lo que haya aparecido arriba.

  /opt/bot/ytmusic_cookies.txt  cookies de music.youtube.com (cuenta principal)
  /opt/bot/lastfm.json          api_key, api_secret, session_key, user
  /opt/bot/scrobble_state.json  ultima foto del historial, pendientes, recientes

Limitaciones: el historial no trae la hora de cada cancion (se estima) y una
cancion repetida seguida no se duplica en el (cuenta una vez).
"""
import hashlib
import html
import json
import logging
import re
import threading
import time
from pathlib import Path

import requests

BASE = Path("/opt/bot")
YTM_COOKIES = BASE / "ytmusic_cookies.txt"
LASTFM_FILE = BASE / "lastfm.json"
STATE_FILE = BASE / "scrobble_state.json"
EVERY = 180                     # segundos entre consultas al historial
SNAPSHOT = 60                   # cuantas entradas del historial se recuerdan
MAX_NEW = 30                    # mas nuevas que esto de golpe = algo raro, no se scrobblea
UNSTABLE_FOR = 20 * 60          # una cancion que "baila" en el historial no cuenta en este rato
MAX_LEN = 15 * 60               # mas larga que esto no es una cancion (mezcla, directo...)
PODCAST_DATE = re.compile(r"^([A-Z][a-z]{2} \d{1,2}, \d{4}|\d{1,2} [a-z]{3}\.? \d{4})$")
LASTFM_API = "https://ws.audioscrobbler.com/2.0/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

log = logging.getLogger("bot")
lock = threading.Lock()
http = requests.Session()


def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.chmod(0o600)
    tmp.replace(path)


def state():
    st = load(STATE_FILE, {})
    st.setdefault("snapshot", [])
    st.setdefault("pending", [])
    st.setdefault("recent", [])
    st.setdefault("paused", False)
    st.setdefault("days", {})       # "2026-10-18": n scrobbles
    return st


# ---------------------------------------------------------------- YouTube Music

def cookie_header(text):
    """Cabecera Cookie con las cookies de youtube.com de un cookies.txt Netscape."""
    pairs = {}
    for line in text.splitlines():
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if line.startswith("#") or len(parts) != 7:
            continue
        if parts[0].lstrip(".").endswith("youtube.com"):
            pairs[parts[5]] = parts[6].strip()
    return "; ".join(f"{k}={v}" for k, v in pairs.items()), pairs


def ytm_client():
    from ytmusicapi import YTMusic
    cookie, pairs = cookie_header(YTM_COOKIES.read_text(errors="replace"))
    if "__Secure-3PAPISID" not in pairs:
        raise RuntimeError("al cookies.txt le falta __Secure-3PAPISID (¿sesión iniciada?)")
    headers = {
        "user-agent": UA, "accept": "*/*", "accept-language": "es-ES,es;q=0.9",
        "content-type": "application/json", "x-goog-authuser": "0",
        "origin": "https://music.youtube.com", "x-origin": "https://music.youtube.com",
        # ytmusicapi reconoce la sesion de navegador por este prefijo y recalcula el hash
        "authorization": "SAPISIDHASH 0_0", "cookie": cookie,
    }
    return YTMusic(auth=headers)


def fetch_history():
    """[{id, title, artist, album, duration}] del historial, de mas nueva a mas vieja."""
    out = []
    for it in ytm_client().get_history():
        artists = [a["name"] for a in it.get("artists") or [] if a.get("name")]
        if not it.get("videoId") or not artists:
            continue
        out.append({"id": it["videoId"], "title": it.get("title") or "",
                    "artist": artists[0],
                    "album": (it.get("album") or {}).get("name") or "",
                    "duration": int(it.get("duration_seconds") or 0),
                    "type": it.get("videoType") or ""})
    return out


def skip_reason(tr):
    """Por que no se scrobblea (podcasts, mezclas o sesiones largas), o None."""
    # Los episodios de podcast llegan sin tipo y con la fecha en el artista ("Sep 13, 2026")
    if "PODCAST" in tr.get("type", "") or PODCAST_DATE.match(tr["artist"]):
        return "podcast"
    if tr["duration"] > MAX_LEN:
        return f"dura {tr['duration'] // 60} min"
    return None


def new_plays(prev, cur):
    """IDs que aparecieron arriba desde la ultima foto (de mas nueva a mas vieja).

    Una cancion repetida no se duplica en el historial: sube arriba. Se busca el
    menor k tal que, quitando cur[:k] de la foto anterior, lo que queda coincide
    con cur[k:]. Esas k primeras son las reproducciones nuevas."""
    if not prev:
        return []
    for k in range(min(len(cur), MAX_NEW) + 1):
        moved = set(cur[:k])
        rest = [v for v in prev if v not in moved]
        n = min(8, len(cur) - k, len(rest))
        if n == 0 or cur[k:k + n] == rest[:n]:
            return cur[:k]
    return None   # no cuadra (historial borrado, cambio grande): no inventar


# ---------------------------------------------------------------- Last.fm

def lastfm():
    return load(LASTFM_FILE, {})


def lf_call(method, cfg, **params):
    params.update(method=method, api_key=cfg["api_key"])
    if cfg.get("session_key") and method not in ("auth.getToken", "auth.getSession"):
        params["sk"] = cfg["session_key"]
    raw = "".join(f"{k}{params[k]}" for k in sorted(params)) + cfg["api_secret"]
    params["api_sig"] = hashlib.md5(raw.encode("utf-8")).hexdigest()
    params["format"] = "json"
    r = http.post(LASTFM_API, data=params, timeout=30)
    data = r.json()
    if "error" in data:
        raise LastfmError(data["error"], data.get("message", ""))
    return data


class LastfmError(Exception):
    def __init__(self, code, message):
        super().__init__(f"Last.fm {code}: {message}")
        self.code = code


def auth_start(api_key, api_secret):
    """Guarda la clave y devuelve el enlace para autorizar (sin pedir contraseña)."""
    cfg = {"api_key": api_key, "api_secret": api_secret}
    token = lf_call("auth.getToken", cfg)["token"]
    cfg["token"] = token
    save(LASTFM_FILE, cfg)
    return f"https://www.last.fm/api/auth/?api_key={api_key}&token={token}"


def auth_finish():
    cfg = lastfm()
    if not cfg.get("token"):
        raise RuntimeError("primero /lastfm API_KEY SECRET")
    s = lf_call("auth.getSession", cfg, token=cfg["token"])["session"]
    cfg.update(session_key=s["key"], user=s["name"])
    cfg.pop("token", None)
    save(LASTFM_FILE, cfg)
    return s["name"]


def scrobble_batch(cfg, items):
    params = {}
    for i, t in enumerate(items):
        params.update({f"artist[{i}]": t["artist"], f"track[{i}]": t["title"],
                       f"timestamp[{i}]": t["ts"]})
        if t["album"]:
            params[f"album[{i}]"] = t["album"]
        if t["duration"]:
            params[f"duration[{i}]"] = t["duration"]
    res = lf_call("track.scrobble", cfg, **params)["scrobbles"]["@attr"]
    return int(res.get("accepted", 0)), int(res.get("ignored", 0))


# ---------------------------------------------------------------- Bucle

def ready():
    return YTM_COOKIES.exists() and bool(lastfm().get("session_key"))


def poll_once(alert=None):
    """Una vuelta: leer historial, detectar nuevas, scrobblear. Devuelve n enviadas."""
    with lock:
        st = state()
        if st["paused"] or not ready():
            return 0
        cfg = lastfm()
        try:
            hist = fetch_history()
        except Exception as e:
            st["last_error"] = f"YouTube Music: {e}"[:200]
            save(STATE_FILE, st)
            msg = str(e).lower()
            if alert and any(w in msg for w in ("401", "403", "sign in", "cookie", "papisid",
                                                "login", "unauthorized")):
                alert("ytm-auth", "🎧 La sesión de YouTube Music para el scrobbler parece "
                      "caducada.\n\nExporta de nuevo las cookies de music.youtube.com con tu "
                      "cuenta principal y mándame el .txt por aquí.", 12 * 3600)
            raise

        by_id = {t["id"]: t for t in hist}
        cur = [t["id"] for t in hist][:SNAPSHOT]
        prev = st["snapshot"]
        plays = new_plays(prev, cur)
        if plays is None:
            log.info("scrobbler: el historial no cuadra con la foto anterior, se reinicia")
            plays = []
        st["snapshot"] = cur

        # Repeticiones a confirmar de la vuelta anterior: YouTube Music a veces devuelve
        # el historial con dos canciones intercambiando el primer puesto entre consultas.
        # Una cancion que "subio" solo cuenta si sigue por encima de la que adelanto.
        # Las que "bailan" asi quedan marcadas un rato y sus subidas no cuentan.
        now = int(time.time())
        unstable = {k: v for k, v in st.get("unstable", {}).items() if v > now}
        confirmed = []
        for h in st.get("hold", []):
            vid, over = h["track"]["id"], h.get("over")
            if vid in unstable:
                continue
            if vid in cur and (over not in cur or cur.index(vid) < cur.index(over)):
                confirmed.append(h["track"])
            else:
                log.info("scrobbler: descartada subida falsa de %s", h["track"]["title"])
                for x in (vid, over):
                    if x:
                        unstable[x] = now + UNSTABLE_FOR
        st["hold"] = []

        # Horas: YouTube Music anota la cancion al empezar. La mas nueva empezo hace
        # ~media vuelta; las anteriores, escalonadas hacia atras por su duracion.
        t = now - EVERY // 2
        batch = []
        for vid in plays:                      # de mas nueva a mas vieja
            tr = dict(by_id[vid])
            tr["ts"] = t
            t -= tr["duration"] if tr["duration"] >= 30 else 180
            why = skip_reason(tr)
            if why:
                log.info("scrobbler: no cuenta %s – %s (%s)", tr["artist"], tr["title"], why)
                st["skipped"] = (st.get("skipped", []) + [
                    {"artist": tr["artist"], "title": tr["title"], "ts": tr["ts"], "why": why}])[-5:]
                continue
            batch.append(tr)
        batch.reverse()                        # Last.fm: de mas vieja a mas nueva
        # No pisar la tanda anterior: si se solapa, desplazar toda la tanda hacia
        # delante (sin pasar de ahora) en vez de repetir horas
        floor = st.get("last_ts", 0) + 30
        if batch and batch[0]["ts"] < floor:
            shift = min(floor - batch[0]["ts"], now - batch[-1]["ts"])
            for tr in batch:
                tr["ts"] += max(shift, 0)
        # Las que ya estaban en el historial y han subido (posible repeticion) esperan
        # a la siguiente vuelta; las nuevas de verdad se envian ya
        fresh = []
        for tr in batch:
            if tr["id"] in prev and prev[0] != tr["id"]:
                if tr["id"] not in unstable:
                    st["hold"].append({"track": tr, "over": prev[0]})
            else:
                fresh.append(tr)
        st["unstable"] = unstable
        batch = sorted(confirmed + fresh, key=lambda x: x["ts"])
        if batch:
            st["last_ts"] = max([st.get("last_ts", 0)] + [x["ts"] for x in batch])
        st["pending"] = (st["pending"] + batch)[-500:]

        sent = 0
        # Last.fm no acepta scrobbles de hace mas de 14 dias
        st["pending"] = [p for p in st["pending"] if now - p["ts"] < 13 * 86400]
        try:
            while st["pending"]:
                chunk = st["pending"][:50]
                ok, ignored = scrobble_batch(cfg, chunk)
                st["pending"] = st["pending"][50:]
                sent += ok
                day = time.strftime("%Y-%m-%d")
                st["days"][day] = st["days"].get(day, 0) + ok
                st["recent"] = (st["recent"] + [{"artist": c["artist"], "title": c["title"],
                                                 "ts": c["ts"]} for c in chunk])[-20:]
                if ignored:
                    log.info("scrobbler: Last.fm ignoro %d", ignored)
            if plays and not skip_reason(by_id[plays[0]]):
                newest = by_id[plays[0]]
                lf_call("track.updateNowPlaying", cfg, artist=newest["artist"],
                        track=newest["title"], **({"album": newest["album"]} if newest["album"] else {}))
            st.pop("last_error", None)
        except LastfmError as e:
            st["last_error"] = str(e)[:200]
            if e.code in (4, 9, 10, 14, 26) and alert:   # sesion/clave invalida o revocada
                alert("lastfm-auth", f"🎧 Last.fm rechaza la sesión del scrobbler ({e}).\n\n"
                      "Vuelve a autorizarlo con /lastfm.", 12 * 3600)
            log.info("scrobbler: %s (quedan %d pendientes)", e, len(st["pending"]))
        except requests.RequestException as e:
            st["last_error"] = f"red: {e}"[:200]
        st["days"] = dict(sorted(st["days"].items())[-30:])
        st["last_poll"] = now
        save(STATE_FILE, st)
        if sent:
            log.info("scrobbler: %d enviadas", sent)
        return sent


def loop(alert):
    time.sleep(30)
    errors = 0
    while True:
        try:
            poll_once(alert)
            errors = 0
        except Exception as e:
            errors += 1
            log.info("scrobbler: %s", e)
        # Si algo falla, esperar mas (hasta ~30 min) para no insistir
        time.sleep(EVERY * min(2 ** errors, 10))


def set_paused(paused):
    with lock:
        st = state()
        st["paused"] = paused
        save(STATE_FILE, st)


def status_text():
    st, cfg = state(), lastfm()
    lines = ["🎧 <b>Scrobbler YouTube Music → Last.fm</b>"]
    lines.append(("✅" if YTM_COOKIES.exists() else "❌") + " Sesión de YouTube Music"
                 + ("" if YTM_COOKIES.exists() else ": mándame el cookies.txt de music.youtube.com"))
    if cfg.get("session_key"):
        lines.append(f"✅ Last.fm: {html.escape(str(cfg.get('user')))}")
    elif cfg.get("token"):
        lines.append("⏳ Last.fm: falta autorizar el enlace y mandar /lastfm listo")
    else:
        lines.append("❌ Last.fm: /lastfm API_KEY SECRET")
    if ready():
        lines.append("⏸️ En pausa" if st["paused"] else f"▶️ Activo (cada {EVERY // 60} min)")
    today = st["days"].get(time.strftime("%Y-%m-%d"), 0)
    lines.append(f"Hoy: {today} · pendientes: {len(st['pending'])}")
    if st.get("last_poll"):
        lines.append("Última consulta: " + time.strftime("%H:%M", time.localtime(st["last_poll"])))
    if st.get("last_error"):
        lines.append(f"⚠️ {html.escape(st['last_error'])}")
    if st["recent"]:
        lines.append("\nÚltimas:")
        for r in reversed(st["recent"][-5:]):
            lines.append(f"• {time.strftime('%H:%M', time.localtime(r['ts']))} "
                         f"{html.escape(r['artist'])} – {html.escape(r['title'])}")
    if st.get("skipped"):
        lines.append(f"\nNo contadas (podcasts o más de {MAX_LEN // 60} min):")
        for r in reversed(st["skipped"][-3:]):
            lines.append(f"• {time.strftime('%H:%M', time.localtime(r['ts']))} "
                         f"{html.escape(r['title'])} ({html.escape(r['why'])})")
    return "\n".join(lines)


def fetch_likes(limit=50):
    """[{id, title, artist}] de «Canciones que me gustan», de mas nueva a mas vieja."""
    out = []
    for t in ytm_client().get_liked_songs(limit=limit).get("tracks", []):
        if t.get("videoId"):
            out.append({"id": t["videoId"], "title": t.get("title") or "",
                        "artist": ", ".join(a["name"] for a in t.get("artists") or []
                                            if a.get("name"))})
    return out
