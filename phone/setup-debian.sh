#!/bin/bash
# Runs INSIDE Debian: the root-mode chroot (tools/install.sh provision) or the no-root proot
# container (tools/noroot-install.sh provision; verified there: 7 min 25 s on a Realme 12+).
# Prepares Debian for the bot: network quirks of Android, packages, Python virtualenv.
#   TZ_NAME=Europe/Madrid  time zone (Debian comes in UTC)       [default UTC]
set -e
TZ_NAME=${TZ_NAME:-UTC}

echo "nameserver 1.1.1.1" > /etc/resolv.conf
ln -sf "/usr/share/zoneinfo/$TZ_NAME" /etc/localtime
echo "$TZ_NAME" > /etc/timezone

# Android only lets the "inet" group (3003) open network sockets; the chroot needs the
# same group IDs. apt normally drops privileges to the _apt user, which would then have
# no network: make it run as root instead, and force IPv4 (many phone networks break IPv6).
getent group aid_inet    >/dev/null || groupadd -g 3003 aid_inet
getent group aid_net_raw >/dev/null || groupadd -g 3004 aid_net_raw
echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99ipv4
echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/99sandbox

export DEBIAN_FRONTEND=noninteractive
apt-get update
# python3-* from apt: prebuilt, so pip does not have to compile them on a slow old CPU.
# gcc & co. are only needed to build TgCrypto and are purged afterwards.
apt-get install -y --no-install-recommends \
  python3 python3-venv ca-certificates tzdata ffmpeg nodejs curl procps iw poppler-utils \
  python3-brotli python3-pycryptodome python3-websockets python3-requests \
  python3-certifi python3-mutagen python3-urllib3 \
  gcc libc6-dev python3-dev

mkdir -p /opt/bot
python3 -m venv --system-site-packages /opt/bot/venv
/opt/bot/venv/bin/pip install --no-cache-dir -r /opt/bot/requirements.txt

apt-get purge -y gcc libc6-dev python3-dev
apt-get autoremove -y
apt-get clean
echo "OK: Debian ready. Python: $(/opt/bot/venv/bin/python3 --version), yt-dlp: $(/opt/bot/venv/bin/yt-dlp --version)"
