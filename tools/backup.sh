#!/usr/bin/env bash
# Copy the bot's configuration AND secrets to your PC (backup/<date>/, never commit it:
# it is in .gitignore). With that plus this repository you can rebuild the server on
# another phone. For the whole Debian system use tools/make-image.sh instead.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_phone

DEST="$ROOT/backup/$(date +%Y%m%d-%H%M)"
mkdir -p "$DEST"

# The files belong to root: copy them to a readable temp folder and pull from there
remote <<EOF
T=$TMP.bk; rm -rf \$T; mkdir -p \$T
cd $DEBIAN/fs/opt/bot
for f in token api.txt cookies.txt owners users.json subs.json cache.json stats.json \
         channels.json likes.json bot.db \
         mtproto.session ytmusic_cookies.txt lastfm.json scrobble_state.json camaras.json \
         voicemonkey.json stt.json device.json; do
  [ -f \$f ] && cp \$f \$T/
done
cp $DEBIAN/server.conf \$T/ 2>/dev/null
$DEBIAN/enter.sh "/opt/bot/venv/bin/pip freeze --local" > \$T/pip-freeze.txt
date +%s > $DEBIAN/fs/opt/bot/last_backup       # for the bot's /salud
# What was changed on the Android side (to rebuild boot and the debloat)
A=\$T/android; mkdir -p \$A
cp /system/bin/ddexe /system/xbin/server-boot /system/xbin/busybox-deb \$A/ 2>/dev/null
cp /data/adb/service.d/server.sh /system/etc/init/server-boot.rc \$A/ 2>/dev/null
cp $DEBIAN/enter.sh $DEBIAN/bot.sh $DEBIAN/charge.sh $DEBIAN/start.sh \$A/ 2>/dev/null
pm list packages -d | sed "s/package://" | sort > \$A/disabled-apps.txt
pm list packages -3 | sed "s/package://" | sort > \$A/user-apps.txt
getprop > \$A/getprop.txt
chmod -R 755 \$T; find \$T -type f -exec chmod 644 {} \;
EOF
a pull "$TMP.bk/." "$(winpath "$DEST")" >/dev/null
remote <<EOF
rm -rf $TMP.bk
EOF

echo "Backup in: $DEST   (contains SECRETS: keep it private)"
ls -l "$DEST"
