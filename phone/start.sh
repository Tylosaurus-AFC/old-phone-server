#!/system/bin/sh
# Server start-up: everything the phone needs to behave like a server, then the bot and
# the watchdog. Installed as /data/debian/start.sh and run AS ROOT at boot by one of the
# small launchers in phone/boot/ (which one depends on how your phone is rooted).
DEBIAN=${DEBIAN:-/data/debian}
[ -f $DEBIAN/server.conf ] && . $DEBIAN/server.conf
BB=${BB:-/system/xbin/busybox-deb}; [ -x "$BB" ] || BB=$DEBIAN/busybox-deb
LOG=$DEBIAN/boot.log
log() { echo "$(date) $*" >> $LOG; }

# Wait (max ~2 min) for Android to finish booting
n=0
until [ "$(getprop sys.boot_completed)" = 1 ] || [ $n -ge 24 ]; do sleep 5; n=$((n + 1)); done
log "server start-up"

# Never sleep: CPU awake with the screen off, Wi-Fi always on
echo server > /sys/power/wake_lock
settings put global wifi_sleep_policy 2
[ "${DOZE_OFF:-0}" = 1 ] && dumpsys deviceidle disable >/dev/null 2>&1
if [ "${LINEAGE_CHARGE_CTRL_OFF:-0}" = 1 ]; then
  content insert --uri content://lineagesettings/system \
    --bind name:s:charging_control_enabled --bind value:s:0 >/dev/null 2>&1
fi

# adb over Wi-Fi. It still asks for the RSA key you already accepted on the phone.
setprop ${ADB_TCP_PROP:-service.adb.tcp.port} ${ADB_TCP_PORT:-5555}
eval "${ADB_RESTART:-stop adbd; sleep 2; start adbd}"

# The bot -- only if you enabled it (the same token must never run on two phones)
if [ -f $DEBIAN/BOT_ENABLED ]; then
  log "BOT_ENABLED: starting the bot"
  $DEBIAN/bot.sh
else
  log "bot disabled (create $DEBIAN/BOT_ENABLED to enable it)"
fi

# Watchdog, forever. If it ever dies it is relaunched a minute later (charge.sh exits
# by itself when another copy is already running).
while true; do
  ${SH:-/system/bin/sh} $DEBIAN/charge.sh >/dev/null 2>&1
  sleep 60
done
