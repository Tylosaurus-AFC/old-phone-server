#!/usr/bin/env bash
# Smoke tests of the PC-side scripts in tools/ with FAKE adb, ssh and curl: configuration
# missing or invalid, phone unreachable, input validation, and what the scripts would run on
# the phone (captured, never executed). No phone, network or real adb needed.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
T="${KEEP_T:-$(mktemp -d)}"; [ -n "${KEEP_T:-}" ] || trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS + 1)); echo "ok   - $1"
          else FAIL=$((FAIL + 1)); echo "FAIL - $1 (expected '$2', got '$3')"; fi; }
has() { grep -qF -- "$2" "$1" 2>/dev/null && echo yes || echo no; }   # has <file> <text>

# A copy of the repository: the scripts find config.sh next to tools/
R="$T/repo"; mkdir -p "$R"
cp -r "$HERE/tools" "$HERE/phone" "$HERE/bot" "$HERE/extras" "$HERE/config.example.sh" "$R/"

S="$T/shims"; mkdir -p "$S" "$T/pushed"
# fake adb: logs every call; `push` keeps a copy of the file (the scripts run on the phone
# arrive this way); get-state answers "device" unless FAKE_ADB_DOWN=1
cat > "$S/adb" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$T/adb.log"
[ "\$1" = -s ] && shift 2
case "\$1" in
  get-state) [ "\${FAKE_ADB_DOWN:-0}" = 1 ] && exit 1; echo device ;;
  push) cp "\$2" "$T/pushed/\$(basename "\$3")" ;;
  pull) : > "\$3" ;;
esac
exit 0
EOF
# fake ssh: logs the remote command and saves its stdin; fails if FAKE_SSH_DOWN=1. A
# "tar -cf" command answers with a small tar (what noroot-backup.sh expects to read).
cat > "$S/ssh" <<EOF
#!/usr/bin/env bash
[ "\${FAKE_SSH_DOWN:-0}" = 1 ] && exit 255
while [ "\$1" = -o ]; do shift 2; done; shift      # options and host
echo "\$*" >> "$T/ssh.log"
n=\$(wc -l < "$T/ssh.log"); cat > "$T/ssh.stdin.\$n"
# FAKE_SSH_EXEC=1: really run the remote command here (with the getprop/df shims), for the
# phone-side scripts that must be checked by what they do, not just sent
if [ "\${FAKE_SSH_EXEC:-0}" = 1 ] && [ "\$*" != "echo ok" ]; then exec bash -c "\$*"; fi
case "\$*" in
  "echo ok") echo ok ;;
  *"tar -cf"*) d=\$(mktemp -d); echo t > "\$d/token"; tar -cf - -C "\$d" token; rm -rf "\$d" ;;
