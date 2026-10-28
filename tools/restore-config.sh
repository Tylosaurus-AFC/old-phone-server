#!/usr/bin/env bash
# Put the configuration of a backup (made with backup.sh) back on the phone.
#   tools/restore-config.sh backup/20261018-1000
# Only /opt/bot's files and server.conf. The android/ folder of the backup (boot launcher,
# busybox, disabled apps) is restored by hand: see docs/*/08-operations.md.
set -euo pipefail
source "$(dirname "$0")/common.sh"
SRC="${1:?Usage: tools/restore-config.sh backup/<date>}"
[ -f "$SRC/token" ] || { echo "$SRC does not look like a backup (no token file)"; exit 1; }
need_phone

a shell "rm -rf $TMP.rc; mkdir -p $TMP.rc"
for f in "$SRC"/*; do
  [ -f "$f" ] && a push "$(winpath "$f")" "$TMP.rc/" >/dev/null 2>&1
done
remote <<EOF
T=$TMP.rc; cd \$T
n=0; bad=0
for f in *; do
  case \$f in
    server.conf) ok() { cp \$f $DEBIAN/; } ;;
    pip-freeze.txt) continue ;;
    # temp copy + mv: the running bot never reads a half-written file (bot.db above all)
    *) ok() { cp \$f $DEBIAN/fs/opt/bot/.\$f.rst && chmod 600 $DEBIAN/fs/opt/bot/.\$f.rst \
              && mv $DEBIAN/fs/opt/bot/.\$f.rst $DEBIAN/fs/opt/bot/\$f; } ;;
  esac
  if ok 2>/dev/null; then n=\$((n + 1)); else bad=\$((bad + 1)); echo "could not restore \$f"; fi
done
rm -rf \$T
echo "\$n files restored"
[ \$bad = 0 ] || { echo "\$bad FAILED"; exit 1; }
EOF
echo "Configuration restored. Run tools/deploy.sh to apply it."
