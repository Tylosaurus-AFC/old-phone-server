#!/usr/bin/env bash
# Tests of phone/noroot/doctor.sh in a FAKE Termux: getprop, uname, df and pgrep are shims and
# sa.sh (Shizuku) answers with a canned Android report. Checks that each problem is reported
# with the right level (OK/WARN/FAIL), the summary line and the exit code. No phone needed.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"
PIDS=""
trap 'kill $PIDS 2>/dev/null; rm -rf "$T"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS + 1)); echo "ok   - $1"
          else FAIL=$((FAIL + 1)); echo "FAIL - $1 (expected '$2', got '$3')"; fi; }
has() { grep -qF -- "$1" "$T/out" && echo yes || echo no; }

S="$T/shims"; mkdir -p "$S"
cat > "$S/getprop" <<'EOF'
#!/bin/sh
case "$1" in
  ro.build.version.sdk) echo "${FAKE_SDK:-34}" ;;
  ro.build.version.release) echo "${FAKE_REL:-14}" ;;
  ro.product.brand) echo realme ;;
esac
EOF
printf '#!/bin/sh\n[ "$1" = -m ] && echo "${FAKE_ARCH:-aarch64}" || /bin/uname "$@"\n' > "$S/uname"
printf '#!/bin/sh\necho "Filesystem 1024-blocks Used Available Capacity Mounted"\necho "/dev/x 100000000 1 $(( ${FAKE_FREE_MB:-5000} * 1024 )) 1%% /"\n' > "$S/df"
printf '#!/bin/sh\n[ "${FAKE_SSHD:-1}" = 1 ]\n' > "$S/pgrep"
chmod +x "$S"/*

# Processes whose command line says charge.sh / bot.sh (doctor.sh checks /proc/<pid>/cmdline)
mkdir -p "$T/procs"
for n in charge.sh bot.sh; do printf '#!/bin/sh\nsleep 300\n' > "$T/procs/$n"; chmod +x "$T/procs/$n"
  "$T/procs/$n" </dev/null >/dev/null 2>&1 & PIDS="$PIDS $!"; eval "PID_${n%.sh}=$!"; done

setup() {     # a complete, healthy installation
  rm -rf "$T/home" "$T/prefix"
  D="$T/home/server"; mkdir -p "$D" "$T/home/.termux/boot"
  OPT="$T/prefix/var/lib/proot-distro/containers/bot/rootfs/opt/bot"; mkdir -p "$OPT/venv/bin"
  printf '#!/bin/sh\n' > "$T/home/.termux/boot/00-server.sh"; chmod +x "$T/home/.termux/boot/00-server.sh"
  printf 'OEM=\nSHIZUKU_AUTH=abc\n' > "$D/server.conf"
  cp "$HERE/phone/noroot/shizuku.sh" "$D/"
  # fake rish: prints what the real one prints in the state given by FAKE_RISH (texts from
  # Shizuku's sources); sa.sh below is what doctor.sh uses when Shizuku works
  cat > "$D/rish" <<'RISH'
#!/bin/sh
case "${FAKE_RISH:-ok}" in
  ok) echo "Entering shell..."; echo SHZ_PROBE_OK ;;
  not-running) echo "Server is not running" >&2; exit 1 ;;
  denied) echo "Entering shell..."; echo "Permission denied" >&2; exit 1 ;;
  timeout) echo "Request timeout. If you are using stealth mode, MANAGER_APPLICATION_ID may not be correct." >&2; exit 1 ;;
  dialog) echo "Entering shell..."; sleep 30 ;;
esac
RISH
  printf '#!/bin/sh\n' > "$OPT/venv/bin/python3"; chmod +x "$OPT/venv/bin/python3"
  touch "$D/BOT_ENABLED"; echo "1:x" > "$OPT/token"; date +%s > "$OPT/heartbeat"
  echo $PID_charge > "$D/charge.pid"; echo $PID_bot > "$D/bot.pid"
  chmod +x "$D/rish"; touch "$D/rish_shizuku.dex"
  printf '#!/bin/sh\ncase "$1" in "echo OK") [ "${FAKE_SHIZUKU:-1}" = 1 ] && echo OK ;; *bootstate*) cat "%s/android" ;; esac\n' "$T" > "$D/sa.sh"
  chmod +x "$D/sa.sh"
  android
}
android() {   # android [key=value...]: the Shizuku report, healthy unless overridden
  local k
  declare -A A=([boot]=1 [bootstate]=stopped=false [bootnl]=notLaunched=false [api]=1 [idle]=1
                [bg]="RUN_ANY_IN_BACKGROUND: allow" [bucket]=10 [phantom]=false [maxph]=null [wake]=1 [adbwifi]=1
                [shzidle]=1 [shzwss]=1 [cred]=NONE)
  for kv in "$@"; do A[${kv%%=*}]="${kv#*=}"; done
  : > "$T/android"; for k in "${!A[@]}"; do echo "$k=${A[$k]}" >> "$T/android"; done
}
run() { HOME="$T/home" PREFIX="$T/prefix" PATH="$S:$PATH" TERMUX_APK_RELEASE=GITHUB TERMUX_VERSION=0.118.3 \
        bash "$HERE/phone/noroot/doctor.sh" > "$T/out" 2>&1; RC=$?; }
first() { head -1 "$T/out" | cut -d' ' -f2; }

setup; run
check "healthy install: RESULT ok, exit 0" "ok 0" "$(first) $RC"
check "healthy install: no WARN/FAIL lines" 0 "$(grep -cE '^(WARN|FAIL)' "$T/out")"

setup; rm "$T/home/.termux/boot/00-server.sh"; run
check "no boot hook: broken, exit 2" "broken 2" "$(first) $RC"
check "no boot hook: says how to fix" yes "$(has "tools/noroot-install.sh scripts")"

setup; android bootnl=notLaunched=true; run
check "Termux:Boot never opened: FAIL with the fix" "broken yes" "$(first) $(has "open the Termux:Boot app once")"
setup; android bootstate=stopped=true; run
check "Termux:Boot force-stopped: FAIL" broken "$(first)"
setup; android boot=0; run
check "Termux:Boot missing: FAIL" yes "$(has "Termux:Boot is not installed")"

setup; android idle=0; run
check "battery optimisation on: FAIL" "broken yes" "$(first) $(has "under battery optimisation")"
setup; android "bg=RUN_ANY_IN_BACKGROUND: ignore"; run
check "background activity denied: FAIL" yes "$(has "not allowed to run in the background")"
setup; android bucket=40; run
check "rare standby bucket: WARN only" "degraded yes" "$(first) $(has "WARN app standby bucket 40")"

setup; android phantom=null; run
check "Android 14, child-process killer on: WARN (degraded)" "degraded yes" "$(first) $(has "phantom process killer")"
setup; android maxph=32; FAKE_SDK=31 FAKE_REL=12 run
check "Android 12, phantom limit 32: WARN" yes "$(has "limit of 32 shared by all apps")"
setup; android maxph=2147483647; FAKE_SDK=31 FAKE_REL=12 run
check "Android 12, limit raised: OK" "ok yes" "$(first) $(has "phantom process limit raised")"
setup; android phantom=true; FAKE_SDK=30 FAKE_REL=11 run
check "Android 11: no phantom check at all" "ok no" "$(first) $(has "phantom")"

setup; android wake=0; run
check "no wake lock: WARN" yes "$(has "no Termux wake lock")"
setup; android adbwifi=0; run
check "wireless debugging off: WARN" yes "$(has "wireless debugging is off")"
setup; android api=0; run
check "no Termux:API: WARN" yes "$(has "Termux:API not installed")"

setup; rm "$T/home/server/rish"; run
check "no Shizuku set up: degraded, battery check advice by hand" "degraded yes" "$(first) $(has "Unrestricted by hand")"
setup; FAKE_SHIZUKU=0 run
check "Shizuku not answering: degraded, says to start it" "degraded yes" "$(first) $(has "open the Shizuku app")"

setup; rm "$T/prefix/var/lib/proot-distro/containers/bot/rootfs/opt/bot/token"; run
check "bot enabled without token: FAIL" yes "$(has "tools/noroot-bot.sh token")"
setup; rm "$T/home/server/BOT_ENABLED" "$T/home/server/bot.pid"; run
check "bot disabled on purpose: not a problem" ok "$(first)"
setup; echo 99999999 > "$T/home/server/charge.pid"; run
check "watchdog not running: FAIL with the restart command" "broken yes" "$(first) $(has "sh ~/.termux/boot/00-server.sh")"
setup; echo $(( $(date +%s) - 900 )) > "$T/prefix/var/lib/proot-distro/containers/bot/rootfs/opt/bot/heartbeat"; run
check "bot silent 15 min: WARN" yes "$(has "bot silent for")"
setup; rm -rf "$T/prefix/var/lib/proot-distro/containers/bot/rootfs/opt/bot/venv"; run
check "container without Python: FAIL, provision" yes "$(has "tools/noroot-install.sh provision")"
setup; printf 'OEM="oops\n' > "$T/home/server/server.conf"; run
check "server.conf syntax error: FAIL" yes "$(has "server.conf has a syntax error")"

setup; FAKE_FREE_MB=200 run
check "200 MB free: FAIL" "broken yes" "$(first) $(has "only 200 MB free")"
setup; FAKE_FREE_MB=800 run
check "800 MB free: WARN" "degraded yes" "$(first) $(has "WARN 800 MB free")"

setup; FAKE_SDK=23 FAKE_REL=6.0 run
check "Android 6: FAIL, use root mode" "broken yes" "$(first) $(has "use root mode")"
setup; FAKE_SDK=29 FAKE_REL=10 run
check "Android 10: WARN, Shizuku cannot autostart" yes "$(has "cannot start by itself at boot")"
setup; FAKE_ARCH=x86_64 run
check "untested CPU: WARN" yes "$(has "CPU x86_64: not tested")"
setup; FAKE_SSHD=0 run
check "sshd down: WARN" yes "$(has "sshd not running")"

# Shizuku down: the cause found by shizuku.sh probe decides the advice
setup; FAKE_SHIZUKU=0 FAKE_RISH=not-running run
check "Shizuku service stopped: says Start, and that the watchdog retries" "yes yes" "$(has "service is stopped") $(has "the watchdog asks it to start by itself")"
setup; sed -i /SHIZUKU_AUTH/d "$T/home/server/server.conf"; FAKE_SHIZUKU=0 FAKE_RISH=not-running run
check "Shizuku stopped without SHIZUKU_AUTH: tells how to enable auto-start" yes "$(has "set SHIZUKU_AUTH")"
setup; FAKE_SHIZUKU=0 FAKE_RISH=timeout run
check "Shizuku app frozen: battery advice for Shizuku itself" yes "$(has "Settings > Apps > Shizuku > Battery")"
setup; FAKE_SHIZUKU=0 FAKE_RISH=denied run
check "Termux not authorised: says where to authorise it" yes "$(has "Authorized applications")"
setup; FAKE_SHIZUKU=0 FAKE_RISH=dialog SHIZUKU_PROBE_TIMEOUT=1 run
check "permission dialog waiting: says to tap Allow" yes "$(has "tap Allow")"
# Shizuku up: what it needs to restart by itself
setup; android shzwss=0; run
check "Shizuku without WRITE_SECURE_SETTINGS: WARN with the pm grant command" yes "$(has "pm grant moe.shizuku.privileged.api")"
setup; android shzidle=0; run
check "Shizuku app battery-optimised: WARN" yes "$(has "the Shizuku app is under battery optimisation")"
setup; sed -i /SHIZUKU_AUTH/d "$T/home/server/server.conf"; run
check "no SHIZUKU_AUTH: WARN with where to find it" yes "$(has "View intents")"
setup; android cred=PIN; run
check "screen lock PIN: WARN that nothing starts after a reboot until unlocked" yes "$(has "NOTHING starts until someone unlocks")"
setup; android cred=; run
check "lock type unknown (format not found): no lock warning" no "$(has "screen lock")"

echo "---- $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
