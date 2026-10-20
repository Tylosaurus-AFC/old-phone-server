#!/system/bin/sh
# OPTIONAL. Pin the phone to your 5 GHz network on LineageOS/Android 12+ (tested on
# Android 16). Many routers publish two networks, e.g. "MyWifi" (2.4 GHz, crowded, slow)
# and "MyWifi_5G". Android stays on 2.4 GHz whenever it can, because its join threshold
# for 5 GHz is -77 dBm. This script removes auto-join from the 2.4 GHz network (without
# forgetting it: the password stays saved) by editing WifiConfigStore.xml.
#
#   wifi-band.sh 5g   -> 5 GHz only; if it cannot connect within 2 min, goes back to 2g
#   wifi-band.sh 2g   -> both networks auto-join (factory behaviour)
#
# Needs in /data/debian/server.conf:   WIFI_2G_SSID="MyWifi"   WIFI_5G_SSID="MyWifi_5G"
# Install as /data/debian/wifi-band.sh. charge.sh calls "2g" after 10 min without
# Internet. Every change restarts Android's framework (~1 min without network; the
# chroot and the bot keep running).
DEBIAN=${DEBIAN:-/data/debian}
[ -f $DEBIAN/server.conf ] && . $DEBIAN/server.conf
BB=${BB:-/system/xbin/busybox-deb}; [ -x "$BB" ] || BB=$DEBIAN/busybox-deb
F=/data/misc/apexdata/com.android.wifi/WifiConfigStore.xml
L=$DEBIAN/fs/opt/bot/service.log
log() { echo "$(date) [red] $*" >> $L; }
[ -n "$WIFI_2G_SSID" ] && [ -n "$WIFI_5G_SSID" ] || { echo "set WIFI_2G_SSID and WIFI_5G_SSID in server.conf"; exit 1; }

setjoin() {   # AutoJoinEnabled of the 2.4 GHz network = $1, then make Android re-read the file
  S=$($BB grep -n "<string name=\"SSID\">&quot;$WIFI_2G_SSID&quot;</string>" $F | $BB cut -d: -f1)
  [ -n "$S" ] || { log "wifi-band: network $WIFI_2G_SSID not found"; exit 1; }
  E=$($BB awk -v s=$S 'NR>s && /<\/Network>/ {print NR; exit}' $F)
  svc wifi disable; sleep 4     # with Wi-Fi off Android does not rewrite the file
  cp $F /data/local/tmp/WifiConfigStore.bak.xml
  $BB sed -i "${S},${E}s|<boolean name=\"AutoJoinEnabled\" value=\"[a-z]*\" />|<boolean name=\"AutoJoinEnabled\" value=\"$1\" />|" $F
  stop; sleep 3; start
  n=0; until [ "$(getprop sys.boot_completed)" = 1 ] && cmd wifi status >/dev/null 2>&1; do
    sleep 3; n=$((n + 1)); [ $n -gt 60 ] && break
  done
  sleep 20; svc wifi enable; sleep 5
  dumpsys deviceidle disable >/dev/null   # restarting the framework turns Doze back on
}

case "$1" in
  5g)
    log "wifi-band: switching to 5 GHz only"
    setjoin false
    for i in $($BB seq 1 24); do
      if cmd wifi status | $BB grep -q "connected to \"$WIFI_5G_SSID\"" && ping -c1 -W3 1.1.1.1 >/dev/null 2>&1; then
        log "wifi-band: on 5 GHz ($(cmd wifi status | $BB grep -oE 'RSSI: -?[0-9]+' | $BB head -1))"
        exit 0
      fi
      sleep 5
    done
    log "wifi-band: cannot connect to 5 GHz within 2 min, going back to 2.4"
    setjoin true ;;
  2g)
    log "wifi-band: back to automatic 2.4 + 5 GHz"
    setjoin true ;;
  *) echo "usage: $0 5g|2g"; exit 1 ;;
esac
