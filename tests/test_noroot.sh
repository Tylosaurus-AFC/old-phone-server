#!/usr/bin/env bash
# Smoke test of phone/noroot/charge.sh with a FAKE Shizuku (sa.sh) and a fake Termux home: one pass
# (ONCE=1) per scenario. Checks what it hands the bot (battery, charge state, Wi-Fi), the
# BOT_ENABLED latch and the USB-disk service gate. No phone needed.
set -u
# NET_HOSTS=127.0.0.1 in each server.conf: the Internet check fails at once instead of
# waiting 5 s per public host (no network in CI / sandboxes).
HERE="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS + 1)); echo "ok   - $1"
          else FAIL=$((FAIL + 1)); echo "FAIL - $1 (expected '$2', got '$3')"; fi; }

# Termux-only commands the script calls
S="$T/shims"; mkdir -p "$S"
# setsid is missing on some PCs (Git Bash): a pass-through stand-in is enough here
for c in getprop pkill termux-wake-lock; do printf '#!/bin/sh\nexit 0\n' > "$S/$c"; done
printf '#!/bin/sh\nexit 1\n' > "$S/pgrep"
printf '#!/bin/sh
exec "$@"
' > "$S/setsid"
chmod +x "$S"/*

setup() {    # setup <conf lines...>; plain battery/Wi-Fi report in $T/out
  rm -rf "$T/home" "$T/prefix"; mkdir -p "$T/home/server/extras" "$T/prefix"
  OPT="$T/prefix/var/lib/proot-distro/containers/bot/rootfs/opt/bot"; mkdir -p "$OPT"
  printf '%s\n' "$@" > "$T/home/server/server.conf"
  # fake sa.sh: "echo OK" -> OK; the big status query -> $T/out
  printf '#!/bin/sh\ncase "$1" in "echo OK") echo OK ;; *capacity*) cat "%s/out" ;; *"# keepalive"*) echo "$1" >> "%s/keepalive.log" ;; esac\n' "$T" "$T" > "$T/home/server/sa.sh"
  chmod +x "$T/home/server/sa.sh"
}
report() {   # report <capacity> <status> <plug> <voltage> <limit> <vol>
  cat > "$T/out" <<EOF
capacity=$1
status=$2
temp=301
voltage_now=$4
current_now=-100
health=Good
technology=Li-poly
plug=$3
uptime=1234.56 2000.00
loadavg=0.10 0.20 0.30 1/200 999
limit=$5
vol=$6
WifiInfo: SSID: x, RSSI: -61, Tx Link speed: 433Mbps, Frequency: 5180MHz
EOF
}
run() { HOME="$T/home" PREFIX="$T/prefix" PATH="$S:$PATH" ONCE=1 bash "$HERE/phone/noroot/charge.sh" >/dev/null 2>&1; RC=$?; }
O() { cat "$OPT/$1" 2>/dev/null; }

setup "OEM=" "NET_HOSTS=127.0.0.1"
report 50 Charging 10 4200 "80 1" ""; run
check "charging at 50%: not paused" 0 "$(O charge_paused)"
check "battery capacity handed to the bot" 50 "$(O sys/battery/capacity)"
check "temperature handed to the bot" 301 "$(O sys/battery/temp)"
check "voltage mV converted to microvolts" 4200000 "$(O sys/battery/voltage_now)"
check "uptime handed to the bot" "1234.56 2000.00" "$(O sys/uptime)"
check "Wi-Fi json for the bot" '{"rssi": -61, "link": 433, "freq": 5180}' "$(O sys/wifi.json)"
check "no OEM: default limit shown" "hasta 80" "$(O charge_range)"

report 80 "Not charging" 10 4300000 "80 1" ""; run
check "plugged in, not charging: reported as paused" 1 "$(O charge_paused)"
check "paused status is shown as Discharging (living off the charger)" Discharging "$(O sys/battery/status)"
check "voltage already in microvolts is kept" 4300000 "$(O sys/battery/voltage_now)"

report 80 Full 10 4300000 "80 1" ""; run
check "Full is not 'paused' status-wise (stays Full)" Full "$(O sys/battery/status)"

report 70 Discharging 00 4000 "80 1" ""; run
check "unplugged: not paused (a real power cut)" 0 "$(O charge_paused)"

setup "OEM=oplus" "NET_HOSTS=127.0.0.1"
report 60 Charging 10 4200 "75 1" ""; run
check "oplus: charge limit read from the phone" "hasta 75" "$(O charge_range)"
report 60 Charging 10 4200 "75 0" ""; run
check "oplus: limiter switched off -> 100" "hasta 100" "$(O charge_range)"

# BOT_ENABLED latch: charge.sh must not start bot.sh without the file
setup "OEM=" "NET_HOSTS=127.0.0.1"
report 50 Charging 10 4200 "80 1" ""
printf '#!/bin/sh\ntouch "%s/bot-started"\n' "$T" > "$T/home/server/bot.sh"; chmod +x "$T/home/server/bot.sh"
rm -f "$T/bot-started"; run
[ -f "$T/bot-started" ] && r=started || r=not-started
check "no BOT_ENABLED: bot.sh not started" not-started "$r"
touch "$T/home/server/BOT_ENABLED"; run
[ -f "$T/bot-started" ] && r=started || r=not-started
check "BOT_ENABLED present: bot.sh started" started "$r"

# USB-disk services: started only with a disk mounted, and a no-<name> file disables one
setup "SERVICES=\"a b\"" "NET_HOSTS=127.0.0.1"
printf '#!/bin/sh\ntouch "%s/svc-a"; sleep 1\n' "$T" > "$T/home/server/extras/a.sh"
printf '#!/bin/sh\ntouch "%s/svc-b"; sleep 1\n' "$T" > "$T/home/server/extras/b.sh"
chmod +x "$T/home/server/extras/"*.sh
rm -f "$T/svc-a" "$T/svc-b"
report 50 Charging 10 4200 "80 1" ""; run; sleep 0.5
[ -f "$T/svc-a" ] && r=started || r=not-started
check "no disk: service not started" not-started "$r"
touch "$T/home/server/no-b"
# the disk id is written during a pass and the services are checked at the start of the
# next one (a minute later in real life): two passes
report 50 Charging 10 4200 "80 1" "ABCD-1234"; run; run; sleep 3
[ -f "$T/svc-a" ] && r=started || r=not-started
check "disk mounted: service a started" started "$r"
[ -f "$T/svc-b" ] && r=started || r=not-started
check "no-b file: service b disabled" not-started "$r"
check "disk id handed to enter.sh" "ABCD-1234" "$(O sys/disk)"

# Shizuku down AND Termux:API answering nothing (not installed / timed out): the pass must
# still reach the bot service (it used to die on arithmetic over an empty voltage)
setup "OEM=" "NET_HOSTS=127.0.0.1"
printf '#!/bin/sh\nexit 0\n' > "$T/home/server/sa.sh"              # Shizuku silent
printf '#!/bin/sh\nexit 0\n' > "$S/termux-battery-status"; printf '#!/bin/sh\nexit 0\n' > "$S/termux-wifi-connectioninfo"
chmod +x "$S/termux-battery-status" "$S/termux-wifi-connectioninfo"
printf '#!/bin/sh\ntouch "%s/bot-started"\n' "$T" > "$T/home/server/bot.sh"; chmod +x "$T/home/server/bot.sh"
touch "$T/home/server/BOT_ENABLED"; rm -f "$T/bot-started"; run
[ -f "$T/bot-started" ] && r=started || r=not-started
check "no Shizuku, empty Termux:API: the pass still relaunches the bot" started "$r"
printf '#!/bin/sh\necho "{\\"percentage\\": 55, \\"temperature\\": 30.4, \\"status\\": \\"CHARGING\\", \\"plugged\\": \\"PLUGGED_AC\\", \\"voltage\\": 4215, \\"health\\": \\"GOOD\\"}"\n' > "$S/termux-battery-status"
rm -f "$T/bot-started"; run
check "no Shizuku, Termux:API battery: capacity handed to the bot" 55 "$(O sys/battery/capacity)"
check "no Shizuku, Termux:API battery: voltage mV -> microvolts" 4215000 "$(O sys/battery/voltage_now)"
rm -f "$S/termux-battery-status" "$S/termux-wifi-connectioninfo"

# A corrupt heartbeat file (half-written, disk full) must not abort the pass
setup "OEM=" "NET_HOSTS=127.0.0.1"
report 50 Charging 10 4200 "80 1" ""
printf '17x\n' > "$OPT/heartbeat"; run
check "corrupt heartbeat: the pass completes (exit 0)" 0 "$RC"

# doctor.sh report: a broken run (disk full -> empty output) must not replace the good one
setup "OEM=" "NET_HOSTS=127.0.0.1"
report 50 Charging 10 4200 "80 1" ""
mkdir -p "$OPT/sys"; printf 'RESULT: ok (0 fail, 0 warn) x\nOK   good\n' > "$OPT/sys/doctor.txt"
printf '#!/bin/sh\nexit 0\n' > "$T/home/server/doctor.sh"; chmod +x "$T/home/server/doctor.sh"
HOME="$T/home" PREFIX="$T/prefix" PATH="$S:$PATH" ONCE=1 bash -c "sed 's/^DOC_AT=.*/DOC_AT=0/' '$HERE/phone/noroot/charge.sh' | bash" >/dev/null 2>&1
check "empty doctor run: the previous report is kept" yes "$(grep -q 'OK   good' "$OPT/sys/doctor.txt" && echo yes || echo no)"
printf '#!/bin/sh\necho "RESULT: degraded (0 fail, 1 warn) y"\n' > "$T/home/server/doctor.sh"
HOME="$T/home" PREFIX="$T/prefix" PATH="$S:$PATH" ONCE=1 bash -c "sed 's/^DOC_AT=.*/DOC_AT=0/' '$HERE/phone/noroot/charge.sh' | bash" >/dev/null 2>&1
check "complete doctor run: the report is replaced" yes "$(grep -q 'RESULT: degraded' "$OPT/sys/doctor.txt" && echo yes || echo no)"

