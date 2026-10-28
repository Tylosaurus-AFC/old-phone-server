#!/usr/bin/env bash
# NO-ROOT mode: put the configuration of a backup back on the phone and start the bot.
# Works with a backup made by tools/noroot-backup.sh AND with one made by tools/backup.sh on
# a rooted phone: that is the MIGRATION path root -> no-root (or the reverse).
#   tools/noroot-restore.sh backup/<date>
# Before migrating, switch the bot OFF on the old phone (tools/enable-bot.sh off): the same
# token on two phones gives Telegram error 409 and duplicated downloads.
set -euo pipefail
source "$(dirname "$0")/noroot-common.sh"
SRC="${1:?Usage: tools/noroot-restore.sh backup/<date>}"
[ -f "$SRC/token" ] || { echo "$SRC does not look like a backup (no token file)"; exit 1; }
need_phone

FILES=""
for f in token api.txt cookies.txt owners users.json subs.json cache.json stats.json channels.json likes.json \
         mtproto.session ytmusic_cookies.txt lastfm.json scrobble_state.json camaras.json stt.json \
         voicemonkey.json device.json bot.db; do
  [ -f "$SRC/$f" ] && FILES="$FILES $f"
done
echo "Restoring:$FILES"
OPT='$PREFIX/var/lib/proot-distro/containers/'"$CONTAINER"'/rootfs/opt/bot'

ph 'rm -f ~/server/BOT_ENABLED; touch ~/server/stopping; pkill -9 -f "[s]erver/bot.sh"; pkill -f "^/opt/bot/venv/bin/python3 /opt/bot/bot.py"; sleep 3; true'
# The extract decides success: a failed cd/tar (no space, missing container) must not be
# reported as a restore.
OK=1
( cd "$SRC" && tar -cf - $FILES ) | ph "cd $OPT && tar -xf - && { chmod 600 token api.txt cookies.txt mtproto.session 2>/dev/null; rm -f heartbeat pending_downloads.json pending_voice.json; true; }" || OK=0
ph 'rm -f ~/server/stopping; touch ~/server/BOT_ENABLED; ~/server/bot.sh'      # back on either way
if [ "$OK" != 1 ]; then
  echo "RESTORE FAILED: the files could not be written on the phone (no space? container '$CONTAINER' missing?)."
  echo "Some of the previous files may already be replaced; the bot was switched back on."
  echo "Check with tools/noroot-doctor.sh, fix it and run this again."
  exit 1
fi
sleep 25
ph 'tail -3 '"$OPT"'/bot.log' || true
echo "Done. Check /estado, /salud and one link."
