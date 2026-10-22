#!/data/data/com.termux/files/usr/bin/sh
# RECIPE: DLNA media server (TVs, VLC, streaming apps) serving the external USB disk, read-only.
# Needs `pkg install rclone`. Name shown on the network: DLNA_NAME (default "Phone server").
# HTTP port 7879; the SSDP announcement goes by multicast (UDP 1900), which some routers/
# firewalls block (Windows Firewall also hides it from your PC): test from the TV itself.
V=/storage/$(~/server/sa.sh "sm list-volumes public 2>&1 | cat" | awk '$2 == "mounted" {print $3; exit}')
[ "$V" != /storage/ ] || { echo "no external disk"; exit 1; }
exec rclone serve dlna "$V" --addr :7879 --name "${DLNA_NAME:-Phone server}" --read-only
