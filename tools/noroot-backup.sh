#!/usr/bin/env bash
# NO-ROOT mode: back up the bot's configuration AND secrets to your PC (backup/noroot-<date>/,
# never commit it: .gitignore covers backup/). For the whole Debian use `proot-distro backup`
# (see docs/*/08-*.md).
set -euo pipefail
source "$(dirname "$0")/noroot-common.sh"
need_phone
DEST="$ROOT/backup/noroot-$(date +%Y%m%d-%H%M)"
mkdir -p "$DEST/android"

FILES="token api.txt cookies.txt owners users.json subs.json cache.json stats.json channels.json likes.json
       mtproto.session ytmusic_cookies.txt lastfm.json scrobble_state.json camaras.json stt.json
       voicemonkey.json device.json bot.db"
FILES=$(echo $FILES)    # one line (it goes inside a remote command)
OPT='$PREFIX/var/lib/proot-distro/containers/'"$CONTAINER"'/rootfs/opt/bot'
ph "cd $OPT && date +%s > last_backup && tar -cf - \$(ls $FILES 2>/dev/null)" | tar -xf - -C "$DEST"
ph "cp ~/server/server.conf /dev/stdout" > "$DEST/noroot-server.conf" 2>/dev/null || true
ph '~/server/enter.sh "/opt/bot/venv/bin/pip freeze --local" 2>/dev/null' | grep -v -E "overlaps|^Warning" > "$DEST/pip-freeze.txt" || true
ph '~/server/sa.sh "pm list packages 2>&1 | cat; echo ---; getprop"' > "$DEST/android/packages-and-getprop.txt" || true
[ -s "$DEST/token" ] || { echo "BACKUP INCOMPLETE: no token in $DEST (is the bot installed on the phone?)."; exit 1; }
echo "Backup in: $DEST   (contains SECRETS: keep it private)"
ls -l "$DEST"
