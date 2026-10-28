#!/data/data/com.termux/files/usr/bin/bash
# NO-ROOT mode: health check of everything the server needs to keep running on its own.
# Read-only: it changes nothing. Run it in Termux (~/server/doctor.sh) or from the PC
# (tools/noroot-doctor.sh). charge.sh also runs it every hour and leaves the result in
# /opt/bot/sys/doctor.txt, which the bot's /salud and /diagnostico show.
#
# Every line is OK, WARN (works, but less reliably or with a feature missing) or FAIL (the
# server will not run or will not come back after a reboot), with what to do about it.
# The first line sums up: "RESULT: ok", "RESULT: degraded" or "RESULT: broken".
# Exit code: 0 ok, 1 degraded, 2 broken.
D=$HOME/server
[ -f $D/server.conf ] && . $D/server.conf 2>/dev/null
CONTAINER=${CONTAINER:-bot}
FS=$PREFIX/var/lib/proot-distro/containers/$CONTAINER/rootfs
OPT=$FS/opt/bot
OUT="" NWARN=0 NFAIL=0
ok()   { OUT="$OUT
OK   $1"; }
warn() { OUT="$OUT
WARN $1
     -> $2"; NWARN=$((NWARN + 1)); }
fail() { OUT="$OUT
FAIL $1
     -> $2"; NFAIL=$((NFAIL + 1)); }
alive() { local p; p=$(cat "$1" 2>/dev/null); [ -n "$p" ] && grep -q "$2" /proc/$p/cmdline 2>/dev/null; }

# --- Android, CPU, Termux --------------------------------------------------------------------
SDK=$(getprop ro.build.version.sdk 2>/dev/null); SDK=${SDK//[!0-9]/}; SDK=${SDK:-0}
REL=$(getprop ro.build.version.release 2>/dev/null)
BRAND=$(getprop ro.product.brand 2>/dev/null)
ARCH=$(uname -m)
if [ "$SDK" -lt 24 ]; then
  fail "Android $REL (SDK $SDK): Termux needs Android 7 or newer" "use root mode (docs/*/02-root.md)"
elif [ "$SDK" -lt 30 ]; then
  warn "Android $REL (SDK $SDK): Shizuku cannot start by itself at boot below Android 11" \
       "after every reboot open Shizuku and start it, or use root mode on this phone"
elif [ "$SDK" -lt 33 ]; then
  # Android 11-12(L) forget the networks allowed for wireless debugging on every reboot
  # (fixed in Android 13, AOSP change 2128832; Shizuku's own sources say so)
  warn "Android $REL (SDK $SDK): after every reboot Android asks again to allow wireless debugging on your Wi-Fi" \
       "after each reboot unlock the phone and tap Allow on that dialog; Shizuku then starts (Android 13+ remembers it)"
else
  ok "Android $REL (SDK $SDK), $BRAND"
fi
case "$ARCH" in
  aarch64|armv7l|armv8l) ok "CPU $ARCH" ;;
  *) warn "CPU $ARCH: not tested with this project" "report how it goes (CONTRIBUTING.md)" ;;
esac
case "${TERMUX_APK_RELEASE:-}" in
  GOOGLE_PLAY_STORE) warn "Termux from Google Play" \
    "install Termux, Termux:Boot and Termux:API from GitHub or F-Droid, all from the same source" ;;
  "") ;;
  *) ok "Termux ${TERMUX_VERSION:-?} ($TERMUX_APK_RELEASE build)" ;;
esac

