#!/system/bin/sh
# Android-side watchdog, once a minute. Installed as /data/debian/charge.sh and run
# forever by start.sh (which relaunches it if it ever dies).
#
#  - restarts bot.sh if it died -- but ONLY if $DEBIAN/BOT_ENABLED exists (the same
#    Telegram token must never run on two phones: error 409 and duplicated downloads)
#  - serves the bot's /reiniciar command (the bot lives in the chroot and cannot reboot Android)
#  - heartbeat: if the bot is alive but frozen (no heartbeat for HUNG seconds), kills it
#    so bot.sh starts a fresh one
#  - network: Wi-Fi power-save kept off, ARP announce, reconnect if the signal stays bad
#    or there is no Internet for 5 min; knows about USB-Ethernet adapters
#  - battery: keeps the charge between LOW and HIGH (see server.conf: BATT_CTRL)
#
# Settings: $DEBIAN/server.conf (re-read every minute).
# Test hooks (see tests/): ONCE=N runs N passes (1 = a single pass); DEBIAN and BB can be overridden.
DEBIAN=${DEBIAN:-/data/debian}
BB=${BB:-/system/xbin/busybox-deb}; [ -x "$BB" ] || BB=$DEBIAN/busybox-deb

# ---- defaults (overridden by server.conf) ------------------------------------------
BATT=/sys/class/power_supply/battery BATT_CTRL=slate BATT_CTRL_FILE=
LOW=40 HIGH=60 MAXTEMP=420 FLOOR=15
WIFI_IFACE=wlan0 WIFI_MIN=-75 FIX_ROUTE=0
ADB_TCP_PORT=5555 ADB_TCP_PROP=service.adb.tcp.port
ADB_RESTART="stop adbd; sleep 2; start adbd"
HUNG=300            # seconds without heartbeat = bot frozen

BOTDIR=$DEBIAN/fs/opt/bot
LOG=$BOTDIR/service.log
EV=$BOTDIR/events.jsonl
HB=$BOTDIR/heartbeat
REQ=$BOTDIR/reboot_request
PID=$DEBIAN/charge.pid
IW="$BB chroot $DEBIAN/fs /usr/sbin/iw"

[ -f $DEBIAN/server.conf ] && . $DEBIAN/server.conf

# Only one instance
OLD=$(cat $PID 2>/dev/null)
if [ -n "$OLD" ] && [ "$OLD" != "$$" ] && $BB grep -q charge.sh /proc/$OLD/cmdline 2>/dev/null; then
  exit 0
fi
echo $$ > $PID

log() { echo "$(date) [carga] $*" >> $LOG; }
# Event for the bot's /historial (same format as health.py; no quotes inside the text)
ev() { echo "{\"t\":$($BB date +%s),\"k\":\"$1\",\"x\":\"$2\"}" >> $EV; }

NETFAIL=0; NETWAIT=5; NETOFF=0
NETDOWN=0
HUNG_UNTIL=0
BADLINK=0
WIFI_UNTIL=0
ETH_WAS=""
OFFLINE=0           # minutes without Internet (for the optional 5 GHz -> 2.4 GHz fallback)

# ---- battery control, whatever the driver ------------------------------------------
ctl_file() {
  if [ -n "$BATT_CTRL_FILE" ]; then echo "$BATT_CTRL_FILE"; return; fi
  case "$BATT_CTRL" in
    slate)  echo $BATT/batt_slate_mode ;;
    enable) echo $BATT/charging_enabled ;;
  esac
}
is_paused() {       # true if the charger is currently switched off
  v=$(cat "$CTL" 2>/dev/null)
  case "$BATT_CTRL" in
    slate)  [ "$v" = 1 ] ;;
    enable) [ "$v" = 0 ] ;;
    *)      false ;;
  esac
}
set_pause() {       # set_pause 1 = stop charging, set_pause 0 = charge
  case "$BATT_CTRL" in
    slate)  echo $1 > "$CTL" ;;
    enable) echo $((1 - $1)) > "$CTL" ;;
  esac
}

# Android 11 does not consult the main routing table: without this rule root (the bot)
# has no route out ("Network is unreachable"). The wlan table is created by netd.
fix_route() {
  T=$(ip route show table all | $BB grep "^default via .* dev $WIFI_IFACE table" \
      | $BB sed 's/.*table \([0-9a-z_]*\).*/\1/' | $BB head -1)
  [ -n "$T" ] || return
  ip rule | $BB grep -q "^20000:.*lookup $T" && return
  ip rule del pref 20000 2>/dev/null
  ip rule add from all lookup $T pref 20000
}

