#!/usr/bin/env bash
# The no-root watchdog's own Telegram message when the bot is dead (the bot cannot report
# its own death). Simulated clock (fake date/sleep), fake curl (records its arguments and,
# separately, the config it reads on stdin; answers like Telegram, up or down), local TCP
# listener as "online". Checks: one message per incident, retries only until confirmed and
# spaced, nothing offline / when disabled / with a live bot, token never on the command line.
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
echo "123456:SECRET-TOKEN" > "$OPT/token"; printf '4242\n100\n' > "$OPT/owners"
printf '#!/bin/sh\nexit 0\n' > "$D/sa.sh"; chmod +x "$D/sa.sh"            # Shizuku silent
printf '#!/bin/sh\ntrue\n' > "$D/bot.sh"; chmod +x "$D/bot.sh"
S="$T/shims"; mkdir -p "$S"
echo 1800000000 > "$T/clock"
printf '#!/bin/sh\ncase "$1" in +%%s) cat "%s/clock" ;; *) exec /bin/date "$@" ;; esac\n' "$T" > "$S/date"
printf '#!/bin/sh\nn=${1%%%%.*}; echo $(( $(cat "%s/clock") + ${n:-0} )) > "%s/clock"\n' "$T" "$T" > "$S/sleep"
cat > "$S/curl" <<EOF
#!/bin/sh
echo "\$*" >> "$T/curl.args"
cat >> "$T/curl.stdin"; echo "---" >> "$T/curl.stdin"
if [ -f "$T/tg_up" ]; then echo '{"ok":true,"result":{"message_id":7}}'; else echo '{"ok":false,"error_code":502}'; fi
EOF
for c in getprop pkill termux-wake-lock termux-battery-status termux-wifi-connectioninfo termux-wifi-enable; do
  printf '#!/bin/sh\nexit 0\n' > "$S/$c"; done
printf '#!/bin/sh\nexit 1\n' > "$S/pgrep"
chmod +x "$S"/*
python3 -c 'import socket,sys
s=socket.socket(); s.bind(("127.0.0.1",0)); s.listen(50); print(s.getsockname()[1]); sys.stdout.flush()
while True:
    c,_=s.accept(); c.close()' > "$T/port" &
LPID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$T/port" ] && break; /bin/sleep 0.2; done
UP="127.0.0.1:$(cat "$T/port")"

now() { cat "$T/clock"; }
passes() {    # passes <n> <conf lines...>
  local n=$1; shift; printf '%s\n' "$@" > "$D/server.conf"
  HOME="$T/home" PREFIX="$T/prefix" PATH="$S:$PATH" ONCE=$n bash "$HERE/phone/noroot/charge.sh" >/dev/null 2>&1
}
fresh() { rm -f "$T"/curl.* "$D/botdown" "$D/charge.pid" "$OPT/events.jsonl"; touch "$D/BOT_ENABLED"
          echo $(( $(now) - 86400 )) > "$D/boot_time"; }      # booted long ago
beat_ago() { echo $(( $(now) - $1 )) > "$OPT/heartbeat"; }

fresh; touch "$T/tg_up"; beat_ago 30
passes 3 "NET_HOSTS=$UP"
check "bot alive: no message" 0 "$(cnt "$T/curl.args" .)"

fresh; touch "$T/tg_up"; beat_ago 1200
passes 1 "NET_HOSTS=$UP"
check "heartbeat 20 min old, online: one message" 1 "$(cnt "$T/curl.args" .)"
check "the message goes to the owner" 1 "$(cnt "$T/curl.stdin" 'chat_id=4242')"
check "it says the bot is not answering" 1 "$(cnt "$T/curl.stdin" 'El bot no responde')"
check "token never on curl's command line" 0 "$(cnt "$T/curl.args" SECRET-TOKEN)"
check "curl reads it from stdin (-K -)" "1 1" "$(cnt "$T/curl.args" '\-K -') $(cnt "$T/curl.stdin" 'bot123456:SECRET-TOKEN/sendMessage')"
check "recorded for /historial" 1 "$(cnt "$OPT/events.jsonl" 'avisó por Telegram')"
passes 60 "NET_HOSTS=$UP"
check "same incident for another hour: still one message" 1 "$(cnt "$T/curl.args" .)"

fresh; rm -f "$T/tg_up"; beat_ago 1200
passes 35 "NET_HOSTS=$UP"
check "Telegram down: retried every 10 min, not every minute (4 tries in 35 min)" 4 "$(cnt "$T/curl.args" .)"
touch "$T/tg_up"; passes 11 "NET_HOSTS=$UP"
check "Telegram back: delivered, then quiet" 5 "$(cnt "$T/curl.args" .)"

fresh; touch "$T/tg_up"; beat_ago 1200
passes 5 "NET_HOSTS=127.0.0.1:1"
check "offline: no attempt (it would fail anyway)" 0 "$(cnt "$T/curl.args" .)"

fresh; touch "$T/tg_up"; beat_ago 1200
passes 1 "NET_HOSTS=$UP"; beat_ago 10; passes 1 "NET_HOSTS=$UP"
check "bot back: incident closed" no "$([ -f "$D/botdown" ] && echo yes || echo no)"
beat_ago 1200; passes 1 "NET_HOSTS=$UP"
check "a new incident later: a new message" 2 "$(cnt "$T/curl.args" .)"

fresh; touch "$T/tg_up"; beat_ago 1200; rm -f "$D/BOT_ENABLED"
passes 3 "NET_HOSTS=$UP"
check "bot disabled on this phone: no message" 0 "$(cnt "$T/curl.args" .)"
fresh; touch "$T/tg_up"; beat_ago 1200
passes 3 "NET_HOSTS=$UP" "BOTDOWN_ALERT=0"
check "BOTDOWN_ALERT=0: no message" 0 "$(cnt "$T/curl.args" .)"

fresh; touch "$T/tg_up"; beat_ago 1200; mv "$S/curl" "$T/curl.off"
HOME="$T/home" PREFIX="$T/prefix" PATH="$S:/usr/local/bin:/bin" ONCE=1 bash "$HERE/phone/noroot/charge.sh" >/dev/null 2>&1; RC=$?
PATH_HAS_CURL=$(PATH="$S:/usr/local/bin:/bin" command -v curl >/dev/null && echo yes || echo no)
[ "$PATH_HAS_CURL" = no ] && check "no curl installed: the pass still completes" 0 "$RC" || echo "skip - curl is in /bin here"
mv "$T/curl.off" "$S/curl"

# Just after a reboot the heartbeat on disk is the one from before (maybe hours old) and the
# bot is still starting: that is not a dead bot
fresh; touch "$T/tg_up"; beat_ago 7200; now > "$D/boot_time"
passes 10 "NET_HOSTS=$UP"
check "just booted with an old heartbeat: no false alarm in the first 10 min" 0 "$(cnt "$T/curl.args" .)"
passes 7 "NET_HOSTS=$UP"
check "still no heartbeat 16 min after boot: now it is reported" 1 "$(cnt "$T/curl.args" .)"

echo "---- $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
