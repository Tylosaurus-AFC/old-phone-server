#!/system/bin/sh
# Companion of server-boot.rc. Install as /data/local/tmp/server-boot.sh.
# EXAMPLE from a Moto X2 (LineageOS 18.1, 2 GB RAM, no launcher): trims what a server
# does not need, then hands over to start.sh. Edit/remove steps that do not fit your phone.
LOG=/data/local/tmp/server-boot.log
echo "$(date) server boot" >> $LOG

# 1) Compressed swap in RAM: 1 GB (lz4). Skip if your kernel has no zram.
if [ -e /sys/block/zram0/disksize ] && [ "$(cat /sys/block/zram0/disksize)" != "1073741824" ]; then
  swapoff /dev/block/zram0
  echo 1 > /sys/block/zram0/reset
  echo lz4 > /sys/block/zram0/comp_algorithm
  echo 1073741824 > /sys/block/zram0/disksize
  mkswap /dev/block/zram0 >/dev/null && swapon /dev/block/zram0
fi
echo 100 > /proc/sys/vm/swappiness

# 2) Screen: with no launcher/systemui Android sits on "Starting phone" (FallbackHome).
#    Stop the boot animation and put the screen to sleep; the CPU stays awake thanks to
#    the wake lock that start.sh takes.
settings put system screen_off_timeout 15000
setprop service.bootanim.exit 1; stop bootanim
input keyevent 223

# 3) Native services a server never uses (names are ROM-specific: `getprop | grep init.svc`)
for s in statsd traced traced_probes incidentd storaged mediametrics \
         vendor.nfc_hal_service vendor.bluetooth-1-0 vendor.gnss_service qcamerasvr \
         vendor.cas-hal-1-2 vendor.drm-clearkey-hal-1-3 vendor.drm-hal-1-0 drm \
         vendor.livedisplay-hal-2-0-sysfs vendor.vibrator-1-1 credstore; do
  stop $s 2>/dev/null
done
echo "$(date) trimmed; handing over to start.sh" >> $LOG

# 4) start.sh never returns (it runs the watchdog loop). It must be `exec`: init kills the
#    children of a service when the service ends, so this script has to stay alive.
exec /system/bin/sh /data/debian/start.sh
