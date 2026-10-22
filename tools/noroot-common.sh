# Shared by the tools/noroot-*.sh scripts (loaded with `source`). Reads ../config.sh.
# NO-ROOT mode talks to Termux over SSH (port 8022), not adb. See docs/*/12-*.md.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/config.sh" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/config.sh"
else
  echo "Missing config.sh -- copy config.example.sh to config.sh and edit it." >&2
  exit 1
fi
H="${NOROOT_SSH:-phone}"          # ssh host alias of the phone (see config.example.sh)
CONTAINER="${CONTAINER:-bot}"
CT='$PREFIX/var/lib/proot-distro/containers/'"$CONTAINER"'/rootfs'   # $PREFIX is expanded on the phone

# Run a script (stdin) on the phone, inside Termux
ph() { ssh -o BatchMode=yes -o ConnectTimeout=15 "$H" "$@"; }

need_phone() {
  ph 'echo ok' >/dev/null 2>&1 || {
    echo "Cannot reach the phone over SSH as '$H'."
    echo "Check: Termux is open/running, sshd is up (run 'sshd' in Termux), the ~/.ssh/config"
    echo "entry (docs/*/12-*.md, step 3) and that the phone is on the same network."
    exit 1
  }
}
