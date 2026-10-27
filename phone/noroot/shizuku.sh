#!/data/data/com.termux/files/usr/bin/bash
# NO-ROOT mode: what state Shizuku is in, and asking it to start.
#   shizuku.sh probe   -> one word on the first line, a detail on the second:
#       ok                rish answered
#       no-rish           rish / rish_shizuku.dex not copied to ~/server (tools/noroot-install.sh rish)
#       dex-writable      Android 14+ refuses a writable rish_shizuku.dex
#       not-running       the Shizuku app answered but its service is stopped (after a reboot
#                         that it could not start from, or a crash)
#       app-unreachable   the Shizuku app did not answer at all (frozen by battery
#                         optimisation, force-stopped, uninstalled, or stealth mode)
#       not-authorized    Termux is not allowed to use Shizuku
#       awaiting-permission  Shizuku is showing a permission dialog on the screen
#       unknown           anything else (the text is in the detail line)
#   shizuku.sh start   -> sends the thedjchi fork's authenticated START broadcast. Needs
#       SHIZUKU_AUTH in server.conf (Shizuku > Settings > "View intents" shows it). The fork
#       then turns wireless debugging on, waits for Wi-Fi, finds the port by mDNS and starts
#       its service: no fixed IP or port involved. Exit code 0 = broadcast delivered (NOT
#       "Shizuku is running": the next probe tells).
# The texts matched below come from Shizuku's own sources (rish, ShizukuShellLoader.java,
# Shell.java of the thedjchi fork, 2026).
D=$HOME/server
[ -f $D/server.conf ] && . $D/server.conf 2>/dev/null
PKG=${SHIZUKU_PKG:-moe.shizuku.privileged.api}
export RISH_APPLICATION_ID=com.termux

case "$1" in
probe)
  if [ ! -x $D/rish ] || [ ! -f $D/rish_shizuku.dex ]; then
    echo no-rish; echo "rish or rish_shizuku.dex missing in ~/server"; exit 0
  fi
  OUT=$(timeout ${SHIZUKU_PROBE_TIMEOUT:-15} $D/rish -c 'echo SHZ_PROBE_OK' </dev/null 2>&1); RC=$?
  case "$OUT" in
    *SHZ_PROBE_OK*) S=ok ;;
    *"Server is not running"*) S=not-running ;;
    *"Permission denied"*) S=not-authorized ;;
    *"Request timeout"*) S=app-unreachable ;;
    *"Cannot find"*) S=no-rish ;;
    *"writable dex"*|*"Cannot remove the write permission"*) S=dex-writable ;;
    *"Entering shell"*) [ $RC = 124 ] && S=awaiting-permission || S=unknown ;;
    *) S=unknown ;;
  esac
  echo $S
  echo "$OUT" | tr -d '\r' | grep -v '^$' | tail -1 | cut -c1-160
  ;;
start)
  [ -n "${SHIZUKU_AUTH:-}" ] || { echo "SHIZUKU_AUTH is not set in server.conf"; exit 2; }
  timeout 20 ${SHIZUKU_AM:-am} broadcast --include-stopped-packages \
    -n $PKG/moe.shizuku.manager.receiver.ManualStartReceiver -a $PKG.START \
    --es auth "$SHIZUKU_AUTH" </dev/null >/dev/null 2>&1
  ;;
*)
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
