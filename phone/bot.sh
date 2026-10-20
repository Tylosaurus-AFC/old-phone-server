#!/system/bin/sh
# Bot service: keeps the bot running; if it dies it restarts it, waiting longer each
# time it falls quickly (10 s, 20 s, 40 s ... up to 10 min).
# Installed as /data/debian/bot.sh. Started by start.sh (only if BOT_ENABLED exists) and
# restarted by charge.sh if it ever dies. Detaches itself (nohup) when called plainly.
DEBIAN=${DEBIAN:-/data/debian}
[ -f $DEBIAN/server.conf ] && . $DEBIAN/server.conf
BB=${BB:-/system/xbin/busybox-deb}; [ -x "$BB" ] || BB=$DEBIAN/busybox-deb
BOT_CMD=${BOT_CMD:-"/opt/bot/venv/bin/python3 /opt/bot/bot.py"}
PING_HOST=${PING_HOST:-api.telegram.org}
LOG=$DEBIAN/fs/opt/bot/service.log
EV=$DEBIAN/fs/opt/bot/events.jsonl

[ "$1" = "--fg" ] || { $BB nohup "$0" --fg </dev/null >/dev/null 2>&1 & exit 0; }

# Only one instance
OLD=$(cat $DEBIAN/bot.pid 2>/dev/null)
if [ -n "$OLD" ] && $BB grep -q bot.sh /proc/$OLD/cmdline 2>/dev/null; then
  exit 0
fi
echo $$ > $DEBIAN/bot.pid

# Event for the bot's /historial (same format as health.py; no quotes inside the text)
ev() { echo "{\"t\":$($BB date +%s),\"k\":\"$1\",\"x\":\"$2\"}" >> $EV; }

FAILS=0
while true; do
  # Wait for the network
  until ping -c1 -W3 $PING_HOST >/dev/null 2>&1; do sleep 10; done
  # Keep the log from growing forever (>1 MB -> keep only the tail)
  if [ "$($BB stat -c %s $LOG 2>/dev/null || echo 0)" -gt 1000000 ]; then
    $BB tail -c 200000 $LOG > $LOG.tmp && mv $LOG.tmp $LOG
  fi
  echo "$(date) starting bot" >> $LOG
  START=$($BB date +%s)
  $DEBIAN/enter.sh "$BOT_CMD" >> $LOG 2>&1
  RC=$?
  RAN=$(( $($BB date +%s) - START ))
  if [ $RC = 143 ] || [ $RC = 137 ]; then
    # Stopped on purpose (deploy, /reiniciar, watchdog): not a crash
    FAILS=0; DELAY=10
  else
    ERR=$($BB tail -n 40 $LOG | $BB grep -E "Error|Exception" | $BB tail -1 \
          | $BB tr -d '"\' | $BB cut -c1-150)
    ev caida "el bot se cerró (código $RC) tras $RAN s: ${ERR:-sin detalle}"
    if [ $RAN -lt 120 ]; then FAILS=$((FAILS + 1)); else FAILS=1; fi
    [ $FAILS -gt 7 ] && FAILS=7
    DELAY=$((10 << (FAILS - 1))); [ $DELAY -gt 600 ] && DELAY=600
  fi
  echo "$(date) bot ended ($RC) after ${RAN}s, restart in ${DELAY}s" >> $LOG
  sleep $DELAY
done
