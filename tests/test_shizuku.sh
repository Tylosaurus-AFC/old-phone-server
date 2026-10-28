#!/usr/bin/env bash
# Shizuku recovery, without a phone:
#  1. phone/noroot/shizuku.sh: each state is recognised from what the real rish prints
#     (texts copied from Shizuku's sources) and `start` sends the fork's authenticated
#     broadcast.
#  2. phone/noroot/charge.sh over HOURS of simulated time (fake `date`/`sleep` move a clock):
#     restart attempts with growing gaps, boot grace, no attempt offline or without
#     SHIZUKU_AUTH, checks thinned out while Shizuku stays down, recovery, the state file the
#     bot reads, and keep-alive settings that Android refuses (reported once, retried less).
# Assumptions: rish's messages and the broadcast format are those of the thedjchi fork's
# sources (2026); real timings of Android/Shizuku are not reproduced.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"; LPID=""
trap 'kill $LPID 2>/dev/null; rm -rf "$T"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS + 1)); echo "ok   - $1"
          else FAIL=$((FAIL + 1)); echo "FAIL - $1 (expected '$2', got '$3')"; fi; }
cnt() { [ -f "$1" ] || { echo 0; return; }; grep -c -- "$2" "$1" || true; }

D="$T/home/server"; mkdir -p "$D" "$T/prefix"
OPT="$T/prefix/var/lib/proot-distro/containers/bot/rootfs/opt/bot"; mkdir -p "$OPT"
cp "$HERE/phone/noroot/shizuku.sh" "$D/"
# fake rish: answers like the real one in the state written in $T/rish_state
cat > "$D/rish" <<EOF
#!/bin/sh
echo "\$*" >> "$T/rish.log"
case "\$(cat "$T/rish_state" 2>/dev/null)" in
  ok) echo "Entering shell..."; echo SHZ_PROBE_OK ;;
  not-running) echo "Server is not running" >&2; exit 1 ;;
  denied) echo "Entering shell..."; echo "Permission denied" >&2; exit 1 ;;
  timeout) echo "Request timeout. If you are using stealth mode, MANAGER_APPLICATION_ID may not be correct." >&2; exit 1 ;;
  dialog) echo "Entering shell..."; sleep 30 ;;
  writable) echo "On Android 14+, app_process cannot load writable dex." ; echo "Cannot remove the write permission of x." ; exit 1 ;;
  *) echo "java.lang.SomethingElse: boom" >&2; exit 1 ;;
esac
EOF
chmod +x "$D/rish"; touch "$D/rish_shizuku.dex"
S="$T/shims"; mkdir -p "$S"
printf '#!/bin/sh\necho "$*" >> "%s/am.log"\n' "$T" > "$S/am"
# simulated clock: `date +%%s` reads it, `sleep N` advances it
echo 1800000000 > "$T/clock"
printf '#!/bin/sh\ncase "$1" in +%%s) cat "%s/clock" ;; *) exec /bin/date "$@" ;; esac\n' "$T" > "$S/date"
printf '#!/bin/sh\nn=${1%%%%.*}; echo $(( $(cat "%s/clock") + ${n:-0} )) > "%s/clock"\n' "$T" "$T" > "$S/sleep"
for c in getprop pkill termux-wake-lock termux-battery-status termux-wifi-connectioninfo termux-wifi-enable; do
  printf '#!/bin/sh\nexit 0\n' > "$S/$c"; done
