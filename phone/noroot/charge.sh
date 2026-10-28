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
put() { echo "$2" > $SYS/$1.tmp && mv $SYS/$1.tmp $SYS/$1; }   # no half-written reads
# Whole number or 0: values read from Android may be empty or "null", and bash arithmetic on
# them aborts the whole script (then nothing after it in the pass runs: bot relaunch, hang check...)
int() { case "$1" in -[0-9]*|[0-9]*) echo "${1%%[!0-9-]*}" ;; *) echo 0 ;; esac; }

# --- Shell permissions: Shizuku (rish) -------------------------------------------------
# Shizuku (thedjchi's fork) starts by itself at boot through wireless debugging and its
# service stays alive even if the Wi-Fi hops between access points.
sa() { $D/sa.sh "$1"; }       # as Android's shell user (see sa.sh)
adb_find() { [ "$(sa 'echo OK')" = OK ]; }
# Detached in its own session (setsid): if Android kills Termux suddenly, Shizuku takes down
# the process group of that rish (that is how guard.sh used to die)
export RISH_APPLICATION_ID=com.termux
detached() { timeout -s KILL 20 $D/rish -c "setsid sh -c '$1' </dev/null >/dev/null 2>&1 &" </dev/null >/dev/null 2>&1; }

# Keep Android from freezing or killing Termux (KEEPALIVE=0 in server.conf turns it off). The
# same settings docs/*/12-*.md asks for by hand, re-applied because Android and the phone
# maker can undo them: no battery optimisation for the Termux apps, background activity
# allowed, "active" standby bucket, and the child-process killer off (Android 12L+: a
# setting; Android 12: a device_config limit that Google Play services may reset, so it is
# simply set again every 30 min instead of disabling the config sync).
# The Shizuku app itself is exempted too: when Android freezes it, rish times out.
# After applying, the values are read back in the same call: a setting Android or the maker
# refuses is reported once (event "aviso") and then retried less and less often (30 min,
# 1 h, 2 h... up to 6 h) instead of hammering it every pass.
keepalive() {
  local out bad=""
  out=$(sa '# keepalive
      for p in com.termux com.termux.boot com.termux.api moe.shizuku.privileged.api; do dumpsys deviceidle whitelist +$p 2>&1 | cat; done
      cmd appops set com.termux RUN_ANY_IN_BACKGROUND allow 2>&1 | cat
      for o in RUN_IN_BACKGROUND RUN_ANY_IN_BACKGROUND; do cmd appops set moe.shizuku.privileged.api $o allow 2>&1 | cat; done
      am set-standby-bucket com.termux active 2>&1 | cat
      S=$(getprop ro.build.version.sdk)
      if [ "$S" -ge 32 ]; then settings put global settings_enable_monitor_phantom_procs false 2>&1 | cat
      elif [ "$S" = 31 ]; then device_config put activity_manager max_phantom_processes 2147483647 2>&1 | cat; fi
      echo "chk_sdk=$S"
      echo "chk_idle=$(dumpsys deviceidle whitelist 2>&1 | grep -c ",com.termux,")"
      echo "chk_bg=$(cmd appops get com.termux RUN_ANY_IN_BACKGROUND 2>&1 | head -1)"
      echo "chk_phantom=$(settings get global settings_enable_monitor_phantom_procs 2>&1)"
      echo "chk_maxph=$(device_config get activity_manager max_phantom_processes 2>&1)"' | tr -d '\r')
  kv() { echo "$out" | sed -n "s/^chk_$1=//p" | head -1; }
  [ -z "$out" ] && return 0                    # no answer: Shizuku went away meanwhile
  [ "$(kv idle)" -ge 1 ] 2>/dev/null || bad="$bad exención de batería de Termux,"
  case "$(kv bg)" in *ignore*|*deny*) bad="$bad actividad en segundo plano," ;; esac
  S=$(kv sdk)
  if [ "${S:-0}" -ge 32 ] 2>/dev/null; then [ "$(kv phantom)" = false ] || bad="$bad límite de procesos de Android,"
  elif [ "$S" = 31 ]; then [ "$(kv maxph)" -ge 1000 ] 2>/dev/null || bad="$bad límite de procesos de Android,"; fi
  if [ -n "$bad" ]; then
    KEEP_FAIL=$((KEEP_FAIL + 1))
    [ $KEEP_FAIL = 1 ] && ev aviso "Android no aceptó:${bad%,} (ver doctor.sh)"
    return 1
  fi
  [ $KEEP_FAIL -gt 0 ] && ev adb "ajustes anti-cierre aplicados por fin"
  KEEP_FAIL=0
}

