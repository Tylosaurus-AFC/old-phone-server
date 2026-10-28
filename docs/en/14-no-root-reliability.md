# 14 · No-root mode: running 24/7 — limits, defences, checks

This page explains **what can stop a no-root server**, what the project does about each cause,
what you must do by hand, and how to check it. It complements [12 · No-root mode](12-no-root.md)
(the install guide).

**Honesty first.** Android is designed to stop background work to save battery. Without root
nothing can *guarantee* that Android or the phone maker will never stop Termux. What the project
can do is: ask for every exemption Android offers, re-apply those that get undone, notice when
something is stopped, bring it back when the system allows it, and tell you clearly when it
cannot. Only one phone (Realme 12+ 5G, Android 16) has been tested end to end; see the matrix below.

## Quick check: `doctor.sh`

```bash
tools/noroot-doctor.sh            # from the PC
~/server/doctor.sh                # or in Termux on the phone
```

It is read-only and lists each requirement as **OK**, **WARN** (works, less reliably or with a
feature missing) or **FAIL** (the server will not run or will not come back after a reboot), each
with what to do. First line: `RESULT: ok | degraded | broken`. The watchdog runs it every hour (the
first time 10 min after start) and the bot shows the worst problem in **`/salud`** ("Android/Termux")
and the full list in **`/diagnostico`**.

What it checks: Android version and CPU; Termux build (Google Play builds warned); boot hook,
`server.conf` syntax, Debian container and the bot's Python; token when the bot is enabled;
watchdog, bot service and heartbeat; `sshd`; free space; and through Shizuku: Termux:Boot installed
and **not in the "stopped" state** (never opened or force-stopped → no start at boot), Termux:API,
battery-optimisation exemption, background activity allowed, app standby bucket, the
phantom-process killer, the Termux wake lock and wireless debugging.

## What can stop the server, and what happens

| Cause | Detected by | Prevented by | Recovered automatically? | You must |
|---|---|---|---|---|
| **Doze / battery optimisation** freezes Termux with the screen off | doctor (via Shizuku) | Termux battery "Unrestricted"; the watchdog re-adds the Termux apps to the Doze whitelist and runs `dumpsys deviceidle disable` whenever Shizuku comes up and every 30 min | yes, once Shizuku runs | set "Unrestricted" once (step 2 of [12](12-no-root.md)) |
| **App standby bucket** "rare/restricted" limits jobs and network | doctor | watchdog sets bucket `active` every 30 min | yes, with Shizuku | — |
| **Background activity** denied (appop `RUN_ANY_IN_BACKGROUND`) | doctor | watchdog sets it to `allow` | yes, with Shizuku | — |
| **Phantom process killer** (Android 12+) kills Termux's background processes: more than 32 children *for all apps together*, or "excessive CPU" | doctor | 12L+: `settings_enable_monitor_phantom_procs=false` (also the developer option "Disable child process restrictions"); 12: `max_phantom_processes` raised. Re-applied every 30 min because Google Play services can reset the Android 12 value; the project does **not** disable Android's config sync, which would also stop RescueParty from undoing bad configs | yes, with Shizuku; on Android 12 there can be a few minutes after a reset | — |
| **CPU sleep** with the screen off | doctor (Termux wake lock held?) | `termux-wake-lock` at boot (a partial wake lock: CPU on, screen off) | — | keep the Termux notification; do not tap "release wakelock" |
| **Maker's own task killer** (Xiaomi, Huawei, Vivo, Oppo/Realme, Samsung…) | indirectly: watchdog/bot missing, `/historial` | vendor settings (see profiles below) | partly: guard.sh reopens Termux (tested on Realme) | apply your vendor's settings |
| **Termux swiped from recents / closed by Android** | guard.sh (no `sshd` for 2 min) | wake lock + exemptions | **yes with Shizuku**: guard.sh opens Termux; `~/.bashrc` restarts the server (Realme: 2 min 9 s). Re-running the boot hook no longer starts a duplicate watchdog loop | — |
| **Termux force-stopped** (Settings → Force stop) | guard.sh | — | yes, as above (Realme test) | — |
| **Termux:Boot force-stopped or never opened** | doctor (`stopped=true` / `notLaunched=true`) | — | **no**: Android delivers no boot event to a stopped app | open Termux:Boot once |
| **Normal reboot**, crash reboot, update reboot | `/historial` "el móvil se encendió" | Termux:Boot hook; Shizuku starts itself through wireless debugging: Android 13+ unattended; Android 11–12 only after you tap *Allow* (they forget allowed networks on reboot) | yes (Realme: bot at 54–104 s) | avoid automatic overnight system updates (they can change settings) |
| **Battery fully drained / phone off** | power-cut detection while running; nothing while off | keep it plugged in; maker's charge limit | **no**: most phones stay off (or in the charging screen) until the power button is pressed. Auto power-on needs an unlocked bootloader or a vendor option | press power; then everything above applies |
| **Wi-Fi / Internet lost** | watchdog every minute; bot loop | — | yes: bot waits and resumes; 5 min offline → Wi-Fi cycled (Shizuku or Termux:API) | check the router if it lasts |
| **Shizuku stopped** (rare; Wi-Fi off at boot, wireless debugging off) | watchdog event; doctor | guard.sh keeps wireless debugging on | the fork restarts itself when wireless debugging is on | open Shizuku and start it |
| **Storage full** | doctor (< 1 GB warn, < 300 MB fail); bot's `/salud` | bot skips updates below 300 MB free; temp downloads deleted at start | partly | free space |
| **Out of memory** (Android kills the biggest process) | `bot.sh` (crash event), heartbeat | — | yes: `bot.sh` restarts with back-off; watchdog relaunches `bot.sh` | if it repeats, fewer parallel downloads / plugins |
| **Bot frozen** | heartbeat older than 5 min | — | yes: killed and restarted | — |
| **Bot dead or crash-looping** (cannot report itself) | watchdog: heartbeat older than 15 min | — | relaunched by `bot.sh`/watchdog; **the watchdog sends you one Telegram message itself** (curl), retried every 10 min until confirmed | look if it does not come back |
| **Screen lock with PIN/password/pattern, then a reboot** (power cut, update) | doctor (lock type, when Android reports it) | use Swipe/None on a dedicated server phone | **no**: until the first unlock Android keeps app data encrypted and does not deliver the boot event; neither Termux nor Shizuku can start | unlock the phone after each reboot, or remove the secure lock |
| **Watchdog itself stopped** | the bot: Shizuku state file not updated for 15 min → alert | the boot loop relaunches `charge.sh` every minute | yes, unless Termux is gone (then guard.sh) | — |

