#!/usr/bin/env bash
# NO-ROOT mode: connect your PC's adb to the phone over Wireless debugging (no cable).
# Your PC must be paired once (Developer options > Wireless debugging > Pair device with code:
# `adb pair <ip>:<pairing-port>`). guard.sh keeps Wireless debugging switched on, but Android
# picks a new port every time: this script finds it by mDNS or, failing that, by scanning
# ports 30000-50000.
#   tools/noroot-adb.sh            -> connects and prints the serial on the last line
#   adb -s "$(tools/noroot-adb.sh | tail -1)" shell ...
# If Termux is down: adb -s <serial> shell am start -n com.termux/.app.TermuxActivity
set -uo pipefail
source "$(dirname "$0")/noroot-common.sh"
IP="${NOROOT_IP}"
ADB="${ADB:-adb}"
ok() { [ "$("$ADB" -s "$1" get-state 2>/dev/null)" = device ]; }

for s in $("$ADB" devices | awk -v ip="$IP" 'index($1, ip ":") == 1 {print $1}'); do
  ok "$s" && { echo "$s"; exit 0; }
  "$ADB" disconnect "$s" >/dev/null 2>&1
done
P=$("$ADB" mdns services 2>/dev/null | awk -v ip="$IP" '/_adb-tls-connect/ && index($3, ip ":") == 1 {split($3, a, ":"); print a[2]; exit}')
if [ -z "$P" ]; then
  P=$(python3 - "$IP" <<'EOF'
import asyncio, sys
ip = sys.argv[1]
async def probe(p, sem, found):
    async with sem:
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(ip, p), 0.5)
            found.append(p); w.close()
        except Exception:
            pass
async def main():
    sem, found = asyncio.Semaphore(1500), []
    await asyncio.gather(*(probe(p, sem, found) for p in range(30000, 50001)))
    print(" ".join(map(str, sorted(found))))
asyncio.run(main())
EOF
)
fi
for p in $P; do
  "$ADB" connect "$IP:$p" >/dev/null 2>&1
  for _ in 1 2 3 4 5 6; do          # just enabled: it takes a few seconds to become "device"
    ok "$IP:$p" && { echo "$IP:$p"; exit 0; }
    sleep 2
  done
  "$ADB" disconnect "$IP:$p" >/dev/null 2>&1
done
echo "Cannot find the phone's Wireless debugging at $IP" >&2
exit 1