# The bot cannot report its own death: if its heartbeat stops for 15 min while online, the
# watchdog tells the owner itself (Telegram Bot API through curl). One message per incident,
# retried every 10 min only until Telegram confirms it ("ok":true); the bot reports its own
# recovery when it comes back (report_crashes). The token goes to curl on stdin (-K -), not
# on the command line. BOTDOWN_ALERT=0 in server.conf turns it off.
tg_owner() {   # tg_owner "text" -> 0 only if Telegram confirmed the message
  local tok own
  tok=$(head -1 $OPT/token 2>/dev/null); own=$(head -1 $OPT/owners 2>/dev/null)
  [ -n "$tok" ] && [ -n "$own" ] && command -v curl >/dev/null || return 1
  printf 'url = "https://api.telegram.org/bot%s/sendMessage"\ndata-urlencode = "chat_id=%s"\ndata-urlencode = "text=%s"\n' \
    "$tok" "$own" "$1" | timeout 40 curl -sS -m 30 -K - 2>/dev/null | grep -q '"ok":true'
}
botdown_check() {
  local age
  [ -f $D/BOT_ENABLED ] && [ "${BOTDOWN_ALERT:-1}" != 0 ] || { rm -f $D/botdown; return; }
  age=$(( NOW - $(int "$(cat $HB 2>/dev/null)") ))
  if [ ! -f $HB ] || [ $age -lt 900 ]; then
    rm -f $D/botdown; return                      # alive (or never started yet)
  fi
  [ -f $D/botdown ] || echo "start=$NOW sent=0 next=0" > $D/botdown
  . $D/botdown 2>/dev/null
  [ "${sent:-0}" = 1 ] || [ $NOW -lt "${next:-0}" ] || ! online && return
  if tg_owner "⚠️ El bot no responde desde las $(date -d @$((NOW - age)) +%H:%M 2>/dev/null || echo '?') (sin señal de vida hace $((age / 60)) min). El vigilante lo está reiniciando; si no vuelve, revisa el móvil o ejecuta tools/noroot-doctor.sh."; then
    echo "start=$start sent=1 next=0" > $D/botdown
    ev aviso "el vigilante avisó por Telegram: el bot no responde"
  else
    echo "start=$start sent=0 next=$((NOW + 600))" > $D/botdown
  fi
}

