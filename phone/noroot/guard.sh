#!/system/bin/sh
# NO-ROOT mode: guardian. Runs as Android's "shell" user (charge.sh launches it through
# Shizuku) and survives Android closing Termux. If it does not see Termux's sshd, it opens
# Termux's window: when it opens, Termux runs ~/.bashrc, which relaunches the server
# (~/.termux/boot/00-server.sh) if it is not running. It also keeps Wireless debugging on.
# Installed as /data/local/tmp/srv-guard.sh (charge.sh copies it from ~/server).
PID=/data/local/tmp/srv-guard.pid
LOG=/data/local/tmp/srv-guard.log
OLD=$(cat $PID 2>/dev/null)
if [ -n "$OLD" ] && grep -q srv-guard /proc/$OLD/cmdline 2>/dev/null; then
  exit 0
fi
echo $$ > $PID
TU=$(stat -c %u /data/data/com.termux 2>/dev/null)   # Termux's uid
[ -n "$TU" ] || exit 1
MISS=0
while true; do
  # Wireless debugging always available to your PC (once paired). Android turns it off on
  # reboot and when the phone hops between router and repeater; the port changes each time
  # (tools/noroot-adb.sh finds it).
  if [ "$(settings get global adb_wifi_enabled 2>/dev/null)" != 1 ]; then
    settings put global adb_wifi_enabled 1 >/dev/null 2>&1 \
      && echo "$(date) wireless debugging re-enabled" >> $LOG
  fi
  if ps -A -o UID,NAME | grep -q "^ *$TU  *sshd$"; then
    MISS=0
  else
    MISS=$((MISS + 1))
    if [ $MISS -ge 2 ]; then          # 2 passes in a row: not just an sshd restart
      echo "$(date) Termux is down: opening its window" >> $LOG
      # With the screen off the window cannot open a session: wake the screen for a moment
      input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
      input swipe 540 2000 540 800 200 >/dev/null 2>&1      # dismiss a swipe-lock screen
      am start -n com.termux/.app.TermuxActivity >/dev/null 2>&1
      sleep 20
      input keyevent KEYCODE_HOME >/dev/null 2>&1
      input keyevent KEYCODE_SLEEP >/dev/null 2>&1
      MISS=0
      sleep 120                       # time for everything to come up
    fi
  fi
  sleep 60
done