esac
exit 0
EOF
printf '#!/bin/sh\necho "curl $*" >> "%s/curl.log"\nexit 1\n' "$T" > "$S/curl"
printf '#!/bin/sh\ncase "$1" in ro.build.version.sdk) echo "${FAKE_SDK:-34}" ;; ro.build.version.release) echo 14 ;; *) echo X ;; esac\n' > "$S/getprop"
printf '#!/bin/sh\necho "Filesystem 1024-blocks Used Available Capacity Mounted"\necho "/dev/x 1 1 $(( ${FAKE_FREE_MB:-5000} * 1024 )) 1%%%% /"\n' > "$S/df"
printf '#!/bin/sh\necho "scp $*" >> "%s/scp.log"\nexit 0\n' "$T" > "$S/scp"
# the scripts wait for the phone (sleep 2..25 s): no need to wait for a fake one
printf '#!/bin/sh\nexit 0\n' > "$S/sleep"
chmod +x "$S"/*

conf() { printf '%s\n' "$@" > "$R/config.sh"; }       # conf <lines...>
reset() { rm -f "$T"/*.log "$T"/ssh.stdin.* "$T"/pushed/*; }
# run <script> [args...]: output in $T/out, exit code in $RC (stdin from $IN, default empty)
run() { reset; (cd "$R" && PATH="$S:$PATH" bash "tools/$1" "${@:2}" < "${IN:-/dev/null}" > "$T/out" 2>&1); RC=$?; }
BASE_CONF=(ADB=adb USB_SERIAL=FAKE123 PHONE_IP=192.0.2.10 ROOT_MODE=su BOOT_MODE=none
           BB_PATH=/data/debian/busybox-deb ARCH=armhf NOROOT_SSH=phone NOROOT_IP=192.0.2.10
           CONTAINER=bot)

# ---- configuration ------------------------------------------------------------------------
rm -f "$R/config.sh"; run enable-bot.sh
check "no config.sh: fails" 1 "$RC"
check "no config.sh: says how to create it" yes "$(has "$T/out" "cp \"$R/config.example.sh\"")"
run noroot-bot.sh enable
check "no config.sh (no-root tools): fails with the same advice" yes "$(has "$T/out" "config.example.sh")"

conf "${BASE_CONF[@]}" ADB=/nonexistent/adb; run enable-bot.sh
check "adb missing: fails" 1 "$RC"
check "adb missing: names ADB and the fix" yes "$(has "$T/out" "adb not found (ADB=/nonexistent/adb")"

conf "${BASE_CONF[@]}" USB_SERIAL= PHONE_IP=; run enable-bot.sh
check "no USB_SERIAL nor PHONE_IP: fails" 1 "$RC"
check "no USB_SERIAL nor PHONE_IP: says what to set" yes "$(has "$T/out" "set USB_SERIAL")"
check "no USB_SERIAL nor PHONE_IP: adb never called" no "$(has "$T/adb.log" "shell")"

conf "${BASE_CONF[@]}" ROOT_MODE=magisk; run enable-bot.sh
check "ROOT_MODE=magisk: still works (as su)" 0 "$RC"
check "ROOT_MODE=magisk: warns" yes "$(has "$T/out" "Warning: ROOT_MODE=magisk")"
check "ROOT_MODE=magisk: runs through su" yes "$(has "$T/adb.log" "su -c")"

conf "${BASE_CONF[@]}" ROOT_MODE=adbroot; run enable-bot.sh
check "ROOT_MODE=adbroot: adb root, no su" "yes no" "$(has "$T/adb.log" " root") $(has "$T/adb.log" "su -c")"

conf "${BASE_CONF[@]}"; FAKE_ADB_DOWN=1 run enable-bot.sh
check "phone unreachable: fails" 1 "$RC"
check "phone unreachable: explains what to try" yes "$(has "$T/out" "Cannot see the phone")"

conf "${BASE_CONF[@]}"; run enable-bot.sh
check "valid config: enable-bot works" 0 "$RC"
check "enable-bot: pushed script creates BOT_ENABLED" yes "$(has "$T/pushed/phonesrv.sh" "touch /data/debian/BOT_ENABLED")"
run enable-bot.sh off
check "enable-bot off: pushed script removes BOT_ENABLED" yes "$(has "$T/pushed/phonesrv.sh" "rm -f /data/debian/BOT_ENABLED")"

conf "${BASE_CONF[@]}" ARCH=x86_64; run fetch-assets.sh
check "fetch-assets with a bad ARCH: fails" 1 "$RC"
check "fetch-assets with a bad ARCH: nothing downloaded" no "$(has "$T/curl.log" "curl")"
conf "${BASE_CONF[@]}"; sed -i '/^ARCH=/d' "$R/config.sh"; run fetch-assets.sh
check "fetch-assets with no ARCH at all: clear message" yes "$(has "$T/out" "must be armhf")"

# ---- input validation (secrets are typed, never passed as arguments) ------------------------
conf "${BASE_CONF[@]}"
printf 'not-a-token\n' > "$T/in"; IN="$T/in" run set-token.sh
check "set-token: rejects a malformed token" 1 "$RC"
check "set-token: nothing pushed" no "$(has "$T/adb.log" "push")"
printf '123456:ABCdef\n' > "$T/in"; IN="$T/in" run set-token.sh
check "set-token: a valid token is pushed" yes "$(has "$T/adb.log" "phonesrv.tok")"
printf '12345\nabc\n' > "$T/in"; IN="$T/in" run set-api.sh
check "set-api: rejects a short api_hash" 1 "$RC"
printf '12x45\n0123456789abcdef0123456789abcdef\n' > "$T/in"; IN="$T/in" run set-api.sh
check "set-api: rejects a non-numeric api_id" 1 "$RC"
printf '12345\n0123456789abcdef0123456789abcdef\n' > "$T/in"; IN="$T/in" run set-api.sh
check "set-api: valid values are pushed" "0 yes" "$RC $(has "$T/adb.log" "phonesrv.api")"
IN=

# ---- restore-config.sh ------------------------------------------------------------------------
mkdir -p "$T/bk-empty"; run restore-config.sh "$T/bk-empty"
check "restore-config: refuses a folder without token" 1 "$RC"
check "restore-config: says why" yes "$(has "$T/out" "does not look like a backup")"
mkdir -p "$T/bk/android"; for f in token owners bot.db channels.json server.conf pip-freeze.txt; do echo x > "$T/bk/$f"; done
run restore-config.sh "$T/bk"
check "restore-config: works with a real backup" 0 "$RC"
check "restore-config: every file pushed (not the android/ folder)" "6 0" \
  "$(grep -c ' push .*/bk/' "$T/adb.log") $(grep -c 'bk/android' "$T/adb.log")"
check "restore-config: the phone-side script is valid sh" 0 "$(sh -n "$T/pushed/phonesrv.sh" 2>/dev/null; echo $?)"
check "restore-config: files replaced atomically" yes "$(has "$T/pushed/phonesrv.sh" ".rst /data/debian/fs/opt/bot/")"

