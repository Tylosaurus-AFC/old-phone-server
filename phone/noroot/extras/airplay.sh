#!/data/data/com.termux/files/usr/bin/sh
# RECIPE (untested against a real Apple TV): play a video from the USB disk on an Apple TV by
# AirPlay, with pyatv (installed in a venv at /opt/airplay inside the container:
#   python3 -m venv /opt/airplay && /opt/airplay/bin/pip install pyatv ).
#   airplay.sh scan                           -> list the Apple TVs on the network
#   airplay.sh <apple-tv-ip> <path-on-disk>   -> e.g. airplay.sh 192.168.1.60 "YouTube/Channel/video.mp4"
# Apple TV 3 (A1469): H.264 up to 1080p and 30 fps (the YouTube mirror already fetches that).
# While playing, only that folder is served over HTTP on port 8090; it stops when playback
# ends (or on Ctrl-C). If the Apple TV asks for a code: AirPlay settings -> "Everyone".
# The phone's own address is auto-detected; override with MYIP=...
if [ "$1" = scan ]; then
  exec $HOME/server/enter.sh "/opt/airplay/bin/atvremote scan"
fi
ATV=$1; F=$2
[ -n "$ATV" ] && [ -n "$F" ] || { sed -n 4,6p "$0"; exit 1; }
DIR=$(dirname "$F"); NAME=$(basename "$F")
exec $HOME/server/enter.sh "
MYIP=\"${MYIP:-}\"
[ -n \"\$MYIP\" ] || MYIP=\$(python3 -c 'import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect((\"1.1.1.1\", 53)); print(s.getsockname()[0])')
cd \"/mnt/disk/$DIR\" || exit 1
python3 -m http.server 8090 --bind 0.0.0.0 >/dev/null 2>&1 &
SRV=\$!; trap 'kill \$SRV' EXIT; sleep 1
U=\"http://\$MYIP:8090/\$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' \"$NAME\")\"
echo \"Playing \$U on $ATV\"
/opt/airplay/bin/atvremote -s $ATV play_url=\"\$U\" || exit 1
# Wait until it ends (the Apple TV stops being in 'playing')
while /opt/airplay/bin/atvremote -s $ATV device_state 2>/dev/null | grep -qiE 'playing|paused|loading'; do sleep 15; done
"