# --- Installation ------------------------------------------------------------------------------
if [ -x ~/.termux/boot/00-server.sh ]; then ok "boot hook ~/.termux/boot/00-server.sh"
else fail "no boot hook: the server will not start after a reboot" "tools/noroot-install.sh scripts"; fi
if [ ! -f $D/server.conf ]; then fail "no ~/server/server.conf" "tools/noroot-install.sh scripts"
elif ! bash -n $D/server.conf 2>/dev/null; then fail "~/server/server.conf has a syntax error" "fix it: nano ~/server/server.conf (check quotes)"
else ok "server.conf"; fi
if [ ! -d $FS ]; then fail "no Debian container '$CONTAINER'" "tools/noroot-install.sh container"
elif [ ! -x $OPT/venv/bin/python3 ]; then fail "Debian container without the bot's Python" "tools/noroot-install.sh provision"
else ok "Debian container '$CONTAINER'"; fi
if [ -f $D/BOT_ENABLED ]; then
  if [ -s $OPT/token ]; then ok "bot enabled, token present"
  else fail "bot enabled but there is no token" "tools/noroot-bot.sh token"; fi
else
  ok "bot disabled on this phone (tools/noroot-bot.sh enable to run it here)"
fi

# --- Processes -----------------------------------------------------------------------------------
if alive $D/charge.pid charge.sh; then ok "watchdog (charge.sh) running"
else fail "watchdog (charge.sh) not running" "sh ~/.termux/boot/00-server.sh  (or reboot the phone)"; fi
if [ -f $D/BOT_ENABLED ]; then
  if alive $D/bot.pid bot.sh; then ok "bot service (bot.sh) running"
  else fail "bot service (bot.sh) not running" "sh ~/.termux/boot/00-server.sh; the watchdog also relaunches it within a minute"; fi
  HB=$(cat $OPT/heartbeat 2>/dev/null); HB=${HB%.*}
  if [ -n "$HB" ]; then
    AGE=$(( $(date +%s) - HB ))
    if [ $AGE -gt 300 ]; then warn "bot silent for $AGE s (no heartbeat)" "wait: the watchdog restarts a frozen bot after 5 min; if it repeats, send /diagnostico"
    else ok "bot heartbeat $AGE s ago"; fi
  fi
fi
if pgrep -x sshd >/dev/null 2>&1; then ok "sshd (port 8022) running"
else warn "sshd not running: no remote access from the PC" "run sshd in Termux"; fi

# --- Storage -------------------------------------------------------------------------------------
FREE=$(df -Pk $HOME 2>/dev/null | awk 'NR == 2 {print int($4 / 1024)}')
if [ -z "$FREE" ]; then warn "cannot read free space" "df -h ~"
elif [ "$FREE" -lt 300 ]; then fail "only $FREE MB free: downloads and updates will fail" "free space on the phone (big files, app caches)"
elif [ "$FREE" -lt 1024 ]; then warn "$FREE MB free" "keep at least 1 GB free"
else ok "$FREE MB free"; fi

# --- What Android lets Termux do (through Shizuku) -----------------------------------------------
if [ ! -x $D/rish ] || [ ! -f $D/rish_shizuku.dex ]; then
  warn "Shizuku not set up: no guardian if Android closes Termux, no reboot from the bot, battery restrictions cannot be checked" \
       "set up Shizuku (docs/*/12-*.md, step 4); meanwhile check Settings > Apps > Termux > Battery = Unrestricted by hand"
elif [ "$($D/sa.sh 'echo OK')" != OK ]; then
  warn "Shizuku does not answer: no guardian, no reboot from the bot" \
       "open the Shizuku app and start it (wireless debugging must be on; enable its start on boot)"
