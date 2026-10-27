# 00 · Overview: what this is and whether it is for you

**old-phone-server** turns an old Android phone into a small, quiet, always-on Linux server,
and ships a real application to run on it: a Telegram bot that downloads videos and photos
from social networks. It was built to rescue phones that are too old for anything else
(a Galaxy S4 mini from 2013 running Android 4.4 has been serving 24/7), then reproduced on a
Moto X2 and a Galaxy Tab A7, and finally — **without root** — on a modern Realme 12+.

Everything in this repository comes from machines that actually ran, with the problems that
showed up along the way written down. The guides do not stop at "it works": they say what
breaks, why, and how to recover.

## Why an old phone makes a good server

| | |
|---|---|
| **Built-in UPS** | The battery keeps the server alive through power cuts (the bot even tells you when the power went off and how long the battery lasted). |
| **Tiny and silent** | No fan, no moving parts, a few watts. |
| **Free** | It is in a drawer already. |
| **Wi-Fi + CPU + RAM + storage** | A 2013 phone has more than a Raspberry Pi 1. |
| **Outbound-only** | A Telegram bot only makes outgoing connections: no port forwarding, no dynamic DNS, no exposure to the Internet. |

## How it works

```
 Android (rooted, screen off, plugged in)
  │
  ├─ boot launcher ──► start.sh      wake-lock, Wi-Fi always on, adb over Wi-Fi
  │   (Magisk service.d,               │
  │    KingRoot hook, or init.rc)      ├─► bot.sh      keeps the bot alive; restarts with
  │                                    │               growing delays (10 s, 20 s ... 10 min)
  │                                    └─► charge.sh   watchdog, once a minute:
  │                                                    frozen bot · Wi-Fi/Internet · battery
  │                                                    kept at 40–60 % · /reiniciar requests
  │
  └─ /data/debian/fs  =  Debian 13 in a chroot  (entered with enter.sh)
       └─ /opt/bot/   bot.py + optional plugins  ◄──► Telegram
```

* **Why a chroot and not Termux/proot?** A chroot runs at native speed, needs no emulation
  layer, and gives you a *complete* Debian (apt, Python, ffmpeg, compilers). The price is that
  it needs **root**. Projects that need no root are listed below.
* **Why two watchdogs?** `bot.sh` and `charge.sh` watch each other: if one dies the other
  relaunches it within a minute. `charge.sh` also notices a bot that is alive but *frozen* (it
  stops writing its heartbeat) and kills it so `bot.sh` starts a fresh one.
* **And without root?** A second flavour runs the same Debian and bot inside **Termux** (proot) and uses
  **Shizuku** for the few system powers the watchdog needs. Same bot, same plugins, same ideas; the
  charger cannot be switched, only reported. See [12 · No-root mode](12-no-root.md).
* **Why care about the battery?** A phone kept at 100 % on a charger for years swells and can
  become dangerous. `charge.sh` switches the charger on and off to hold 40–60 %
  (see [06 · Battery and heat](06-battery-and-heat.md)).

## What the example application does

A Telegram bot, in Spanish (strings are easy to translate; see [FAQ](11-faq-and-safety.md)):

* Send it a link from TikTok, Instagram, Facebook, Threads, YouTube, X, Reddit… (yt-dlp and
  gallery-dl cover 1000+ sites). It posts the video or photos in the same chat with the title
  linked to the original and deletes your message.
* 1080p video (lower if over 2 GB), uploads **up to 2 GB** per file, a cache that re-sends a
  link instantly, `/mp3`, `/original`, PDF → images, YouTube channel following.
* **Voice notes → text**, entirely on the phone (whisper.cpp + Vosk), nothing sent to the cloud.
* Health: `/estado`, `/salud`, `/historial`, `/bateria`, `/velocidad`, automatic alerts
  (expired cookies, hot battery, low disk, Internet or Telegram outages, power cuts).
* **Telegram channels as destinations:** followed YouTube channels can be posted to your private chat,
  to a Telegram channel of yours, or both (`/canal`, `/destino`).
* **Plugins** for things that only suit some people: CCTV snapshots, Alexa announcements,
  Last.fm scrobbling, YouTube-Music likes → channel, sticker maker ([09 · Plugins](09-plugins.md)).
