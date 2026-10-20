"""Transcripcion de notas de voz en el propio movil (sin mandar audio a nadie).

Motores, de mejor a peor:
  whisper.cpp  /opt/stt/whisper.cpp/build/bin/whisper-cli + /opt/stt/ggml-<modelo>.bin
  Vosk         /opt/stt/vosk (modelo pequeño del idioma), mas rapido pero peor

El idioma se elige en /opt/bot/stt.json con {"lang": "es"} (por defecto "es"; usa el
codigo de Whisper: en, pt, fr...). Los modelos de Vosk: https://alphacephei.com/vosk/models
"""
import json
import logging
import os
import subprocess
import time
import wave
from pathlib import Path

STT = Path("/opt/stt")
WHISPER_BIN = STT / "whisper.cpp" / "build" / "bin" / "whisper-cli"
WHISPER_MODEL = "base-q5_1"           # se cambia por /transcribir modelo
VOSK_MODEL = next((p for p in (STT / "vosk", STT / "vosk-es") if p.exists()), STT / "vosk")
THREADS = min(8, os.cpu_count() or 2)   # con 2 nucleos, 2 hilos; con 8, los 8 (lo mas rapido medido)
CONFIG = Path("/opt/bot/stt.json")    # {"model": ..., "lang": "es", "off": [chat_ids]}
log = logging.getLogger("bot")
_vosk = {}


def config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg))


def whisper_model_path():
    return STT / f"ggml-{config().get('model', WHISPER_MODEL)}.bin"


def engine():
    if WHISPER_BIN.exists() and whisper_model_path().exists():
        return f"whisper {config().get('model', WHISPER_MODEL)}"
    if VOSK_MODEL.exists():
        return "vosk"
    return None


def to_wav(src: Path, dst: Path):
    """Cualquier audio/video -> WAV 16 kHz mono (lo que piden los dos motores)."""
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vn",
                        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)],
                       capture_output=True, text=True, timeout=300)
    if p.returncode:
        raise RuntimeError(f"no pude convertir el audio: {p.stderr[-200:]}")
    with wave.open(str(dst)) as w:
        return w.getnframes() / w.getframerate()


def _whisper(wav: Path, timeout):
    p = subprocess.run([str(WHISPER_BIN), "-m", str(whisper_model_path()), "-f", str(wav),
                        "-l", config().get("lang", "es"), "-t", str(THREADS), "-nt", "-np"],
                       capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"whisper: {p.stderr[-200:]}")
    return " ".join(l.strip() for l in p.stdout.splitlines() if l.strip())


def _vosk_text(wav: Path):
    from vosk import KaldiRecognizer, Model, SetLogLevel
    SetLogLevel(-1)
    if "model" not in _vosk:
        _vosk["model"] = Model(str(VOSK_MODEL))
    rec = KaldiRecognizer(_vosk["model"], 16000)
    parts = []
    with wave.open(str(wav)) as w:
        while True:
            data = w.readframes(8000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                parts.append(json.loads(rec.Result()).get("text", ""))
    parts.append(json.loads(rec.FinalResult()).get("text", ""))
    text = " ".join(p for p in parts if p).strip()
    return (text[:1].upper() + text[1:]) if text else ""


def transcribe(src: Path, on_draft=None):
    """-> (texto, segundos de audio, segundos que tardo, motor).

    Si hay Whisper y Vosk: Vosk saca un borrador en segundos (on_draft(texto)) y
    Whisper, ~4x la duracion del audio en un movil de 2 nucleos, da la version buena."""
    eng = engine()
    if not eng:
        raise RuntimeError("no hay motor de transcripción instalado")
    wav = src.with_suffix(".16k.wav")
    try:
        secs = to_wav(src, wav)
        t = time.time()
        if not eng.startswith("whisper"):
            return _vosk_text(wav), secs, time.time() - t, eng
        draft = ""
        if on_draft and VOSK_MODEL.exists():
            try:
                draft = _vosk_text(wav)
                if draft:
                    on_draft(draft)
            except Exception as e:
                log.info("stt borrador vosk: %s", e)
        try:
            text = _whisper(wav, timeout=max(600, int(secs * 30)))
        except Exception as e:
            if not draft:
                raise
            log.info("stt whisper fallo, me quedo con vosk: %s", e)
            return draft, secs, time.time() - t, "vosk"
        return text, secs, time.time() - t, eng
    finally:
        wav.unlink(missing_ok=True)


def enabled(chat_id):
    return chat_id not in config().get("off", [])


def set_enabled(chat_id, on):
    cfg = config()
    off = set(cfg.get("off", []))
    (off.discard if on else off.add)(chat_id)
    cfg["off"] = sorted(off)
    save_config(cfg)
