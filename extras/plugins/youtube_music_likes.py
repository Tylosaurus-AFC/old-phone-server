"""Plugin opcional: las canciones a las que das «me gusta» en YouTube Music se bajan solas
y se publican en un canal de Telegram (o en tu privado).

Comando (solo el dueño, por privado): /likes [pausa|reanudar|bajar N|todos [rehacer]|parar]
Necesita el plugin `lastfm_scrobbler` instalado y con las cookies de music.youtube.com
(comparten la sesión: _scrobbler.YTM_COOKIES). El canal de destino se conecta con /canal:
añade el bot como administrador de un canal cuyo nombre incluya «canciones» (o /canal canciones N).

Cada canción se baja como audio m4a con portada cuadrada y etiquetas (modo "song" del núcleo)
y la cola masiva (/likes todos) se mete de a poco para no atrasar los enlaces normales.
Es un EJEMPLO de plugin que usa colas de trabajo, canales de Telegram y varios hilos.
"""
import json
import threading
import time

import _scrobbler as scrobbler

LIKES_EVERY = 5 * 60
lock = threading.Lock()


def setup(api):
    FILE = api.BASE / "likes.json"
    log, say, edit, health = api.log, api.say, api.edit, api.health

    def state():
        try:
            return json.loads(FILE.read_text())
        except (OSError, ValueError):
            return {}

    def save(st):
        FILE.write_text(json.dumps(st))

    def targets(owner):
        pc = api.role_channel("canciones")
        return [pc["id"]] if pc else [owner]

    def enqueue(owner, tr, bulk=False):
        api.jobs.put({"chat": owner, "msg_id": None, "only_link": False, "mode": "song",
                      "url": f"https://music.youtube.com/watch?v={tr['id']}", "sender": "",
                      "targets": targets(owner), "quiet": True, **({"bulk": True} if bulk else {})})

    def check():
        """Canciones nuevas en «Canciones que me gustan» de YouTube Music -> descargar."""
        owner, _ = api.load_owners()
        if not owner or not scrobbler.YTM_COOKIES.exists():
            return
        with lock:
            st = state()
            likes = scrobbler.fetch_likes(50)
            ids = [t["id"] for t in likes]
            if not st.get("init"):                    # primera vez: lo que ya tenias no se baja
                st.update(init=True, seen=ids)
            else:
                new = [t for t in reversed(likes) if t["id"] not in st.get("seen", [])]
                if len(new) > 10:                     # algo raro (estado perdido): no bajar de golpe
                    api.alert("likes-many", f"❤️ Veo {len(new)} likes nuevos de golpe; no los bajo "
                              "solos. Si los quieres: /likes bajar N", 6 * 3600)
                elif not st.get("paused"):
                    for t in new:
                        log.info("like nuevo: %s - %s", t["artist"], t["title"])
                        enqueue(owner, t)
                st["seen"] = (st.get("seen", []) + [t["id"] for t in new])[-300:]
            save(st)

    def bulk_text(b):
        done = b["ok"] + b["fail"]
        el = time.time() - b["t0"]
        rate = done / (el / 60) if el > 60 and done else 0
        eta = f" · quedan ~{health.ago((b['total'] - done) / rate * 60)}" \
            if rate and done < b["total"] else ""
        return (f"❤️ Likes → canal: {done}/{b['total']} · ✅ {b['ok']} · ❌ {b['fail']}\n"
                f"⏱️ {health.ago(el)}" + (f" · {rate:.1f} canciones/min{eta}" if rate else ""))

    def bulk_done(job, ok, err):
        """Una cancion de la cola masiva termino: contar, y avisar cada tanto o al acabar."""
        owner, _ = api.load_owners()
        with lock:
            st = state()
            b = st.get("bulk")
            if not b:
                return
            b["ok" if ok else "fail"] += 1
            if not ok:
                b["failed"].append([job["url"].split("v=")[-1], (err or "sin detalle")[:80]])
            done = b["ok"] + b["fail"]
            finished = done >= b["total"]
            if finished or done % 15 == 0:
                edit(owner, b.get("msg"), bulk_text(b))
            if finished:
                el = time.time() - b["t0"]
                txt = (f"✅ Cola de likes terminada: {b['ok']} de {b['total']} en "
                       f"{health.ago(el)} ({b['total'] / (el / 60):.1f}/min)")
                if b["failed"]:
                    txt += f"\n❌ {b['fail']} fallaron:\n" + "\n".join(
                        f"• music.youtube.com/watch?v={i} — {e}" for i, e in b["failed"][:15])
                    if len(b["failed"]) > 15:
                        txt += f"\n… y {len(b['failed']) - 15} más"
                say(owner, txt)
                st.pop("bulk", None)
            else:
                st["bulk"] = b
            save(st)

    def feeder():
        """Mete la cola masiva de a poquitos: asi los enlaces que mandes tu no esperan
        detras de mil canciones y un reinicio no pierde nada (la cola vive en likes.json)."""
        while True:
            time.sleep(15)
            try:
                owner, _ = api.load_owners()
                with lock:
                    st = state()
                    backlog = st.get("backlog") or []
                    free = 2 - api.jobs.qsize()
                    if not owner or not backlog or free <= 0:
                        continue
                    for t in backlog[:free]:
                        enqueue(owner, t, bulk=True)
                    st["backlog"] = backlog[free:]
                    save(st)
            except Exception:
                log.exception("likes_feeder")

    def bulk_start(chat, only_new=True):  # only_new=False: rehacer todo
        """Todos los likes de la cuenta -> cola masiva (de la mas vieja a la mas nueva)."""
        likes = scrobbler.fetch_likes(None)
        todo = [t for t in reversed(likes)
                if not only_new or not api.cache_get(
                    api.cache_key(f"https://music.youtube.com/watch?v={t['id']}", "song"))]
        with lock:
            st = state()
            if st.get("bulk"):
                say(chat, "❤️ Ya hay una cola en marcha (/likes para ver cómo va, /likes parar).")
                return
            if not todo:
                say(chat, f"❤️ Los {len(likes)} likes ya están en el canal.")
                return
            mid = say(chat, f"❤️ Encolando {len(todo)} canciones de {len(likes)} likes "
                            f"(las {len(likes) - len(todo)} que ya estaban en el canal se "
                            "saltan)…")
            st["backlog"] = [{"id": t["id"], "title": t["title"], "artist": t["artist"]}
                             for t in todo]
            st["bulk"] = {"total": len(todo), "ok": 0, "fail": 0, "t0": time.time(), "msg": mid,
                          "failed": []}
            save(st)

    def loop():
        time.sleep(90)
        fails = 0
        while True:
            try:
                check()
                fails = 0
            except Exception as e:
                fails += 1
                log.info("likes: %s", e)
                if fails == 6:                        # ~30 min seguidos
                    api.alert("likes-fail", f"❤️ No puedo leer tus likes de YouTube Music: {e}\n"
                              "Puede que las cookies de YouTube Music hayan caducado.", 12 * 3600)
            time.sleep(LIKES_EVERY)

    def safe(chat, fn, *a):
        try:
            fn(*a)
        except Exception as e:
            log.exception("likes")
            say(chat, f"❌ {e}")

    def command(msg, chat, user, arg):
        owner, _ = api.load_owners()
        words = arg.lower().split()
        st = state()
        pc = api.role_channel("canciones")
        if words[:1] in (["pausa"], ["reanudar"]):
            with lock:
                st = state()
                st["paused"] = words[0] == "pausa"
                save(st)
            say(chat, "⏸️ Likes en pausa: no bajaré los nuevos." if st["paused"]
                else "▶️ Likes activados otra vez.")
        elif words[:1] in (["todos"], ["todo"]):
            threading.Thread(target=lambda: safe(chat, bulk_start, chat, "rehacer" not in words),
                             daemon=True).start()
        elif words[:1] == ["parar"]:
            with lock:
                st = state()
                left = len(st.pop("backlog", []))
                b = st.pop("bulk", None)
                save(st)
            say(chat, f"⏹️ Cola detenida: {left} canciones sin empezar descartadas"
                      + (f" ({b['ok']} ya enviadas)." if b else "."))
        elif words[:1] == ["bajar"] and len(words) == 2 and words[1].isdigit():
            n = max(1, min(int(words[1]), 30))
            try:
                tracks = scrobbler.fetch_likes(n)
            except Exception as e:
                say(chat, f"❌ {e}")
                return
            for t in reversed(tracks):
                enqueue(owner, t)
            say(chat, f"❤️ Bajando tus últimos {len(tracks)} likes"
                      + (f" al canal «{pc['title']}»." if pc
                         else " (sin canal de canciones: aquí)."))
        else:
            say(chat, "❤️ Likes de YouTube Music → "
                + (f"canal «{pc['title']}»" if pc
                   else "tu privado (aún no hay canal de canciones: /canal)")
                + f"\nEstado: {'en pausa' if st.get('paused') else 'activo'} · revisión cada "
                  f"{LIKES_EVERY // 60} min · calidad: la mejor que da YouTube (m4a, sin "
                  "recodificar)"
                + (f"\n\n{bulk_text(st['bulk'])}" if st.get("bulk") else "")
                + "\n\n/likes pausa · /likes reanudar · /likes bajar N (tus últimos N) · "
                  "/likes todos [rehacer] (toda tu lista; rehacer = también las ya enviadas) · "
                  "/likes parar (cancela la cola)")

    return {
        "commands": {"likes": {
            "fn": command, "thread": False,
            "help": "/likes – los likes de YouTube Music se bajan solos al canal de canciones "
                    "(<i>pausa</i>, <i>reanudar</i>, <i>bajar N</i>, <i>todos</i>, <i>parar</i>)",
            "menu": "Likes de YouTube Music → canal"}},
        "loops": [loop, feeder],
        "job_done": [bulk_done],
        "channel_roles": {"canciones": "las canciones a las que des like en YouTube Music"},
        "about": ["• Baja a un canal las canciones a las que das like en YouTube Music"],
    }
