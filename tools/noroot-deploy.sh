#!/usr/bin/env bash
# NO-ROOT mode: push the bot code, your plugins and the phone scripts over SSH, check the
# syntax on the phone, and restart the bot and the watchdog (they relaunch each other).
#   tools/noroot-deploy.sh           bot/*.py, plugins (PLUGINS in config.sh), phone/noroot/*
set -euo pipefail
source "$(dirname "$0")/noroot-common.sh"
need_phone

S="$(mktemp -d)"; mkdir -p "$S/plugins" "$S/extras"
cp "$ROOT"/bot/*.py "$ROOT/bot/requirements.txt" "$S/"
cp "$ROOT"/phone/noroot/{boot.sh,bot.sh,charge.sh,enter.sh,guard.sh,sa.sh,ui.sh} "$S/"
cp "$ROOT"/phone/noroot/extras/*.sh "$S/extras/"
[ -f "$ROOT/device.json" ] && cp "$ROOT/device.json" "$S/"
cp "$ROOT"/extras/plugins/_*.py "$S/plugins/" 2>/dev/null || true
for p in ${PLUGINS:-}; do
  [ -f "$ROOT/extras/plugins/$p.py" ] || { echo "No such plugin: extras/plugins/$p.py"; exit 1; }
  cp "$ROOT/extras/plugins/$p.py" "$S/plugins/"
done
VER="$(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo '?') $(date +%d/%m)"

ph 'rm -rf ~/server-new; mkdir -p ~/server-new ~/server'
scp -q -r "$S"/. "$H:server-new/"
rm -rf "$S"

ph CONTAINER="$CONTAINER" "VER='$VER'" bash -s <<'EOF'
set -e
OPT=$PREFIX/var/lib/proot-distro/containers/$CONTAINER/rootfs/opt/bot
T=~/server-new D=~/server
mkdir -p $OPT/plugins $D/extras
cp $T/*.py $T/requirements.txt $OPT/
[ -f $T/device.json ] && cp $T/device.json $OPT/
rm -f $OPT/plugins/*.py; cp $T/plugins/*.py $OPT/plugins/ 2>/dev/null || true
# The .sh files run in loops: copy aside and rename (new inode) so the running copies are
# not changed under their feet; the old processes keep their own version.
for s in boot.sh bot.sh charge.sh enter.sh guard.sh sa.sh ui.sh; do
  cp $T/$s $D/$s.new && chmod 700 $D/$s.new && mv $D/$s.new $D/$s
done
cp $T/extras/*.sh $D/extras/ && chmod 700 $D/extras/*.sh
cp $T/boot.sh ~/.termux/boot/00-server.sh 2>/dev/null && chmod 700 ~/.termux/boot/00-server.sh || true
rm -rf $T
$D/enter.sh "cd /opt/bot && /opt/bot/venv/bin/python3 -m py_compile *.py plugins/*.py"
echo "$VER" > $OPT/VERSION
echo "Syntax OK on the phone"
# Make bot.sh and charge.sh run the new version: kill them and the mutual supervision
# relaunches them (charge.sh relaunches bot.sh; the boot loop relaunches charge.sh).
alive() { P=$(cat $1 2>/dev/null); [ -n "$P" ] && grep -q $2 /proc/$P/cmdline 2>/dev/null; }
wait_new() {   # wait_new pidfile name old_pid
  n=0
  while [ $n -lt 45 ]; do
    if alive $1 $2 && [ "$(cat $1)" != "$3" ]; then echo "$2 relaunched in $((n * 2)) s"; return 0; fi
    sleep 2; n=$((n + 1))
  done
  echo "WARNING: $2 did not relaunch by itself within 90 s"; return 1
}
if [ -f $D/BOT_ENABLED ]; then
  OLDB=$(cat $D/bot.pid 2>/dev/null || true)
  touch $D/deploying            # so charge.sh does not count it as a crash
  pkill -9 -f "[s]erver/bot.sh" || true
  pkill -f "[o]pt/bot/bot.py" || true
  wait_new $D/bot.pid bot.sh "$OLDB" || true
else
  echo "Bot is disabled on this phone (no ~/server/BOT_ENABLED): not starting it."
fi
# guard.sh (shell side, via Shizuku) runs apart: stop it so charge.sh starts the new one
$D/sa.sh 'kill $(cat /data/local/tmp/srv-guard.pid) 2>/dev/null' >/dev/null || true
OLDC=$(cat $D/charge.pid 2>/dev/null || true)
kill -9 $OLDC 2>/dev/null || true
wait_new $D/charge.pid charge.sh "$OLDC" || true
EOF
sleep 15
ph 'tail -1 $PREFIX/var/lib/proot-distro/containers/'"$CONTAINER"'/rootfs/opt/bot/bot.log' || true
