#!/bin/bash
# Runs INSIDE the Debian chroot. Makes /tmp/debian-rootfs.tgz (+ .sha256): a complete,
# restorable copy of this Debian WITHOUT your secrets (token, cookies, Telegram session,
# API keys). Restore it on another phone with tools/restore-full.sh, then put the secrets
# back with tools/restore-config.sh. The bot keeps running while this is made (~10 min).
set -e
OUT=/tmp/debian-rootfs.tgz
tar -czpf $OUT \
  --exclude=./proc --exclude=./sys --exclude=./dev --exclude=./tmp --exclude=./sdcard \
  --exclude=./run --exclude=./var/cache/apt --exclude=./var/lib/apt/lists \
  --exclude=./opt/bot/token --exclude=./opt/bot/api.txt --exclude=./opt/bot/owners \
  --exclude=./opt/bot/users.json --exclude=./opt/bot/subs.json --exclude=./opt/bot/cache.json \
  --exclude='./opt/bot/*.session' --exclude='./opt/bot/*.session-journal' \
  --exclude=./opt/bot/cookies.txt --exclude=./opt/bot/ytmusic_cookies.txt \
  --exclude=./opt/bot/lastfm.json --exclude=./opt/bot/scrobble_state.json \
  --exclude=./opt/bot/camaras.json --exclude=./opt/bot/voicemonkey.json \
  --exclude=./opt/bot/stt.json --exclude=./opt/bot/events.jsonl --exclude='./opt/bot/bot.log*' \
  --exclude='./opt/bot/pending_*.json' --exclude=./opt/bot/heartbeat \
  --exclude=./root/.bash_history --exclude=./root/.cache \
  -C / .
cd /tmp && sha256sum debian-rootfs.tgz > debian-rootfs.tgz.sha256
ls -lh $OUT
