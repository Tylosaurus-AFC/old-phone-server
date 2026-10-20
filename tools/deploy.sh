#!/usr/bin/env bash
# Push the bot code, your chosen plugins and the phone scripts, check the syntax on the
# phone and restart everything (the bot and the watchdog relaunch each other).
#   tools/deploy.sh             bot/*.py, plugins (PLUGINS in config.sh) and phone/*.sh
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_phone

# Staging folder on the PC: exactly what will land on the phone
S="$ROOT/.push"; rm -rf "$S"; mkdir -p "$S/plugins"
cp "$ROOT"/bot/*.py "$ROOT/bot/requirements.txt" "$S/"
cp "$ROOT"/phone/{enter.sh,bot.sh,charge.sh,start.sh} "$S/"
[ -f "$ROOT/phone/extras/wifi-band.sh" ] && cp "$ROOT/phone/extras/wifi-band.sh" "$S/"
[ -f "$ROOT/device.json" ] && cp "$ROOT/device.json" "$S/"
cp "$ROOT"/extras/plugins/_*.py "$S/plugins/" 2>/dev/null || true   # helper modules
for p in ${PLUGINS:-}; do
  [ -f "$ROOT/extras/plugins/$p.py" ] || { echo "No such plugin: extras/plugins/$p.py"; exit 1; }
  cp "$ROOT/extras/plugins/$p.py" "$S/plugins/"
done

VER="$(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo '?') $(date +%d/%m)"
a shell "rm -rf $TMP.d; mkdir -p $TMP.d"
a push "$(winpath "$S")/." "$TMP.d/" >/dev/null
rm -rf "$S"

remote <<EOF
set -e
T=$TMP.d
BOT=$DEBIAN/fs/opt/bot
mkdir -p \$BOT/plugins
cp \$T/*.py \$T/requirements.txt \$BOT/
[ -f \$T/device.json ] && cp \$T/device.json \$BOT/
# plugins: exactly the chosen ones (+ helpers)
rm -f \$BOT/plugins/*.py
cp \$T/plugins/*.py \$BOT/plugins/ 2>/dev/null || true
# The .sh files run in loops: copy aside and rename (new inode) so the running copies
# are not changed under their feet; the old processes keep their own version.
for s in enter.sh bot.sh charge.sh start.sh wifi-band.sh; do
  [ -f \$T/\$s ] || continue
  cp \$T/\$s $DEBIAN/\$s.new && chmod 755 $DEBIAN/\$s.new && mv $DEBIAN/\$s.new $DEBIAN/\$s
done
[ -f $DEBIAN/server.conf ] || echo "WARNING: $DEBIAN/server.conf missing -- run tools/install.sh scripts"
rm -rf \$T
$DEBIAN/enter.sh "/opt/bot/venv/bin/python3 -m py_compile /opt/bot/*.py /opt/bot/plugins/*.py"
echo "$VER" > \$BOT/VERSION
echo "Syntax OK on the phone"

# Make bot.sh and charge.sh run the new version. They are NOT launched from here (adb
# would wait forever for the processes the session inherits): they are killed and the
# mutual supervision relaunches them. -9 because Android's sh ignores SIGTERM while it
# waits for a child; "[d]" so pkill does not match this very command.
BB=$BB_PATH; [ -x \$BB ] || BB=/system/xbin/busybox-deb
alive() { P=\$(cat \$1 2>/dev/null); [ -n "\$P" ] && \$BB grep -q \$2 /proc/\$P/cmdline 2>/dev/null; }
wait_new() {   # wait_new pidfile name old_pid
  n=0
  while [ \$n -lt 45 ]; do
    if alive \$1 \$2 && [ "\$(cat \$1)" != "\$3" ]; then echo "\$2 relaunched in \$((n * 2)) s"; return 0; fi
    sleep 2; n=\$((n + 1))
  done
  echo "WARNING: \$2 did not relaunch by itself within 90 s"; return 1
}
if [ ! -f $DEBIAN/BOT_ENABLED ]; then
  echo "Bot is disabled on this phone (no $DEBIAN/BOT_ENABLED): not starting it. tools/enable-bot.sh enables it."
else
  OLDB=\$(cat $DEBIAN/bot.pid 2>/dev/null)
  touch $DEBIAN/deploying            # so charge.sh does not count it as a crash
  \$BB pkill -9 -f "[d]ata/debian/bot.sh" || true
  \$BB pkill -f "[o]pt/bot/bot.py" || true
  wait_new $DEBIAN/bot.pid bot.sh "\$OLDB" || true
fi
OLDC=\$(cat $DEBIAN/charge.pid 2>/dev/null)
kill -9 \$OLDC 2>/dev/null || true
wait_new $DEBIAN/charge.pid charge.sh "\$OLDC" || true
EOF

sleep 15
remote <<EOF
tail -1 $DEBIAN/fs/opt/bot/bot.log
EOF