# Keep-alive settings through Shizuku: applied when Shizuku answers, unless KEEPALIVE=0
setup "OEM=" "NET_HOSTS=127.0.0.1"
report 50 Charging 10 4200 "80 1" ""
rm -f "$T/keepalive.log"; run
check "keepalive: applied when Shizuku answers" yes "$(grep -q 'deviceidle whitelist +$p' "$T/keepalive.log" 2>/dev/null && echo yes || echo no)"
check "keepalive: covers the phantom process killer (12L+ and 12)" "yes yes" \
  "$(grep -q settings_enable_monitor_phantom_procs "$T/keepalive.log" && echo yes || echo no) $(grep -q max_phantom_processes "$T/keepalive.log" && echo yes || echo no)"
check "keepalive: never disables Android's config sync" no "$(grep -q set_sync_disabled "$T/keepalive.log" && echo yes || echo no)"
setup "OEM=" "NET_HOSTS=127.0.0.1" "KEEPALIVE=0"
rm -f "$T/keepalive.log"; run
check "KEEPALIVE=0: nothing applied" no "$([ -f "$T/keepalive.log" ] && echo yes || echo no)"

# boot.sh: running it again (Termux reopened) must not start a second watchdog loop
setup "OEM=" "NET_HOSTS=127.0.0.1"
printf '#!/bin/sh\nexit 0\n' > "$S/sshd"; chmod +x "$S/sshd"
printf '#!/bin/sh\nsleep 1\n' > "$T/home/server/charge.sh"; chmod +x "$T/home/server/charge.sh"
boot() { HOME="$T/home" PREFIX="$T/prefix" PATH="$S:$PATH" sh "$HERE/phone/noroot/boot.sh" >/dev/null 2>&1; }
loops() { n=0; for p in $(pgrep -f "[w]hile true; do $T/home/server/charge.sh" 2>/dev/null); do n=$((n + 1)); done; echo $n; }
boot; sleep 0.5; boot; sleep 0.5; boot; sleep 0.5
check "boot.sh run 3 times: one watchdog loop" 1 "$(loops)"
L=$(cat "$T/home/server/loop.pid"); pkill -P $L 2>/dev/null; kill $L 2>/dev/null; sleep 0.3
boot; sleep 0.5
check "boot.sh after the loop died: starts a new one" 1 "$(loops)"
L=$(cat "$T/home/server/loop.pid"); pkill -P $L 2>/dev/null; kill $L 2>/dev/null

echo "---- $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
