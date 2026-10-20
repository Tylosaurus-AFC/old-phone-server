# 10 · Tested devices

Three real phones/tablets, with what each needed and what it measured. Use them as templates
for yours. (Numbers are from the original installation, October 2026.)

## At a glance

| | Galaxy S4 mini | Moto X2 | Galaxy Tab A7 |
|---|---|---|---|
| Model | Samsung SCH-I435 (Verizon) | Motorola XT1097 "victara" | Samsung SM-T500 |
| Year / Android | 2013 / **4.4.2** | 2014 / **11** (LineageOS 18.1, userdebug, microG) | 2020 / **16** (LineageOS 23) |
| CPU | Snapdragon 400, 2 cores 1.7 GHz, **32-bit** | Snapdragon 801, 32-bit | Snapdragon 662, 8 cores, **64-bit** |
| RAM | 1.3 GB + 1 GB vnswap | 2 GB + zram 1 GB | 2.7 GB + zram 2 GB |
| Free storage with Debian | 7.9 GB of 11.5 | – | ~7 GB of 22 |
| Battery | 1900 mAh | 2281 mAh (healthy) | 7040 mAh |
| Bootloader | **locked** (Verizon) | unlocked | unlocked |
| Root | KingRoot (route B) | `adb root` (userdebug, route C) | Magisk 30.7 (route A) |
| `ARCH` | armhf | armhf | **arm64** |
| `ROOT_MODE` / `BOOT_MODE` | `su` / `kingroot` | `adbroot` / `initrc` | `su` / `magisk` |
| `BB_PATH` | `/system/xbin/busybox-deb` | `/data/debian/busybox-deb` | `/data/debian/busybox-deb` (Magisk's busybox) |
| `BATT_CTRL` | `slate` | `enable` | `slate` |
| Special in `server.conf` | defaults, `LOW=40 HIGH=60` | `FIX_ROUTE=1`, `ADB_TCP_PROP=persist.adb.tcp.port`, `LOW=25 HIGH=65` | `DOZE_OFF=1`, `LINEAGE_CHARGE_CTRL_OFF=1`, `WIFI_MIN=-85`, `ADB_RESTART="setprop ctl.restart adbd"` |
| Role | production 24/7 | cold spare | test bench / candidate |

## Galaxy S4 mini (Verizon SCH-I435, Android 4.4.2) — the reference

* Debian 13 armhf in a chroot, Python 3.13, ffmpeg 7.1, Node 20. Bot process: 19–45 MB.
* Root with KingRoot; **never remove or update it** (locked bootloader).
* Quirks: `sec_restrict_fork` (busybox must live in `/system/xbin`); SELinux blocks
  `install-recovery.sh` (hence the `ddexe` hook); `batt_slate_mode` for the charger;
  Android 4.4 sticks to the first access point; adbd serves one connection at a time; Android
  4.4 lacks the Let's Encrypt root certificates (add ISRG Root X1/X2 to
  `/system/etc/security/cacerts/` if Android-side tools need them; the chroot uses Debian's own).
* 195 preinstalled packages disabled (50 remain active) to free RAM; ~980 MB available at idle.
* Telethon's Python AES was 0.5 MB/s on this CPU; **TgCrypto** (C) raised uploads to ~3.5 MB/s.
* `libvosk.so` needs `patchelf --clear-execstack` or glibc 2.41 refuses to load it.

Measured (Wi-Fi 802.11n 5 GHz, next to the router, ~50–66 Mbps down / ~48–54 up):

| Task | Time |
|---|---|
| TikTok / Instagram / Threads link | 5–20 s |
| 154 MB YouTube video (download + 2 GB-path upload) | ~2 min (upload ~3.5 MB/s) |
| Re-sending a cached link | ~0.3 s |
| `/mp3` of 10 min of audio | ~95 s |
| Voice note: Vosk draft / Whisper `base` final | seconds / ~4× the audio length |
| Whisper `small` | ~13× the audio length (too slow here) |
| 3 simultaneous YouTube downloads | no swap; minimum available RAM 886 MB |

## Moto X2 (Android 11, LineageOS 18.1) — the cold spare

* Same chroot and scripts; `ROOT_MODE=adbroot`. `adb root` must be repeated after every reboot.
* No `su`: files are installed with `/` remounted read-write; boot via `init.rc`.
* Quirks: Android 11 needs `FIX_ROUTE=1`; with no launcher/systemui Android sits on
  *"Starting phone"* (`server-boot.sh` stops the boot animation and sleeps the screen);
  `charging_enabled` for the charger.
* **Never disable `com.android.permissioncontroller`**: `system_server` crash-loops on the next
  reboot ("There must be exactly one permissions manager; found []"), `sys.boot_completed`
  never arrives and `pm` stops answering. Fix: remove the `enabled="3"` entry of that package
  in `/data/system/users/0/package-restrictions.xml` (adb root still works). Test each batch of
  disabled apps with a reboot.
* Processes like `systemui` and `nfc` respawn even when disabled; RAM free after boot ~760–890 MB.
* The bot is installed but disabled (`BOT_ENABLED` absent): the same token must not run twice.

## Galaxy Tab A7 (SM-T500, Android 16, LineageOS 23) — the faster option

* Debian 13 **arm64**; whisper.cpp rebuilt for the CPU (3 min 23 s vs 10+ min on the S4).
* Magisk's busybox (1.36.1 aarch64) in `/data/debian/busybox-deb`; boot via `service.d`.
* De-bloated: 81 apps and 4 Magisk modules disabled, Bluetooth/location off. RAM available at
  idle 698 → **1050 MB**, processes of Android apps 25 → 9, and — more valuable than the speed —
  timings stopped varying.
* Quirks found: the LineageOS charge schedule (22:00–06:00) cut the charger and the tablet
  went flat while "plugged in" → `LINEAGE_CHARGE_CTRL_OFF=1`; do not update LineageOS without
  re-patching Magisk (no root = nothing starts); `stop; start` of the framework (used by the
  band-pinning script) re-enables Doze, so it is switched off again afterwards.

Measured against the S4 mini:

| Task | S4 mini | Tab A7 |
|---|---|---|
| Voice note, Whisper `base` | ~4× audio length | ~0.2–0.5× (8–10× faster) |
| Voice note, Whisper `small` | ~13× | ~1.2–1.4× |
| Large upload | 3.5 MB/s | ~8 MB/s (**×2.3**) |
| `/mp3` | – | ×4 faster |
| 255 MB YouTube (download + upload) | – | 105 s |
| 1.6 GB 1080p (download + merge) | – | 6 min 42 s |
| Link download (TikTok/X/Threads) | 5–20 s | 8–14 s (limited by the network) |
| Wi-Fi speed test | 50–66 ↓ / 48–54 ↑ Mbps (next to the router, 802.11n) | 180 ↓ / 115 ↑ Mbps (5 GHz, −57 dBm, 802.11ac, repeater nearby) |
| Battery life in a power cut | 1900 mAh | 7040 mAh (**4×**) |
| Bot process memory | 19–45 MB | 78 MB (peak 226 MB, 64-bit) |

What does **not** improve: normal downloads (limited by your Internet and the sites), and
anything dominated by the access point rather than the phone.

## Add your phone

If you install this on another model, please send a pull request adding a section like the
ones above: model, Android, ABI, root route, `BB_PATH`, `BATT_CTRL`, what you had to change,
and a couple of measurements. Failed attempts are as valuable as successes.
