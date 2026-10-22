#!/data/data/com.termux/files/usr/bin/bash
# ui.sh dump | ui.sh tap "Text"   -- drive the phone's own screen (through Shizuku).
# Some maker settings can only be changed from the UI (e.g. Realme's "Disable permission
# monitoring" or its charge limit): `dump` lists the texts on screen, `tap` taps one.
X=$(~/server/sa.sh "uiautomator dump /sdcard/Download/.ui.xml >/dev/null 2>&1; cat /sdcard/Download/.ui.xml")
case "$1" in
  dump) echo "$X" | grep -oE "text=\"[^\"]+\"" | sed "s/text=//" | tr "\n" "|"; echo ;;
  tap) b=$(echo "$X" | sed "s/<node/\n<node/g" | grep -F "text=\"$2\"" | head -1 | grep -oE "bounds=\"[^\"]+\"" | grep -oE "[0-9]+")
       set -- $b; [ -z "$4" ] && { echo "not found"; exit 1; }
       ~/server/sa.sh "input tap $((($1+$3)/2)) $((($2+$4)/2)) 2>&1 | cat" >/dev/null; sleep 2 ;;
esac
