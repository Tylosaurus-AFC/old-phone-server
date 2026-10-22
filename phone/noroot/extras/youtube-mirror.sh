#!/data/data/com.termux/files/usr/bin/sh
# RECIPE: mirror of the YouTube channels the bot follows (/opt/bot/subs.json) onto the USB disk:
#   /mnt/disk/YouTube/<channel>/<date> - <title> [<id>].mp4 (+ thumbnail .jpg)
# To watch them offline, through DLNA/Jellyfin, or on an old Apple TV by AirPlay: H.264 up to
# 1080p and 30 fps (the Apple TV 3 cannot play 60 fps). No Shorts, no live streams.
# Usage: youtube-mirror.sh [N]   (N = latest videos per channel to fetch, default 5; the KEEP=10
#        newest of each channel are kept and older ones deleted, so the disk never fills)
#        CHANNELS="UCxxx UCyyy" youtube-mirror.sh   (other channels, ignoring subs.json)
# Run it by hand, or from the nightly job: NIGHTLY="youtube-mirror.sh 3" in server.conf.
N=${1:-5}
exec $HOME/server/enter.sh "
[ -f /mnt/disk/.nas ] || { echo 'no USB disk mounted (missing /mnt/disk/.nas)'; exit 1; }
C=\"${CHANNELS:-}\"
[ -n \"\$C\" ] || C=\$(python3 -c 'import json; print(\" \".join(json.load(open(\"/opt/bot/subs.json\"))))')
D=/mnt/disk/YouTube; mkdir -p \$D
for ch in \$C; do
  /opt/bot/venv/bin/yt-dlp --js-runtimes node --no-progress \
    --playlist-end $N --download-archive \$D/.archive.txt \
    --match-filter '!is_live & live_status!=is_upcoming & duration>90' \
    -f 'bv*[vcodec^=avc1][height<=1080][fps<=30]+ba[ext=m4a]/b[vcodec^=avc1][height<=1080]/bv*[height<=1080]+ba/b' \
    --merge-output-format mp4 --embed-metadata --write-thumbnail --convert-thumbnails jpg --no-write-playlist-metafiles \
    -o \"\$D/%(channel)s/%(upload_date>%Y-%m-%d)s - %(title).100B [%(id)s].%(ext)s\" \
    \"https://www.youtube.com/channel/\$ch/videos\"
done
# Keep only the ${KEEP:-10} most recent of each channel; they stay in .archive.txt, so
# they are not downloaded again
for c in \$D/*/; do
  ls -1 \"\$c\"*.mp4 2>/dev/null | sort -r | tail -n +$((${KEEP:-10} + 1)) | while read -r f; do
    rm -f \"\$f\" \"\${f%.mp4}.jpg\"
  done
done
du -sh \$D
"
