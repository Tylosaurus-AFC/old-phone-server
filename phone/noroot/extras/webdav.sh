#!/data/data/com.termux/files/usr/bin/sh
# RECIPE: NAS over WebDAV (port 8080) serving the external USB disk. Needs `pkg install rclone`.
# Set a password first:   mkdir -p ~/.config/server && echo 'a-long-password' > ~/.config/server/webdav.pass
# User name: WEBDAV_USER (default "webdav"). Reach it from your PC at http://<phone-ip>:8080
# (Windows: "Map network drive" with the WebDAV address; macOS/Linux: any WebDAV client).
# Plain HTTP and one shared password: only on a LAN you trust. Never expose it to the Internet.
V=/storage/$(~/server/sa.sh "sm list-volumes public 2>&1 | cat" | awk '$2 == "mounted" {print $3; exit}')
[ "$V" != /storage/ ] || { echo "no external disk"; exit 1; }
[ -s ~/.config/server/webdav.pass ] || { echo "create ~/.config/server/webdav.pass first"; exit 1; }
exec rclone serve webdav "$V" --exclude "Backups/**" --addr :8080 --user "${WEBDAV_USER:-webdav}" --pass "$(cat ~/.config/server/webdav.pass)"
