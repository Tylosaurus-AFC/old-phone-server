#!/system/bin/sh
# BOOT LAUNCHER for phones rooted with Magisk (any Android that Magisk supports).
# Install as /data/adb/service.d/server.sh (mode 755). Magisk runs every script in that
# folder as root at boot, so this is all that is needed.
/system/bin/sh /data/debian/start.sh
