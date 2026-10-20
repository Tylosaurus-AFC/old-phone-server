# Shared by the scripts in tools/ (loaded with `source`). Reads ../config.sh.
export MSYS_NO_PATHCONV=1      # Git Bash on Windows: do not mangle /data/... paths

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/config.sh" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/config.sh"
else
  echo "Missing config.sh -- copy config.example.sh to config.sh and edit it." >&2
  exit 1
fi
DEBIAN=/data/debian
TMP=/data/local/tmp/phonesrv

a() { "$ADB" -s "$SERIAL" "$@"; }

# adb.exe is a Windows program: it needs C:/... paths
winpath() { cygpath -m "$1" 2>/dev/null || echo "$1"; }

# Use USB if the phone is plugged in; otherwise connect over Wi-Fi. SERIAL=... forces one.
need_phone() {
  if [ -n "${SERIAL:-}" ]; then
    :
  elif [ -n "$USB_SERIAL" ] && "$ADB" -s "$USB_SERIAL" get-state >/dev/null 2>&1; then
    SERIAL="$USB_SERIAL"
  else
    SERIAL="$PHONE_IP:5555"
    # A stale ("offline") connection gets in the way: drop it and retry a few times
    for _ in 1 2 3; do
      a get-state >/dev/null 2>&1 && break
      "$ADB" disconnect "$SERIAL" >/dev/null 2>&1 || true
      "$ADB" connect "$SERIAL" >/dev/null 2>&1 || true
      sleep 2
    done
  fi
  a get-state >/dev/null 2>&1 || {
    echo "Cannot see the phone: not over USB (${USB_SERIAL:-no USB_SERIAL set}) nor Wi-Fi ($PHONE_IP:5555)."
    echo "If the bot still answers in Telegram:"
    echo "  - if 'ping $PHONE_IP' answers: send /reiniciar adb (adb serves ONE network"
    echo "    connection at a time and hangs if one drops)"
    echo "  - if it does not answer: /reiniciar wifi (then /reiniciar confirmar)"
    exit 1
  }
  [ "$ROOT_MODE" = adbroot ] && { a root >/dev/null 2>&1 || true; sleep 2; a get-state >/dev/null 2>&1 || true; }
  echo "Connected to $SERIAL"
}

# Run, as root on the phone, the script that arrives on stdin. It is pushed as a file to
# avoid fighting the quoting of bash -> adb -> su -> sh.
remote() {
  local f
  f="$(mktemp)"
  cat > "$f"
  a push "$(winpath "$f")" "$TMP.sh" >/dev/null
  rm -f "$f"
  if [ "$ROOT_MODE" = adbroot ]; then
    a shell "sh $TMP.sh; rm -f $TMP.sh"
  else
    a shell "su -c 'sh $TMP.sh; rm -f $TMP.sh'"
  fi
}
