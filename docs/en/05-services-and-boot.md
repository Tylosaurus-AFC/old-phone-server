# 05 · Services and boot

How the server starts by itself after a power cut, and what keeps it alive.

## The boot chain

```
power on → Android boots
   └─ boot launcher  (ONE of these, depending on how the phone is rooted)
        ├─ Magisk   : /data/adb/service.d/server.sh        (Magisk runs it as root)
        ├─ KingRoot : /system/bin/ddexe → /system/xbin/server-boot   (a hook, see below)
        └─ initrc   : /system/etc/init/server-boot.rc → /data/local/tmp/server-boot.sh
             └─ start.sh   (/data/debian/start.sh, as root)
                  ├─ waits for sys.boot_completed (max 2 min)
                  ├─ wake-lock (CPU awake with the screen off) · Wi-Fi sleep policy: never
                  ├─ optional: Doze off, LineageOS charging-control off
                  ├─ adb over Wi-Fi on :5555 (restarts adbd)
                  ├─ bot.sh   — only if /data/debian/BOT_ENABLED exists
                  └─ forever:  charge.sh ; sleep 60   (relaunched if it ever dies)
```

Each launcher is a few lines whose only job is to run `start.sh` as root. Install the one for
your phone with `tools/install.sh boot` (it reads `BOOT_MODE` from `config.sh`).

## Magisk

Nothing to think about. `tools/install.sh boot` copies the launcher to
`/data/adb/service.d/server.sh` (mode 755). Magisk runs every script in that folder as root
at boot.

## KingRoot (Android 4.4/5)

Why such a strange hook: on the Galaxy S4 mini, SELinux blocks `/system/etc/install-recovery.sh`
(the classic autostart point on Android 4.4). What *does* run at boot as root is KingRoot's own
wrapper, `/system/bin/ddexe`, a short shell script protected with `chattr +i +a`. The trick is to
add one line to it that launches our script.

> ⚠ **`ddexe` is part of the boot of the phone.** A mistake in it can stop Android from
> booting, and on a locked-bootloader phone recovery options are limited. Work slowly,
> keep a copy of the original, check the syntax before you reboot.

```bash
tools/install.sh boot         # installs /system/xbin/server-boot (and prints the next steps)

# then, by hand:
adb pull /system/bin/ddexe ddexe.orig            # keep this safe!
cp ddexe.orig ddexe.new                          # edit ddexe.new (Unix line endings!)
```

In `ddexe.new`, add this line **before** the line that runs `ddexe_real`:

```sh
/system/xbin/server-boot &
```

Check it, install it, and **verify** before rebooting:

```bash
sh -n ddexe.new                                  # syntax check on the PC: must print nothing
adb push ddexe.new /data/local/tmp/ddexe.new
adb shell
su
mount -o rw,remount /system
/system/xbin/busybox-deb chattr -ia /system/bin/ddexe
cp /data/local/tmp/ddexe.new /system/bin/ddexe
chmod 755 /system/bin/ddexe
/system/xbin/busybox-deb chattr +ia /system/bin/ddexe
mount -o ro,remount /system
grep -n server-boot /system/bin/ddexe            # must show your line, before ddexe_real
```

Then `adb reboot` and wait ~2 minutes: `/data/debian/boot.log` should show "server start-up" and
(if enabled) the bot starts. The launcher waits up to 5 min for `su` to answer, because KingRoot
brings root up late.

## initrc (custom ROM with `adb root`, no `su`)

Copy `phone/boot/initrc/server-boot.rc` to `/system/etc/init/` and `server-boot.sh` to
`/data/local/tmp/` (`tools/install.sh boot` does both, remounting `/` read-write).
**Edit `server-boot.sh` first**: its service-stopping list and the 1 GB zram are from a Moto X2
and ROM-specific. Remember `init` kills a service's children when the service ends, so the
script `exec`s `start.sh`, which never returns.

## What `charge.sh` does, once a minute

| Check | Action |
|---|---|
| `bot.sh` not running and `BOT_ENABLED` exists | relaunch it (counted as a crash in `/historial`, unless `tools/deploy.sh` stopped it on purpose) |
| bot alive but **no heartbeat for 5 min** | `kill -9` it; `bot.sh` starts a fresh one. 10 min grace afterwards |
| `/reiniciar adb \| wifi \| confirmar` requested by the bot | restart adbd · cycle Wi-Fi · reboot |
| Wi-Fi power-save on | turn it off (with the screen off the chip sleeps and the phone vanishes from the LAN) |
| signal below `WIFI_MIN` for 5 min | cycle Wi-Fi to re-scan for the strongest access point |
| no Internet for 5 min | cycle Wi-Fi |
| USB-Ethernet adapter connected | note it in `/historial`; leave Wi-Fi alone while the cable is up |
| battery outside `LOW`–`HIGH`, too hot, or below `FLOOR` | switch the charger ([06](06-battery-and-heat.md)) |
| announces its IP by gratuitous ARP | so the PC and mesh routers always know where it is |

And `bot.sh` restarts the bot after a crash with delays 10 s → 20 s → 40 s … → 10 min (reset
to 10 s after the bot has run 2 minutes), and tells you at the next start how many crashes there
were and the last error.

The two scripts are separate processes that watch each other, so `tools/deploy.sh` can replace
either one safely: it kills it and the other relaunches it with the new code.

## `server.conf` reference

Plain shell, on the phone at `/data/debian/server.conf`; edit with `tools/edit-conf.sh`.
Full commented list: [`phone/server.conf.example`](../../phone/server.conf.example).

| Setting | Default | Meaning |
|---|---|---|
| `BATT`, `BATT_CTRL`, `BATT_CTRL_FILE` | `/sys/class/power_supply/battery`, `slate` | charger switch: `slate` · `enable` · `none` |
| `LOW`, `HIGH`, `MAXTEMP`, `FLOOR` | 40, 60, 420, 15 | resume at ≤ LOW %, pause at ≥ HIGH %, pause above 42.0 °C, always charge below FLOOR % |
| `WIFI_IFACE`, `WIFI_MIN` | `wlan0`, -75 | interface; weak-signal threshold (dBm) |
| `FIX_ROUTE` | 0 | `1` on Android 11+ if root gets *Network is unreachable* |
| `ADB_TCP_PORT`, `ADB_TCP_PROP`, `ADB_RESTART` | 5555, `service.adb.tcp.port`, `stop adbd; …` | adb over Wi-Fi; newer Android uses `persist.adb.tcp.port` and `setprop ctl.restart adbd` |
| `DOZE_OFF` | 0 | `1` = `dumpsys deviceidle disable` (Android 6+) |
| `LINEAGE_CHARGE_CTRL_OFF` | 0 | `1` = disable LineageOS "Charging control" (it cuts the charger on a schedule and fights `charge.sh`) |
| `BOT_CMD`, `PING_HOST` | venv python + `bot.py`, `api.telegram.org` | what `bot.sh` runs, and what it waits to reach |

Next: [06 · Battery and heat](06-battery-and-heat.md).
