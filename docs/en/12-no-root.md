# 12 · No-root mode (Termux + proot + Shizuku)

For phones you **cannot root** (locked bootloader with no unlock route, a vendor that refuses,
or you simply do not want to). The same Debian, the same bot, the same watchdog idea — but
running inside **Termux** instead of a chroot, with **Shizuku** giving the few system powers
the watchdog needs.

It was built and tested end to end on a **Realme 12+ 5G** (Android 16, Realme UI 7, Dimensity
7050, locked bootloader: the root attempt failed). Everything in this page was verified there.

## Root mode or no-root mode?

| | Root mode (chroot) | **No-root mode (Termux + proot)** |
|---|---|---|
| Needs | root ([02](02-root.md)) | nothing special; Android **11+ recommended** |
| Speed | native | proot adds overhead per system call; on a modern phone it is not noticeable (Realme: the same download times as the root tablet) |
| Charge control | the script switches the charger | **only the maker's own limit** (e.g. "limit to 80 %"); the script reports it |
| Reading battery, Wi-Fi, uptime | direct from `/sys`, `iw` | not allowed to apps: Shizuku reads them and `charge.sh` hands them to the bot |
| Reboot / Wi-Fi restart from the bot | yes | yes **with Shizuku**; without it, no reboot |
| Survives reboot | boot launcher as root | Termux:Boot (must be opened once by hand) |
| Android kills background apps | no | it *can*: the guardian reopens Termux (tested) |
| Old phones | **yes, down to Android 4.4** | no: Termux needs Android 7+, auto-started Shizuku needs 11+ |

Rule of thumb: **old phone (≤ Android 10) → root mode. Modern phone you cannot or will not
root → this page.** (For a no-root server without a bot, see also the projects listed in
[00 · Overview](00-overview.md).)

## How it works

```
 Android (no root, screen off, plugged in)
  │
  ├─ Termux:Boot ─► 00-server.sh   wake-lock · sshd (:8022) · bot.sh · charge.sh loop
  │                    │
  │                    ├─► bot.sh      restarts the bot with growing delays (like root mode)
  │                    └─► charge.sh   once a minute: reads battery/Wi-Fi/uptime THROUGH SHIZUKU
  │                                    and writes them to /opt/bot/sys; heartbeat; Wi-Fi/Internet;
  │                                    /reiniciar; optional USB-disk services
  │
  ├─ Shizuku (shell-user powers, starts itself at boot over wireless debugging)
  │     └─ guard.sh  runs as the shell user: if Android closes Termux, it opens it again
  │
  └─ Termux → proot-distro container "bot" = Debian 13 → /opt/bot  (bot.py + plugins)
       enter.sh bind-mounts /opt/bot/sys/{battery,uptime,loadavg} where the bot expects them,
       so bot.py is the very same file as in root mode
```

Why Shizuku? An ordinary app cannot read `/sys/class/power_supply`, run `svc wifi`, or reboot.
Shizuku runs a small service with the permissions of Android's `shell` user (the one `adb shell`
has) and lets Termux ask it for commands through `rish`. Why not wireless adb to itself?
Android switches wireless debugging off whenever the phone hops between access points (router ↔
repeater): *"Detected wifi network change. Disabling adbwifi"*. Shizuku's service stays alive.

## Install, step by step

PC-side commands are `tools/noroot-*.sh`; they talk to Termux over **SSH** (port 8022), not adb.

### 1. Install the Termux apps (not from Google Play)

