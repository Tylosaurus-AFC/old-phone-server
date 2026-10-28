#!/usr/bin/env bash
# Shared harness for long simulated runs of phone/noroot/charge.sh (sourced by
# tests/test_longrun.sh). Time is simulated: `date +%s` reads $T/clock and `sleep N` moves it,
# so one watchdog pass = one simulated minute and 72 h take minutes, not days.
#
# Faults follow a schedule file ($T/schedule), one per line:  <kind> <from_s> <to_s>
# with times in seconds since the start of the run. Kinds:
#   net        Internet down (the local TCP "Internet" stops listening)
#   shizuku    Shizuku's service stopped (sa.sh silent, rish says "Server is not running")
#   telegram   Telegram answers errors to curl
#   botdead    the bot does not beat (heartbeat not refreshed)
#   termuxapi  Termux:API returns nothing
# The shims below read the schedule and the clock, nothing else: what they simulate and what
# they do not is listed in docs/FAILURE-CATALOG.md.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp -d)"; NETPID=""
cleanup() { kill $NETPID 2>/dev/null; pkill -f "[l]ongrun-bot $T" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
D="$T/home/server"; mkdir -p "$D" "$T/prefix"
OPT="$T/prefix/var/lib/proot-distro/containers/bot/rootfs/opt/bot"; mkdir -p "$OPT"
echo "123456:SECRET-TOKEN" > "$OPT/token"; printf '4242\n' > "$OPT/owners"
T0=1800000000; echo $T0 > "$T/clock"; : > "$T/schedule"
echo $((T0 - 86400)) > "$D/boot_time"
touch "$D/BOT_ENABLED"             # without it the watchdog neither relaunches nor reports the bot

# active <kind>: is that fault scheduled now?
cat > "$T/active" <<EOF
#!/bin/sh
now=\$(( \$(cat "$T/clock") - $T0 ))
while read k a b; do [ "\$k" = "\$1" ] && [ \$now -ge \$a ] && [ \$now -lt \$b ] && exit 0; done < "$T/schedule"
exit 1
EOF
chmod +x "$T/active"; A="$T/active"

S="$T/shims"; mkdir -p "$S"
printf '#!/bin/sh\ncase "$1" in +%%s) cat "%s/clock" ;; *) exec /bin/date "$@" ;; esac\n' "$T" > "$S/date"
# sleep: advance the clock; the fake bot beats here (once per simulated minute) unless dead
cat > "$S/sleep" <<EOF
#!/bin/sh
n=\${1%%.*}; c=\$(( \$(cat "$T/clock") + \${n:-0} )); echo \$c > "$T/clock"
"$A" botdead || echo \$c > "$OPT/heartbeat"
EOF
cat > "$S/curl" <<EOF
#!/bin/sh
cat > /dev/null; echo x >> "$T/curl.log"
if "$A" telegram || "$A" net; then echo '{"ok":false}'; else echo '{"ok":true}'; fi
EOF
printf '#!/bin/sh\necho "$*" >> "%s/am.log"\n' "$T" > "$S/am"
cat > "$S/termux-battery-status" <<EOF
#!/bin/sh
"$A" termuxapi && exit 0
echo '{"percentage": 80, "temperature": 30.1, "status": "CHARGING", "plugged": "PLUGGED_AC", "voltage": 4200, "health": "GOOD"}'
EOF
printf '#!/bin/sh\necho x >> "%s/wifi.log"\n' "$T" > "$S/termux-wifi-enable"
for c in getprop pkill termux-wake-lock termux-wifi-connectioninfo; do printf '#!/bin/sh\nexit 0\n' > "$S/$c"; done
printf '#!/bin/sh\nexit 1\n' > "$S/pgrep"
chmod +x "$S"/*

# Shizuku: sa.sh answers unless "shizuku" is scheduled; rish tells why
cat > "$D/sa.sh" <<EOF
#!/bin/sh
"$A" shizuku && exit 0
case "\$1" in
  "echo OK") echo OK ;;
  *"# keepalive"*) echo x >> "$T/keep.log"; printf 'chk_sdk=34\nchk_idle=1\nchk_bg=x: allow\nchk_phantom=false\nchk_maxph=null\n' ;;
  *versionName*) echo 13.7.0-thedjchi ;;
  *capacity*) printf 'capacity=80\nstatus=Charging\ntemp=301\nvoltage_now=4200\nplug=10\nuptime=1 1\nloadavg=0 0 0\nlimit=80 1\nvol=\n' ;;
esac
EOF
cat > "$D/rish" <<EOF
#!/bin/sh
echo x >> "$T/rish.log"
"$A" shizuku && { echo "Server is not running" >&2; exit 1; }
echo SHZ_PROBE_OK
EOF
touch "$D/rish_shizuku.dex"; cp "$HERE/phone/noroot/shizuku.sh" "$D/"
# The bot service: a process whose command line says bot.sh, counted at each launch
cat > "$D/bot.sh" <<EOF
#!/bin/bash
echo x >> "$T/botlaunch.log"
(exec -a "bot.sh longrun-bot $T" /bin/sleep 100000) </dev/null >/dev/null 2>&1 &
echo \$! > "$D/bot.pid"
EOF
chmod +x "$D"/*.sh "$D/rish"

# The "Internet": listens on a local port except while "net" is scheduled
python3 - "$T" "$T0" > "$T/port" <<'PY' &
import socket, sys, time
T, T0 = sys.argv[1], int(sys.argv[2])
def down():
    try:
        now = int(open(T + "/clock").read()) - T0
    except ValueError:              # read while `sleep` was rewriting it: keep the last state
        return s is None and port != 0
    for line in open(T + "/schedule"):
        k, a, b = line.split()
        if k == "net" and int(a) <= now < int(b):
            return True
    return False
s = None; port = 0
while True:
    if down():
        if s: s.close(); s = None
    elif s is None:
        s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port)); s.listen(64); s.settimeout(0.02)
        if not port:
            port = s.getsockname()[1]; print(port, flush=True)
    if s:
        try:
            c, _ = s.accept(); c.close()
        except OSError:
            pass
    else:
        time.sleep(0.02)
PY
NETPID=$!
for _ in $(seq 50); do [ -s "$T/port" ] && break; /bin/sleep 0.1; done
NET="127.0.0.1:$(head -1 "$T/port")"
printf 'NET_HOSTS=%s\nSHIZUKU_AUTH=s3cret\n' "$NET" > "$D/server.conf"

# simulate <hours>: run the watchdog for that many simulated hours in one process
simulate() {
  HOME="$T/home" PREFIX="$T/prefix" PATH="$S:$PATH" ONCE=$(( $1 * 60 )) \
    bash "$HERE/phone/noroot/charge.sh" >/dev/null 2>"$T/charge.err"
}
elapsed_h() { echo $(( ( $(cat "$T/clock") - T0 ) / 3600 )); }
count() { [ -f "$1" ] || { echo 0; return; }; grep -c -- "${2:-.}" "$1" || true; }
