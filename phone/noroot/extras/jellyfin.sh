#!/data/data/com.termux/files/usr/bin/sh
# RECIPE: Jellyfin (media server with web UI and apps, port 8096) inside the Debian container.
# Needs Jellyfin installed in the container (see docs/*/13-*.md). Data and cache stay in the
# phone's internal storage (/opt/jellyfin); add the library from the web UI pointing at
# /mnt/disk (the USB disk). First time: open http://<phone-ip>:8096 and run the wizard.
exec $HOME/server/enter.sh "
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
mkdir -p /opt/jellyfin/data /opt/jellyfin/cache /opt/jellyfin/log
exec /usr/bin/jellyfin --datadir /opt/jellyfin/data --cachedir /opt/jellyfin/cache \
  --logdir /opt/jellyfin/log --webdir /usr/share/jellyfin/web \
  --ffmpeg /usr/lib/jellyfin-ffmpeg/ffmpeg
"
