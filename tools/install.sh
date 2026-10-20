#!/usr/bin/env bash
# Step-by-step installer, run from your PC with the phone connected (USB debugging on,
# phone already rooted). Each step is a sub-command so you can repeat just the one that
# failed. Full explanation: docs/en/03-install.md (docs/es/03-instalacion.md).
#
#   tools/install.sh check             what phone is this? CPU, Android, root, storage
#   tools/install.sh busybox [file]    put busybox on the phone and test its `chroot`
#   tools/install.sh rootfs  [file]    push and unpack the Debian root filesystem
#   tools/install.sh scripts           push enter.sh, bot.sh, charge.sh, start.sh, server.conf
#   tools/install.sh provision         inside Debian: packages, Python venv, yt-dlp...
#   tools/install.sh boot              install the boot launcher for your BOOT_MODE
#   tools/install.sh voice             (optional) speech-to-text: whisper.cpp + Vosk
set -euo pipefail
source "$(dirname "$0")/common.sh"
step="${1:-}"; shift || true
case "$step" in
  check|busybox|rootfs|scripts|provision|boot|voice) need_phone ;;
esac

case "$step" in
check)
  remote <<'EOF'
echo "== Phone =="
echo "model:      $(getprop ro.product.manufacturer) $(getprop ro.product.model) ($(getprop ro.product.device))"
echo "android:    $(getprop ro.build.version.release) (SDK $(getprop ro.build.version.sdk))"
echo "cpu abis:   $(getprop ro.product.cpu.abilist)   <- armeabi-v7a = 32-bit ARM (armhf), arm64-v8a = 64-bit"
echo "kernel:     $(uname -r) $(uname -m)"
echo "selinux:    $(getenforce 2>/dev/null)"
echo "root:       $(id)"
echo "RAM:        $(grep -E 'MemTotal|MemAvailable' /proc/meminfo | tr -s ' ' | tr '\n' ' ')"
echo "/data free: $(df /data | tail -1)"
echo "battery:    $(cat /sys/class/power_supply/battery/capacity 2>/dev/null)% health=$(cat /sys/class/power_supply/battery/health 2>/dev/null) temp=$(cat /sys/class/power_supply/battery/temp 2>/dev/null)"
echo "charge-control files present on this phone:"
for f in batt_slate_mode charging_enabled input_suspend charge_control_limit store_mode; do
  [ -e /sys/class/power_supply/battery/$f ] && echo "   battery/$f = $(cat /sys/class/power_supply/battery/$f 2>/dev/null)"
done
[ -e /system/xbin/busybox-deb ] && echo "busybox:    /system/xbin/busybox-deb present"
[ -e /data/debian/busybox-deb ] && echo "busybox:    /data/debian/busybox-deb present"
echo "(abilist tells you which ARCH to put in config.sh; BATT_CTRL goes in server.conf)"
EOF
  ;;

busybox)
  FILE="${1:-$ROOT/downloads/busybox-armv7l}"
  [ -f "$FILE" ] || { echo "No busybox at $FILE (run tools/fetch-assets.sh, or pass a file)"; exit 1; }
  a push "$(winpath "$FILE")" /data/local/tmp/busybox-new >/dev/null
  remote <<EOF
set -e
mkdir -p $DEBIAN
D=$BB_PATH
case "\$D" in /system/*) mount -o rw,remount /system ;; esac
cp /data/local/tmp/busybox-new \$D
chmod 755 \$D
case "\$D" in /system/*) chcon u:object_r:system_file:s0 \$D 2>/dev/null; mount -o ro,remount /system || true ;; esac
rm -f /data/local/tmp/busybox-new
echo "busybox: \$(\$D | head -1)"
\$D --list | grep -qx chroot && echo "chroot applet: OK" || { echo "THIS BUSYBOX HAS NO chroot -- use another build"; exit 1; }
EOF
  ;;

rootfs)
  FILE="${1:-$ROOT/downloads/rootfs-$ARCH.tar.xz}"
  [ -f "$FILE" ] || { echo "No rootfs at $FILE (run tools/fetch-assets.sh, or pass a file)"; exit 1; }
  # busybox tar often lacks xz: recompress as gzip on the PC (a few minutes)
  GZ="$ROOT/downloads/rootfs-$ARCH.tar.gz"
  if [ ! -f "$GZ" ]; then
    echo "Recompressing as .tar.gz for the phone's busybox..."
    xz -dc "$FILE" | gzip -6 > "$GZ"
  fi
  if remote <<'EOF' | grep -q HAS_DEBIAN
[ -d /data/debian/fs/usr ] && echo HAS_DEBIAN
EOF
  then
    echo "/data/debian/fs already holds a Debian. Move or delete it first (docs/*/03-install.md)."
    exit 1
  fi
  echo "Pushing $(du -h "$GZ" | cut -f1) to the phone..."
  a push "$(winpath "$GZ")" /data/local/tmp/rootfs.tar.gz
  remote <<EOF