# Shizuku state, for the bot (/salud, alerts) and doctor.sh: $SYS/shizuku (key=value).
# Which Shizuku: the official app and the thedjchi fork share the package name; only the
# fork's versionName ends in "-thedjchi", and only the fork has the START receiver. Read
# while Shizuku works (dumpsys needs it) and remembered across restarts in $SYS/shizuku.
# A user who stops Shizuku on purpose creates ~/server/no-shizuku-restart: no START then.
# When it is down: why (shizuku.sh probe), checks only every 5 min after the first 10 min
# (each failed check costs ~40 s of rish time-outs), and, if SHIZUKU_AUTH is set, asks the
# fork to start itself with growing gaps (2, 5, 10, 30 min, then every 30 min), never
# during the first 5 min after boot (the fork starts by itself then) nor while offline.
shizuku_check() {
  adb_find; HAVE=$?
  if [ $HAVE = 0 ]; then
    if [ "$SHZ_STATE" != ok ] || [ -z "$SHZ_VERSION" ]; then
      SHZ_VERSION=$(sa 'dumpsys package moe.shizuku.privileged.api 2>&1 | grep -m1 -o "versionName=[^ ]*"' | tr -d '\r' | sed 's/^versionName=//')
      case "$SHZ_VERSION" in *thedjchi*) SHZ_VARIANT=fork ;; "") ;; *) SHZ_VARIANT=official ;; esac
    fi
    SHZ_STATE=ok SHZ_DETAIL="" SHZ_SINCE=0 SHZ_TRIES=0 SHZ_TRY_AT=0 SHZ_CHECK_AT=0
  else
    P=$(bash $D/shizuku.sh probe 2>/dev/null)          # one rish call: state + detail
    SHZ_STATE=$(echo "$P" | sed -n 1p); SHZ_STATE=${SHZ_STATE:-unknown}
    SHZ_DETAIL=$(echo "$P" | sed -n 2p | tr -d '"\\')
    [ "$SHZ_STATE" = ok ] && SHZ_STATE=flaky       # rish answered but sa.sh did not
    [ $SHZ_SINCE = 0 ] && SHZ_SINCE=$NOW
    [ $((NOW - SHZ_SINCE)) -ge 600 ] && SHZ_CHECK_AT=$((NOW + 300))
    case "$SHZ_STATE" in
      not-running|app-unreachable)
        if [ -n "${SHIZUKU_AUTH:-}" ] && [ "$SHZ_VARIANT" != official ] && [ ! -f $D/no-shizuku-restart ] \
           && [ $NOW -ge $SHZ_TRY_AT ] && [ $((NOW - BOOT0)) -ge 300 ] && online; then
          SHZ_TRIES=$((SHZ_TRIES + 1))
          if bash $D/shizuku.sh start; then ev adb "Shizuku parado ($SHZ_STATE): le pido que arranque (intento $SHZ_TRIES)"
          else ev aviso "no pude mandar la orden de arranque a Shizuku (intento $SHZ_TRIES)"; fi
          case $SHZ_TRIES in 1) G=120 ;; 2) G=300 ;; 3) G=600 ;; *) G=1800 ;; esac
          SHZ_TRY_AT=$((NOW + G))
        fi ;;
    esac
  fi
  printf 'state=%s\nsince=%s\ntries=%s\nauth=%s\nchecked=%s\nboot=%s\ndetail=%s\nvariant=%s\nversion=%s\npaused=%s\n' \
    "$SHZ_STATE" "$SHZ_SINCE" "$SHZ_TRIES" "$([ -n "${SHIZUKU_AUTH:-}" ] && echo 1 || echo 0)" "$NOW" "$BOOT0" \
    "$SHZ_DETAIL" "$SHZ_VARIANT" "$SHZ_VERSION" "$([ -f $D/no-shizuku-restart ] && echo 1 || echo 0)" > $SYS/shizuku.tmp \
    && mv $SYS/shizuku.tmp $SYS/shizuku
}

NETFAIL=0 NETDOWN=0 NETWAIT=5 NETOFF=0 HUNG_UNTIL=0 WAS="" ADBWAS="" KEEP_AT=0 KEEP_FAIL=0 HAVE=1
SHZ_STATE=unknown SHZ_DETAIL="" SHZ_SINCE=0 SHZ_TRIES=0 SHZ_TRY_AT=0 SHZ_CHECK_AT=0
SHZ_VARIANT=$(sed -n 's/^variant=//p' $SYS/shizuku 2>/dev/null)     # known from a previous run
SHZ_VERSION=$(sed -n 's/^version=//p' $SYS/shizuku 2>/dev/null)
DOC_AT=$(( $(date +%s) - 3000 ))   # first check 10 min after start: Shizuku needs time at boot
BOOT0=$(cat $D/boot_time 2>/dev/null || date +%s)

