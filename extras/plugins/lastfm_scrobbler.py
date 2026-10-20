"""Plugin opcional: scrobbler de YouTube Music a Last.fm.

Comandos (solo el dueño, por privado): /scrobble [pausa|reanudar|probar] y /lastfm.
Detalles y puesta en marcha en _scrobbler.py y docs/*/09-plugins.md.
Es el EJEMPLO de plugin más completo: comandos, bucle en segundo plano, comprobación
para /salud y recepción de un archivo (.txt de cookies) que manda el dueño.
"""
import time

import _scrobbler as scrobbler


def setup(api):
    say, delete = api.say, api.delete

    def command(msg, chat, user, arg):
        cmd = msg["text"].split()[0].split("@")[0].lower() if msg.get("text") else "/scrobble"
        a = arg.split()
        try:
            if cmd == "/lastfm" and len(a) == 2:
                delete(chat, msg["message_id"])     # la clave es un secreto: fuera del chat
                url = scrobbler.auth_start(a[0], a[1])
                say(chat, "🔑 Clave de Last.fm guardada (borré tu mensaje).\n\n"
                          f"1. Abre este enlace y pulsa «Yes, allow access»:\n{url}\n"
                          "2. Luego mándame: /lastfm listo")
            elif cmd == "/lastfm" and a[:1] == ["listo"]:
                name = scrobbler.auth_finish()
                say(chat, f"✅ Last.fm conectado como {name}.\n\n" + scrobbler.status_text(),
                    parse_mode="HTML")
            elif cmd == "/lastfm":
                say(chat, "Uso: /lastfm API_KEY SECRET (de last.fm/api/accounts), "
                          "y después /lastfm listo")
            elif a[:1] == ["pausa"]:
                scrobbler.set_paused(True)
                say(chat, "⏸️ Scrobbler en pausa.")
            elif a[:1] == ["reanudar"]:
                scrobbler.set_paused(False)
                say(chat, "▶️ Scrobbler activo.")
            elif a[:1] == ["probar"]:
                n = scrobbler.poll_once(api.alert)
                say(chat, f"🔄 Consulta hecha: {n} nueva(s).\n\n" + scrobbler.status_text(),
                    parse_mode="HTML")
            else:
                say(chat, scrobbler.status_text(), parse_mode="HTML")
        except Exception as e:
            api.log.exception("scrobble_command")
            say(chat, f"❌ {e}")

    def health():
        st = scrobbler.state()
        if not scrobbler.ready():
            return api._check("Scrobbler", None, "sin configurar")
        age = time.time() - st.get("last_poll", 0)
        ok = None if st["paused"] else (age < scrobbler.EVERY * 3 and not st.get("last_error"))
        return api._check("Scrobbler", ok or (None if st["paused"] else False),
                          "en pausa" if st["paused"] else
                          f"última consulta hace {api.health.ago(age)}"
                          + (f", error: {api.html.escape(st['last_error'])}"
                             if st.get("last_error") else ""))

    def cookies(msg, doc, text):
        """Cookies de music.youtube.com para el scrobbler: se guardan aparte para que
        el descargador nunca use la cuenta principal."""
        if "youtube" not in doc.get("file_name", "").lower():
            return False
        chat = msg["chat"]["id"]
        _, pairs = scrobbler.cookie_header(text)
        if "__Secure-3PAPISID" not in pairs:
            say(chat, "❌ A ese cookies.txt le falta la sesión de YouTube (__Secure-3PAPISID). "
                      "Expórtalo estando en music.youtube.com con tu cuenta iniciada.")
            return True
        scrobbler.YTM_COOKIES.write_text(text)
        scrobbler.YTM_COOKIES.chmod(0o600)
        delete(chat, msg["message_id"])
        api.log.info("cookies de YouTube Music actualizadas")
        api.health.event("cookies", "sesión de YouTube Music renovada")
        try:
            last = scrobbler.fetch_history()[:1]
            song = f"«{last[0]['artist']} – {last[0]['title']}»" if last else "(historial vacío)"
            say(chat, f"🎧 Sesión de YouTube Music guardada (borré tu mensaje).\n"
                      f"Lo último que escuchaste: {song}\n\n" + scrobbler.status_text(),
                parse_mode="HTML")
        except Exception as e:
            say(chat, f"⚠️ Guardé las cookies, pero YouTube Music no me deja leer el "
                      f"historial: {e}")
        return True

    return {
        "commands": {
            "scrobble": {"fn": command,
                         "help": "/scrobble – scrobbler de YouTube Music a Last.fm "
                                 "(<i>pausa</i>, <i>reanudar</i>, <i>probar</i>)",
                         "menu": "Scrobbler YouTube Music → Last.fm"},
            "lastfm": {"fn": command,
                       "help": "/lastfm – conectar Last.fm (<i>API_KEY SECRET</i>, luego "
                               "<i>listo</i>)",
                       "menu": "Conectar Last.fm"},
        },
        "health": [health],
        "loops": [lambda: scrobbler.loop(api.alert)],
        "documents": [cookies],
        "about": ["• Lleva a Last.fm todo lo que se escucha en YouTube Music"],
    }
