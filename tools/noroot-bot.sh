#!/usr/bin/env bash
# NO-ROOT mode: token and on/off switch of the bot.
#   tools/noroot-bot.sh token      asks for the @BotFather token silently and stores it (chmod 600)
#   tools/noroot-bot.sh api        asks for api_id / api_hash (my.telegram.org) for 2 GB uploads
#   tools/noroot-bot.sh enable     creates ~/server/BOT_ENABLED and starts the bot
#   tools/noroot-bot.sh disable    removes it and stops the bot
# The bot only runs where BOT_ENABLED exists. Never enable it on two phones with the same token.
set -euo pipefail
source "$(dirname "$0")/noroot-common.sh"
need_phone
OPT='$PREFIX/var/lib/proot-distro/containers/'"$CONTAINER"'/rootfs/opt/bot'
case "${1:-}" in
token)
  read -r -s -p "Paste the bot token (nothing is shown): " TOKEN; echo
  case "$TOKEN" in [0-9]*:?*) ;; *) echo "That does not look like a bot token (digits:letters)."; exit 1 ;; esac
  printf '%s\n' "$TOKEN" | ph "mkdir -p $OPT && cat > $OPT/token && chmod 600 $OPT/token && echo 'token saved'"
  ;;
api)
  read -r -p "api_id (digits): " API_ID
  read -r -s -p "api_hash (nothing is shown): " API_HASH; echo
  case "$API_ID" in ''|*[!0-9]*) echo "api_id must be only digits."; exit 1 ;; esac
  [[ "$API_HASH" =~ ^[0-9a-fA-F]{32}$ ]] || { echo "api_hash looks wrong: it is 32 hex characters (0-9, a-f), from my.telegram.org."; exit 1; }
  printf '%s\n%s\n' "$API_ID" "$API_HASH" | ph "mkdir -p $OPT && cat > $OPT/api.txt && chmod 600 $OPT/api.txt && echo 'api.txt saved'"
  ;;
enable)
  ph 'touch ~/server/BOT_ENABLED; ~/server/bot.sh; sleep 8; tail -3 '"$OPT"'/service.log'
  ;;
disable)
  ph 'rm -f ~/server/BOT_ENABLED; touch ~/server/stopping; pkill -9 -f "[s]erver/bot.sh"; pkill -f "[o]pt/bot/bot.py"; echo "bot disabled and stopped"'
  ;;
*) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
