#!/usr/bin/env bash
# NO-ROOT mode installer, run from your PC over SSH into Termux. Full guide: docs/en/12-no-root.md
# (docs/es/12-modo-sin-root.md). Do the manual steps of that guide first (Termux apps, sshd +
# your SSH key, Shizuku); this script does the rest in steps you can repeat one by one.
#
#   tools/noroot-install.sh check               can this phone run it? (Android, CPU, space, Termux build)
#   tools/noroot-install.sh packages            Termux packages (proot-distro, openssh, termux-api, jq...)
#   tools/noroot-install.sh container [file]    create the Debian container (from Docker Hub, or a rootfs file)
#   tools/noroot-install.sh provision           packages + Python venv + yt-dlp inside Debian
#   tools/noroot-install.sh scripts             ~/server/*.sh, server.conf, boot hook, .bashrc hook
#   tools/noroot-install.sh rish <folder>       copy rish + rish_shizuku.dex exported from the Shizuku app
#   tools/noroot-install.sh voice               (optional) speech-to-text: whisper.cpp + Vosk
set -euo pipefail
source "$(dirname "$0")/noroot-common.sh"
step="${1:-}"; shift || true
case "$step" in
  check|packages|container|provision|scripts|rish|voice) need_phone ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac

# Before installing anything: stop on what cannot work, warn about the rest. Free-space
# thresholds are estimates (Debian + Python + ffmpeg + yt-dlp), not measurements.
preflight() {
  ph 'S=$(getprop ro.build.version.sdk); R=$(getprop ro.build.version.release)
      F=$(df -Pk $HOME | awk "NR == 2 {print int(\$4 / 1024)}")
      echo "Android $R (SDK $S) · $(getprop ro.product.manufacturer) $(getprop ro.product.model) · CPU $(uname -m) · ${F} MB free · Termux ${TERMUX_VERSION:-?} (${TERMUX_APK_RELEASE:-unknown build})"
      bad=0
      [ "${S:-0}" -ge 24 ] || { echo "STOP: Termux needs Android 7 or newer. Use root mode (docs/*/02-root.md)."; bad=1; }
      [ "${S:-0}" -ge 30 ] || echo "WARN: below Android 11 Shizuku cannot start by itself at boot: you will start it by hand after each reboot."
      case "$(uname -m)" in aarch64|armv7l|armv8l) ;; *) echo "WARN: CPU $(uname -m) has not been tested with this project." ;; esac
      [ "${F:-0}" -ge 1024 ] || { echo "STOP: less than 1 GB free. Free space first (about 3 GB is comfortable)."; bad=1; }
      [ "${F:-0}" -ge 3072 ] || echo "WARN: under 3 GB free: the install fits, but downloads need room too."
      [ "${TERMUX_APK_RELEASE:-}" = GOOGLE_PLAY_STORE ] && echo "WARN: Termux from Google Play. Install Termux, Termux:Boot and Termux:API from GitHub or F-Droid (same source for all three)."
      exit $bad' </dev/null
}

case "$step" in
check)
  preflight && echo "OK: nothing blocks the install. Next: tools/noroot-install.sh packages"
  ;;

packages)
  preflight || { echo "Fix the STOP items above first."; exit 1; }
  ph 'pkg update -y && pkg install -y proot-distro openssh termux-api jq curl tar xz-utils procps findutils'
  echo "Packages installed. (rclone is only needed for the optional NAS/DLNA recipes: pkg install rclone)"
  ;;

container)
  SRC="${1:-debian:trixie}"
  NAME="$CONTAINER"
  if ph "proot-distro list 2>&1 | grep -qw $NAME"; then
    echo "Container '$NAME' already exists. Remove it first with: ssh $H proot-distro remove $NAME"; exit 1
  fi
  if [ -f "$SRC" ]; then       # a rootfs archive (e.g. a tools/make-image.sh image, arm64)
    scp -q "$SRC" "$H:rootfs-upload.tar.gz"
    ph "proot-distro install --name $NAME ~/rootfs-upload.tar.gz && rm -f ~/rootfs-upload.tar.gz"
  else                         # an image from Docker Hub
    ph "proot-distro install --name $NAME $SRC"
  fi
  ph "proot-distro list"
  echo "Next: tools/noroot-install.sh provision (skip it if the archive was a finished image)."
  ;;

