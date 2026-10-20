#!/usr/bin/env bash
# Enable or disable the bot on this phone.  tools/enable-bot.sh [off]
# The bot only runs where $DEBIAN/BOT_ENABLED exists. Never enable it on two phones with the
# same Telegram token: Telegram answers 409 and every download is made twice.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_phone
if [ "${1:-on}" = off ]; then
  remote <<EOF
rm -f $DEBIAN/BOT_ENABLED
BB=$BB_PATH; [ -x \$BB ] || BB=/system/xbin/busybox-deb
\$BB pkill -9 -f "[d]ata/debian/bot.sh"; \$BB pkill -f "[o]pt/bot/bot.py"
echo "bot disabled and stopped"
EOF
else
  remote <<EOF
touch $DEBIAN/BOT_ENABLED
$DEBIAN/bot.sh
sleep 5
echo "bot enabled; log: $DEBIAN/fs/opt/bot/service.log"
tail -3 $DEBIAN/fs/opt/bot/service.log
EOF
fi
