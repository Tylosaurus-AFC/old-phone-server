"""Plugin opcional: fotos y clips de un grabador de cámaras Dahua (o compatible).

Comandos (solo el dueño): /foto_camaras [cámara] y /clip_camaras cámara [fecha] inicio fin.
Sin nada detrás, ofrecen botones: elegir cámara (y, para el clip, el tramo hasta ahora).
Configuración: /opt/bot/camaras.json  {"host": "192.168.1.10", "user": "...", "password": "..."}
Es un EJEMPLO de plugin: el protocolo es el CGI de Dahua (ver _camaras.py).
"""
import html
import json
import re
import shutil
import threading
import time

import _camaras as camaras


def setup(api):
    JOBS, log = api.JOBS, api.log

    def cam_buttons(cmd, all_label):
        """Un boton por camara (de dos en dos) y otro para todas."""
        cams = [(f"{n}. {name}", f"{cmd} {n}") for n, name in camaras.channels()]
        return [cams[i:i + 2] for i in range(0, len(cams), 2)] + [[(all_label, f"{cmd} todas")]]

    def acting(action, fn):
        def run(msg, chat, user, arg):
            act = api.ChatAction(chat, action).start()    # «enviando foto/vídeo…»
            try:
                fn(msg, chat, user, arg)
            finally:
                act.stop()
        return run

    def photo(msg, chat, user, arg):
        """Foto actual de una camara, o de todas en un album."""
        d = JOBS / f"cam_{int(time.time() * 1000)}"
        d.mkdir(parents=True, exist_ok=True)
        try:
            if not arg:
                api.say(chat, "📷 ¿Qué cámara?", buttons=cam_buttons("/foto_camaras", "📷 Todas"))
                return
            chans = camaras.channels() if arg.lower() == "todas" else [camaras.resolve(arg)]
            hora = time.strftime("%d/%m %H:%M")
            shots, fails = [], []

            def take(c):
                try:
                    shots.append((c, camaras.snapshot(c[0], d / f"cam{c[0]}.jpg")))
                except Exception as e:
                    fails.append(f"{c[1]}: {e}")

            threads = [threading.Thread(target=take, args=(c,)) for c in chans]
            [t.start() for t in threads]
            [t.join(60) for t in threads]
            shots.sort(key=lambda x: x[0][0])
            if len(shots) == 1:
                (n, name), f = shots[0]
                api.send_file(chat, f, html.escape(f"📷 {name} · {hora}"))
            elif shots:
                files = {f"f{i}": (f.name, f.open("rb"), "image/jpeg")
                         for i, (_, f) in enumerate(shots)}
                media = [{"type": "photo", "media": f"attach://f{i}",
                          "caption": f"📷 {name} · {hora}"}
                         for i, ((_, name), _) in enumerate(shots)]
                try:
                    api.tg("sendMediaGroup", _timeout=300, files=files, chat_id=chat,
                           media=json.dumps(media))
                finally:
                    [fh.close() for _, fh, _ in files.values()]
            if fails:
                api.say(chat, "⚠️ " + "\n".join(fails))
        except camaras.CamError as e:
            api.say(chat, f"📷 {e}")
        except Exception as e:
            log.exception("foto_camaras")
            api.say(chat, f"❌ Error con las cámaras: {e}")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def clip(msg, chat, user, arg):
        """Fragmento grabado: /clip_camaras camara [fecha] inicio fin.
        Sin nada mas: el ultimo minuto de todas las camaras, una detras de otra (el
        grabador entrega mejor un archivo cada vez)."""
        d = JOBS / f"clip_{int(time.time() * 1000)}"
        d.mkdir(parents=True, exist_ok=True)
        status = None
        try:
            toks = arg.split()
            if not toks:
                api.say(chat, "🎬 ¿De qué cámara?",
                        buttons=cam_buttons("/clip_camaras", "🎬 Todas · último minuto"))
                return
            if len(toks) == 1 and toks[0].lower() != "todas":
                n, name = camaras.resolve(toks[0])
                api.say(chat, f"🎬 {name}: ¿qué tramo? (hasta ahora mismo)", buttons=[
                    [(t, f"/clip_camaras {n} -{m}") for t, m in (("Último min", 1), ("5 min", 5), ("15 min", 15))],
                    [(t, f"/clip_camaras {n} -{m}") for t, m in (("30 min", 30), ("1 hora", 60))]])
                return
            if toks[0].lower() == "todas":
                start, end = camaras.last_minute()
                cams = camaras.channels()
            elif len(toks) == 2 and re.fullmatch(r"-\d{1,2}", toks[1]):   # los ultimos N minutos
                end = camaras.last_minute()[1]
                start = end - camaras.dt.timedelta(minutes=min(int(toks[1][1:]), camaras.MAX_CLIP_MIN))
                cams = [camaras.resolve(toks[0])]
            else:
                cam, start, end = camaras.parse_clip(arg)
                cams = [camaras.resolve(cam)]
            rango = f"{start:%d/%m/%Y %H:%M:%S}–{end:%H:%M:%S}"
            for i, (n, name) in enumerate(cams, 1):
                step = f" ({i}/{len(cams)})" if len(cams) > 1 else ""
                status = api.say(chat, f"🎬 Sacando del grabador {name}, {rango}…{step}")
                try:
                    f = camaras.clip(n, start, end, d / f"{name}_{start:%Y%m%d_%H%M%S}.mp4")
                except camaras.CamError as e:
                    if len(cams) == 1:
                        raise
                    api.delete(chat, status)
                    api.say(chat, f"🎬 {name}: {e}")
                    continue
                codec = camaras.video_codec(f)
                cap = html.escape(f"🎬 {name} · {rango}")
                if codec == "hevc":
                    cap += "\n<i>(vídeo H.265: si no se reproduce aquí, descárgalo)</i>"
                api.edit(chat, status,
                         f"📤 Enviando {name}, {f.stat().st_size / 2**20:.1f} MB…{step}")
                api._tl.sent_msgs = []
                api.publish(chat, [f], cap, status)
                log.info("clip camara %s %s (%s, %.1f MB)", n, rango, codec,
                         f.stat().st_size / 2**20)
                api.delete(chat, status)
                # al archivo de N dias (si esta activado; /guardar lo copia al NAS)
                api.archive_put([f], chat, list(api._tl.sent_msgs), None,
                                f"Cámara {name} {start:%Y-%m-%d %H.%M}")
                api._tl.sent_msgs = None
                f.unlink(missing_ok=True)
        except camaras.CamError as e:
            if status:
                api.delete(chat, status)
            api.say(chat, f"🎬 {e}")
        except Exception as e:
            log.exception("clip_camaras")
            api.say(chat, f"❌ Error sacando el clip: {e}")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def health():
        try:
            camaras.config()
        except camaras.CamError:
            return api._check("Cámaras", None, "sin configurar")
        try:
            camaras._http("/cgi-bin/magicBox.cgi?action=getDeviceType", timeout=5)
            return api._check("Cámaras", True, "el grabador responde")
        except Exception as e:
            return api._check("Cámaras", False,
                              f"el grabador no responde ({type(e).__name__})")

    return {
        "commands": {
            "foto_camaras": {
                "fn": acting("upload_photo", photo), "anywhere": True,
                "help": "/foto_camaras [<i>cámara</i>] – foto actual de una cámara (número o "
                        "nombre) o de todas",
                "menu": "Foto actual de las cámaras"},
            "clip_camaras": {
                "fn": acting("upload_video", clip), "anywhere": True,
                "help": "/clip_camaras <i>cámara [fecha] inicio fin</i> – fragmento grabado "
                        "(sin nada más: el último minuto de todas). Ej.: <i>2 14:59 15:02</i> · "
                        "<i>2 ayer 23:50 23:58</i> · <i>patio 17/10 2:59 3:02</i> (máx. 60 min)",
                "menu": "Fragmento grabado de una cámara"},
        },
        "health": [health],
        "about": ["• Ve las cámaras de seguridad de la casa: fotos en vivo y clips de la grabación"],
    }
