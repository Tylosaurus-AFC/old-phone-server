# config.sh -- settings for the PC-side scripts in tools/. Copy this file to config.sh
# (it is git-ignored) and edit it:   cp config.example.sh config.sh
# It is plain bash. Anything set in your environment overrides it.

# adb executable. On Linux/macOS usually just `adb`; on Windows (Git Bash) the full path, e.g.
#   ADB=/c/Users/YOU/AppData/Local/Android/Sdk/platform-tools/adb.exe
ADB="${ADB:-adb}"

# How to reach the phone. USB is used when the serial answers (`adb devices` shows it);
# otherwise the scripts connect over Wi-Fi to PHONE_IP:5555. Reserve that IP in your router.
USB_SERIAL="${USB_SERIAL:-}"
PHONE_IP="${PHONE_IP:-192.168.1.50}"

# How the phone is rooted -- decides how commands run as root and how the server starts
# at boot (see docs/*/02-root.md and docs/*/05-services-and-boot.md):
#   su       an ordinary `su` binary (KingRoot, Magisk, SuperSU...)      [most phones]
#   adbroot  no `su`, but `adb root` works (a LineageOS "userdebug" build)
ROOT_MODE="${ROOT_MODE:-su}"

# Boot launcher to install with `tools/install.sh --boot`:
#   kingroot   hook in /system/bin/ddexe        (Android 4.4/5, KingRoot)
#   magisk     /data/adb/service.d/server.sh    (Magisk)
#   initrc     /system/etc/init/server-boot.rc  (userdebug ROMs without su)
#   none       you do it yourself
BOOT_MODE="${BOOT_MODE:-magisk}"

# Where busybox lives on the phone. Old Samsung kernels (sec_restrict_fork) forbid root
# from running binaries stored in /data, so there it must be in /system/xbin.
# Everywhere else /data/debian/busybox-deb is fine.
BB_PATH="${BB_PATH:-/data/debian/busybox-deb}"

# CPU architecture of the Debian to install: armhf (32-bit ARM) or arm64.
# Check with: adb shell getprop ro.product.cpu.abilist
ARCH="${ARCH:-armhf}"

# Optional plugins to deploy with `tools/deploy.sh` (see extras/plugins/ and docs/*/09-plugins.md).
# Space separated names of files in extras/plugins/ without .py. Empty = none.
#   cameras alexa stickers lastfm_scrobbler
PLUGINS="${PLUGINS:-}"

# Time zone for the Debian clock (Debian is installed in UTC). IANA name.
TZ_NAME="${TZ_NAME:-UTC}"
