#!/usr/bin/env bash
# Long simulated runs of the no-root watchdog with scheduled and random faults
# (harness: tests/longrun_env.sh). Simulated hours are a test of the LOGIC (bounded retries,
# no silent stop, consistent state); they are not a 72 h test on a phone.
#   bash tests/test_longrun.sh                 short versions (run by tests/run.sh, ~2 min)
#   LONG=1 bash tests/test_longrun.sh          12 h, 24 h, 48 h and 72 h versions (~30 min)
#   SEED=123 bash tests/test_longrun.sh        another random scenario (C), reproducible
set -u
cd "$(dirname "$0")/.."
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS + 1)); echo "ok   - $1"
          else FAIL=$((FAIL + 1)); echo "FAIL - $1 (expected '$2', got '$3')"; fi; }
le() { [ "$2" -le "$3" ] && echo yes || echo "no ($2 > $3)"; }    # le <name> <value> <max>
LONG=${LONG:-0}; SEED=${SEED:-20261028}

# Generic invariants after any run of <hours>
invariants() {
  local h=$1 tag=$2
  check "$tag: every pass ran (no silent stop, no abort)" yes "$([ "$(elapsed_h)" -ge $((h - 1)) ] && echo yes || echo "no ($(elapsed_h) h)")"
  check "$tag: no shell errors" 0 "$(grep -cE 'syntax error|integer expression|unbound variable|command not found' "$T/charge.err")"
  check "$tag: events stay bounded (<= 6/h)" yes "$(le x "$(count "$OPT/events.jsonl")" $((h * 6 + 10)))"
  check "$tag: Shizuku START requests bounded (<= 3/h)" yes "$(le x "$(count "$T/am.log" broadcast)" $((h * 3 + 5)))"
  check "$tag: Wi-Fi cycles bounded (<= 2/h)" yes "$(le x "$(count "$OPT/events.jsonl" 'reinicio el Wi-Fi')" $((h * 2 + 4)))"
  check "$tag: watchdog Telegram messages bounded (<= 6/h)" yes "$(le x "$(count "$T/curl.log")" $((h * 6 + 2)))"
  check "$tag: one bot service, never duplicated" yes "$(le x "$(pgrep -fc "[l]ongrun-bot $T" || true)" 1)"
  check "$tag: service.log stays small (< 200 KB)" yes "$(le x "$(stat -c %s "$OPT/service.log" 2>/dev/null || echo 0)" 200000)"
}

run_A() {   # A: a long Internet outage
  local h=$1
  ( source tests/longrun_env.sh
    echo "net 600 $(( (h - 1) * 3600 ))" > "$T/schedule"
    simulate $h
    invariants $h "A ${h}h outage"
    n=$(count "$OPT/events.jsonl" 'reinicio el Wi-Fi')
    exp=$(( 4 + (h - 2) ))        # 5+10+20+40 min, then one per hour
    check "A ${h}h outage: Wi-Fi cycles back off to hourly (about $exp, not $(( (h - 1) * 12 )))" yes "$(le x $n $((exp + 2)))"
    check "A ${h}h outage: 'Internet volvió' once when it returns" 1 "$(count "$OPT/events.jsonl" 'Internet volvió')"
    check "A ${h}h outage: the bot still alive (relaunched at most once)" yes "$(le x "$(count "$T/botlaunch.log")" 1)"
    )
}

run_B() {   # B: chained failures, all at once and overlapping
  local h=$1 u=$(( $1 * 3600 / 12 ))     # 12 "units" over the run
  ( source tests/longrun_env.sh
    cat > "$T/schedule" <<EOF
shizuku $((1 * u)) $((5 * u))
net $((2 * u)) $((3 * u))
telegram $((2 * u)) $((6 * u))
botdead $((3 * u)) $((4 * u))
termuxapi $((4 * u)) $((8 * u))
botdead $((7 * u)) $((9 * u))
EOF
    simulate $h
    invariants $h "B ${h}h chained"
    check "B ${h}h chained: Shizuku back at the end" ok "$(sed -n 's/^state=//p' "$OPT/sys/shizuku")"
    check "B ${h}h chained: second bot death (Telegram up) told once" yes "$(le x 1 "$(count "$OPT/events.jsonl" 'avisó por Telegram')")"
    check "B ${h}h chained: bot-death messages delivered at most once per incident" yes "$(le x "$(count "$OPT/events.jsonl" 'avisó por Telegram')" 2)"
    check "B ${h}h chained: battery data kept flowing (from Shizuku or Termux:API)" yes "$([ -s "$OPT/sys/battery/capacity" ] && echo yes || echo no)"
    )
}

run_C() {   # C: random faults, reproducible from SEED
  local h=$1
  ( source tests/longrun_env.sh
    RANDOM=$SEED
    for k in net shizuku telegram botdead termuxapi; do
      for _ in 1 2 3; do
        a=$(( RANDOM % (h * 3600) )); len=$(( 60 * (1 + RANDOM % 240) ))
        echo "$k $a $((a + len))" >> "$T/schedule"
      done
    done
    simulate $h
    invariants $h "C ${h}h random (seed $SEED)"
    )
}

OUT=$(mktemp)
{ if [ "$LONG" = 1 ]; then
    for h in 12 24 48 72; do run_A $h; run_B $h; run_C $h; done
  else
    run_A 6; run_B 4; run_C 4
  fi; } 2>&1 | tee "$OUT"
P=$(grep -c '^ok' "$OUT"); F=$(grep -c '^FAIL' "$OUT"); rm -f "$OUT"
echo "---- $P passed, $F failed"
[ "$F" = 0 ]