set -e
B=$BB_PATH; [ -x \$B ] || B=/system/xbin/busybox-deb
mkdir -p $DEBIAN/fs && cd $DEBIAN/fs
\$B tar -xzpf /data/local/tmp/rootfs.tar.gz
mkdir -p proc sys dev tmp sdcard; chmod 1777 tmp
rm -f /data/local/tmp/rootfs.tar.gz
echo "Debian unpacked: \$(cat $DEBIAN/fs/etc/debian_version)"
EOF
  ;;

scripts)
  TMPD="$ROOT/.push"; rm -rf "$TMPD"; mkdir -p "$TMPD"
  cp "$ROOT"/phone/{enter.sh,bot.sh,charge.sh,start.sh} "$TMPD/"
  cp "$ROOT/phone/server.conf.example" "$TMPD/server.conf"
  [ -f "$ROOT/phone/extras/wifi-band.sh" ] && cp "$ROOT/phone/extras/wifi-band.sh" "$TMPD/"
  a shell "rm -rf $TMP.d; mkdir -p $TMP.d"
  a push "$(winpath "$TMPD")/." "$TMP.d/" >/dev/null
  rm -rf "$TMPD"
  remote <<EOF
set -e
mkdir -p $DEBIAN
cd $TMP.d
for s in enter.sh bot.sh charge.sh start.sh wifi-band.sh; do
  [ -f \$s ] && cp \$s $DEBIAN/\$s && chmod 755 $DEBIAN/\$s
done
[ -f $DEBIAN/server.conf ] || { cp server.conf $DEBIAN/server.conf; echo "created $DEBIAN/server.conf (EDIT IT: battery control, Wi-Fi...)"; }
rm -rf $TMP.d
mkdir -p $DEBIAN/fs/opt/bot
echo "scripts installed in $DEBIAN"
EOF
  ;;

provision)
  a shell "rm -rf $TMP.p; mkdir -p $TMP.p"
  a push "$(winpath "$ROOT")/phone/setup-debian.sh" "$(winpath "$ROOT")/bot/requirements.txt" "$TMP.p/" >/dev/null
  remote <<EOF
set -e
cp $TMP.p/setup-debian.sh $DEBIAN/fs/root/setup-debian.sh
mkdir -p $DEBIAN/fs/opt/bot && cp $TMP.p/requirements.txt $DEBIAN/fs/opt/bot/requirements.txt
rm -rf $TMP.p
$DEBIAN/enter.sh "TZ_NAME='$TZ_NAME' bash /root/setup-debian.sh"
EOF
  ;;

boot)
  case "$BOOT_MODE" in
  magisk)
    a push "$(winpath "$ROOT")/phone/boot/magisk-service.d.sh" "$TMP.boot" >/dev/null
    remote <<EOF
mkdir -p /data/adb/service.d
cp $TMP.boot /data/adb/service.d/server.sh && chmod 755 /data/adb/service.d/server.sh && rm -f $TMP.boot
echo "installed /data/adb/service.d/server.sh"
EOF
    ;;
  kingroot)
    a push "$(winpath "$ROOT")/phone/boot/kingroot-ddexe.sh" "$TMP.boot" >/dev/null
    remote <<EOF
mount -o rw,remount /system
cp $TMP.boot /system/xbin/server-boot && chmod 755 /system/xbin/server-boot
chcon u:object_r:system_file:s0 /system/xbin/server-boot 2>/dev/null
mount -o ro,remount /system || true
rm -f $TMP.boot
echo "installed /system/xbin/server-boot"
EOF
    cat <<'MSG'

MANUAL STEP (deliberately not automated: a mistake here can stop the phone booting).
Follow docs/*/05-services-and-boot.md, section "KingRoot": add the line
    /system/xbin/server-boot &
to /system/bin/ddexe, before the line that runs ddexe_real, keeping a copy of the original.
MSG
    ;;
  initrc)
    a push "$(winpath "$ROOT")/phone/boot/initrc/server-boot.sh" "$TMP.sb" >/dev/null
    a push "$(winpath "$ROOT")/phone/boot/initrc/server-boot.rc" "$TMP.rc" >/dev/null
    remote <<EOF
mount -o rw,remount / 2>/dev/null || mount -o rw,remount /system
cp $TMP.rc /system/etc/init/server-boot.rc && chmod 644 /system/etc/init/server-boot.rc
cp $TMP.sb /data/local/tmp/server-boot.sh && chmod 755 /data/local/tmp/server-boot.sh
rm -f $TMP.rc $TMP.sb
echo "installed server-boot.rc and server-boot.sh (REVIEW the service list in server-boot.sh first!)"
EOF
    ;;
  *) echo "BOOT_MODE=$BOOT_MODE: install your boot launcher by hand (docs/*/05-*.md)" ;;
  esac
  ;;

voice)
  a push "$(winpath "$ROOT")/phone/extras/setup-voice.sh" "$TMP.v" >/dev/null
  remote <<EOF
cp $TMP.v $DEBIAN/fs/root/setup-voice.sh && rm -f $TMP.v
$DEBIAN/enter.sh "bash /root/setup-voice.sh"
EOF
  ;;

*)
  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
  exit 1 ;;
esac
