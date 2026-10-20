#!/system/bin/sh
# BOOT LAUNCHER for old phones rooted with KingRoot (Android 4.4-5.x, e.g. Galaxy S4 mini).
# Install as /system/xbin/server-boot (mode 755, context u:object_r:system_file:s0) and
# add the line `/system/xbin/server-boot &` to /system/bin/ddexe, BEFORE the line that runs
# ddexe_real. See docs/*/05-services-and-boot.md for why it has to be done this way.
#
# Waits until `su` answers, then runs start.sh as root with a full root context.
n=0
until /system/xbin/su -c true >/dev/null 2>&1 || [ $n -ge 60 ]; do
  sleep 5; n=$((n + 1))
done
/system/xbin/su -c "/system/bin/sh /data/debian/start.sh"
