#!/usr/bin/env bash
# Store the Telegram bot token (from @BotFather) on the phone, readable only by root.
# The token is asked silently so it does not end up in your shell history.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_phone
read -r -s -p "Paste the bot token (nothing is shown): " TOKEN; echo
case "$TOKEN" in
  [0-9]*:?*) ;;
  *) echo "That does not look like a bot token (digits:letters)."; exit 1 ;;
esac
F="$(mktemp)"; printf '%s\n' "$TOKEN" > "$F"
a push "$(winpath "$F")" "$TMP.tok" >/dev/null; rm -f "$F"
remote <<EOF
mkdir -p $DEBIAN/fs/opt/bot
cp $TMP.tok $DEBIAN/fs/opt/bot/token && chmod 600 $DEBIAN/fs/opt/bot/token && rm -f $TMP.tok
echo "token saved in $DEBIAN/fs/opt/bot/token"
EOF
echo "Optional (files over 50 MB, up to 2 GB): put api_id and api_hash from my.telegram.org"
echo "in /opt/bot/api.txt, two lines (see docs)."
