#!/data/data/com.termux/files/usr/bin/sh
# NO-ROOT mode: enter the Debian container.  Usage: enter.sh [command...]
# Without root the bot cannot read the battery or uptime of Android: charge.sh copies them
# every minute into /opt/bot/sys and here they are bind-mounted where the bot looks for them.
D=$HOME/server
[ -f $D/server.conf ] && . $D/server.conf
CONTAINER=${CONTAINER:-bot}
FS=$PREFIX/var/lib/proot-distro/containers/$CONTAINER/rootfs
SYS=$FS/opt/bot/sys
B=""
[ -d $SYS/battery ] && B="$B --bind $SYS/battery:/sys/class/power_supply/battery"
for f in uptime loadavg; do
  [ -s $SYS/$f ] && B="$B --bind $SYS/$f:/proc/$f"
done
# External USB disk (exFAT): at /mnt/disk inside, if mounted (charge.sh notes which one)
V=$(cat $SYS/disk 2>/dev/null)
[ -n "$V" ] && [ -d /storage/$V ] && B="$B --bind /storage/$V:/mnt/disk"
unset LD_PRELOAD
if [ $# -eq 0 ]; then
  exec proot-distro login $CONTAINER $B --env LANG=C.UTF-8
else
  exec proot-distro login $CONTAINER $B --env LANG=C.UTF-8 -- /bin/bash -lc "$*"
fi