provision)
  scp -q "$ROOT/phone/setup-debian.sh" "$ROOT/bot/requirements.txt" "$H:"
  ph "C=$CT; mkdir -p \$C/opt/bot && cp ~/requirements.txt \$C/opt/bot/ && cp ~/setup-debian.sh \$C/root/ && rm -f ~/requirements.txt ~/setup-debian.sh
      unset LD_PRELOAD
      proot-distro login $CONTAINER -- env TZ_NAME='$TZ_NAME' bash /root/setup-debian.sh"
  ;;

scripts)
  # (staged and pushed with scp; modes set on the phone)
  S="$(mktemp -d)"
  cp "$ROOT"/phone/noroot/{boot.sh,bot.sh,charge.sh,doctor.sh,enter.sh,guard.sh,sa.sh,shizuku.sh,ui.sh} "$S/"
  cp "$ROOT/phone/noroot/server.conf.example" "$S/server.conf.new"
  mkdir -p "$S/extras"; cp "$ROOT"/phone/noroot/extras/*.sh "$S/extras/"
  ph 'rm -rf ~/server-new; mkdir -p ~/server-new ~/server/extras ~/server/svc'
  scp -q -r "$S"/. "$H:server-new/"
  rm -rf "$S"
  ph 'set -e
      cd ~/server-new
      for s in boot.sh bot.sh charge.sh doctor.sh enter.sh guard.sh sa.sh shizuku.sh ui.sh; do
        cp $s ~/server/$s && chmod 700 ~/server/$s
      done
      cp extras/*.sh ~/server/extras/ && chmod 700 ~/server/extras/*.sh
      [ -f ~/server/server.conf ] || { cp server.conf.new ~/server/server.conf; echo "created ~/server/server.conf (EDIT IT)"; }
      mkdir -p ~/.termux/boot && cp boot.sh ~/.termux/boot/00-server.sh && chmod 700 ~/.termux/boot/00-server.sh
      # If Android closes Termux, opening it again restarts the server (guard.sh does the opening)
      grep -q "phone-server" ~/.bashrc 2>/dev/null || cat >> ~/.bashrc <<RC
# phone-server: if Android closed Termux, opening it again restarts the server
pgrep -x sshd >/dev/null || sh ~/.termux/boot/00-server.sh
RC
      rm -rf ~/server-new
      echo "scripts installed in ~/server; boot hook in ~/.termux/boot/00-server.sh"'
  echo "Remember: open the Termux:Boot app ONCE by hand, or Android never delivers the boot event to it."
  echo; echo "== Health check (tools/noroot-doctor.sh) =="
  ph 'bash ~/server/doctor.sh' </dev/null || true
  ;;

rish)
  DIR="${1:?Usage: tools/noroot-install.sh rish <folder with rish and rish_shizuku.dex>}"
  [ -f "$DIR/rish" ] && [ -f "$DIR/rish_shizuku.dex" ] || { echo "rish and rish_shizuku.dex not found in $DIR"; exit 1; }
  ph 'mkdir -p ~/server'
  scp -q "$DIR/rish" "$DIR/rish_shizuku.dex" "$H:server/"
  # Android 14+ needs the dex read-only and inside the app's private dir (~ is). sa.sh sets
  # RISH_APPLICATION_ID=com.termux, so the exported rish file needs no editing.
  ph 'cd ~/server && chmod 700 rish && chmod 400 rish_shizuku.dex
      echo "test: $(~/server/sa.sh "id")"'
  echo "If that printed uid=2000(shell): Shizuku works. If not: see docs/*/12-*.md, \"Shizuku\"."
  ;;

voice)
  scp -q "$ROOT/phone/extras/setup-voice.sh" "$H:"
  ph "C=$CT; cp ~/setup-voice.sh \$C/root/ && rm -f ~/setup-voice.sh
      unset LD_PRELOAD; proot-distro login $CONTAINER -- bash /root/setup-voice.sh"
  ;;
esac
