#!/data/data/com.termux/files/usr/bin/bash
# NO-ROOT mode: watchdog, once a minute (the counterpart of phone/charge.sh, which needs root).
# Started at boot by ~/.termux/boot/00-server.sh. It:
#  - hands the bot what it cannot see from inside proot (battery, uptime, charge state, Wi-Fi):
#    written to /opt/bot/sys, which enter.sh bind-mounts where the bot looks for it
#  - relaunches bot.sh if it dies, ONLY if ~/server/BOT_ENABLED exists (the same token must not
#    run on two phones: Telegram answers 409 and downloads are duplicated)
#  - serves /reiniciar and the heartbeat (bot alive but silent for 5 min -> restarted)
#  - network: 5 minutes without Internet -> cycles Wi-Fi
#  - optional: services that need a USB disk (SERVICES) and a nightly job (NIGHTLY)
# The charger is limited by the phone maker's own feature (Settings > Battery); without root
# this script only records the pauses and resumptions (see server.conf, OEM).
#
# Android permissions: with Shizuku (rish) Termux has those of the "shell" user: read
# /sys/class/power_supply, svc wifi, reboot... If Shizuku does not answer it falls back to
# Termux:API for the battery and Wi-Fi, and rebooting the phone from the bot is impossible.
D=$HOME/server
[ -f $D/server.conf ] && . $D/server.conf
CONTAINER=${CONTAINER:-bot}
CHARGE_LIMIT_DEFAULT=${CHARGE_LIMIT_DEFAULT:-80}
OPT=$PREFIX/var/lib/proot-distro/containers/$CONTAINER/rootfs/opt/bot
SYS=$OPT/sys
LOG=$OPT/service.log
EV=$OPT/events.jsonl
HB=$OPT/heartbeat
PID=$D/charge.pid
REQ=$OPT/reboot_request

OLD=$(cat $PID 2>/dev/null)
if [ -n "$OLD" ] && [ "$OLD" != "$$" ] && grep -q charge.sh /proc/$OLD/cmdline 2>/dev/null; then
  exit 0
fi
echo $$ > $PID
mkdir -p $SYS/battery $D/svc
getprop ro.product.brand > $SYS/battery/batt_type 2>/dev/null   # maker shown in /bateria

HUNG=300            # seconds without heartbeat = bot frozen
log() { echo "$(date) [$1] $2" >> $LOG; }
# Event for the bot's /historial (same format as health.py; no quotes inside the text)
ev() { echo "{\"t\":$(date +%s),\"k\":\"$1\",\"x\":\"$2\"}" >> $EV; }
# Internet check: TCP to port 53 of NET_HOSTS (server.conf; default two public DNS servers)
online() {
  local h
  for h in ${NET_HOSTS:-1.1.1.1 8.8.8.8}; do
    timeout 5 bash -c "</dev/tcp/$h/53" 2>/dev/null && return 0
  done
  return 1
}
put() { echo "$2" > $SYS/$1.tmp && mv $SYS/$1.tmp $SYS/$1; }   # no half-written reads

# --- Shell permissions: Shizuku (rish) -------------------------------------------------
# Shizuku (thedjchi's fork) starts by itself at boot through wireless debugging and its
# service stays alive even if the Wi-Fi hops between access points.
sa() { $D/sa.sh "$1"; }       # as Android's shell user (see sa.sh)
adb_find() { [ "$(sa 'echo OK')" = OK ]; }
# Detached in its own session (setsid): if Android kills Termux suddenly, Shizuku takes down
# the process group of that rish (that is how guard.sh used to die)
export RISH_APPLICATION_ID=com.termux
detached() { timeout -s KILL 20 $D/rish -c "setsid sh -c '$1' </dev/null >/dev/null 2>&1 &" </dev/null >/dev/null 2>&1; }

NETFAIL=0 NETDOWN=0 HUNG_UNTIL=0 WAS="" ADBWAS=""
BOOT0=$(cat $D/boot_time 2>/dev/null || date +%s)

