# 03 · Install: busybox, Debian and the scripts

> **No root?** This page is for root mode. Use [12 · No-root mode](12-no-root.md) instead.

Assumes: the phone is rooted ([02](02-root.md)), USB debugging works, and `config.sh` is filled
in ([01](01-prepare.md)). All commands run on your **PC**, from the repository folder, in bash.

The installer is split into steps so that you can repeat just the one that failed.

```bash
tools/fetch-assets.sh              # 1. download Debian (+ busybox on 32-bit ARM)
tools/install.sh check             # 2. what did I plug in?
tools/install.sh busybox           # 3. busybox on the phone
tools/install.sh rootfs            # 4. unpack Debian on the phone
tools/install.sh scripts           # 5. enter.sh, bot.sh, charge.sh, start.sh, server.conf
tools/install.sh provision         # 6. packages + Python venv inside Debian
```

## 1. Download

`tools/fetch-assets.sh` downloads into `downloads/` (git-ignored):

* **Debian 13 "trixie" root filesystem** for your `ARCH`, from
  <https://images.linuxcontainers.org/images/debian/trixie/> (the newest build), and verifies it
  against the published `SHA256SUMS`.
* **busybox** (32-bit ARM only) from <https://busybox.net/downloads/binaries/>.

> Prefer another distro or version? Any rootfs of the right architecture works for the chroot;
> the scripts assume Debian/apt in `provision`.

## 2. Check

`tools/install.sh check` prints the model, Android version, CPU ABIs, RAM, free space, SELinux
mode and — important — which **battery control files** exist. Copy what it tells you into
`config.sh` (`ARCH`) and later `server.conf` (`BATT_CTRL`, see [06](06-battery-and-heat.md)).

## 3. busybox

The chroot is entered with busybox's `chroot` and `mount`; Android's own toolbox has neither.
You need a **static** busybox that includes the `chroot` applet (`install.sh busybox` verifies it).

**Where it must live** — this decides `BB_PATH` in `config.sh`:

| Situation | `BB_PATH` |
|---|---|
| Most phones, Magisk, custom ROMs | `/data/debian/busybox-deb` (default) |
| **Old Samsung kernels** with `sec_restrict_fork` (Galaxy S4 era, Android 4.4–5): root is forbidden to execute binaries stored in `/data`, you get *Permission denied* / *Operation not permitted* | `/system/xbin/busybox-deb` (the script remounts `/system` read-write and back) |

How to tell: push busybox to `/data/local/tmp`, then
`adb shell su -c /data/local/tmp/busybox true`. If that is refused, use `/system/xbin`.
(Inside the chroot this restriction does not apply.)

* **32-bit ARM:** `tools/fetch-assets.sh` gets `busybox-armv7l`.
* **arm64:** busybox.net has no aarch64 build. If you use Magisk it already ships one:
  `adb shell su -c "cp /data/adb/magisk/busybox /data/local/tmp/busybox-arm64"`, `adb pull` it, and
  run `tools/install.sh busybox path/to/busybox-arm64`.

## 4. Debian

`tools/install.sh rootfs` re-compresses the `.tar.xz` as `.tar.gz` on the PC (busybox often lacks
xz), pushes it, and unpacks it into `/data/debian/fs` **preserving permissions** (`tar -p`). It
refuses to run if `/data/debian/fs` already holds a Debian: move or delete that yourself.

## 5. Scripts

`tools/install.sh scripts` copies to `/data/debian/`:

| File | Role |
|---|---|
| `enter.sh` | mounts `/proc`, `/sys`, `/dev`… and enters the chroot. `enter.sh` opens a shell; `enter.sh "cmd"` runs a command |
| `bot.sh` | keeps the bot running, restarting with back-off |
| `charge.sh` | the once-a-minute watchdog |
| `start.sh` | runs at boot: wake-lock, Wi-Fi, adb, then `bot.sh` and `charge.sh` |
| `server.conf` | **your settings** (created from `phone/server.conf.example`, never overwritten) |

**Edit `server.conf` now**, especially the battery driver
([06](06-battery-and-heat.md)). The reference of every setting is in
[`phone/server.conf.example`](../../phone/server.conf.example). To edit the copy on the phone:

```bash
tools/edit-conf.sh        # downloads it, opens your $EDITOR, uploads it if you changed it
```

(`charge.sh` re-reads it every minute, so later edits need no restart.)

## 6. Provision Debian

`tools/install.sh provision` runs `phone/setup-debian.sh` **inside** the chroot. It takes
10–30 minutes on a slow phone and needs the phone's Internet. It:

* writes `resolv.conf`, sets your time zone;
* creates the `aid_inet` (3003) and `aid_net_raw` (3004) groups — Android only lets processes in
  group *inet* use the network, and apt would otherwise drop to a user that is not in it — and
  tells apt to run as root with IPv4 only;
* installs Python, ffmpeg, Node.js (yt-dlp needs a JS runtime for YouTube), `iw`,
  poppler-utils, and the Python libraries that exist as prebuilt Debian packages;
* builds a virtualenv at `/opt/bot/venv` and installs `bot/requirements.txt` (yt-dlp,
  gallery-dl, Telethon + TgCrypto…); the compiler needed for TgCrypto is removed afterwards.

When it ends it prints the Python and yt-dlp versions.

### Quick manual check

```bash
adb shell su -c "/data/debian/enter.sh 'cat /etc/debian_version; python3 --version; ping -c1 1.1.1.1'"
```

## If something fails

| Symptom | Cause / fix |
|---|---|
| `exec format error` when entering the chroot | wrong `ARCH`: a 32-bit phone needs `armhf` |
| `chroot: not found` / no `chroot applet` | that busybox build lacks it; use another (`busybox --list \| grep chroot`) |
| `Permission denied` running busybox from `/data` | `sec_restrict_fork`: use `BB_PATH=/system/xbin/busybox-deb` |
| `mount: Operation not permitted` | not really root, or SELinux enforcing blocks it: try `su -c 'setenforce 0'` once to confirm; some ROMs need the Magisk "SELinux permissive" route |
| apt: *Temporary failure resolving* | `/etc/resolv.conf` empty (the provision step writes it), or the phone has no Internet |
| apt: *Could not create temporary file* / network unreachable | the `aid_inet` group/`Sandbox::User root` setting is missing; re-run `provision` |
| *No space left on device* | `/data` is full; free space or remove voice models |
| Android 11+: `Network is unreachable` as root | set `FIX_ROUTE=1` in `server.conf` ([07](07-network.md)) |

## What the installer does, by hand

If you would rather do it manually: push busybox to its place (`chmod 755`; `chcon
u:object_r:system_file:s0` if it is in `/system`); create `/data/debian/fs` and `tar -xzpf` the
rootfs into it; copy the scripts from `phone/` to `/data/debian/` with `chmod 755`; copy
`bot/requirements.txt` to `/data/debian/fs/opt/bot/`; then run `phone/setup-debian.sh` through
`enter.sh`.

Next: [04 · Telegram bot](04-telegram-bot.md).
