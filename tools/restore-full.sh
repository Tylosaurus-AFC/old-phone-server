#!/usr/bin/env bash
# Restore a complete Debian copy (backup/image-<date>/debian-rootfs.tgz) on a phone: for a
# damaged Debian or to move the server to another phone that already has root + busybox.
#   tools/restore-full.sh backup/image-20261018            (phone with no Debian yet)
#   tools/restore-full.sh backup/image-20261018 --force    (moves the current one to fs.old)
# The image has no secrets: afterwards run tools/restore-config.sh or tools/set-token.sh.
# The CPU architecture must match (an armhf image does not run on a pure arm64 userland).
set -euo pipefail
source "$(dirname "$0")/common.sh"
SRC="${1:?Usage: tools/restore-full.sh backup/image-<date> [--force]}"
FORCE="${2:-}"
IMG="$SRC/debian-rootfs.tgz"
[ -f "$IMG" ] || { echo "Cannot find $IMG"; exit 1; }
if [ -f "$IMG.sha256" ]; then
  echo "Checking the image..."
  want=$(cut -d' ' -f1 "$IMG.sha256"); have=$(sha256sum "$IMG" | cut -d' ' -f1)
  [ "$want" = "$have" ] || { echo "The image is damaged (sha256 does not match)"; exit 1; }
fi
need_phone

if remote <<EOF | grep -q HAS_DEBIAN
[ -d $DEBIAN/fs/usr ] && echo HAS_DEBIAN
EOF
then
  [ "$FORCE" = "--force" ] || { echo "$DEBIAN/fs already holds a Debian. Use --force to move it to fs.old"; exit 1; }
fi

echo "Pushing the image ($(du -h "$IMG" | cut -f1))..."
a push "$(winpath "$IMG")" /data/local/tmp/debian-rootfs.tgz

remote <<EOF
B=$BB_PATH; [ -x \$B ] || B=/system/xbin/busybox-deb
\$B pkill -f $DEBIAN/bot.sh; \$B pkill -f opt/bot/bot.py; \$B pkill -f $DEBIAN/charge.sh
for m in sdcard dev/shm dev/pts dev sys proc; do \$B umount $DEBIAN/fs/\$m 2>/dev/null; done
mkdir -p $DEBIAN
if [ -d $DEBIAN/fs ]; then rm -rf $DEBIAN/fs.old; mv $DEBIAN/fs $DEBIAN/fs.old; fi
mkdir -p $DEBIAN/fs && cd $DEBIAN/fs
\$B tar -xzpf /data/local/tmp/debian-rootfs.tgz && echo "Debian unpacked"
mkdir -p proc sys dev tmp sdcard; chmod 1777 tmp
rm -f /data/local/tmp/debian-rootfs.tgz
EOF
echo "Done. Now: tools/install.sh scripts && tools/restore-config.sh (or set-token.sh), then tools/enable-bot.sh"
