# 11 · FAQ and safety

## Safety

**Battery.** An old lithium battery on a charger 24/7 is the main physical risk. Read
[06](06-battery-and-heat.md): keep it between 40–60 %, inspect it monthly, never run a swollen
one, give it air. When in doubt, unplug and replace it.

**Rooting.** It can erase your data, void the warranty, and brick the phone. KingRoot (the route for
locked-bootloader phones) is closed-source software with a questionable reputation: use it only on a
dedicated, wiped phone with no personal accounts. See [02](02-root.md).

**Secrets.** The bot token, API keys, cookies and the Telegram session are credentials.
They live in `/opt/bot` with mode 600, never in git. `.gitignore` excludes `config.sh`, `backup/`
and the usual file names; `make-image.sh` leaves them out of the image. If a token leaks,
revoke it in @BotFather (`/revoke`) and set a new one with `tools/set-token.sh`.

**Who controls the bot.** The first account to send `/start` in private becomes the owner.
Do that yourself right after enabling the bot ([04](04-telegram-bot.md)). The bot ignores everyone
not authorised, and leaves groups it is added to by anyone other than the owner.

**Cookies.** Use a secondary account, never your main one. A cookies file is a logged-in
session. The bot deletes your upload message after saving it and keeps the file mode 600.

**Shizuku and wireless debugging (no-root mode).** Shizuku gives Termux the powers of Android's `shell` user (read
system state, `svc`, reboot, install/uninstall apps): authorise **only Termux**, and treat anyone with an SSH key to
your Termux as having those powers. Keep SSH key-only (`PasswordAuthentication no`) and on your LAN. Wireless
debugging is a second door: pair only PCs you control and never forward its port.

**Network exposure.** Nothing needs an inbound port. Keep adb (:5555) on your LAN, protected by its RSA
key. Do not forward it from your router.

**Plugins and code.** A plugin runs with the bot's privileges. Install only plugins you have read.

## Legal

* Downloading content from social networks may violate their terms of service and, depending on what you
  download and where you live, copyright law. This project is a tool; **you** are responsible
  for what you download and for having the right to do so. Use it for content you own, that is
  licensed for it, or that you are otherwise allowed to keep.
* Do not use it to bypass paywalls, DRM or access controls, and do not use other people's accounts.
* The authors give no warranty (see [LICENSE](../../LICENSE)).

## FAQ

**Does it work without root?**
Yes, on modern phones: [12 · No-root mode](12-no-root.md) (Termux + proot + Shizuku), tested end to end on a Realme 12+.
You lose charger control and support for phones older than ~Android 11. Root mode remains the choice for the oldest phones.

**Why offer a chroot at all, if proot works without root?**
Native speed (proot translates every system call), direct control of the charger and Wi-Fi, and it runs on Android
versions that modern Termux and Shizuku no longer support. On a modern phone, no-root mode is simpler and almost as fast.

**What about iPhones?**
No. iOS cannot run this.

**Can the phone's screen stay off? Do I need a SIM?**
Screen off, yes (a wake-lock keeps the CPU up). No SIM needed; Wi-Fi only.

**How much power does it use?** A few watts, comparable to a small single-board computer. Measure
yours with a plug-in energy meter; it varies with the phone and the load.

**How many people can use the bot?** As many as you authorise; downloads run three at a time
and queue the rest (`WORKERS` in `bot/bot.py`). Heavy use of voice transcription is the thing that
loads a 2-core phone.

**Can I run something other than the bot?**
Yes. After [05](05-services-and-boot.md) you have Debian in a chroot with a watchdog and charge
control. Leave `BOT_ENABLED` absent and use `tools/install.sh`'s steps as the base for any service
(`BOT_CMD` in `server.conf` can run any command at start-up).

**How do I translate the bot?**
The user-visible strings are Spanish and live in `bot/bot.py` (and the plugins). A real
translation layer would be a great contribution; until then you can edit the strings in place.

**The bot says my phone is "S4 mini" / has the wrong battery.**
`/opt/bot/device.json` customises the texts of `/estado`, `/bateria` and `/acerca`; copy
`phone/device.example.json` to `device.json` in the repository root and `tools/deploy.sh`.

**Things worked, then stopped after weeks.** Most likely candidates, in order: yt-dlp needs
updating (`/actualizar`), cookies expired (`/cookies`), Wi-Fi signal/AP issues
([07](07-network.md)), an app or the ROM auto-updated, the battery got too hot. `/salud` and
`/historial` check all of them.

## Credits and licences

Written by people who needed a use for old phones. Built on excellent free software:
[yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), [gallery-dl](https://github.com/mikf/gallery-dl)
(GPL-2.0, run as a separate program), [Telethon](https://github.com/LonamiWebs/Telethon) (MIT),
[TgCrypto](https://github.com/pyrogram/tgcrypto) (LGPL-3.0), [ytmusicapi](https://github.com/sigma67/ytmusicapi) (MIT),
[whisper.cpp](https://github.com/ggml-org/whisper.cpp) (MIT), [Vosk](https://alphacephei.com/vosk/) (Apache-2.0),
Debian, busybox (GPL-2.0), Magisk (GPL-3.0). The code of this repository is MIT licensed.
Check the licence of each tool you install.