## Shizuku: what can and cannot be recovered

Read from the sources of the thedjchi fork (2026) and of `rish`, and from Android's documentation:

* Shizuku's service is a process started through adb as the `shell` user: **it dies on every reboot**.
  With *start on boot* the fork queues a job that waits for Wi-Fi, switches `adb_enabled` and
  `adb_wifi_enabled` on itself (it needs `WRITE_SECURE_SETTINGS`, granted once from a PC), sets
  "adb authorisation timeout" off, finds the wireless-debugging **port by mDNS** and starts the service.
  No fixed IP or port is involved, so DHCP changes and the changing port do not matter.
* If the Wi-Fi network is **not yet authorised** for wireless debugging, Android switches it back off.
  When the phone is locked the fork waits for the next unlock; otherwise it retries later. Fix once: *Always
  allow on this network*.
* The fork has a **watchdog** (opt-in) that restarts the service if it crashes, and an exported
  `START` receiver protected by a secret (`auth`). With `SHIZUKU_AUTH` in `server.conf` the server's watchdog
  sends that broadcast (`shizuku.sh start`) when Shizuku is stopped: 2, 5, 10, 30 min apart then every
  30 min, never in the first 5 min after boot, never offline, and never for problems only the user can fix.
* What the server **cannot** do: re-enable wireless debugging or Shizuku without Shizuku (Termux has no
  permission to change those settings); authorise Termux in Shizuku; get past a PIN after a reboot. Then it
  detects, explains and alerts.
* The fork's author has paused its maintenance (README, 2026): if a future Android breaks it, the official
  Shizuku still works but only starts by hand after each reboot.

`shizuku.sh probe` tells the state from what `rish` prints; `/opt/bot/sys/shizuku` keeps it for the bot.
Shortest fix for each:

| State | Meaning | Shortest fix |
|---|---|---|
| `not-running` | app alive, service stopped | automatic with `SHIZUKU_AUTH`; else open Shizuku → Start (Wi-Fi on) |
| `app-unreachable` | the Shizuku app does not answer (frozen, force-stopped) | open Shizuku once; Battery → Unrestricted (the START broadcast also tries to wake it) |
| `not-authorized` | Termux not allowed | Shizuku → Authorized applications → Termux on |
| `awaiting-permission` | a permission dialog is waiting on screen | unlock, tap Allow |
| `dex-writable` | Android 14+ refuses a writable dex | `chmod 400 ~/server/rish_shizuku.dex` |
| `no-rish` | not set up | `tools/noroot-install.sh rish <folder>` |

