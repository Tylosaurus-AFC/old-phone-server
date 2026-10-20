# 01 · Prepare: PC, phone and settings

## What you need

**Hardware**

* The phone and a **good charger and cable**. It will be plugged in permanently.
* A place with decent Wi-Fi, near the router if you can (a weak signal is the commonest source of
  trouble, see [07 · Network](07-network.md)), on a hard, ventilated surface.
* A **healthy battery**: not swollen, not hot. Read [06 · Battery and heat](06-battery-and-heat.md)
  before you leave a phone running unattended.

**On your PC** (Windows, Linux or macOS)

| Tool | Why | Get it |
|---|---|---|
| `adb` (Android platform-tools) | talk to the phone | <https://developer.android.com/tools/releases/platform-tools> |
| `bash` | run the scripts in `tools/` | Linux/macOS: built in. Windows: **Git Bash** (comes with [Git for Windows](https://git-scm.com/download/win)) |
| `curl`, `xz`, `gzip`, `sha256sum` | download and prepare Debian | included in Git Bash and most Linux/macOS |
| Python 3 + `pip install requests` | only to run the test-suite (optional) | |

**Accounts**: a Telegram account (to talk to @BotFather and to the bot). Nothing else.

## 1. Get the repository

```bash
git clone https://github.com/Tylosaurus-AFC/old-phone-server.git
cd old-phone-server
```

## 2. Enable USB debugging on the phone

1. *Settings → About phone* → tap **Build number** 7 times ("You are now a developer").
2. *Settings → Developer options* → enable **USB debugging**.
   (On Android 4.4 *Developer options* is under *Settings → More*.)
3. Plug the phone into the PC, accept the "Allow USB debugging?" prompt (tick *Always allow*).
4. Check:

```bash
adb devices          # must list your phone as "device", not "unauthorized"
```

## 3. Find out what you have

```bash
adb shell getprop ro.product.cpu.abilist
adb shell getprop ro.build.version.release
```

| `cpu.abilist` contains | Debian to install (`ARCH`) |
|---|---|
| only `armeabi-v7a` (and maybe `armeabi`) | **`armhf`** (32-bit) |
| `arm64-v8a` | **`arm64`** |
| `x86`/`x86_64` | not tested here |

Android version tells you which root route and which boot launcher you will use
([02 · Root](02-root.md)). Once the phone is rooted, `tools/install.sh check` prints all of this
plus which battery-control files exist on your phone.

## 4. Create `config.sh`

```bash
cp config.example.sh config.sh
```

Open `config.sh` and set at least:

| Setting | What to put |
|---|---|
| `ADB` | `adb`, or on Windows the full path, e.g. `/c/Users/you/AppData/Local/Android/Sdk/platform-tools/adb.exe` |
| `ARCH` | `armhf` or `arm64` (table above) |
| `PHONE_IP` | the phone's Wi-Fi address; **reserve it in your router** (DHCP reservation) so it never changes |
| `USB_SERIAL` | the serial shown by `adb devices` (lets the scripts prefer USB over Wi-Fi) |
| `ROOT_MODE` | `su` (almost always) or `adbroot` (custom ROM with `adb root` but no `su`) |
| `BOOT_MODE` | `magisk`, `kingroot` or `initrc`: decided in [02](02-root.md) and [05](05-services-and-boot.md) |
| `BB_PATH` | `/data/debian/busybox-deb`, **except** on old Samsung kernels, see [03](03-install.md#3-busybox) |
| `TZ_NAME` | your time zone, e.g. `Europe/Madrid`, `America/Mexico_City` |

`config.sh` is git-ignored. Keep it that way.

> **Windows tip.** Run everything from *Git Bash*, not PowerShell or cmd. The scripts set
> `MSYS_NO_PATHCONV=1` so Git Bash does not rewrite `/data/...` paths into `C:/...`.

## 5. Make sure the tests pass on your machine (optional but cheap)

```bash
pip install requests
tests/run.sh
```

This checks the shell syntax of every script, exercises the battery logic against a fake
battery, and tests plugin loading/dispatch of the bot. No phone is needed.

Next: [02 · Root](02-root.md).
