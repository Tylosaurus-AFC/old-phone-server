#!/usr/bin/env bash
# Every backup/restore script must cover the same persistent files of /opt/bot (settings,
# secrets, history). They used to drift apart: a file added to one list but not the others
# was silently lost on restore. When the bot gets a new persistent file, add it here and to
# every script below.
set -u
cd "$(dirname "$0")/.."
FILES="token api.txt cookies.txt owners users.json subs.json cache.json stats.json channels.json
       likes.json mtproto.session ytmusic_cookies.txt lastfm.json scrobble_state.json camaras.json
       stt.json voicemonkey.json device.json bot.db"
PASS=0; FAIL=0
for s in tools/backup.sh tools/noroot-backup.sh tools/noroot-restore.sh phone/noroot/extras/backup.sh; do
  miss=""
  for f in $FILES; do grep -qwF "$f" "$s" || miss="$miss $f"; done
  if [ -z "$miss" ]; then PASS=$((PASS + 1)); echo "ok   - $s covers every persistent file"
  else FAIL=$((FAIL + 1)); echo "FAIL - $s is missing:$miss"; fi
done
# restore-config.sh copies whatever the backup holds, atomically (temp copy + mv)
if grep -q 'mv .*\.rst' tools/restore-config.sh; then PASS=$((PASS + 1)); echo "ok   - restore-config.sh replaces files atomically"
else FAIL=$((FAIL + 1)); echo "FAIL - restore-config.sh must replace files atomically"; fi
echo "---- $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
