"""Plugin opcional: convertir un vídeo/GIF en sticker de vídeo de Telegram.

Comando (cualquier usuario autorizado): /sticker [emoji], en el pie de un vídeo o
respondiendo a uno. Crea el pack del usuario la primera vez (necesita ffmpeg con VP9).
"""
import json
import shutil
import time
from pathlib import Path

import _stickers as stickers


def video_of(m):
    if not m:
        return None
    doc = m.get("document") or {}
    return (m.get("video") or m.get("animation") or m.get("video_note")
            or (doc if doc.get("mime_type", "").startswith("video/") else None))


def setup(api):
    TOKEN, tg, http, log = api.TOKEN, api.tg, api.http, api.log

    def command(msg, chat, user, arg):
        media = video_of(msg) or video_of(msg.get("reply_to_message"))
        if not media:
            api.say(chat, "Uso: responde a un vídeo (o GIF) con /sticker 😎, o mándalo con "
                          "ese texto como pie. Uso los primeros 3 segundos.",
                    reply_to=msg["message_id"])
            return
        if media.get("file_size", 0) > stickers.MAX_INPUT:
            api.say(chat, "🎨 Ese vídeo pasa de 20 MB y Telegram no me deja bajarlo; "
                          "mándame un recorte más corto.", reply_to=msg["message_id"])
            return
        emoji = arg.split()[0] if arg else "🎬"
        uid = user["id"]
        # El nombre corto (el del enlace) tiene que acabar en _by_<usuario del bot>
        owner, _ = api.load_owners()
        name = f"Stickers{'' if uid == owner else f'_{uid}'}_by_{api.BOT['username']}"
        status = api.say(chat, "🎨 Haciendo el sticker…", reply_to=msg["message_id"])
        d = api.JOBS / f"stk_{abs(chat)}_{msg['message_id']}"
        d.mkdir(parents=True, exist_ok=True)
        try:
            path = tg("getFile", file_id=media["file_id"])["file_path"]
            src = d / ("in" + (Path(path).suffix or ".mp4"))
            r = http.get(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=120)
            r.raise_for_status()
            src.write_bytes(r.content)
            t0 = time.time()
            out = stickers.convert(src, d / "sticker.webm")
            log.info("sticker %.0f KB en %.0fs", out.stat().st_size / 1024, time.time() - t0)
            try:
                tg("getStickerSet", name=name)
                exists = True
            except api.TelegramError:
                exists = False
            item = {"sticker": "attach://s", "format": "video", "emoji_list": [emoji]}
            bot_name = api.BOT.get("first_name") or "Bot"
            with out.open("rb") as fh:
                files = {"s": ("sticker.webm", fh, "video/webm")}
                if exists:
                    tg("addStickerToSet", files=files, user_id=uid, name=name,
                       sticker=json.dumps(item))
                else:
                    title = f"Stickers de {bot_name}" if uid == owner else \
                        f"Stickers de {bot_name} · {user.get('first_name') or uid}"[:64]
                    tg("createNewStickerSet", files=files, user_id=uid, name=name,
                       title=title, stickers=json.dumps([item]))
            pack = tg("getStickerSet", name=name)["stickers"]
            tg("sendSticker", chat_id=chat, sticker=pack[-1]["file_id"])
            api.bump("stickers")
            api.edit(chat, status, f"✅ {'Añadido a' if exists else 'Creado'} tu pack "
                                   f"({len(pack)} sticker{'s' if len(pack) != 1 else ''}): "
                                   f"https://t.me/addstickers/{name}")
        except stickers.StickerError as e:
            api.edit(chat, status, f"🎨 {e}")
        except api.TelegramError as e:
            hint = (" (el primer dato tiene que ser un emoji, p.ej. /sticker 😎)"
                    if "EMOJI" in str(e).upper() else "")
            log.info("sticker: %s", e)
            api.edit(chat, status,
                     f"❌ Telegram no lo aceptó: {str(e).replace(TOKEN, '…')}{hint}")
        except Exception as e:
            log.exception("sticker")
            api.edit(chat, status,
                     f"❌ Error haciendo el sticker: {str(e).replace(TOKEN, '…')}")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    return {
        "commands": {"sticker": {
            "fn": command, "owner": False, "anywhere": True,
            "help": "/sticker <i>emoji</i> – respondiendo a un vídeo o GIF: lo convierte en "
                    "sticker de vídeo (3 s) y lo añade a tu pack",
            "menu": "Vídeo → sticker de vídeo en tu pack"}},
        "about": ["• Convierte vídeos en stickers animados de Telegram"],
    }
