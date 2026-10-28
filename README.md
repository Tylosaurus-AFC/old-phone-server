# old-phone-server

**Turn an old Android phone into a 24/7 Linux server — with root (even a 2013 phone) or without it.**

🇪🇸 [Léeme en español](README.es.md)

A Debian on your phone (a chroot if you can root it, Termux + proot if you cannot), a pair of watchdogs that keep
everything alive, charge limiting that protects the battery, and a real application on top: a **Telegram bot that downloads videos and photos
from social networks** (uploads up to 2 GB, voice-note transcription on the phone itself, YouTube
channel following, health reports). It was built on a **Galaxy S4 mini (2013, Android 4.4)** that has
been serving 24/7, then reproduced on a **Moto X2 (Android 11)**, a **Galaxy Tab A7 (Android 16)** and, **without
root**, on a **Realme 12+ 5G (Android 16)**.

```
 Android (rooted) ─► start.sh ─┬─► bot.sh     keeps the bot alive (crash back-off)
   boot launcher               └─► charge.sh  watchdog: frozen bot · Wi-Fi/Internet · battery 40–60 %
 /data/debian/fs = Debian 13 (chroot)  ─►  /opt/bot: bot.py + plugins  ◄──►  Telegram
```

## Is it for you?

| Your phone | Use |
|---|---|
| **Android 4.4–10, 32- or 64-bit, can be rooted, must run 24/7** | **this project — root mode** |
| **Android 11+, cannot / will not root, a 24/7 service** | **this project — [no-root mode](docs/en/12-no-root.md)** (Termux + proot + Shizuku) |
| Android 10+, 64-bit, no root, wants ready-made apps | [homedroid](https://github.com/sudiptacmd/homedroid) |
| 64-bit, no root, wants a desktop / Home Assistant | [mayukh4/linux-android](https://github.com/mayukh4/linux-android) |
| Rooted, wants a plain Termux walkthrough | [MultiX0/old-phone-to-server](https://github.com/MultiX0/old-phone-to-server), [Android-Phone-as-Server](https://github.com/Nikhil-Richhariya/Android-Phone-as-Server) |

Those are independent projects. What this one adds: support for phones where current Termux cannot
install, a native chroot *and* a no-root mode, and the unglamorous parts of 24/7 operation — watchdogs,
crash back-off, Wi-Fi recovery, **battery charge limiting**, backups/restore, and a recovery procedure for each
failure that actually happened.

## Quick start — root mode

You need: the phone **already rooted** ([guide](docs/en/02-root.md)), a PC with `adb` and bash
(Git Bash on Windows), and a Telegram account. Details and explanations are in the [guides](#guides).

```bash
git clone https://github.com/Tylosaurus-AFC/old-phone-server.git && cd old-phone-server
cp config.example.sh config.sh && $EDITOR config.sh      # ARCH, PHONE_IP, ROOT_MODE, BOOT_MODE, BB_PATH…

tools/fetch-assets.sh          # Debian 13 for your CPU (+ busybox) → downloads/
tools/install.sh check         # what phone is this? (also shows battery control files)
tools/install.sh busybox       # busybox on the phone
tools/install.sh rootfs        # unpack Debian
tools/install.sh scripts       # enter.sh, bot.sh, charge.sh, start.sh, server.conf
tools/edit-conf.sh             # ← set your battery driver (docs/en/06-battery-and-heat.md)
tools/install.sh provision     # packages + Python venv inside Debian (10–30 min)
tools/install.sh boot          # start at power-on (follow the printed notes for KingRoot)

tools/set-token.sh             # token from @BotFather
tools/deploy.sh                # push the bot
tools/enable-bot.sh            # go!  then send /start to your bot — the first person becomes the owner
```

## Quick start — no-root mode

You need: a modern phone (Android 11+ recommended), a PC with `adb`, `ssh` and bash. First, by hand (the
[guide](docs/en/12-no-root.md) walks through it): install Termux, Termux:Boot and Termux:API from GitHub/F-Droid,
exempt them from battery limits, set up SSH into Termux and Shizuku (thedjchi fork) + `rish`. Then:

```bash
cp config.example.sh config.sh && $EDITOR config.sh      # NOROOT_SSH, NOROOT_IP, TZ_NAME…
tools/noroot-install.sh check        # can this phone run it?
tools/noroot-install.sh packages     # proot-distro, openssh, termux-api, jq
tools/noroot-install.sh container    # Debian 13 container "bot" (from Docker Hub)
tools/noroot-install.sh provision    # Python venv, yt-dlp, ffmpeg…
tools/noroot-install.sh scripts      # ~/server/*.sh + Termux:Boot hook
tools/noroot-install.sh rish <dir>   # rish files exported from the Shizuku app
tools/noroot-bot.sh token            # token from @BotFather
tools/noroot-deploy.sh               # bot + plugins
tools/noroot-bot.sh enable           # go!
```

## What you get

* **Server-grade basics on a phone:** wake-lock, Wi-Fi that never sleeps, adb over Wi-Fi (or SSH in no-root mode),
  restart-on-crash with exponential back-off, frozen-process detection via heartbeat, Wi-Fi
  and Internet recovery, boot persistence for three root types (Magisk, KingRoot, init.rc) and for Termux:Boot.
* **Battery care:** root mode keeps charge at 40–60 %, stops above 42 °C, never lets it die; supports Samsung
  `batt_slate_mode`, `charging_enabled`, or none. No-root mode reports the maker's own limit. Both notice power cuts
  and report how long the battery lasted.
* **The Telegram bot** (messages in Spanish): downloads from 1000+ sites via yt-dlp/gallery-dl, 1080p, 2 GB
  uploads over MTProto, instant cache, MP3, PDF → images, followed YouTube channels, per-user access
  control, cookie handling, daily auto-update, `/salud` `/historial` `/bateria`, local speech-to-text, followed
  YouTube channels posted to a private chat and/or a Telegram channel, public-first Instagram/Facebook with clean links,
  inline buttons (MP3 / original / save to disk under every video), `/buscar` YouTube search, `/cola` queue with cancel,
  `/stats` from an SQLite log, an optional 7-day archive with `/guardar` to the USB disk.
* **Plugins:** drop-in extras — CCTV snapshots (Dahua), Alexa announcements, YouTube-Music→Last.fm
  scrobbling, YouTube-Music likes → Telegram channel, video stickers — and a simple API for your own.
* **NAS / media server recipes** for a phone with a USB disk: WebDAV, DLNA, Jellyfin, YouTube mirror, weekly backup.
* **Operations:** deploy, backup/restore of config and of the whole Debian image, move to another phone.
* **Tests that need no phone:** `tests/run.sh` (72 checks: battery logic against a fake battery, the no-root
  watchdog against a fake Shizuku, back-off and boot sequence, plugin loading, command dispatch, helpers).

## Guides

English: [docs/en](docs/en/) · Español: [docs/es](docs/es/)

| | |
|---|---|
| [00 Overview](docs/en/00-overview.md) | what, why, how it works, other projects |
| [01 Prepare](docs/en/01-prepare.md) | PC tools, adb, `config.sh` |
| [02 Root](docs/en/02-root.md) | picking a rooting route, honestly |
| [03 Install](docs/en/03-install.md) | busybox, Debian, scripts, provisioning, troubleshooting |
| [04 Telegram bot](docs/en/04-telegram-bot.md) | token, owner, commands, cookies, voice |
| [05 Services and boot](docs/en/05-services-and-boot.md) | boot chain, watchdogs, `server.conf` |
| [06 Battery and heat](docs/en/06-battery-and-heat.md) | **safety**, charge limiting, drivers |
| [07 Network](docs/en/07-network.md) | fixed IP, adb over Wi-Fi, sticky APs, Ethernet |
| [08 Operations](docs/en/08-operations.md) | update, backup, restore, troubleshooting |
| [09 Plugins](docs/en/09-plugins.md) | using and writing plugins |
| [10 Tested devices](docs/en/10-tested-devices.md) | S4 mini, Moto X2, Tab A7, Realme 12+: quirks and measurements |
| [11 FAQ and safety](docs/en/11-faq-and-safety.md) | legal, security, credits |
| [12 No-root mode](docs/en/12-no-root.md) | Termux + proot + Shizuku, step by step, with tested supervision |
| [14 No-root 24/7](docs/en/14-no-root-reliability.md) | what can stop a no-root server, the defences, `doctor.sh`, Shizuku recovery, automatic alerts, vendor profiles, compatibility matrix |
| [15 WhatsApp evaluation](docs/en/15-whatsapp-evaluation.md) | can WhatsApp be a second channel? options, costs, risks, recommendation (not implemented) |
| [13 Media recipes](docs/en/13-media-recipes.md) | USB disk, WebDAV, DLNA, Jellyfin, YouTube mirror, hub pitfalls |

## Status

* **Root mode (chroot):** the design and every script come from three real devices — a Galaxy S4 mini (production,
  24/7), a Moto X2 (cold spare) and a Galaxy Tab A7 (test bench) — which ran the original per-device scripts. This
  repository merges them into one parametrised set (`server.conf`), covered by the automated checks and waiting for
  reports from fresh installs on other phones.
* **No-root mode:** tested end to end on a Realme 12+ 5G: every bot feature, five supervision scenarios, reboot
  recovery, USB-disk services. The installer's container and provisioning steps were re-run from scratch on that
  phone for this release.
* **Not covered yet:** a real power cut in no-root mode, groups, several days of unattended running there;
  USB-Ethernet adapters (a first try was unreliable); AirPlay against a real Apple TV; non-Dahua CCTV; x86 phones.
* Rooting is risky and device-specific; this repository does not do it for you.
  Downloading content may breach site terms or copyright: **you** are responsible for what you use it for
  ([FAQ](docs/en/11-faq-and-safety.md)).

## Layout

```
bot/            the Telegram bot (bot.py, bigupload, health, pending, stt, thumbs)
extras/plugins/ optional plugins: cameras, alexa, stickers, lastfm_scrobbler, youtube_music_likes
phone/          scripts that run on the phone (root mode: enter, bot, charge, start, boot launchers, extras)
phone/noroot/   the same for no-root mode (Termux): boot, bot, charge, enter, sa (Shizuku), guard, extras/ recipes
tools/          scripts that run on your PC (root: fetch-assets, install, deploy…; no-root: noroot-*.sh)
tests/          tests that need no phone
docs/{en,es}/   the guides
```

## Contributing

Add your phone to [Tested devices](docs/en/10-tested-devices.md), report what broke, translate the
bot's strings, or write a plugin. See [CONTRIBUTING.md](CONTRIBUTING.md). Code is MIT licensed
([LICENSE](LICENSE)); the third-party tools it installs have their own licences.
