#!/data/data/com.termux/files/usr/bin/sh
# NO-ROOT mode: server start-up. Installed as ~/.termux/boot/00-server.sh; the Termux:Boot app
# runs it when the phone powers on. (Termux:Boot must have been opened by hand ONCE: Android
# does not deliver the boot broadcast to an app that was never opened.)
D=$HOME/server
termux-wake-lock                       # CPU awake with the screen off
pgrep -x sshd >/dev/null || sshd       # SSH on port 8022, key-only
date +%s > $D/boot_time
echo "$(date) server start-up; bot $( [ -f $D/BOT_ENABLED ] && echo enabled || echo disabled)" >> $D/boot.log

# The bot, right here (bot.sh detaches itself): if charge.sh started it, every boot would
# count as a crash and alert the owner
[ -f $D/BOT_ENABLED ] && $D/bot.sh

# Watchdog (battery/Wi-Fi/uptime for the bot, hangs, /reiniciar, the bot if enabled).
# If it dies it is relaunched a minute later (charge.sh exits by itself if another runs).
# This file also runs when Termux is reopened (~/.bashrc hook, guard.sh): only one loop.
OLD=$(cat $D/loop.pid 2>/dev/null)
if [ -z "$OLD" ] || ! grep -q "charge.sh" /proc/$OLD/cmdline 2>/dev/null; then
  setsid nohup sh -c "while true; do $D/charge.sh >/dev/null 2>&1; sleep 60; done" \
    </dev/null >/dev/null 2>&1 &
  echo $! > $D/loop.pid
fi
