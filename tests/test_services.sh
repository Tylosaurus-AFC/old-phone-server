#!/usr/bin/env bash
# Tests of phone/bot.sh (crash back-off, events) and phone/start.sh (boot sequence, the
# BOT_ENABLED latch) with fake Android commands, no phone needed.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS + 1)); echo "ok   - $1"
          else FAIL=$((FAIL + 1)); echo "FAIL - $1 (expected '$2', got '$3')"; fi; }

# Shims for the Android-only commands. sleep is nearly instant so back-off runs in a blink.
S="$T/shims"; mkdir -p "$S"
for c in ping getprop settings setprop stop start dumpsys content; do
  printf '#!/bin/sh\n[ "$(basename "$0")" = getprop ] && echo 1\nexit 0\n' > "$S/$c"
done
printf '#!/bin/sh\nexec /usr/bin/sleep 0.05\n' > "$S/sleep"
printf '#!/bin/sh\nexec "$@"\n' > "$T/bb"
chmod +x "$S"/* "$T/bb"

fresh() { rm -rf "$T/d"; mkdir -p "$T/d/fs/opt/bot"; : > "$T/d/server.conf"; }

# ---- bot.sh: a bot that dies at once is restarted with 10 s, 20 s, 40 s ... ----------
fresh
printf '#!/bin/sh\necho "Traceback ... RuntimeError: boom" >&2\nexit 1\n' > "$T/d/enter.sh"; chmod +x "$T/d/enter.sh"
PATH="$S:$PATH" DEBIAN="$T/d" BB="$T/bb" timeout 6 sh "$HERE/phone/bot.sh" --fg >/dev/null 2>&1
LOG="$T/d/fs/opt/bot/service.log"
delays="$(grep -o 'restart in [0-9]*s' "$LOG" | head -4 | tr -dc '0-9\n' | tr '\n' ' ')"
check "bot.sh: back-off doubles after quick crashes" "10 20 40 80 " "$delays"
n="$(grep -c '"k":"caida"' "$T/d/fs/opt/bot/events.jsonl")"
[ "$n" -ge 3 ] && r=yes || r=no
check "bot.sh: each crash is an event for /historial" yes "$r"
grep -q 'boom' "$T/d/fs/opt/bot/events.jsonl" && r=yes || r=no
check "bot.sh: the last error is included in the event" yes "$r"

# A bot stopped on purpose (exit 143) is not a crash: no event, delay stays 10
fresh
printf '#!/bin/sh\nexit 143\n' > "$T/d/enter.sh"; chmod +x "$T/d/enter.sh"
PATH="$S:$PATH" DEBIAN="$T/d" BB="$T/bb" timeout 4 sh "$HERE/phone/bot.sh" --fg >/dev/null 2>&1
[ -f "$T/d/fs/opt/bot/events.jsonl" ] && r=events || r=none
check "bot.sh: exit 143 (killed on purpose) writes no crash event" none "$r"

# ---- start.sh: boot sequence and the BOT_ENABLED latch ------------------------------
fresh
printf '#!/bin/sh\ntouch "%s/bot-started"\n' "$T" > "$T/d/bot.sh"; chmod +x "$T/d/bot.sh"
printf '#!/bin/sh\ntouch "%s/charge-ran"\n' "$T" > "$T/d/charge.sh"; chmod +x "$T/d/charge.sh"
rm -f "$T/bot-started" "$T/charge-ran"
PATH="$S:$PATH" DEBIAN="$T/d" BB="$T/bb" SH=sh timeout 3 sh "$HERE/phone/start.sh" >/dev/null 2>&1
grep -q 'server start-up' "$T/d/boot.log" && r=yes || r=no
check "start.sh: logs the start-up" yes "$r"
grep -q 'bot disabled' "$T/d/boot.log" && r=yes || r=no
check "start.sh: without BOT_ENABLED it says the bot is disabled" yes "$r"
[ -f "$T/bot-started" ] && r=started || r=not-started
check "start.sh: without BOT_ENABLED bot.sh is NOT started" not-started "$r"
[ -f "$T/charge-ran" ] && r=ran || r=no
check "start.sh: the watchdog (charge.sh) always runs" ran "$r"

touch "$T/d/BOT_ENABLED"; rm -f "$T/bot-started"
PATH="$S:$PATH" DEBIAN="$T/d" BB="$T/bb" SH=sh timeout 3 sh "$HERE/phone/start.sh" >/dev/null 2>&1
[ -f "$T/bot-started" ] && r=started || r=not-started
check "start.sh: with BOT_ENABLED bot.sh is started" started "$r"

echo "---- $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