while true; do
  NOW=$(date +%s)
  [ -f $D/server.conf ] && . $D/server.conf
  adb_find; HAVE=$?
  if [ "$HAVE" != "$ADBWAS" ]; then
    if [ "$HAVE" = 0 ]; then
      ev adb "Shizuku disponible: hay control del sistema"
      # No Doze and Wi-Fi always on (Android forgets this on reboot)
      sa 'dumpsys deviceidle disable 2>&1 | cat; settings put global wifi_sleep_policy 2 2>&1 | cat' >/dev/null
    else
      ev adb "Shizuku no responde: /reiniciar del móvil no disponible"
    fi
    ADBWAS=$HAVE
  fi
  # Shell-side guardian (guard.sh): if Android closes Termux, it opens it again. Relaunched
  # every 10 min in case Shizuku restarted (it exits by itself if one is already running).
  if [ $HAVE = 0 ] && [ $((NOW - ${GUARD_AT:-0})) -ge 600 ]; then
    cp $D/guard.sh /sdcard/Download/.srv-guard.sh 2>/dev/null
    sa 'cp /sdcard/Download/.srv-guard.sh /data/local/tmp/srv-guard.sh; chmod 755 /data/local/tmp/srv-guard.sh' >/dev/null
    detached '/data/local/tmp/srv-guard.sh'
    GUARD_AT=$NOW
  fi

  # Leftover temp files of sa.sh when a command was cut short
  find /sdcard/Download -maxdepth 1 -name ".srv-shell-*" -mmin +10 -delete 2>/dev/null

  # --- Optional services that need a USB disk, and the nightly job ------------------------
  # Started if a disk is mounted and relaunched if they die. Disable one: touch ~/server/no-<name>
  if [ -s $SYS/disk ]; then
    for n in $SERVICES; do
      [ -f $D/no-$n ] && continue
      [ -x $D/extras/$n.sh ] || continue
      P=$(cat $D/svc/$n.pid 2>/dev/null)
      # Logs over 1 MB keep their last 200 KB (in place: a running service keeps writing)
      if [ "$(stat -c %s $D/svc/$n.log 2>/dev/null || echo 0)" -gt 1000000 ]; then
        tail -c 200000 $D/svc/$n.log > $D/svc/$n.log.tmp && cat $D/svc/$n.log.tmp > $D/svc/$n.log
        rm -f $D/svc/$n.log.tmp
      fi
      if [ -z "$P" ] || ! kill -0 $P 2>/dev/null; then
        echo "$(date) starting $n" >> $D/svc/$n.log
        setsid nohup $D/extras/$n.sh >> $D/svc/$n.log 2>&1 </dev/null &
        echo $! > $D/svc/$n.pid
      fi
    done
    if [ -n "$NIGHTLY" ] && [ "$(date +%H)" = 04 ] && [ "$(cat $D/nightly.day 2>/dev/null)" != "$(date +%F)" ] && [ ! -f $D/no-nightly ]; then
      date +%F > $D/nightly.day
      ev aviso "trabajo nocturno: $NIGHTLY"
      setsid nohup sh -c "$D/extras/$NIGHTLY" >> $D/svc/nightly.log 2>&1 </dev/null &
    fi
    # Weekly backup of the bot to the disk (WEEKLY_BACKUP=1): Sundays at 04:00
    if [ "$WEEKLY_BACKUP" = 1 ] && [ "$(date +%u%H)" = 704 ] && [ "$(cat $D/backup.day 2>/dev/null)" != "$(date +%F)" ]; then
      date +%F > $D/backup.day
      if $D/extras/backup.sh >> $D/svc/backup.log 2>&1; then
        ev respaldo "respaldo semanal del bot en el disco"
      else
        ev aviso "falló el respaldo semanal en el disco (ver ~/server/svc/backup.log)"
      fi
    fi
  fi

  # --- Battery, uptime and Wi-Fi for the bot -------------------------------------------
  if [ $HAVE = 0 ]; then
    OUT=$(sa 'B=/sys/class/power_supply; for f in capacity status temp voltage_now current_now health technology; do echo "$f=$(cat $B/battery/$f)"; done
              echo "plug=$(cat $B/usb/online)$(cat $B/ac/online)"
              echo "uptime=$(cat /proc/uptime)"; echo "loadavg=$(cat /proc/loadavg)"
              echo "limit=$(settings get system regular_charge_protection_open_power_level 2>&1) $(settings get system regular_charge_protection_switch_state 2>&1)"
              echo "vol=$(sm list-volumes public 2>&1 | grep " mounted " | cut -d" " -f3 | head -1)"
              cmd wifi status 2>&1 | grep -m1 WifiInfo' | tr -d '\r')
    val() { echo "$OUT" | sed -n "s/^$1=//p" | head -1; }
    cap=$(val capacity) status=$(val status) temp=$(val temp)
    case "$(val plug)" in *1*) plugged=1 ;; *) plugged=0 ;; esac
    for f in current_now health technology; do put battery/$f "$(val $f)"; done
    v=$(val voltage_now); [ "${v:-0}" -lt 100000 ] && v=$((${v:-0} * 1000))
    put battery/voltage_now "$v"                 # some phones give mV; the bot expects µV
    put uptime "$(val uptime)"; put loadavg "$(val loadavg)"
    # USB disk mounted (enter.sh binds it). Only when the query worked: if Shizuku did not
    # answer, keep the previous value (otherwise the bot would start without its disk).
    # The .nas marker on the disk root lets the bot tell the real disk from an empty folder.
    if echo "$OUT" | grep -q "^vol="; then
      put disk "$(val vol)"
      v=$(val vol)
      [ -n "$v" ] && [ -d /storage/$v ] && [ ! -f /storage/$v/.nas ] && \
        echo "Disk of the phone server (marker for the bot: do not delete)" > /storage/$v/.nas
    fi
    LIMIT=$CHARGE_LIMIT_DEFAULT
    if [ "$OEM" = oplus ]; then
      set -- $(val limit); LIMIT=$1; [ "$2" = 1 ] || LIMIT=100
    fi
    WI=$(echo "$OUT" | grep -m1 WifiInfo)
    RSSI=$(echo "$WI" | sed -n 's/.*RSSI: \(-\?[0-9]*\).*/\1/p')
    LINK=$(echo "$WI" | grep -o 'Tx Link speed: [0-9]*' | head -1 | grep -o '[0-9]*$')
    FREQ=$(echo "$WI" | sed -n 's/.*Frequency: \([0-9]*\)MHz.*/\1/p')
  else
    J=$(timeout 30 termux-battery-status 2>/dev/null)
    cap=$(echo "$J" | jq -r .percentage) temp=$(echo "$J" | jq -r '.temperature * 10 | floor')
    status=$(echo "$J" | jq -r .status | sed 's/^CHARGING$/Charging/; s/^DISCHARGING$/Discharging/; s/^FULL$/Full/; s/^NOT_CHARGING$/Not charging/')
    [ "$(echo "$J" | jq -r .plugged)" = UNPLUGGED ] && plugged=0 || plugged=1
    put battery/voltage_now "$(( $(echo "$J" | jq -r '.voltage // 0') * 1000 ))"
    put battery/health "$(echo "$J" | jq -r .health | sed 's/^GOOD$/Good/; s/^OVERHEAT$/Overheat/')"
    put battery/technology "$(echo "$J" | jq -r .technology)"
    put uptime "$((NOW - BOOT0)).00 0.00"          # approximate: since Termux's boot
    rm -f $SYS/loadavg                              # no real data: let proot show its own
    LIMIT=$CHARGE_LIMIT_DEFAULT
    W=$(timeout 30 termux-wifi-connectioninfo 2>/dev/null)
    RSSI=$(echo "$W" | jq -r .rssi) LINK=$(echo "$W" | jq -r .link_speed_mbps)
    FREQ=$(echo "$W" | jq -r .frequency_mhz)
  fi
  # Plugged in but not charging = the maker's charge limit has it paused: told to the bot
  # through $OPT/charge_paused ("on pause, living off the charger")
  if [ -n "$cap" ] && [ "$cap" != null ]; then
    PAUSED=0
    [ $plugged = 1 ] && [ "$status" != Charging ] && PAUSED=1
    [ $PAUSED = 1 ] && [ "$status" != Full ] && status=Discharging
    put battery/capacity "$cap"; put battery/temp "$temp"; put battery/status "$status"
    echo $PAUSED > $OPT/charge_paused
    echo "hasta $LIMIT" > $OPT/charge_range                # for /estado and /bateria
    NOWST="$plugged$PAUSED"
    if [ -n "$WAS" ] && [ "$NOWST" != "$WAS" ]; then
      case "$NOWST" in
        11) ev carga "pausa la carga al ${cap}% ($((temp / 10)) °C)" ;;
        10) ev carga "reanuda la carga al ${cap}% ($((temp / 10)) °C)" ;;
      esac
    fi
    WAS=$NOWST
  fi
  [ -n "$RSSI" ] && [ "$RSSI" != null ] && \
    put wifi.json "{\"rssi\": $RSSI, \"link\": ${LINK:-null}, \"freq\": ${FREQ:-null}}"

  # --- /reiniciar ---------------------------------------------------------------------------
  if [ -f $REQ ]; then
    what=$(cat $REQ); rm -f $REQ
    case "$what" in
      adb)   log adb "restart requested by /reiniciar adb: SSH"
             pkill -x sshd; sshd ;;
      wifi)  log red "reconnect requested by /reiniciar wifi"
             if [ $HAVE = 0 ]; then detached 'svc wifi disable; sleep 5; svc wifi enable'
             else termux-wifi-enable false; sleep 5; termux-wifi-enable true; fi ;;
      phone) log sistema "reboot requested by /reiniciar"
             if [ $HAVE = 0 ]; then detached 'sleep 2; svc power reboot'
             else ev aviso "no pude reiniciar el móvil: Shizuku no responde"; fi ;;
    esac
  fi

  # --- The bot service ----------------------------------------------------------------------
  BPID=$(cat $D/bot.pid 2>/dev/null)
  if [ -f $D/BOT_ENABLED ] && { [ -z "$BPID" ] || ! grep -q bot.sh /proc/$BPID/cmdline 2>/dev/null; }; then
    if [ -f $D/deploying ]; then   # tools/noroot-deploy.sh stopped it on purpose: not a crash
      rm -f $D/deploying
      log salud "deploy: relaunching bot.sh"
      ev actualizacion "código nuevo desplegado"
    else
      log salud "bot.sh was not running, relaunching it"
      ev caida "el servicio del bot no estaba corriendo; relanzado"
    fi
    pkill -9 -f "[o]pt/bot/bot.py"   # the orphan bot of a dead service (same token)
    $D/bot.sh
  fi

  # Heartbeat: the bot's main loop writes the time to $HB on every pass (at most ~70 s
  # apart). Older than 5 min with the process alive = frozen.
  if [ -f $HB ] && [ $NOW -gt $HUNG_UNTIL ]; then
    LAST=$(cat $HB 2>/dev/null); LAST=${LAST%.*}; LAST=${LAST:-$NOW}
    if [ $((NOW - LAST)) -gt $HUNG ] && pgrep -f "[o]pt/bot/bot.py" >/dev/null; then
      log salud "bot frozen $((NOW - LAST))s, restarting"
      ev colgado "el bot no respondía ($((NOW - LAST)) s sin señal de vida); reiniciado"
      pkill -9 -f "[o]pt/bot/bot.py"   # -9: a frozen process may ignore SIGTERM
      HUNG_UNTIL=$((NOW + 600))
    fi
  fi

  # --- Network: 5 minutes without Internet -> cycle Wi-Fi --------------------------------------
  if online; then
    NETFAIL=0
    if [ $NETDOWN -gt 0 ]; then ev wifi "Internet volvió tras reiniciar el Wi-Fi"; NETDOWN=0; fi
  else
    NETFAIL=$((NETFAIL + 1))
    if [ $NETFAIL -ge 5 ]; then
      log red "no Internet for 5 min, cycling Wi-Fi"
      ev wifi "5 min sin Internet: reinicio el Wi-Fi"
      if [ $HAVE = 0 ]; then detached 'svc wifi disable; sleep 5; svc wifi enable'
      else termux-wifi-enable false; sleep 5; termux-wifi-enable true; fi
      NETFAIL=0; NETDOWN=1
    fi
  fi
  [ -n "$ONCE" ] && break
  sleep 60
done
