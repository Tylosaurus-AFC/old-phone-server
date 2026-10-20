#!/usr/bin/env bash
# Make a complete copy of the phone's Debian (no secrets inside) and download it to
# backup/image-<date>/. The bot keeps running meanwhile (~10 min + the download).
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_phone
D="$ROOT/backup/image-$(date +%Y%m%d)"; mkdir -p "$D"

a push "$(winpath "$ROOT")/phone/extras/make-image.sh" "$TMP.mi" >/dev/null
remote <<EOF
cp $TMP.mi $DEBIAN/fs/root/make-image.sh && rm -f $TMP.mi
$DEBIAN/enter.sh "bash /root/make-image.sh"
# adb cannot read inside /data/debian: move the image out first
mv $DEBIAN/fs/tmp/debian-rootfs.tgz* /data/local/tmp/ && chmod 644 /data/local/tmp/debian-rootfs.tgz*
EOF
a pull /data/local/tmp/debian-rootfs.tgz "$(winpath "$D")/"
a pull /data/local/tmp/debian-rootfs.tgz.sha256 "$(winpath "$D")/"
( cd "$D" && sha256sum -c debian-rootfs.tgz.sha256 )
remote <<EOF
rm -f /data/local/tmp/debian-rootfs.tgz*
EOF
echo "Image saved in $D"
