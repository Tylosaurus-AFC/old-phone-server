# old-phone-server

**Turn an old Android phone into a 24/7 Linux server — even a 2013 phone that nothing else will run on.**

🇪🇸 [Léeme en español](README.es.md)

A rooted phone, a Debian chroot, a pair of watchdogs that keep everything alive, charge limits that
protect the battery, and a real application on top: a **Telegram bot that downloads videos and photos
from social networks** (uploads up to 2 GB, voice-note transcription on the phone itself, YouTube
channel following, health reports). It was built on a **Galaxy S4 mini (2013, Android 4.4)** that has
been serving 24/7, then reproduced on a **Moto X2 (Android 11)** and a **Galaxy Tab A7 (Android 16)**.

```
 Android (rooted) ─► start.sh ─┬─► bot.sh     keeps the bot alive (crash back-off)
   boot launcher               └─► charge.sh  watchdog: frozen bot · Wi-Fi/Internet · battery 40–60 %
 /data/debian/fs = Debian 13 (chroot)  ─►  /opt/bot: bot.py + plugins  ◄──►  Telegram
```

## Is it for you?

| Your phone | Use |
|---|---|
| **Android 4.4–9, 32- or 64-bit, can be rooted, must run 24/7** | **this project** |
| Android 10+, 64-bit, no root | [homedroid](https://github.com/sudiptacmd/homedroid) |
| 64-bit, no root, wants a desktop / Home Assistant | [mayukh4/linux-android](https://github.com/mayukh4/linux-android) |
| Rooted, wants a plain Termux walkthrough | [MultiX0/old-phone-to-server](https://github.com/MultiX0/old-phone-to-server), [Android-Phone-as-Server](https://github.com/Nikhil-Richhariya/Android-Phone-as-Server) |

Those are independent projects. What this one adds: support for phones where current Termux cannot
install, a native chroot (no proot slowdown), and the unglamorous parts of 24/7 operation — watchdogs,
crash back-off, Wi-Fi recovery, **battery charge limiting**, backups/restore, and a recovery procedure for each
failure that actually happened.

## Quick start

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

## What you get

* **Server-grade basics on a phone:** wake-lock, Wi-Fi that never sleeps, adb over Wi-Fi,
  restart-on-crash with exponential back-off, frozen-process detection via heartbeat, Wi-Fi
  and Internet recovery, boot persistence for three root types (Magisk, KingRoot, init.rc).
* **Battery care:** keeps charge at 40–60 %, stops above 42 °C, never lets it die, notices power cuts and
  reports how long the battery lasted. Supports Samsung `batt_slate_mode`, `charging_enabled`, or none.
* **The Telegram bot** (messages in Spanish): downloads from 1000+ sites via yt-dlp/gallery-dl, 1080p, 2 GB
  uploads over MTProto, instant cache, MP3, PDF → images, followed YouTube channels, per-user access
  control, cookie handling, daily auto-update, `/salud` `/historial` `/bateria`, local speech-to-text.
* **Plugins:** drop-in extras — CCTV snapshots (Dahua), Alexa announcements, YouTube-Music→Last.fm
  scrobbling, video stickers — and a simple API for your own.
* **Operations:** deploy, backup/restore of config and of the whole Debian image, move to another phone.
* **Tests that need no phone:** `tests/run.sh` (battery logic against a fake battery, plugin loading,
  command dispatch, helpers).

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
| [10 Tested devices](docs/en/10-tested-devices.md) | S4 mini, Moto X2, Tab A7: quirks and measurements |
| [11 FAQ and safety](docs/en/11-faq-and-safety.md) | legal, security, credits |

## Status — please read

* The design comes from three machines that ran in production or on the bench. The **unified**
  scripts in this repository (one `charge.sh`/`start.sh`/`server.conf` for all of them, replacing three
  device-specific copies) were assembled afterwards: they pass the automated tests here
  (`tests/run.sh`: 47 checks) but **have not yet been re-validated on each physical device** —
  treat your first install as a validation run, start with the bot disabled, and
  [report what you find](CONTRIBUTING.md).
* Not tested with real hardware: USB-Ethernet adapters, arm64 voice setup scripts on other CPUs,
  non-Dahua CCTV, x86 phones.
* Rooting is risky and device-specific; this repository does not do it for you.
  Downloading content may breach site terms or copyright: **you** are responsible for what you use it for
  ([FAQ](docs/en/11-faq-and-safety.md)).

## Layout

```
bot/            the Telegram bot (bot.py, bigupload, health, pending, stt, thumbs)
extras/plugins/ optional plugins: cameras, alexa, stickers, lastfm_scrobbler
phone/          scripts that run on the phone (enter, bot, charge, start, boot launchers, extras)
tools/          scripts that run on your PC (fetch-assets, install, deploy, backup, restore…)
tests/          tests that need no phone
docs/{en,es}/   the guides
```

## Contributing

Add your phone to [Tested devices](docs/en/10-tested-devices.md), report what broke, translate the
bot's strings, or write a plugin. See [CONTRIBUTING.md](CONTRIBUTING.md). Code is MIT licensed
([LICENSE](LICENSE)); the third-party tools it installs have their own licences.
