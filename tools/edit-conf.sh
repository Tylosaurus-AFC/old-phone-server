#!/usr/bin/env bash
# Edit the phone's /data/debian/server.conf comfortably: downloads it, opens it in your
# editor ($EDITOR, or nano/vi/notepad), and uploads it back if you changed it.
# charge.sh re-reads server.conf every minute, so no restart is needed.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_phone
F="$(mktemp)"
remote <<EOF
cp $DEBIAN/server.conf $TMP.conf && chmod 644 $TMP.conf
EOF
a pull "$TMP.conf" "$(winpath "$F")" >/dev/null
before="$(sha256sum "$F" | cut -d' ' -f1)"
"${EDITOR:-$(command -v nano || command -v vi || echo notepad)}" "$F"
if [ "$before" = "$(sha256sum "$F" | cut -d' ' -f1)" ]; then
  echo "No changes."
else
  a push "$(winpath "$F")" "$TMP.conf" >/dev/null
  remote <<EOF
cp $TMP.conf $DEBIAN/server.conf && chmod 644 $DEBIAN/server.conf && echo "server.conf updated"
EOF
fi
rm -f "$F"
remote <<EOF
rm -f $TMP.conf
EOF