While Shizuku is down the watchdog checks it every minute for 10 min, then every 5 min (each failed check
costs ~40 s of `rish` time-outs, which used to delay the rest of every pass).

## Automatic alerts (Telegram)

The bot evaluates the real state every 5 min and messages the owner **only when it changes**
(`bot/alerts.py`):

* **broken** — the server cannot do its main job: no Internet (TCP + DNS checked), < 300 MB free,
  yt-dlp/gallery-dl do not start (actually run, every 30 min), the no-root watchdog has stopped, a `FAIL`
  of `doctor.sh`. **degraded** — it works with limits: < 1 GB free, Shizuku down > 5 min (outside boot),
  ≥ 3 bot restarts in 6 h, ≥ 5 failed downloads in 1 h, a `WARN` of `doctor.sh`. **ok** — none confirmed.
* A problem counts after 2 checks and 5 min (broken) / 10 min (degraded): one-minute blips are ignored.
  Everything new in a check goes in **one** message with the impact and what to do; level changes and
  recoveries (after 5 min absent) are announced once; broken problems are reminded every 12 h.
* A message counts as delivered only when Telegram returns its id. If Telegram (or Internet) is down,
  retries back off (1, 2, 5, 10, 30 min) and no stale queue builds up: the next message tells the current
  state, how late it is and what happened and was solved meanwhile. `/salud` shows the channel state.
* The state is saved on disk, so a restart repeats nothing. Texts pass through the same filter as
  `/diagnostico` (no tokens, IDs, IPs).
* When the **bot itself** is dead, the no-root watchdog sends one message by curl (see the table above;
  `BOTDOWN_ALERT=0` turns it off).

What if Telegram is the thing failing? The server keeps working and keeps a record (`/historial`); it never
claims a message was delivered without Telegram's confirmation; once Telegram answers, one catch-up
message arrives. A second channel for that case is evaluated in [15](15-whatsapp-evaluation.md).

### proot compared with root's chroot

proot intercepts system calls with `ptrace`: it works without root but adds overhead per system
call (not noticeable on the tested phone), cannot use real `mount`, raw sockets or hardware access,
and everything runs inside Termux's app process tree — so **everything above that can stop Termux
stops Debian too**. With root (chroot) the server is started by the system itself and Android's app
killers do not apply. If a phone can be rooted, root mode remains the most robust option.

### Alternatives evaluated

