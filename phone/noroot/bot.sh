#!/data/data/com.termux/files/usr/bin/bash
# NO-ROOT mode: bot service. Restarts the bot if it dies, waiting longer each time it falls
# quickly (10 s, 20 s, 40 s ... up to 10 min). Started by boot.sh / charge.sh, only if
# ~/server/BOT_ENABLED exists.
D=$HOME/server
[ -f $D/server.conf ] && . $D/server.conf
CONTAINER=${CONTAINER:-bot}
OPT=$PREFIX/var/lib/proot-distro/containers/$CONTAINER/rootfs/opt/bot
LOG=$OPT/service.log
EV=$OPT/events.jsonl

[ "$1" = "--fg" ] || { setsid nohup "$0" --fg </dev/null >/dev/null 2>&1 & exit 0; }

# Only one instance
OLD=$(cat $D/bot.pid 2>/dev/null)
if [ -n "$OLD" ] && grep -q bot.sh /proc/$OLD/cmdline 2>/dev/null; then
  exit 0
fi
echo $$ > $D/bot.pid

# Event for the bot's /historial (same format as health.py; no quotes inside the text)
ev() { echo "{\"t\":$(date +%s),\"k\":\"$1\",\"x\":\"$2\"}" >> $EV; }
# Internet check: TCP to NET_HOSTS (server.conf; default two public DNS servers, port 53;
# "host:port" for another port, e.g. your router's 192.168.1.1:80)
online() {
  local h
  for h in ${NET_HOSTS:-1.1.1.1 8.8.8.8}; do
    case $h in *:*) ;; *) h=$h:53 ;; esac
    timeout 5 bash -c "</dev/tcp/${h%:*}/${h##*:}" 2>/dev/null && return 0
  done
  return 1
}

termux-wake-lock                 # never sleep with the screen off

FAILS=0
while true; do
  until online; do sleep 10; done
  # Keep the log from growing forever (>1 MB -> keep only the tail)
  if [ "$(stat -c %s $LOG 2>/dev/null || echo 0)" -gt 1000000 ]; then
    tail -c 200000 $LOG > $LOG.tmp && mv $LOG.tmp $LOG
  fi
  echo "$(date) starting bot" >> $LOG
  START=$(date +%s)
  $D/enter.sh "exec /opt/bot/venv/bin/python3 /opt/bot/bot.py" >> $LOG 2>&1
  RC=$?
  RAN=$(( $(date +%s) - START ))
  if [ $RC = 143 ] || [ $RC = 137 ] || [ -f $D/stopping ]; then
    # Stopped on purpose (deploy, /reiniciar, watchdog): not a crash
    rm -f $D/stopping
    FAILS=0; DELAY=10
  else
    ERR=$(tail -n 40 $LOG | grep -E "Error|Exception" | tail -1 | tr -d '"\\' | cut -c1-150)
    ev caida "el bot se cerró (código $RC) tras $RAN s: ${ERR:-sin detalle}"
    if [ $RAN -lt 120 ]; then FAILS=$((FAILS + 1)); else FAILS=1; fi
    [ $FAILS -gt 7 ] && FAILS=7
    DELAY=$((10 << (FAILS - 1))); [ $DELAY -gt 600 ] && DELAY=600
  fi
  echo "$(date) bot ended ($RC) after ${RAN}s, restart in ${DELAY}s" >> $LOG
  sleep $DELAY
done
