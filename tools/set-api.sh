#!/usr/bin/env bash
# OPTIONAL: lets the bot upload files up to 2 GB (the plain Bot API stops at 50 MB).
# Get an api_id and api_hash for free at https://my.telegram.org -> "API development tools",
# then run this script. They are stored in /opt/bot/api.txt (two lines), readable only by root.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_phone
read -r -p "api_id (digits): " API_ID
read -r -s -p "api_hash (nothing is shown): " API_HASH; echo
case "$API_ID" in ''|*[!0-9]*) echo "api_id must be only digits."; exit 1 ;; esac
case "$API_HASH" in [0-9a-f]*) ;; *) echo "api_hash looks wrong (32 hex characters)."; exit 1 ;; esac
F="$(mktemp)"; printf '%s\n%s\n' "$API_ID" "$API_HASH" > "$F"
a push "$(winpath "$F")" "$TMP.api" >/dev/null; rm -f "$F"
remote <<EOF
mkdir -p $DEBIAN/fs/opt/bot
cp $TMP.api $DEBIAN/fs/opt/bot/api.txt && chmod 600 $DEBIAN/fs/opt/bot/api.txt && rm -f $TMP.api
echo "saved in $DEBIAN/fs/opt/bot/api.txt -- restart the bot (tools/deploy.sh) to use it"
EOF
