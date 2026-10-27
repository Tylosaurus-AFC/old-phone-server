# Shared by the scripts in tools/ (loaded with `source`). Reads ../config.sh.
export MSYS_NO_PATHCONV=1      # Git Bash on Windows: do not mangle /data/... paths

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/config.sh" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/config.sh"
else
  echo "Missing $ROOT/config.sh -- create it from the example and edit it:" >&2
  echo "  cp \"$ROOT/config.example.sh\" \"$ROOT/config.sh\"" >&2
  exit 1
fi
DEBIAN=/data/debian
TMP=/data/local/tmp/phonesrv

a() { "$ADB" -s "$SERIAL" "$@"; }

# adb.exe is a Windows program: it needs C:/... paths
winpath() { cygpath -m "$1" 2>/dev/null || echo "$1"; }

# Settings that cannot work, found before talking to the phone (clearer than a failed adb
# call later). Unknown ROOT_MODE/ARCH only warn: other values keep their old behaviour.
check_config() {
  local bad=0
  if ! command -v "${ADB:-}" >/dev/null 2>&1; then
    echo "adb not found (ADB=${ADB:-} in config.sh). Install Android platform-tools, or set ADB to" >&2
    echo "the full path of adb (adb.exe on Windows), e.g. ADB=/c/.../platform-tools/adb.exe" >&2
    bad=1
  fi
  if [ -z "${SERIAL:-}" ] && [ -z "${USB_SERIAL:-}" ] && [ -z "${PHONE_IP:-}" ]; then
    echo "No way to reach the phone: set USB_SERIAL (see 'adb devices') or PHONE_IP in config.sh." >&2
    bad=1
  fi
  case "${ROOT_MODE:-su}" in
    su|adbroot) ;;
    *) echo "Warning: ROOT_MODE=$ROOT_MODE is not 'su' or 'adbroot'; using su." >&2 ;;
  esac
  case "${ARCH:-armhf}" in
    armhf|arm64) ;;
    *) echo "Warning: ARCH=$ARCH is not 'armhf' or 'arm64' (see config.example.sh)." >&2 ;;
  esac
  [ "$bad" = 0 ] || exit 1
}

# Use USB if the phone is plugged in; otherwise connect over Wi-Fi. SERIAL=... forces one.
need_phone() {
  check_config
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
