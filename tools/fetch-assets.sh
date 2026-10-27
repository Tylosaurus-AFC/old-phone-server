#!/usr/bin/env bash
# Downloads, into downloads/, the two big files you need besides this repository:
#   - the Debian 13 root filesystem for your CPU (armhf or arm64) from linuxcontainers.org,
#     checked against its SHA256SUMS
#   - a static busybox (32-bit ARM only; on arm64 + Magisk use Magisk's own busybox, see docs)
# Usage:  tools/fetch-assets.sh          (uses ARCH from config.sh)
set -euo pipefail
source "$(dirname "$0")/common.sh"
OUT="$ROOT/downloads"; mkdir -p "$OUT"
case "${ARCH:-}" in
  armhf|arm64) ;;
  *) echo "ARCH=${ARCH:-}: must be armhf (32-bit ARM) or arm64 in config.sh." >&2
     echo "Check the phone with: adb shell getprop ro.product.cpu.abilist" >&2; exit 1 ;;
esac
BASE="https://images.linuxcontainers.org/images/debian/trixie/$ARCH/default"

echo "Looking for the newest Debian trixie $ARCH image..."
LATEST="$(curl -fsSL "$BASE/" | grep -oE 'href="[0-9]{8}_[0-9]{2}(:|%3A)[0-9]{2}/"' | sed 's/href="//; s/"$//' | sort | tail -1)"
[ -n "$LATEST" ] || { echo "Could not read $BASE/ -- download rootfs.tar.xz by hand (docs)."; exit 1; }
echo "Newest: $LATEST"

curl -fL --progress-bar -o "$OUT/rootfs-$ARCH.tar.xz" "$BASE/${LATEST}rootfs.tar.xz"
curl -fsSL -o "$OUT/SHA256SUMS-$ARCH" "$BASE/${LATEST}SHA256SUMS"
want="$(grep ' rootfs.tar.xz$' "$OUT/SHA256SUMS-$ARCH" | cut -d' ' -f1)"
have="$(sha256sum "$OUT/rootfs-$ARCH.tar.xz" | cut -d' ' -f1)"
[ -n "$want" ] && [ "$want" = "$have" ] && echo "rootfs: SHA-256 OK" \
  || { echo "rootfs: SHA-256 does NOT match -- delete it and retry"; exit 1; }

if [ "$ARCH" = armhf ]; then
  curl -fL --progress-bar -o "$OUT/busybox-armv7l" \
    "https://busybox.net/downloads/binaries/1.31.0-defconfig-multiarch-musl/busybox-armv7l"
  echo "busybox: downloaded $OUT/busybox-armv7l ($(wc -c < "$OUT/busybox-armv7l") bytes)."
  echo "         No checksum is published for it: it comes from busybox.net over HTTPS."
else
  echo "arm64: get busybox from Magisk (/data/adb/magisk/busybox) -- see docs/*/03-install.md (busybox section)"
fi
echo "Done. Next: tools/install.sh check"