# ---- no-root tools ------------------------------------------------------------------------------
conf "${BASE_CONF[@]}"
FAKE_SSH_DOWN=1 run noroot-bot.sh enable
check "no-root: phone unreachable over SSH: fails" 1 "$RC"
check "no-root: unreachable: explains what to check" yes "$(has "$T/out" "Cannot reach the phone over SSH as 'phone'")"
run noroot-bot.sh
check "noroot-bot.sh without a command: prints usage, fails" "1 yes" "$RC $(has "$T/out" "tools/noroot-bot.sh token")"
printf '12345\nnot-hex\n' > "$T/in"; IN="$T/in" run noroot-bot.sh api
check "noroot-bot api: rejects a bad api_hash (like set-api.sh)" 1 "$RC"
check "noroot-bot api: nothing written to the phone" no "$(has "$T/ssh.log" "api.txt")"
printf '12345\n0123456789abcdef0123456789abcdef\n' > "$T/in"; IN="$T/in" run noroot-bot.sh api
check "noroot-bot api: valid values are written (chmod 600)" yes "$(has "$T/ssh.log" "chmod 600")"
IN=
conf "${BASE_CONF[@]}" NOROOT_IP=; run noroot-adb.sh
check "noroot-adb without NOROOT_IP: fails with advice" "1 yes" "$RC $(has "$T/out" "Set NOROOT_IP")"

for f in token device.json bot.db channels.json junk.txt; do echo x > "$T/bk/$f"; done
conf "${BASE_CONF[@]}"; run noroot-restore.sh "$T/bk"
n=$(grep -n "tar -xf" "$T/ssh.log" | cut -d: -f1)
LIST=$(tar -tf "$T/ssh.stdin.$n" 2>/dev/null | tr '\n' ' ')
check "noroot-restore: works" 0 "$RC"
check "noroot-restore: sends device.json, bot.db, channels.json" "yes yes yes" \
  "$(for f in device.json bot.db channels.json; do case " $LIST" in *" $f "*) printf yes ;; *) printf no ;; esac; [ $f = channels.json ] || printf ' '; done)"
check "noroot-restore: unknown files are not sent" no "$(case " $LIST" in *junk.txt*) echo yes ;; *) echo no ;; esac)"
check "noroot-restore: the bot is stopped first" yes "$(head -2 "$T/ssh.log" | grep -q BOT_ENABLED && echo yes || echo no)"

rm -rf "$R/backup"; run noroot-backup.sh
check "noroot-backup: works" 0 "$RC"
check "noroot-backup: asks for bot.db too" yes "$(has "$T/ssh.log" "bot.db")"
check "noroot-backup: files land in backup/<date>/" yes "$(ls "$R"/backup/*/token >/dev/null 2>&1 && echo yes || echo no)"

conf "${BASE_CONF[@]}"; run noroot-doctor.sh
check "noroot-doctor: runs ~/server/doctor.sh over SSH" "0 yes" "$RC $(has "$T/ssh.log" "bash ~/server/doctor.sh")"
FAKE_SSH_DOWN=1 run noroot-doctor.sh
check "noroot-doctor: phone unreachable: clear message" "1 yes" "$RC $(has "$T/out" "Cannot reach the phone over SSH")"

# noroot-install.sh check/packages: the phone-side preflight, really executed
conf "${BASE_CONF[@]}"
FAKE_SSH_EXEC=1 run noroot-install.sh check
check "preflight: a fine phone passes" "0 yes" "$RC $(has "$T/out" "OK: nothing blocks the install")"
FAKE_SSH_EXEC=1 FAKE_SDK=23 run noroot-install.sh check
check "preflight: Android 6 stops, pointing to root mode" "1 yes" "$RC $(has "$T/out" "STOP: Termux needs Android 7")"
FAKE_SSH_EXEC=1 FAKE_SDK=29 run noroot-install.sh check
check "preflight: Android 10 passes with the Shizuku warning" "0 yes" "$RC $(has "$T/out" "WARN: below Android 11")"
FAKE_SSH_EXEC=1 FAKE_FREE_MB=500 run noroot-install.sh check
check "preflight: 500 MB free stops" "1 yes" "$RC $(has "$T/out" "STOP: less than 1 GB free")"
FAKE_SSH_EXEC=1 FAKE_FREE_MB=2000 run noroot-install.sh check
check "preflight: 2 GB free only warns" "0 yes" "$RC $(has "$T/out" "WARN: under 3 GB free")"
FAKE_SSH_EXEC=1 FAKE_SDK=23 run noroot-install.sh packages
check "packages: refuses to install when the preflight stops" "1 no" "$RC $(has "$T/out" "pkg update")"
run noroot-install.sh scripts
check "scripts: ends with the health check" "0 yes" "$RC $(has "$T/ssh.log" "bash ~/server/doctor.sh")"
check "scripts: doctor.sh is among the files sent" yes "$(grep -q 'doctor.sh ~/server/doctor.sh\|for s in .*doctor.sh' "$T/ssh.log" && echo yes || echo no)"
printf '' > "$T/in"; run noroot-bot.sh enable
check "noroot-bot enable: shows the health check" yes "$(has "$T/ssh.log" "bash ~/server/doctor.sh")"

echo "---- $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
