#!/data/data/com.termux/files/usr/bin/bash
# RECIPE: weekly backup of the bot to the external USB disk: settings and secrets (token,
# cookies, owners, followed channels, cache and statistics in bot.db...) to
# <disk>/Backups/bot-YYYYMMDD.tgz, keeping the last 8. charge.sh runs it on Sundays at 04:00
# when server.conf has WEEKLY_BACKUP=1; you can also run it by hand: ~/server/extras/backup.sh
# It holds the bot token: the webdav and dlna recipes do NOT serve the Backups folder.
D=$HOME/server
[ -f $D/server.conf ] && . $D/server.conf
OPT=$PREFIX/var/lib/proot-distro/containers/${CONTAINER:-bot}/rootfs/opt/bot
V=/storage/$(cat $OPT/sys/disk 2>/dev/null)
[ -f $V/.nas ] || { echo "no USB disk (missing $V/.nas)"; exit 1; }
R=$V/Backups
mkdir -p $R
F=$R/bot-$(date +%Y%m%d).tgz
T=$(mktemp -d)
cd $OPT && cp $(ls token api.txt cookies.txt owners users.json subs.json cache.json mtproto.session \
  camaras.json stt.json lastfm.json scrobble_state.json ytmusic_cookies.txt voicemonkey.json \
  device.json stats.json bot.db 2>/dev/null) $T/
cp ~/.config/server/webdav.pass $T/ 2>/dev/null
tar -czf $F.tmp -C $T . && mv $F.tmp $F || { rm -rf $T $F.tmp; echo "backup failed"; exit 1; }
rm -rf $T
date +%s > $OPT/last_backup                        # for /salud
ls -1t $R/bot-*.tgz | tail -n +9 | xargs -r rm -f  # keep the last 8
echo "Backup in $F ($(du -h $F | cut -f1))"