| Option | Verdict |
|---|---|
| **proot-distro (current)** | Kept. Same Debian and the very same `bot.py` as root mode, tested on a real phone. Its weak point is Android killing Termux, which the defences above address. |
| Termux packages only (no Debian) | Possible later: no proot overhead and fewer processes, but a second set of dependencies (Termux's Python, ffmpeg, yt-dlp) to keep working, and other paths. Not worth it without evidence that proot itself is a cause of outages. |
| Android's Linux terminal / Virtualization Framework (Android 15+) | A real Debian VM, but only on a few phones (Pixel) and new; the goal of this project is *old* phones. To revisit. |
| Wireless adb to itself instead of Shizuku | Rejected: Android disables wireless debugging when the phone changes access point (documented in [12](12-no-root.md)); Shizuku's service survives it. |
| Disable Android's config sync (`set_sync_disabled_for_tests persistent`) | Rejected: it also stops RescueParty/rollbacks from undoing bad configurations. Re-applying the value is enough. |

## Vendor profiles

Settings names change between versions and models. **Only Realme was verified by this project**; the
rest are the usual names reported by the community (see your brand on
[dontkillmyapp.com](https://dontkillmyapp.com)) and are **not verified**. Apply them to Termux,
Termux:Boot, Termux:API and Shizuku.

| Maker | Usual settings (not verified unless stated) |
|---|---|
| All | Battery → Unrestricted; disable automatic overnight system updates; Developer options: wireless debugging on, "Disable adb authorization timeout"; Android 14+: "Disable child process restrictions" |
| **Realme / OPPO / OnePlus (ColorOS) — verified on Realme 12+** | Battery → power saving settings: standby optimisation off; Developer options → "Disable permission monitoring" on; set the charge limit in Battery health; `OEM=oplus` in `server.conf` |
| Samsung (One UI) | Battery → background usage limits: add the apps to "Never sleeping apps"; "Put unused apps to sleep" off |
| Xiaomi / Redmi / POCO | App info: "Autostart" on; battery saver "No restrictions"; lock Termux in recents |
| Huawei / Honor | App launch: manage manually, allow auto-launch, secondary launch and run in background |
| Vivo / iQOO | Battery: allow high background power consumption; allow auto-start |
| Google Pixel / stock Android | Battery → Unrestricted is usually enough |

## Compatibility and reliability matrix

Classes: **V** verified on a real phone · **S** verified by automated tests/simulation only ·
**D** expected from Android/Termux documentation, pending physical validation · **N** not supported or
not guaranteed.

| Capability | Android 7–10 | Android 11 | Android 12 | Android 12L–15 | Android 16 (Realme 12+, arm64) |
|---|---|---|---|---|---|
| Termux + proot Debian, bot runs | D | D | D | D | **V** |
| Start after reboot (Termux:Boot) | D | D | D | D | **V** |
| Shizuku starts by itself at boot | N (manual start each boot) | N (tap *Allow* after each reboot) | N (tap *Allow* after each reboot) | 12L: N; 13–15: D | **V** |
| guard.sh reopens a closed Termux | N without Shizuku | D | D | D | **V** |
| Keep-alive settings re-applied, read back | N without Shizuku | S | S | S | S (new; physical test pending) |
| Shizuku state detection, restart via START intent | N (Android < 11: no wireless debugging) | S | S | S | S (physical test pending) |
| State-change alerts / bot-down message | S | S | S | S | S (physical test pending) |
| Starts after a reboot with a PIN lock, before unlock | N | N | N | N | N |
| Phantom killer handled | not needed | not needed | S (limit re-applied) | S (setting) | S |
| `doctor.sh` / `/salud` line | S | S | S | S | S (physical run pending) |
| Single watchdog loop when Termux reopens | S | S | S | S | S |
| Recovery after battery fully drained | N | N | N | N | N |
| ARMv7 (32-bit) phones | D | D | D | D | — |

## Reproducible tests on real hardware

A test lasting seconds proves nothing about 24/7. Record, for each test: phone, Android, Termux
versions, `doctor.sh` output before and after, start/end time, and the bot's `/historial`.

| Test | How | Pass if |
|---|---|---|
| Screen off, long | plugged in, screen off ≥ 12 h (ideally 72 h); send a link every few hours | every link answered; `/historial` shows no "colgado"/"caida" without cause; doctor still `ok` |
| Wake-lock cost | `adb shell dumpsys batterystats --reset`, 12 h screen off on charger, then `dumpsys batterystats \| grep -i termux` | partial wake lock time ≈ the period (expected) and no unexpected screen-on wake locks |
| Reboot | `/reiniciar confirmar` and a power-button reboot | SSH and bot back without touching the phone; time noted |
| Termux closed | swipe from recents; and Settings → Force stop | back within ~3 min (guard.sh) |
| Termux:Boot stopped | force-stop Termux:Boot, run doctor | doctor FAILs with "open the Termux:Boot app once" |
| Keep-alive undone | `adb shell dumpsys deviceidle whitelist -com.termux`; wait ≤ 30 min | doctor `ok` again without touching anything |
| Phantom killer | Android 12+: set `settings_enable_monitor_phantom_procs` back to `true`; wait ≤ 30 min | value `false` again |
| Network | router off 10 min | "sin conexión de … a …" reported; downloads resume |
| Storage | fill the phone to < 300 MB free | doctor FAIL; bot skips updates; no crash loop |
| Memory | open heavy apps while downloading | bot restarted by `bot.sh` if killed; no lost settings |
| Shizuku restart | in Shizuku, Stop; wait ≤ 3 min with `SHIZUKU_AUTH` set | `/historial` shows the start request and "Shizuku disponible" |
| Shizuku after reboot, new network | reboot on a Wi-Fi not yet authorised for wireless debugging, screen locked | doctor/alert says Shizuku down; after unlocking and "Always allow", it starts |
| Alerts | stop the router 20 min | one "falla algo importante" message after Internet returns ("Aviso con retraso"), then one "Resuelto" |
| Bot dead | make it unable to start for 20 min: rename `/opt/bot/bot.py` to `bot.py.off` (a frozen bot does not count: it is restarted after 5 min) | one message from the watchdog; rename back, the bot reports the restarts |
| Power cut | unplug for an hour with the bot running | the power cut appears in `/historial` and `/bateria`; everything keeps running on battery |

## Turning the automatic settings off

`KEEPALIVE=0` in `~/server/server.conf` stops the watchdog from re-applying the keep-alive settings
(it does not undo them: use Settings, or `dumpsys deviceidle whitelist -com.termux`,
`settings delete global settings_enable_monitor_phantom_procs`,
`device_config delete activity_manager max_phantom_processes`).
