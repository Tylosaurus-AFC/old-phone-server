#!/usr/bin/env bash
# Runs every test. Needs bash and python3 with `requests` installed (pip install requests).
set -e
cd "$(dirname "$0")/.."
echo "== shell syntax =="; for f in tools/*.sh phone/*.sh phone/boot/*.sh phone/boot/initrc/*.sh phone/extras/*.sh phone/noroot/*.sh phone/noroot/extras/*.sh config.example.sh; do bash -n "$f"; done; echo ok
echo "== charge.sh against a fake battery =="; bash tests/test_charge.sh
echo "== no-root charge.sh with a fake Shizuku =="; bash tests/test_noroot.sh
echo "== bot.sh back-off and start.sh boot sequence =="; bash tests/test_services.sh
echo "== bot, plugins, helpers =="; "${PYTHON:-python3}" tests/test_bot.py