Install **Termux**, **Termux:Boot** and **Termux:API** from the same source — all three must
be signed by the same key to share a user. Use the [GitHub releases](https://github.com/termux/termux-app/releases)
or F-Droid. (The Google Play build is no longer maintained.) The tested versions were
the GitHub builds Termux 0.118.3, Boot 0.8.1, API 0.53.0, installed with `adb install -g` (which also
grants them `WRITE_SECURE_SETTINGS`). Open Termux:Boot **once** by hand.

### 2. Keep Android from killing Termux

* *Settings → Apps → Termux → Battery*: **unrestricted / allow background activity** (it covers all
  three apps: they share a user).
* From your PC with adb (USB or wireless), once:
  ```bash
  adb shell dumpsys deviceidle whitelist +com.termux
  adb shell settings put global settings_enable_monitor_phantom_procs false
  adb shell device_config put activity_manager max_phantom_processes 2147483647
  ```
  The last two stop Android 12+ from killing Termux's child processes.
* Vendor power settings: turn off "standby optimisation during sleep" (Realme: *Battery → Power
  saving settings*), disable automatic system updates and "install updates overnight".
* **Developer options → Wireless debugging: on**, and "Disable adb authorization timeout".
* Realme/OPPO only: **Developer options → Disable permission monitoring: On** (without it ColorOS
  limits adb/Shizuku permissions).

### 3. SSH into Termux

In Termux: `pkg install openssh`, then `whoami` (it is `u0_aNNN`) and `sshd`. On your PC:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/phone_ed25519          # no passphrase if the scripts must run unattended
# put the .pub line into ~/.ssh/authorized_keys on the phone (type it in Termux, or from a PC with
# adb:  adb shell run-as com.termux ... — the apps from GitHub are debug builds so run-as works)
```

`~/.ssh/config` on the PC:

```
Host phone
    HostName 192.168.1.50       # the phone's IP; reserve it in your router
    Port 8022
    User u0_a123                # what `whoami` said in Termux
    IdentityFile ~/.ssh/phone_ed25519
```

Set `NOROOT_SSH=phone`, `NOROOT_IP=…` in `config.sh`. In `$PREFIX/etc/ssh/sshd_config` put
`PasswordAuthentication no` (key-only). `ssh phone echo ok` must work.

### 4. Shizuku

1. Install the **thedjchi fork of Shizuku** (GitHub `thedjchi/Shizuku`; tested: 13.7.0). The official
   Shizuku can only start by itself at boot on rooted phones; the fork starts through wireless debugging.
2. In Shizuku: *Start via wireless debugging* (pair once), and enable **start on boot**.
3. In Shizuku: *Use Shizuku in terminal apps* → export `rish` and `rish_shizuku.dex`; authorise **Termux**.
4. Copy both files to a folder on your PC and run:
   ```bash
   tools/noroot-install.sh rish path/to/folder      # prints "test: uid=2000(shell)…" when it works
   ```
   (Android 14+ requires the `.dex` to be read-only and inside the app's own directory: the script does it.)

Without Shizuku the watchdog still runs: it falls back to Termux:API for the battery and Wi-Fi, and
the bot's `/reiniciar confirmar` tells you it cannot reboot the phone.

### 5. Debian + the bot

```bash
tools/noroot-install.sh packages          # proot-distro, openssh, termux-api, jq…
tools/noroot-install.sh container         # Debian 13 in a proot-distro container ("bot"; from Docker Hub)
tools/noroot-install.sh provision         # Python venv, yt-dlp, ffmpeg…  (same script as root mode)
tools/noroot-install.sh scripts           # ~/server/*.sh, server.conf, Termux:Boot hook
tools/noroot-bot.sh token                 # token from @BotFather
tools/noroot-deploy.sh                    # bot code + plugins + scripts
tools/noroot-bot.sh enable                # go; then /start in Telegram: you become the owner
```

Verified from scratch on the Realme for this release: `container` (the Docker Hub `debian:trixie` image) took a minute
or two, `provision` **7 min 25 s**, and the bot's 24 unit tests then passed inside the new container (Python 3.13.5,
aarch64); the generic `charge.sh`, `sa.sh` and `enter.sh` were exercised against the real Shizuku (battery, Wi-Fi, USB disk,
bind-mounts).

Notes:

* `container` takes an optional rootfs file instead of the Docker image: `tools/noroot-install.sh
  container path/to/image.tar.gz` (for example an arm64 image made with `tools/make-image.sh` on a
  rooted phone; that is how the original Realme was built).
* Edit `~/server/server.conf` on the phone (`ssh phone nano ~/server/server.conf`): `OEM=oplus` for
  Realme/OPPO/OnePlus, `CONTAINER`, and the optional `SERVICES`/`NIGHTLY` of [13 · Media recipes](13-media-recipes.md).
* Voice notes: `tools/noroot-install.sh voice`.
* `tools/noroot-deploy.sh` is the equivalent of `tools/deploy.sh`; the bot is the same code.

### 6. The charge limit — by hand

Without root nothing here can switch the charger. Turn on the maker's own limiter (Realme: *Settings →
Battery → Battery health → Custom charge limit → 80 %*; Samsung "Protect battery"; Pixel "Limit to
80 %"; Xiaomi "Battery protection"). `charge.sh` notices "plugged in but not charging" and reports it as
a paused charge, so `/estado` and `/bateria` say *"en pausa, vive del cargador"*, and power cuts are
detected the same way as in root mode. Read [06 · Battery and heat](06-battery-and-heat.md): the safety
advice is identical.

### 7. De-bloat (optional)

`adb shell pm uninstall -k --user 0 <package>` removes an app **for the current user without deleting
it from the system**: reversible with `adb shell cmd package install-existing <package>`. 142 packages
were removed from the Realme; nine are protected by ColorOS and cannot be removed or disabled from
adb at all (`co.sitic.pp`, `com.coloros.assistantscreen`, `com.coloros.bootreg`,
`com.coloros.lockassistant`, `com.nearme.instant.platform`, `com.oplus.aiunit`, `com.oplus.ota`,
`com.oplus.pay`, `com.oplus.sau`). Keep: the battery app, Settings, launcher, SystemUI, Wi-Fi/network,
permission controller, WebView, keyboard, and Google Play Services if you want Google apps.
Realme also blocks `cmd appops set`, `pm grant` and `pm disable-user` on protected Oplus apps from
adb: change those in the Settings UI (`~/server/ui.sh dump` / `ui.sh tap "Text"` can drive the screen).

## What the scripts do

| File (`~/server/`) | Role |
|---|---|
| `boot.sh` → `~/.termux/boot/00-server.sh` | at power-on: wake-lock, `sshd`, `bot.sh`, the `charge.sh` loop |
| `bot.sh` | restarts the bot with back-off 10 s → 10 min (same as root mode) |
| `charge.sh` | watchdog. Writes battery/uptime/Wi-Fi to `/opt/bot/sys`; heartbeat (5 min frozen → kill); `/reiniciar`; Wi-Fi/Internet recovery; starts `guard.sh`; optional USB-disk services |
| `enter.sh` | `proot-distro login` with the `/opt/bot/sys` binds (and the USB disk at `/mnt/disk`) |
| `sa.sh 'cmds'` | runs commands as the shell user through `rish` and returns the output reliably (see below) |
| `guard.sh` → `/data/local/tmp/srv-guard.sh` | shell-side guardian: keeps wireless debugging on; if Termux's `sshd` is gone for 2 passes, opens Termux's window so `~/.bashrc` restarts the server |
| `doctor.sh` | read-only health check: OK/WARN/FAIL with what to do (`tools/noroot-doctor.sh` from the PC; hourly into `/salud`). See [14](14-no-root-reliability.md) |
| `ui.sh` | tap and read the phone's own screen through Shizuku |
| `server.conf` | settings (container name, `OEM`, services, nightly job, `NET_HOSTS` for the Internet check, `KEEPALIVE`) |

### Gotchas that cost real time (so you can skip them)

* **`rish` loses lines of output at random and does not return exit codes.** `sa.sh` makes the
  shell side write to a file on shared storage and reads it back. `cmd` commands (`settings`, `pm`,
  `cmd wifi`) fail if their output *is* that file: wrap them in `$(…)` or a pipe with `2>&1`.
* **Inside scripts always call `rish`/`sa.sh` with `</dev/null`**: `rish` reads stdin and eats the rest
  of the script.
* **`guard.sh` must live in its own session (`setsid`).** If it hangs off the `rish` that launched it,
  Shizuku kills it together with Termux. That is exactly how the first guard died.
* **Termux:Boot must be opened by hand once.** The first reboot test failed because of this.
* `pkill -f pattern` inside `ssh host "…"` kills itself (the command line contains the pattern):
  write `[p]attern`.
* **Android can close Termux** (it happened once in a night). `guard.sh` reopens it; a forced
  `am force-stop com.termux` test recovered SSH and the bot in **2 min 9 s**.

## Supervision, tested (Realme)

| Test | Result |
|---|---|
| `kill -9` the bot | `bot.sh` relaunches in **11 s** |
| `bot.sh` dies | `charge.sh` relaunches; bot back in **31 s** |
| bot frozen (`kill -STOP` the bot **and its proot**) | killed after **302 s** without heartbeat, relaunched 10 s later |
| `/reiniciar confirmar` (through Shizuku) | phone off in 45 s, Android up at 85 s, SSH at 100 s, **bot running at 104 s**; Shizuku ~70 s after boot, Doze off again by itself |
| `am force-stop com.termux` | SSH and bot back in **2 min 9 s** |
| Internet cut of 90 s | bot reports "sin conexión de 07:49 a 07:51" |
| Reboot with every extra enabled | SSH and bot at **54 s**, Jellyfin at 78 s, wireless debugging again on at 2 min 45 s |

Full feature test with the test bot: links (YouTube, Instagram, Facebook, TikTok, Dailymotion), carousels,
`/original`, `/mp3`, big uploads over MTProto, drop to 720p above 2 GB, cache, six parallel downloads,
resume after a restart, voice notes, `/pdf`, `/sticker`, `/seguir`…`/dejar`, `/actualizar`, `/estado`,
`/bateria`, `/salud`, `/velocidad`, `/reiniciar wifi|confirmar` — all OK. **Not covered yet:** a real
power cut, groups, and several days of unattended running.

## Remote control without touching the phone

* `ssh phone` (key-only).
* Wireless adb from your PC: pair once, `guard.sh` keeps it on; `tools/noroot-adb.sh` finds the changing
  port (mDNS, else a scan of 30000–50000) and connects: `adb -s "$(tools/noroot-adb.sh | tail -1)" shell …`.
  After switching it off by hand the PC reconnected by itself in 51 s.
* If Termux is down: `adb … shell am start -n com.termux/.app.TermuxActivity` (or `reboot`).

## Moving between modes

Backups are interchangeable: `tools/backup.sh` (root) or `tools/noroot-backup.sh`, then
`tools/noroot-restore.sh backup/<date>` (or `tools/restore-config.sh` on a rooted phone). **Switch the bot
off on the old phone first** — the same token on two phones gives Telegram error 409 and duplicated
downloads.

**Check the installation** at any time with `tools/noroot-doctor.sh`. What can still stop the server,
what the watchdog re-applies by itself (battery exemptions, the phantom-process killer…) and how to test
it for days: [14 · No-root 24/7](14-no-root-reliability.md).

Next: [13 · Media recipes](13-media-recipes.md) (a NAS and media server on the same phone).
