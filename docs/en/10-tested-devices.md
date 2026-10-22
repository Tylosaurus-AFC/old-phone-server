# 10 · Tested devices

Three real phones/tablets, with what each needed and what it measured. Use them as templates
for yours. (Numbers are from the original installation, October 2026.)

## At a glance

| | Galaxy S4 mini | Moto X2 | Galaxy Tab A7 | Realme 12+ 5G |
|---|---|---|---|---|
| Model | Samsung SCH-I435 (Verizon) | Motorola XT1097 "victara" | Samsung SM-T500 | Realme RMX3867 |
| Year / Android | 2013 / **4.4.2** | 2014 / **11** (LineageOS 18.1, userdebug, microG) | 2020 / **16** (LineageOS 23) | 2024 / **16** (Realme UI 7) |
| CPU | Snapdragon 400, 2 cores 1.7 GHz, **32-bit** | Snapdragon 801, 32-bit | Snapdragon 662, 8 cores, **64-bit** | Dimensity 7050: 2×A78 2.6 GHz + 6×A55 2.0 GHz, **64-bit** |
| RAM | 1.3 GB + 1 GB vnswap | 2 GB + zram 1 GB | 2.7 GB + zram 2 GB | **12 GB** (~7.5 GB free at idle) |
| Storage | 7.9 GB free of 11.5 | – | ~7 GB free of 22 | ~205 GB free of 256 (+ a 466 GB USB disk) |
| Battery | 1900 mAh | 2281 mAh (healthy) | 7040 mAh | 5000 mAh |
| Bootloader | **locked** (Verizon) | unlocked | unlocked | **locked** (root attempt failed) |
| Mode | root + chroot | root + chroot | root + chroot | **no root**: Termux + proot + Shizuku ([12](12-no-root.md)) |
| Root route | KingRoot (B) | `adb root` (C) | Magisk 30.7 (A) | none |
| `ARCH` / container | armhf | armhf | **arm64** | arm64 (proot-distro) |
| `ROOT_MODE` / `BOOT_MODE` | `su` / `kingroot` | `adbroot` / `initrc` | `su` / `magisk` | – / Termux:Boot |
| `BB_PATH` | `/system/xbin/busybox-deb` | `/data/debian/busybox-deb` | `/data/debian/busybox-deb` (Magisk's) | – |
| Charger control | `BATT_CTRL=slate` | `enable` | `slate` | the maker's own limit (80 %), reported by `charge.sh` |
| Special in `server.conf` | defaults, `LOW=40 HIGH=60` | `FIX_ROUTE=1`, `ADB_TCP_PROP=persist.adb.tcp.port`, `LOW=25 HIGH=65` | `DOZE_OFF=1`, `LINEAGE_CHARGE_CTRL_OFF=1`, `WIFI_MIN=-85`, `ADB_RESTART="setprop ctl.restart adbd"` | `OEM=oplus` (no-root `server.conf`) |
| Role | production 24/7 | cold spare | test bench | test server, candidate for production |

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

## Realme 12+ 5G (RMX3867, Android 16, Realme UI 7) — no root

* **Locked bootloader and no unlock route** (Realme offers no "Deep Testing" app for this model): the root
  attempt failed, so it runs **[no-root mode](12-no-root.md)**: Termux + proot-distro Debian + Shizuku (thedjchi fork).
* The ColorOS particulars: *Developer options → Disable permission monitoring: On* (Shizuku needs it); the
  charge limiter is the phone's own (*Battery health → Custom charge limit → 80 %*, readable as
  `settings system regular_charge_protection_*`); nine system packages cannot be removed or disabled from adb;
  `cmd appops set`, `pm grant` and `pm disable-user` are blocked for protected Oplus apps (use the UI).
* 142 packages removed with `pm uninstall -k --user 0` (reversible); **~7.5 GB RAM free at idle**.

Measured (test bot, Wi-Fi 5 GHz at −70 dBm unless noted):

| Task | S4 mini | Tab A7 | **Realme** |
|---|---|---|---|
| `/velocidad` | 50–66 ↓ / 48–54 ↑ Mbps | 47–72 ↓ / 68–76 ↑ | **160 ↓ / 155 ↑** (187 ↓ / 137 ↑ at −35 dBm) |
| Short YouTube clip (19 s) | – | 16 s | 10 s |
| YouTube 1080p, 5 min, large upload | 154 MB in ~2 min | 255 MB in 105 s | **48 s** (download 28 s + upload 19 s) |
| `/mp3` | 10 min of audio in 95 s | ~22 s per 10 min | 3.5 min in 29 s |
| Photo from 4 cameras (plugin) | ~8 s | 13 s | **4.6 s** |
| Whisper `base`, 33 s of audio | ~4× | ~0.5× | **0.34×** (11 s) |
| Whisper `small`, 33 s of audio | ~13× | 1.2–1.4× | **1.06×** (35 s) |
| 6 parallel 1080p YouTube downloads (5–13 min videos) | – | – | **all in 3 min 19 s**, min. free RAM 8.8 GB, battery ≤ 27.6 °C |
| A 1-hour 8K video | – | – | 1080p exceeded 2 GB → redone at 720p (336 MB): 10 min 45 s, ~7.5 of them wasted on the first attempt; upload ~7.6 MB/s |
| Instagram reel / carousel / Facebook / TikTok | – | – | 12 s / 16 s / 16 s / 17 s |

Real Spanish speech, 60 s, 8 threads — **model quality matters more than speed here**:

| Whisper model | Time | Quality |
|---|---|---|
| base | 48 s (0.8×) | poor (garbled names) |
| small | 129 s (2.2×) | good |
| medium | 387 s (6.5×) | good |
| **large-v3-turbo** | 254 s (4.2×) | the best |

Local LLM (llama.cpp, Qwen2.5 Q4_K_M): 1.5B ≈ 24 tokens/s reading and **~6 tokens/s writing**; 3B ≈ 12 and
**~3.5**. Fewer threads were better (4 beat 8); pinned to the two A78 cores it is slower (the vendor caps their
clock). Fine for short, unhurried summaries, not for chatting. "High performance mode" changed nothing: the limit
is the chip and its memory, so it only adds heat.

Supervision tests, the full feature checklist, the USB disk/NAS numbers and the hub problems are in
[12 · No-root mode](12-no-root.md) and [13 · Media recipes](13-media-recipes.md).

## Add your phone

If you install this on another model, please send a pull request adding a section like the
ones above: model, Android, ABI, root route, `BB_PATH`, `BATT_CTRL`, what you had to change,
and a couple of measurements. Failed attempts are as valuable as successes.