while true; do
  NOW=$($BB date +%s)
  [ -f $DEBIAN/server.conf ] && . $DEBIAN/server.conf
  CTL=$(ctl_file)
  [ "$FIX_ROUTE" = 1 ] && fix_route

  # /reiniciar from the bot
  if [ -f $REQ ]; then
    what=$(cat $REQ); rm -f $REQ
    case "$what" in
      adb)   echo "$(date) [adb] restart requested by /reiniciar adb" >> $LOG
             $IW dev $WIFI_IFACE set power_save off
             setprop $ADB_TCP_PROP $ADB_TCP_PORT; eval "$ADB_RESTART" ;;
      wifi)  echo "$(date) [red] reconnect requested by /reiniciar wifi" >> $LOG
             svc wifi disable; sleep 5; svc wifi enable ;;
      phone) echo "$(date) [sistema] reboot requested by /reiniciar" >> $LOG
             sync; reboot ;;
    esac
  fi

  # Keep bot.sh alive (only if the bot is enabled on this phone); bot.sh detaches itself
  # and exits at once if another copy is already running
  BPID=$(cat $DEBIAN/bot.pid 2>/dev/null)
  if [ -f $DEBIAN/BOT_ENABLED ] && { [ -z "$BPID" ] || ! $BB grep -q bot.sh /proc/$BPID/cmdline 2>/dev/null; }; then
    if [ -f $DEBIAN/deploying ]; then   # tools/deploy.sh stopped it on purpose: not a crash
      rm -f $DEBIAN/deploying
      echo "$(date) [salud] deploy: relaunching bot.sh" >> $LOG
      ev actualizacion "código nuevo desplegado"
    else
      echo "$(date) [salud] bot.sh was not running, relaunching it" >> $LOG
      ev caida "el servicio del bot no estaba corriendo; relanzado"
    fi
    $BB pkill -9 -f opt/bot/bot.py   # the orphan bot of a dead service (same token)
    $DEBIAN/bot.sh
  fi

  # Heartbeat: the bot's main loop writes the time to $HB on every pass (at most ~70 s
  # apart). If it is older than HUNG and the process is still alive, it is frozen: kill
  # it so bot.sh relaunches it. 10 min of grace after acting.
  if [ -f $HB ] && [ $NOW -gt $HUNG_UNTIL ]; then
    LAST=$(cat $HB 2>/dev/null); LAST=${LAST:-$NOW}
    if [ $((NOW - LAST)) -gt $HUNG ] && $BB pgrep -f opt/bot/bot.py >/dev/null; then
      echo "$(date) [salud] bot frozen $((NOW - LAST))s, restarting" >> $LOG
      ev colgado "el bot no respondía ($((NOW - LAST)) s sin señal de vida); reiniciado"
      $BB pkill -9 -f opt/bot/bot.py   # -9: a frozen process may ignore SIGTERM
      HUNG_UNTIL=$((NOW + 600))
    fi
  fi

  # Wi-Fi power-save: with the screen off the chip sleeps and stops answering local
  # network traffic (ARP), so adb over Wi-Fi disappears even though the bot still has
  # Internet. Android turns it back on when it reconnects, so check every pass.
  if $IW dev $WIFI_IFACE get power_save 2>/dev/null | $BB grep -q ": on"; then
    $IW dev $WIFI_IFACE set power_save off && echo "$(date) [red] Wi-Fi power-save turned off" >> $LOG
  fi

  # Cable (USB-Ethernet adapter): Android prefers it to Wi-Fi; while there is a link the
  # Wi-Fi is left alone.
  ETH=""
  for n in /sys/class/net/eth* /sys/class/net/usb*; do
    [ "$(cat $n/operstate 2>/dev/null)" = up ] && { ETH=${n##*/}; break; }
  done
  if [ "$ETH" != "$ETH_WAS" ]; then
    if [ -n "$ETH" ]; then
      echo "$(date) [red] Ethernet connected ($ETH, $(cat /sys/class/net/$ETH/speed 2>/dev/null) Mbit/s)" >> $LOG
      ev red "Ethernet conectado ($ETH)"
    elif [ -n "$ETH_WAS" ]; then
      echo "$(date) [red] Ethernet disconnected: back on Wi-Fi" >> $LOG
      ev red "Ethernet desconectado: sigue por Wi-Fi"
    fi
    ETH_WAS=$ETH
  fi

  # Access point: old Android keeps the first one it finds and never jumps to a better
  # one while connected (after a reboot a phone stayed on -84 dBm / 9 Mbps with a
  # -69 dBm / 40 Mbps one available). If the signal stays below WIFI_MIN for 5 min,
  # restart Wi-Fi: scanning again picks the strongest.
  SIG=$($IW dev $WIFI_IFACE link 2>/dev/null | $BB awk '/signal:/ {print $2}')
  if [ -z "$ETH" ] && [ -n "$SIG" ] && [ "$SIG" -lt "$WIFI_MIN" ]; then
    BADLINK=$((BADLINK + 1))
  else
    BADLINK=0
  fi
  if [ $BADLINK -ge 5 ] && [ $NOW -gt $WIFI_UNTIL ]; then
    echo "$(date) [red] signal $SIG dBm for 5 min, reconnecting to look for a better AP" >> $LOG
    ev wifi "señal Wi-Fi mala ($SIG dBm) 5 min: reconecto al punto más fuerte"
    svc wifi disable; sleep 5; svc wifi enable
    BADLINK=0; WIFI_UNTIL=$((NOW + 1800))   # if nothing better exists, do not insist for 30 min
  fi
  # Announce ourselves on the LAN (gratuitous ARP) so the PC and mesh always know where we are
  MYIP=$(ip -4 addr show $WIFI_IFACE 2>/dev/null | $BB awk '/inet / {split($2, a, "/"); print a[1]}')
  [ -n "$MYIP" ] && $BB arping -U -c 1 -I $WIFI_IFACE $MYIP >/dev/null 2>&1

  # Network watchdog: 5 minutes without Internet -> restart Wi-Fi
  if ping -c1 -W5 1.1.1.1 >/dev/null 2>&1 || ping -c1 -W5 8.8.8.8 >/dev/null 2>&1; then
    NETFAIL=0; OFFLINE=0; NETWAIT=5; NETOFF=0
    if [ $NETDOWN -gt 0 ]; then
      ev wifi "Internet volvió tras reiniciar el Wi-Fi"
      NETDOWN=0
    fi
  else
    NETFAIL=$((NETFAIL + 1)); OFFLINE=$((OFFLINE + 1)); NETOFF=$((${NETOFF:-0} + 1))
    # Optional (phone/extras/wifi-band.sh): pinned to 5 GHz and 10 min offline -> allow 2.4 GHz again
    if [ $OFFLINE -ge 10 ] && [ -z "$ETH" ] && [ -f $DEBIAN/wifi-band.sh ] \
       && $BB grep -q '<boolean name="AutoJoinEnabled" value="false" />' \
            /data/misc/apexdata/com.android.wifi/WifiConfigStore.xml 2>/dev/null; then
      ev wifi "10 min sin Internet en 5 GHz: vuelvo a permitir el Wi-Fi de 2,4 GHz"
      /system/bin/sh $DEBIAN/wifi-band.sh 2g
      OFFLINE=0; NETFAIL=0; NETDOWN=1
    elif [ $NETFAIL -ge ${NETWAIT:-5} ]; then
      # after 5 min, then 10, 20, 40, 60, 60... (a long outage is not fixed by cycling Wi-Fi)
      NETWAIT=$((${NETWAIT:-5} * 2)); [ $NETWAIT -gt 60 ] && NETWAIT=60
      echo "$(date) [red] no Internet for $NETOFF min, restarting Wi-Fi (next try in $NETWAIT min)" >> $LOG
      ev wifi "$NETOFF min sin Internet: reinicio el Wi-Fi (siguiente intento en $NETWAIT min)"
      svc wifi disable; sleep 5; svc wifi enable
      NETFAIL=0; NETDOWN=1
    fi
  fi

  # Battery
  if [ "$BATT_CTRL" != none ] && [ -n "$CTL" ] && [ -e "$CTL" ]; then
    echo "$LOW–$HIGH" > $BOTDIR/charge_range   # for the bot's /estado
    cap=$(cat $BATT/capacity)
    temp=$(cat $BATT/temp)         # tenths of a degree
    paused=0; is_paused && paused=1
    want=$paused
    if [ "$cap" -le "$FLOOR" ]; then
      want=0                       # safety: never let it die
    elif [ "$temp" -ge "$MAXTEMP" ]; then
      want=1                       # too hot: stop charging
    elif [ "$cap" -ge "$HIGH" ]; then
      want=1
    elif [ "$cap" -le "$LOW" ]; then
      want=0
    fi
    if [ "$want" != "$paused" ]; then
      set_pause $want
      if [ "$want" = 1 ]; then
        log "pausa carga (${cap}%, $((temp / 10))°C)"
        ev carga "pausa la carga al ${cap}% ($((temp / 10)) °C)"
      else
        log "reanuda carga (${cap}%, $((temp / 10))°C)"
        ev carga "reanuda la carga al ${cap}% ($((temp / 10)) °C)"
      fi
      paused=$want
    elif [ "$want" = 1 ] && [ "$(cat $BATT/status)" = "Charging" ]; then
      # After a reboot some drivers show "paused" without applying it and keep charging:
      # writing it again (off -> on) makes them apply it for real
      set_pause 0; sleep 2; set_pause 1
      log "the pause was not applied (still charging at ${cap}%), re-applied"
      ev carga "la pausa de carga no se aplicaba (seguía cargando al ${cap}%); corregido"
    fi
    echo $paused > $BOTDIR/charge_paused   # for the bot's /estado and /bateria
  else
    echo "—" > $BOTDIR/charge_range
    echo 0 > $BOTDIR/charge_paused
  fi
  if [ -n "$ONCE" ]; then ONCE=$((ONCE - 1)); [ $ONCE -le 0 ] && break; fi   # ONCE=N: N passes
  sleep 60
done
