"""Subidas de hasta 2 GB por MTProto (Telethon) con el mismo token del bot.

La Bot API por HTTP solo deja subir 50 MB; un bot conectado por MTProto llega a
2000 MB. Necesita /opt/bot/api.txt con dos lineas: api_id y api_hash
(de https://my.telegram.org -> API development tools).
"""
import asyncio
import json
import logging
import subprocess
import threading
from pathlib import Path

import thumbs

BASE = Path("/opt/bot")
API_FILE = BASE / "api.txt"
SESSION = BASE / "mtproto"            # Telethon crea mtproto.session
MAX_BYTES = 1990 * 1024 * 1024
log = logging.getLogger("bot")

_loop = None
_client = None
_lock = threading.Lock()


def _fast_aes():
    """Telethon cifra AES-IGE via ctypes a ~0.7 MB/s en este ARMv7; TgCrypto (C)
    es decenas de veces mas rapido. Se sustituye si esta instalado."""
    try:
        import os
        import tgcrypto
        from telethon.crypto import aes
    except ImportError:
        return

    def enc(plain, key, iv):
        pad = len(plain) % 16
        if pad:
            plain += os.urandom(16 - pad)
        return tgcrypto.ige256_encrypt(plain, key, iv)

    aes.AES.encrypt_ige = staticmethod(enc)
    aes.AES.decrypt_ige = staticmethod(lambda cipher, key, iv: tgcrypto.ige256_decrypt(cipher, key, iv))


PART = 512 * 1024
PARALLEL = 16


async def _upload_parallel(path: Path, progress_cb=None):
    """Como client.upload_file pero con PARALLEL trozos en vuelo a la vez:
    Telethon los sube de uno en uno y espera cada confirmacion (~0.4 MB/s aqui)."""
    import random
    from telethon import types
    from telethon.tl.functions.upload import SaveBigFilePartRequest

    size = path.stat().st_size
    total = (size + PART - 1) // PART
    file_id = random.getrandbits(63)
    sem = asyncio.Semaphore(PARALLEL)
    done = [0]

    with path.open("rb") as fh:
        async def part(i):
            async with sem:
                fh.seek(i * PART)
                data = fh.read(PART)
                for attempt in range(5):
                    try:
                        await _client(SaveBigFilePartRequest(file_id, i, total, data))
                        break
                    except Exception:
                        if attempt == 4:
                            raise
                        await asyncio.sleep(2 * (attempt + 1))
                done[0] += 1
                if progress_cb:
                    progress_cb(done[0] * PART, size)

        await asyncio.gather(*(part(i) for i in range(total)))
    return types.InputFileBig(file_id, total, path.name)


def available():
    return API_FILE.exists()


def _start():
    """Arranca (una vez) un bucle asyncio en su propio hilo con el cliente conectado."""
    global _loop, _client
    with _lock:
        if _client is not None:
            return
        from telethon import TelegramClient
        _fast_aes()
        api_id, api_hash = API_FILE.read_text().split()[:2]
        token = (BASE / "token").read_text().strip()
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True).start()

        async def connect():
            c = TelegramClient(str(SESSION), int(api_id), api_hash, receive_updates=False)
            await c.start(bot_token=token)
            return c

        _client = asyncio.run_coroutine_threadsafe(connect(), _loop).result(120)
        log.info("MTProto conectado")


def _probe(path: Path):
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True)
    try:
        info = json.loads(p.stdout)
        s = info["streams"][0]
        return int(float(info["format"]["duration"])), s["width"], s["height"]
    except Exception:
        return 0, 0, 0


def send(chat_id: int, path: Path, caption_html: str = None, progress=None, reply_to=None,
         as_doc=False):
    """Envia un archivo grande y devuelve el message_id.
    progress(pct) se llama al avanzar la subida."""
    _start()
    from telethon import types

    is_video = not as_doc and path.suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
    attrs, thumb = [], None
    if is_video:
        dur, w, h = _probe(path)
        attrs = [types.DocumentAttributeVideo(duration=dur, w=w, h=h, supports_streaming=True)]
        thumb = thumbs.make(path)

    last = [-10]

    def cb(sent, total):
        pct = int(sent * 100 / total) if total else 0
        if progress and pct >= last[0] + 10:
            last[0] = pct
            try:
                progress(pct)
            except Exception:
                pass

    async def do():
        peer = await _peer(chat_id)
        uploaded = await _upload_parallel(path, cb)
        return await _client.send_file(peer, uploaded, caption=caption_html, parse_mode="html",
                                attributes=attrs or None, thumb=str(thumb) if thumb else None,
                                mime_type="video/mp4" if is_video else None,
                                supports_streaming=is_video, force_document=not is_video,
                                reply_to=reply_to)

    try:
        msg = asyncio.run_coroutine_threadsafe(do(), _loop).result(3600)
        return msg.id   # mismo message_id que ve la Bot API (sirve para copyMessage)
    finally:
        if thumb:
            thumb.unlink(missing_ok=True)


async def _peer(chat_id):
    from telethon import types, utils
    real_id, peer_type = utils.resolve_id(chat_id)
    try:
        return await _client.get_input_entity(peer_type(real_id))
    except ValueError:
        # Un bot puede usar access_hash=0 con chats en los que ya esta
        return {types.PeerUser: lambda: types.InputPeerUser(real_id, 0),
                types.PeerChat: lambda: types.InputPeerChat(real_id),
                types.PeerChannel: lambda: types.InputPeerChannel(real_id, 0)}[peer_type]()


def download(chat_id: int, msg_id: int, dest: Path, timeout=1800):
    """Baja el archivo adjunto de un mensaje. La Bot API solo deja bajar 20 MB;
    por MTProto se llega a 2 GB."""
    _start()

    async def do():
        msg = await _client.get_messages(await _peer(chat_id), ids=msg_id)
        if not msg or not msg.media:
            raise RuntimeError("no encuentro ese archivo")
        return await _client.download_media(msg, file=str(dest))

    return Path(asyncio.run_coroutine_threadsafe(do(), _loop).result(timeout))
