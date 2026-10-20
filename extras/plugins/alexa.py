"""Plugin opcional: que las Alexa de casa digan un texto (vía Voice Monkey).

Comando (solo el dueño): /alexa [@altavoz] texto
Configuración: /opt/bot/voicemonkey.json  (ver _alexa.py). Es un EJEMPLO de plugin
sencillo: un comando que llama a una API web.
"""
import _alexa as alexa


def setup(api):
    def command(msg, chat, user, arg):
        try:
            name = None
            if arg.startswith("@"):
                name, _, arg = arg[1:].partition(" ")
            if not arg.strip():
                devs = ", ".join(d["name"] for d in alexa.devices())
                api.say(chat, f"Uso: /alexa texto (o /alexa @altavoz texto)\nAltavoces: {devs}")
                return
            where = alexa.speak(arg, name)
            api.log.info("alexa %s: %d caracteres", where, len(arg))
            api.say(chat, f"🔊 Dicho en {where}.")
        except alexa.AlexaError as e:
            api.say(chat, f"🔊 {e}")
        except Exception as e:
            api.log.exception("alexa")
            api.say(chat, f"❌ Error con Alexa: {e}")

    return {
        "commands": {"alexa": {
            "fn": command, "anywhere": True,
            "help": "/alexa [<i>@altavoz</i>] <i>texto</i> – lo dice la Alexa de casa",
            "menu": "Que lo diga la Alexa de casa"}},
        "about": ["• Hace hablar a las Alexa de la casa"],
    }