printf '#!/bin/sh\nexit 1\n' > "$S/pgrep"
chmod +x "$S"/*
# a local TCP listener stands for "Internet is up" (NET_HOSTS=127.0.0.1:<port>)
python3 -c 'import socket,sys,time
s=socket.socket(); s.bind(("127.0.0.1",0)); s.listen(50); print(s.getsockname()[1]); sys.stdout.flush()
while True:
    c,_=s.accept(); c.close()' > "$T/port" &
LPID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$T/port" ] && break; /bin/sleep 0.2; done
UP="127.0.0.1:$(cat "$T/port")"

# fake sa.sh: Shizuku answers only while $T/shz_up exists; keep-alive answers $T/keep.out
cat > "$D/sa.sh" <<EOF
#!/bin/sh
case "\$1" in
  "echo OK") [ -f "$T/shz_up" ] && echo OK ;;
  *"# keepalive"*) echo x >> "$T/keep.log"; echo "\$1" >> "$T/keep.cmd"; cat "$T/keep.out" 2>/dev/null ;;
  *versionName*) [ -f "$T/shz_up" ] && cat "$T/version" 2>/dev/null ;;
esac
EOF
chmod +x "$D/sa.sh"

probe() { echo "$1" > "$T/rish_state"; HOME="$T/home" SHIZUKU_PROBE_TIMEOUT=1 bash "$D/shizuku.sh" probe | head -1; }
# ---- 1. shizuku.sh -----------------------------------------------------------------------------
check "probe: rish answers -> ok" ok "$(probe ok)"
check "probe: 'Server is not running' -> not-running" not-running "$(probe not-running)"
check "probe: 'Permission denied' -> not-authorized" not-authorized "$(probe denied)"
check "probe: 'Request timeout' -> app-unreachable" app-unreachable "$(probe timeout)"
check "probe: hangs after 'Entering shell' -> awaiting-permission" awaiting-permission "$(probe dialog)"
check "probe: writable dex on Android 14+ -> dex-writable" dex-writable "$(probe writable)"
check "probe: anything else -> unknown (with the text as detail)" "unknown" "$(probe other)"
check "probe: detail line carries rish's message" "java.lang.SomethingElse: boom" \
  "$(echo other > "$T/rish_state"; HOME="$T/home" bash "$D/shizuku.sh" probe | sed -n 2p)"
mv "$D/rish_shizuku.dex" "$T/dex.bak"
check "probe: no rish_shizuku.dex -> no-rish" no-rish "$(probe ok)"
mv "$T/dex.bak" "$D/rish_shizuku.dex"

rm -f "$T/am.log"; printf '' > "$D/server.conf"
HOME="$T/home" PATH="$S:$PATH" bash "$D/shizuku.sh" start >/dev/null; RC=$?
check "start without SHIZUKU_AUTH: refuses (exit 2), sends nothing" "2 0" "$RC $(cnt "$T/am.log" broadcast)"
printf 'SHIZUKU_AUTH=s3cret\n' > "$D/server.conf"
HOME="$T/home" PATH="$S:$PATH" bash "$D/shizuku.sh" start
check "start: explicit broadcast to the fork's ManualStartReceiver with auth" 1 \
  "$(cnt "$T/am.log" "broadcast --include-stopped-packages -n moe.shizuku.privileged.api/moe.shizuku.manager.receiver.ManualStartReceiver -a moe.shizuku.privileged.api.START --es auth s3cret")"

# ---- 2. charge.sh over simulated time ---------------------------------------------------------
# passes <n> <conf lines...>: n watchdog passes, one simulated minute apart
passes() {
  local n=$1; shift
  printf '%s\n' "$@" > "$D/server.conf"
  HOME="$T/home" PREFIX="$T/prefix" PATH="$S:$PATH" ONCE=$n bash "$HERE/phone/noroot/charge.sh" >/dev/null 2>&1
}
fresh() {      # fresh <rish state>: Shizuku down for that reason, boot long ago, clean logs
  rm -f "$T"/*.log "$T/shz_up" "$T/keep.out" "$OPT/events.jsonl" "$OPT/sys/shizuku" "$D/charge.pid"
  echo "$1" > "$T/rish_state"
  echo $(( $(cat "$T/clock") - 86400 )) > "$D/boot_time"
}
st() { sed -n "s/^$1=//p" "$OPT/sys/shizuku"; }

fresh not-running
passes 40 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "stopped service, auth set, online: 4 start requests in 40 min (0, 2, 7, 20 min)" 4 "$(cnt "$T/am.log" broadcast)"
check "state file for the bot: state" not-running "$(st state)"
check "state file: attempts counted" 4 "$(st tries)"
check "state file: auth configured" 1 "$(st auth)"
check "state file: never contains the auth secret" 0 "$(cnt "$OPT/sys/shizuku" s3cret)"
check "events: every start request is recorded for /historial" 4 "$(cnt "$OPT/events.jsonl" "le pido que arranque")"
check "events: the secret never reaches /historial" 0 "$(cnt "$OPT/events.jsonl" s3cret)"
n=$(grep -c SHZ_PROBE "$T/rish.log")
check "checks thinned out after 10 min down (rish probes in 40 min < 20, not 40)" yes "$([ "$n" -lt 20 ] && echo yes || echo "no ($n)")"

fresh not-running
passes 30 "NET_HOSTS=$UP"
check "no SHIZUKU_AUTH: never sends a start request" 0 "$(cnt "$T/am.log" broadcast)"
check "no SHIZUKU_AUTH: state file says so (the bot tells the user how to enable it)" 0 "$(st auth)"

fresh not-running
passes 10 "NET_HOSTS=127.0.0.1:1" "SHIZUKU_AUTH=s3cret"
check "offline: no start requests (Shizuku needs Wi-Fi to start)" 0 "$(cnt "$T/am.log" broadcast)"

fresh not-authorized; echo denied > "$T/rish_state"
passes 10 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "Termux not authorised: no start requests (only the user can authorise)" "0 not-authorized" "$(cnt "$T/am.log" broadcast) $(st state)"

fresh timeout
passes 2 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "Shizuku app frozen: the start broadcast also wakes it (1 request)" "1 app-unreachable" "$(cnt "$T/am.log" broadcast) $(st state)"

fresh not-running; date +%s > /dev/null; cat "$T/clock" > "$D/boot_time"
passes 4 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "just booted: no request in the first 5 min (the fork starts by itself)" 0 "$(cnt "$T/am.log" broadcast)"
passes 3 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "after the boot grace: requests start" 1 "$(cnt "$T/am.log" broadcast)"

fresh not-running
passes 3 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
touch "$T/shz_up"; echo ok > "$T/rish_state"
passes 2 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "Shizuku back: state ok, attempts reset" "ok 0" "$(st state) $(st tries)"
check "Shizuku back: recorded for /historial" 1 "$(cnt "$OPT/events.jsonl" "Shizuku disponible")"

# keep-alive settings read back: a refused setting is reported once and retried less often
fresh ok; touch "$T/shz_up"
printf 'chk_sdk=34\nchk_idle=1\nchk_bg=RUN_ANY_IN_BACKGROUND: allow\nchk_phantom=false\nchk_maxph=null\n' > "$T/keep.out"
passes 180 "NET_HOSTS=$UP"
check "keep-alive accepted: applied every 30 min (6 times in 3 h)" 6 "$(cnt "$T/keep.log" x)"
check "keep-alive accepted: no warning" 0 "$(cnt "$OPT/events.jsonl" "Android no aceptó")"
fresh ok; touch "$T/shz_up"
printf 'chk_sdk=34\nchk_idle=0\nchk_bg=RUN_ANY_IN_BACKGROUND: allow\nchk_phantom=null\nchk_maxph=null\n' > "$T/keep.out"
passes 180 "NET_HOSTS=$UP"
check "keep-alive refused: retried less often (0, 30, 90 min: 3 times in 3 h)" 3 "$(cnt "$T/keep.log" x)"
check "keep-alive refused: reported once, naming what failed" 1 "$(cnt "$OPT/events.jsonl" "Android no aceptó: exención de batería de Termux, límite de procesos de Android")"

# Which Shizuku: detected while it works, remembered, and it decides whether START is tried
fresh ok; touch "$T/shz_up"; echo "13.7.0-thedjchi" > "$T/version"
passes 2 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "variant detected while Shizuku works: fork + version" "fork 13.7.0-thedjchi" "$(st variant) $(st version)"
rm -f "$T/shz_up"; echo not-running > "$T/rish_state"; echo $(( $(cat "$T/clock") - 86400 )) > "$D/boot_time"
rm -f "$D/charge.pid"; passes 2 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "variant remembered across a watchdog restart while Shizuku is down" fork "$(st variant)"
check "fork: START is tried" 1 "$(cnt "$T/am.log" broadcast)"

fresh ok; touch "$T/shz_up"; echo "13.6.0.r1086.2650830" > "$T/version"
passes 2 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
rm -f "$T/shz_up" "$T/am.log"; echo not-running > "$T/rish_state"
passes 10 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "official Shizuku: never sends START (it has no such receiver)" "official 0" "$(st variant) $(cnt "$T/am.log" broadcast)"

fresh not-running; rm -f "$OPT/sys/shizuku"; touch "$D/no-shizuku-restart"
passes 10 "NET_HOSTS=$UP" "SHIZUKU_AUTH=s3cret"
check "~/server/no-shizuku-restart: Shizuku stopped on purpose is left alone" "0 1" "$(cnt "$T/am.log" broadcast) $(st paused)"
rm -f "$D/no-shizuku-restart"

fresh ok; touch "$T/shz_up"; rm -f "$T/keep.cmd"
printf 'chk_sdk=34\nchk_idle=1\nchk_bg=RUN_ANY_IN_BACKGROUND: allow\nchk_phantom=false\nchk_maxph=null\n' > "$T/keep.out"
passes 1 "NET_HOSTS=$UP"
check "keep-alive also lets the Shizuku app run in the background (its wiki's advice)" 1 "$(cnt "$T/keep.cmd" 'cmd appops set moe.shizuku.privileged.api $o allow')"

echo "---- $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
