#!/system/bin/sh
# Mount and enter the Debian chroot.  Usage: enter.sh [command...]
# Installed on the phone as /data/debian/enter.sh and run as root.
DEBIAN=${DEBIAN:-/data/debian}
BB=${BB:-/system/xbin/busybox-deb}
[ -x "$BB" ] || BB=$DEBIAN/busybox-deb   # Magisk / LineageOS: busybox lives in /data
R=$DEBIAN/fs

mounted() { $BB grep -q " $1 " /proc/mounts; }

mounted $R/proc    || $BB mount -t proc proc $R/proc
mounted $R/sys     || $BB mount -t sysfs sys $R/sys
mounted $R/dev     || $BB mount -o bind /dev $R/dev
mounted $R/dev/pts || $BB mount -t devpts devpts $R/dev/pts
mounted $R/dev/shm || { $BB mkdir -p $R/dev/shm; $BB mount -t tmpfs tmpfs $R/dev/shm; }
# Phone storage visible inside the chroot (optional; the path differs per Android version)
if [ -d /data/media/0 ]; then
  mounted $R/sdcard || { $BB mkdir -p $R/sdcard; $BB mount -o bind /data/media/0 $R/sdcard; }
fi

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root TERM=${TERM:-linux} LANG=C.UTF-8 TMPDIR=/tmp
unset LD_PRELOAD ANDROID_ROOT BOOTCLASSPATH

if [ $# -eq 0 ]; then
  exec $BB chroot $R /bin/bash -l
else
  exec $BB chroot $R /bin/bash -lc "$*"
fi
