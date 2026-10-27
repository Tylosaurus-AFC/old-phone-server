#!/usr/bin/env bash
# Runs every test. Needs bash and python3 with `requests` installed (pip install requests).
set -e
cd "$(dirname "$0")/.."
echo "== shell syntax =="; for f in tools/*.sh phone/*.sh phone/boot/*.sh phone/boot/initrc/*.sh phone/extras/*.sh phone/noroot/*.sh phone/noroot/extras/*.sh config.example.sh; do bash -n "$f"; done; echo ok
echo "== no secrets committed =="
# Telegram bot tokens (123456:AA...) and private keys in tracked files. The test token in
# tests/test_bot.py does not match (too short).
if git ls-files -z 2>/dev/null | xargs -0 grep -nIE '[0-9]{8,10}:AA[A-Za-z0-9_-]{33}|BEGIN [A-Z ]*PRIVATE KEY' 2>/dev/null; then
  echo "FAIL: possible secret above"; exit 1
fi; echo ok
echo "== charge.sh against a fake battery =="; bash tests/test_charge.sh
echo "== no-root charge.sh with a fake Shizuku =="; bash tests/test_noroot.sh
echo "== bot.sh back-off and start.sh boot sequence =="; bash tests/test_services.sh
echo "== bot, plugins, helpers =="; "${PYTHON:-python3}" tests/test_bot.py