else
  ok "Shizuku answers"
  Q=$($D/sa.sh 'echo "boot=$(pm list packages com.termux.boot 2>&1 | grep -c "package:com.termux.boot$")"
    echo "bootstate=$(dumpsys package com.termux.boot 2>&1 | grep -m1 -oE "stopped=(true|false)")"
    echo "bootnl=$(dumpsys package com.termux.boot 2>&1 | grep -m1 -oE "notLaunched=(true|false)")"
    echo "api=$(pm list packages com.termux.api 2>&1 | grep -c "package:com.termux.api$")"
    echo "idle=$(dumpsys deviceidle whitelist 2>&1 | grep -c ",com.termux,")"
    echo "bg=$(cmd appops get com.termux RUN_ANY_IN_BACKGROUND 2>&1 | head -1)"
    echo "bucket=$(am get-standby-bucket com.termux 2>&1 | head -1)"
    echo "phantom=$(settings get global settings_enable_monitor_phantom_procs 2>&1)"
    echo "maxph=$(device_config get activity_manager max_phantom_processes 2>&1)"
    echo "wake=$(dumpsys power 2>&1 | grep -c "termux:service-wakelock")"
    echo "adbwifi=$(settings get global adb_wifi_enabled 2>&1)"' | tr -d '\r')
  v() { echo "$Q" | sed -n "s/^$1=//p" | head -1; }
  if [ "$(v boot)" != 1 ]; then
    fail "Termux:Boot is not installed: nothing starts the server after a reboot" \
         "install Termux:Boot from the same source as Termux, then open it once"
  elif [ "$(v bootstate)" = stopped=true ] || [ "$(v bootnl)" = notLaunched=true ]; then
    fail "Termux:Boot was never opened (or was force-stopped): Android will not start it at boot" \
         "open the Termux:Boot app once by hand (and never force-stop it)"
  else
    ok "Termux:Boot installed and allowed to start at boot"
  fi
  [ "$(v api)" = 1 ] || warn "Termux:API not installed: no battery/Wi-Fi fallback when Shizuku is down" \
                             "install Termux:API from the same source as Termux"
  if [ "$(v idle)" -ge 1 ] 2>/dev/null; then ok "Termux exempt from battery optimisation (Doze)"
  else fail "Termux is under battery optimisation: Android may freeze it with the screen off" \
            "Settings > Apps > Termux > Battery > Unrestricted (the watchdog also requests it through Shizuku)"; fi
  case "$(v bg)" in
    *ignore*|*deny*) fail "Termux is not allowed to run in the background" \
                          "Settings > Apps > Termux > Battery > allow background activity" ;;
  esac
  B=$(v bucket)
  case "$B" in
    5|10|20) ok "app standby bucket $B (active/working set)" ;;
    30|40|45|50) warn "app standby bucket $B: Android limits Termux's jobs and network" \
                      "open Termux now and then, or let the watchdog set it (KEEPALIVE in server.conf)" ;;
  esac
  if [ "$SDK" -ge 32 ]; then
    if [ "$(v phantom)" = false ]; then ok "Android's child-process killer is off"
    else warn "Android 12L+ may kill Termux's background processes (phantom process killer)" \
              "Developer options > Disable child process restrictions, or let the watchdog set it (KEEPALIVE)"; fi
  elif [ "$SDK" = 31 ]; then
    M=$(v maxph)
    if [ "${M:-0}" -ge 1000 ] 2>/dev/null; then ok "phantom process limit raised ($M)"
    else warn "Android 12 may kill Termux's background processes (limit of 32 shared by all apps)" \
              "the watchdog raises it every 30 min (KEEPALIVE); Google Play services can reset it"; fi
  fi
  if [ "$(v wake)" -ge 1 ] 2>/dev/null; then ok "Termux wake lock held (CPU stays awake with the screen off)"
  else warn "no Termux wake lock: the CPU may sleep with the screen off" \
            "run termux-wake-lock (the boot hook does it); the Termux notification must say 'wake lock held'"; fi
  [ "$(v adbwifi)" = 1 ] || warn "wireless debugging is off: Shizuku cannot restart by itself" \
                                 "turn it on (Developer options); the guardian keeps it on once Shizuku runs"
fi

if [ $NFAIL -gt 0 ]; then R=broken; RC=2
elif [ $NWARN -gt 0 ]; then R=degraded; RC=1
else R=ok; RC=0; fi
echo "RESULT: $R ($NFAIL fail, $NWARN warn) $(date '+%Y-%m-%d %H:%M')$OUT"
exit $RC