* **NAS and media server** recipes for a phone with a USB disk: WebDAV, DLNA, Jellyfin, a YouTube
  mirror ([13 · Media recipes](13-media-recipes.md)).

You can ignore the bot entirely and use the phone as a Debian server for something else:
everything up to and including [05](05-services-and-boot.md) is application-independent.

## Is your phone suitable?

You need **all** of these:

1. **Root** for the chroot mode — getting it is device specific and the riskiest step
   ([02 · Root](02-root.md)) — **or** a reasonably modern phone (Android 11+ recommended) for the
   no-root mode ([12](12-no-root.md)).
2. **≥ 3 GB of free storage** (Debian + bot ≈ 1.3 GB, voice models ≈ 0.3 GB, and working room for
   downloads: a long video can be several GB) and **≥ 1 GB of RAM** (the S4 mini has 1.3 GB and
   runs three simultaneous downloads).
3. An ARM CPU: 32-bit (`armeabi-v7a`) or 64-bit (`arm64-v8a`). x86 phones are untested.
4. A phone you no longer need as a phone, a charger, and Wi-Fi.

### Other projects, for other phones

This project has two modes: **root + chroot** (the only option for the oldest phones) and **no-root +
Termux/proot** (for modern ones). If what you want is not a 24/7 bot-style server, these independent projects
(not affiliated with this one) may fit better:

| Your phone | Try |
|---|---|
| Android 10+, 64-bit, no root, wants ready-made apps | [homedroid](https://github.com/sudiptacmd/homedroid): one APK (SSH, Jellyfin, Immich, AdGuard…) with its own proot |
| 64-bit, no root, wants a desktop or Home Assistant | [mayukh4/linux-android](https://github.com/mayukh4/linux-android): Termux + Termux-X11 + proot |
| Rooted with Magisk, wants a step-by-step Termux guide | [MultiX0/old-phone-to-server](https://github.com/MultiX0/old-phone-to-server) and [Nikhil-Richhariya/Android-Phone-as-Server](https://github.com/Nikhil-Richhariya/Android-Phone-as-Server) |
| **Android 4.4–10, 32- or 64-bit, rootable, must run 24/7** | **this project, root mode** |
| **Android 11+, no root, a 24/7 service with watchdogs, a Telegram bot and optional NAS** | **this project, no-root mode** |

What sets this one apart: it supports phones where current Termux cannot even install
(Termux needs Android 7+), offers a native chroot as well as the proot mode, and includes the unglamorous
parts of running 24/7: watchdogs, crash back-off, Wi-Fi recovery, battery charge limits,
backups and restore, and a documented recovery procedure for every failure we hit.

## Roadmap through the guides

| # | Guide | You will |
|---|---|---|
| 01 | [Prepare](01-prepare.md) | install adb, check your phone, fill in `config.sh` |
| 02 | [Root](02-root.md) | choose a rooting route (and understand its risks) |
| 03 | [Install](03-install.md) | busybox, Debian chroot, scripts, packages |
| 04 | [Telegram bot](04-telegram-bot.md) | create the bot, set the token, become the owner |
| 05 | [Services and boot](05-services-and-boot.md) | make it start by itself and stay up |
| 06 | [Battery and heat](06-battery-and-heat.md) | protect the battery (**do not skip**) |
| 07 | [Network](07-network.md) | fixed IP, adb over Wi-Fi, Wi-Fi problems, Ethernet |
| 08 | [Operations](08-operations.md) | update, back up, restore, troubleshoot |
| 09 | [Plugins](09-plugins.md) | optional extras and how to write your own |
| 10 | [Tested devices](10-tested-devices.md) | measurements and quirks of four real devices |
| 11 | [FAQ and safety](11-faq-and-safety.md) | legal, security, risks, common questions |
| 12 | [No-root mode](12-no-root.md) | the same server with Termux + proot + Shizuku, no root needed |
| 14 | [No-root 24/7](14-no-root-reliability.md) | limits of no-root mode, defences, `doctor.sh`, compatibility matrix |
| 13 | [Media recipes](13-media-recipes.md) | optional NAS / DLNA / Jellyfin / YouTube mirror on a USB disk |
