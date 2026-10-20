#!/bin/bash
# OPTIONAL. Runs INSIDE the Debian chroot (tools/install.sh voice). Installs speech-to-text so
# the bot can transcribe voice notes on the phone itself:
#   - whisper.cpp (compiled here, with the flags for YOUR cpu)  -> /opt/stt/whisper.cpp
#   - a Whisper model                                           -> /opt/stt/ggml-<model>.bin
#   - Vosk + a small model, for a quick first draft             -> /opt/stt/vosk
#
#   WHISPER_MODEL=base-q5_1   base-q5_1 (60 MB) is a good size for an old 2-core phone;
#                             small-q5_1 (190 MB) is better but ~3x slower. tiny-q5_1 is faster.
#   VOSK_MODEL_URL=...        default: Spanish small model. Pick yours from
#                             https://alphacephei.com/vosk/models  and set the same language
#                             in /opt/bot/stt.json  {"lang": "en"}
#   SKIP_VOSK=1               no Vosk draft (Whisper only)
#
# Compiling whisper.cpp takes ~10+ min on a 2-core phone (3 min on 8 cores). Best effort:
# derived from a working install; if the build fails, read the cmake error and adapt the flags.
set -e
WHISPER_MODEL=${WHISPER_MODEL:-base-q5_1}
VOSK_MODEL_URL=${VOSK_MODEL_URL:-https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip}
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends git cmake g++ make patchelf unzip wget ca-certificates
mkdir -p /opt/stt && cd /opt/stt

# ---- whisper.cpp -----------------------------------------------------------------
[ -d whisper.cpp ] || git clone --depth 1 https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
case "$(uname -m)" in
  armv7l|armv8l) FLAGS="-mfpu=neon-vfpv4 -mfloat-abi=hard" ;;   # add -mcpu=cortex-aNN for your core
  *)             FLAGS="" ;;
esac
cmake -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="$FLAGS" -DCMAKE_CXX_FLAGS="$FLAGS" \
      -DWHISPER_BUILD_TESTS=OFF
cmake --build build -j"$(nproc)" --target whisper-cli
test -x build/bin/whisper-cli
cd /opt/stt
[ -f "ggml-$WHISPER_MODEL.bin" ] || wget -q --show-progress -O "ggml-$WHISPER_MODEL.bin" \
  "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$WHISPER_MODEL.bin"

# ---- Vosk (quick draft) ----------------------------------------------------------
if [ -z "$SKIP_VOSK" ]; then
  /opt/bot/venv/bin/pip install --no-cache-dir vosk
  # glibc 2.41+ refuses libraries that ask for an executable stack
  LIB="$(/opt/bot/venv/bin/python3 -c 'import vosk,os;print(os.path.join(os.path.dirname(vosk.__file__),"libvosk.so"))')"
  patchelf --clear-execstack "$LIB" || true
  if [ ! -d vosk ]; then
    wget -q --show-progress -O vosk.zip "$VOSK_MODEL_URL"
    unzip -q vosk.zip && rm vosk.zip
    mv vosk-model-* vosk
  fi
fi
echo "OK. In Telegram: /transcribir (owner) shows the engine in use."