while true; do
  NOW=$(date +%s)
  [ -f $D/server.conf ] && . $D/server.conf
  [ $NOW -ge $SHZ_CHECK_AT ] && shizuku_check
  if [ "$HAVE" != "$ADBWAS" ]; then
    if [ "$HAVE" = 0 ]; then
      ev adb "Shizuku disponible: hay control del sistema"
      # No Doze and Wi-Fi always on (Android forgets this on reboot)
      sa 'dumpsys deviceidle disable 2>&1 | cat; settings put global wifi_sleep_policy 2 2>&1 | cat' >/dev/null
    else
      ev adb "Shizuku no responde ($SHZ_STATE): /reiniciar del móvil no disponible"
    fi
    ADBWAS=$HAVE
    KEEP_AT=0                     # Shizuku (re)appeared: apply the keep-alive settings now
  fi
  if [ $HAVE = 0 ] && [ "${KEEPALIVE:-1}" != 0 ] && [ $NOW -ge $KEEP_AT ]; then
    if keepalive; then KEEP_AT=$((NOW + 1800))
    else G=$((1800 << (KEEP_FAIL > 4 ? 4 : KEEP_FAIL - 1))); [ $G -gt 21600 ] && G=21600; KEEP_AT=$((NOW + G)); fi
  fi
  # Health check (doctor.sh) every hour, for the bot's /salud and /diagnostico
  if [ $((NOW - DOC_AT)) -ge 3600 ] && [ -x $D/doctor.sh ]; then
    $D/doctor.sh > $SYS/doctor.txt.tmp 2>&1; mv $SYS/doctor.txt.tmp $SYS/doctor.txt
    DOC_AT=$NOW
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
    v=$(int "$(val voltage_now)"); [ "$v" -lt 100000 ] && v=$((v * 1000))
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
    put battery/voltage_now "$(( $(int "$(echo "$J" | jq -r '.voltage // 0' 2>/dev/null)") * 1000 ))"
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
    temp=$(int "$temp")
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
    LAST=$(int "$(cat $HB 2>/dev/null)"); [ "$LAST" = 0 ] && LAST=$NOW   # empty/corrupt: no verdict
    if [ $((NOW - LAST)) -gt $HUNG ] && pgrep -f "[o]pt/bot/bot.py" >/dev/null; then
      log salud "bot frozen $((NOW - LAST))s, restarting"
      ev colgado "el bot no respondía ($((NOW - LAST)) s sin señal de vida); reiniciado"
      pkill -9 -f "[o]pt/bot/bot.py"   # -9: a frozen process may ignore SIGTERM
      HUNG_UNTIL=$((NOW + 600))
    fi
  fi

  botdown_check

  # --- Network: no Internet -> cycle Wi-Fi after 5 min, then after 10, 20, 40, 60, 60... ----
  # The first cycle fixes a stuck Wi-Fi; in a long router/ISP outage cycling every 5 min
  # helps nothing and floods /historial (a 24 h outage used to mean 288 cycles).
  if online; then
    NETFAIL=0 NETWAIT=5 NETOFF=0
    if [ $NETDOWN -gt 0 ]; then ev wifi "Internet volvió tras reiniciar el Wi-Fi"; NETDOWN=0; fi
  else
    NETFAIL=$((NETFAIL + 1)) NETOFF=$((NETOFF + 1))
    if [ $NETFAIL -ge $NETWAIT ]; then
      NETWAIT=$((NETWAIT * 2)); [ $NETWAIT -gt 60 ] && NETWAIT=60
      log red "no Internet for $NETOFF min, cycling Wi-Fi (next try in $NETWAIT min)"
      ev wifi "$NETOFF min sin Internet: reinicio el Wi-Fi (siguiente intento en $NETWAIT min)"
      if [ $HAVE = 0 ]; then detached 'svc wifi disable; sleep 5; svc wifi enable'
      else termux-wifi-enable false; sleep 5; termux-wifi-enable true; fi
      NETFAIL=0; NETDOWN=1
    fi
  fi
  # ONCE=N: N passes and stop (tests; ONCE=1 = a single pass)
  if [ -n "$ONCE" ]; then ONCE=$((ONCE - 1)); [ $ONCE -le 0 ] && break; fi
  sleep 60
done
