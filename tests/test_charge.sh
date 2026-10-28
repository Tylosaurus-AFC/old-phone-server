#!/usr/bin/env bash
# Smoke test of phone/charge.sh against a FAKE battery and filesystem (no phone needed).
# It runs one pass of the watchdog (ONCE=1) per scenario and checks the battery logic:
# pause above HIGH, resume below LOW, always charge under FLOOR, stop when hot, the three
# BATT_CTRL drivers, and the "pause not applied" re-write.
#   tests/run.sh      (runs this and the Python tests)
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0

# `$BB cmd args` just runs `cmd args` on the PC
printf '#!/bin/sh\nexec "$@"\n' > "$T/bbshim"; chmod +x "$T/bbshim"

setup() {   # setup <ctrl> <ctl_file_value> <capacity> <temp> <status>
  rm -rf "$T/d" "$T/batt"; mkdir -p "$T/d/fs/opt/bot" "$T/batt"
  echo "$3" > "$T/batt/capacity"; echo "$4" > "$T/batt/temp"; echo "$5" > "$T/batt/status"
  case "$1" in
    slate)  echo "$2" > "$T/batt/batt_slate_mode" ;;
    enable) echo "$2" > "$T/batt/charging_enabled" ;;
  esac
  printf 'BATT=%s\nBATT_CTRL=%s\nLOW=40\nHIGH=60\nMAXTEMP=420\nFLOOR=15\n' "$T/batt" "$1" > "$T/d/server.conf"
}
run() { DEBIAN="$T/d" BB="$T/bbshim" ONCE=1 sh "$HERE/phone/charge.sh" >/dev/null 2>&1; }
check() {   # check <name> <expected> <actual>
  if [ "$2" = "$3" ]; then PASS=$((PASS + 1)); echo "ok   - $1"
  else FAIL=$((FAIL + 1)); echo "FAIL - $1 (expected '$2', got '$3')"; fi
}

# Samsung "slate" driver: 1 = charger off
setup slate 0 70 300 Charging; run
check "slate: 70% charging  -> pause"            1 "$(cat "$T/batt/batt_slate_mode")"
check "slate: bot told the charge is paused"     1 "$(cat "$T/d/fs/opt/bot/charge_paused")"
grep -q 'pausa la carga al 70%' "$T/d/fs/opt/bot/events.jsonl" && r=yes || r=no
check "slate: event written for /historial"    yes "$r"

setup slate 1 35 300 Discharging; run
check "slate: 35% paused   -> resume"            0 "$(cat "$T/batt/batt_slate_mode")"

setup slate 1 50 300 Discharging; run
check "slate: 50% paused   -> stay paused"       1 "$(cat "$T/batt/batt_slate_mode")"

setup slate 0 50 300 Charging; run
check "slate: 50% charging -> keep charging"     0 "$(cat "$T/batt/batt_slate_mode")"

setup slate 1 10 300 Discharging; run
check "slate: 10% (below FLOOR) -> always charge" 0 "$(cat "$T/batt/batt_slate_mode")"

setup slate 0 50 450 Charging; run
check "slate: 45 C -> stop charging"             1 "$(cat "$T/batt/batt_slate_mode")"

# Paused but the driver keeps charging: the pause is written again (1 -> 0 -> 1)
setup slate 1 50 300 Charging; run
check "slate: pause not applied -> re-applied"   1 "$(cat "$T/batt/batt_slate_mode")"
grep -q 'no se aplicaba' "$T/d/fs/opt/bot/events.jsonl" && r=yes || r=no
check "slate: re-apply event written"          yes "$r"

# Qualcomm/Moto "charging_enabled" driver: 0 = charger off
setup enable 1 70 300 Charging; run
check "enable: 70% -> charging_enabled=0"        0 "$(cat "$T/batt/charging_enabled")"
check "enable: bot told the charge is paused"    1 "$(cat "$T/d/fs/opt/bot/charge_paused")"
setup enable 0 35 300 Discharging; run
check "enable: 35% -> charging_enabled=1"        1 "$(cat "$T/batt/charging_enabled")"

# No control available: nothing is touched
setup none 0 90 300 Charging; run
check "none: bot told the charge is not paused"  0 "$(cat "$T/d/fs/opt/bot/charge_paused")"
check "none: range shown as unknown"             "—" "$(cat "$T/d/fs/opt/bot/charge_range")"

# BOT_ENABLED gate: charge.sh must not start bot.sh when the file is missing
setup slate 0 50 300 Charging
printf '#!/bin/sh\ntouch "%s/bot-started"\n' "$T" > "$T/d/bot.sh"; chmod +x "$T/d/bot.sh"
run
[ -f "$T/bot-started" ] && r=started || r=not-started
check "gate: no BOT_ENABLED -> bot.sh not started" not-started "$r"
touch "$T/d/BOT_ENABLED"; run
[ -f "$T/bot-started" ] && r=started || r=not-started
check "gate: BOT_ENABLED present -> bot.sh started" started "$r"

# Long Internet outage (6 simulated hours: fake date/sleep move a clock): Wi-Fi restarted
# after 5 min, then 10, 20, 40, 60 min apart -- not every 5 min (that was 72 restarts)
setup none 0 50 300 Charging
S="$T/shims"; mkdir -p "$S"; echo 1800000000 > "$T/clock"
printf '#!/bin/sh\ncase "$1" in +%%s) cat "%s/clock" ;; *) exec /bin/date "$@" ;; esac\n' "$T" > "$S/date"
printf '#!/bin/sh\nn=${1%%%%.*}; echo $(( $(cat "%s/clock") + ${n:-0} )) > "%s/clock"\n' "$T" "$T" > "$S/sleep"
printf '#!/bin/sh\nexit 1\n' > "$S/ping"
printf '#!/bin/sh\necho "$*" >> "%s/svc.log"\n' "$T" > "$S/svc"
chmod +x "$S"/*
DEBIAN="$T/d" BB="$T/bbshim" PATH="$S:$PATH" ONCE=360 sh "$HERE/phone/charge.sh" >/dev/null 2>&1
n=$(grep -c 'reinicio el Wi-Fi' "$T/d/fs/opt/bot/events.jsonl" 2>/dev/null || true)
check "6 h without Internet: Wi-Fi restarts back off (8, not 72)" yes "$([ "${n:-0}" -ge 5 ] && [ "${n:-0}" -le 10 ] && echo yes || echo "no ($n)")"
check "6 h without Internet: each restart says how long it has been" yes "$(grep -q '135 min sin Internet' "$T/d/fs/opt/bot/events.jsonl" && echo yes || echo no)"

echo "---- $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
