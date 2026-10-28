# 16 · Shizuku without root — audit, compatibility and recovery matrix

October 2026. Evidence tags: **[src]** read in the source code (repository and version named),
**[wiki]** the fork's own wiki, **[doc]** Android documentation, **[sim]** covered by an automated test
with fakes (not a phone), **[V]** verified on a real phone (only what the project's guide already reported
for the Realme 12+ 5G, Android 16, fork 13.7.0). Nothing in this page was verified on a phone during this
audit.

## Which Shizuku

| | Official Shizuku | thedjchi fork |
|---|---|---|
| Source | [RikkaApps/Shizuku](https://github.com/RikkaApps/Shizuku) — last release **v13.6.0 (2025-05-25)**, last commit 2025-06-18 [src] | [thedjchi/Shizuku](https://github.com/thedjchi/Shizuku) — releases `v13.6.0.rNNNN-thedjchi` … **v13.7.0-thedjchi**; last commit 2026-07-14; the author has paused maintenance [src] |
| Package name | `moe.shizuku.privileged.api` | **the same** `moe.shizuku.privileged.api` [src] |
| How to tell them apart | `versionName` like `13.6.0.r<commits>.<hash>` | `versionName` ends in `-thedjchi` [src]; different signing key, so one must be uninstalled before installing the other |
| `versionCode` | number of git commits (`gitCommitCount`) [src] | same scheme, different numbers [src] |
| Start methods | root; wireless debugging (Android 11+); PC adb | the same, plus **TCP mode** (`adb tcpip` equivalent) [src][wiki] |
| Start at boot without root | **Android 13+** and `WRITE_SECURE_SETTINGS` granted: one attempt at `LOCKED_BOOT_COMPLETED`/`BOOT_COMPLETED`, switches wireless debugging on, waits **3 s** for the port by mDNS, no Wi-Fi wait, no retry [src v13.6.0 `BootCompleteReceiver`] | Android 11+ and `WRITE_SECURE_SETTINGS`: a WorkManager job after `BOOT_COMPLETED` that **waits for Wi-Fi**, switches wireless debugging on, finds the port by mDNS (15 s), **retries** [src `AdbStartWorker`]; "may take a few minutes" [wiki] |
| Before the first unlock | its boot receiver is `directBootAware` (it may start Shizuku before unlock) [src] | only after unlock (`BOOT_COMPLETED`) [src] |
| Watchdog (restart if the service dies) | no | yes, opt-in foreground service [src][wiki] |
| Intents for other apps | none to start it | exported `ManualStartReceiver`, action `moe.shizuku.privileged.api.START` (and STOP), extra `auth` = a secret shown under *View intents* [src] |

**Consequence for this project**: automatic restart by the server (`SHIZUKU_AUTH`, `shizuku.sh start`) only
exists with the fork. The watchdog now records which variant it sees (`variant=` in `/opt/bot/sys/shizuku`)
and never sends START to the official app [sim]; `doctor.sh` names the variant and its limits [sim].

## Three different operations

1. **Starting Shizuku's service without root** — Shizuku connects to the phone's own adb daemon
   (wireless debugging, or `adb` from a PC) and runs its server as the `shell` user. Needs: wireless
   debugging paired once (pairing code), or a PC. The service is a process: it **dies on every reboot**, when
   USB debugging or developer options are switched off, and — reported by the fork — when the USB mode
   changes (Android Auto by cable, changing USB mode) [wiki].
2. **Getting it back after a reboot** — someone must start it again: the app at boot (above), the fork's job
   or watchdog, the server's START request (fork), or the user. Conditions: Android 11+ (fork) / 13+
   (official), `WRITE_SECURE_SETTINGS`, Shizuku last started through adb (not root), Wi-Fi up, and the
   network **authorised** for wireless debugging.
3. **Re-enabling / re-authorising wireless debugging** — switching it on is a setting
   (`adb_wifi_enabled`): Shizuku with `WRITE_SECURE_SETTINGS` can do it [src], Termux cannot (no permission).
   **Authorising a network** ("Always allow on this network") is a dialog that only a person can answer.
   Android 11–12 forget allowed networks on every reboot; Android 13 fixed it (AOSP change 2128832, cited in
   both apps' sources; the fork warns about it) [src]. Re-pairing after "Revoke USB debugging authorisations"
   or a reset also needs a person.

## Permissions

| Permission / setting | Granted how | Survives reboot? | Notes |
|---|---|---|---|
| `WRITE_SECURE_SETTINGS` for Shizuku | once from a PC: `adb shell pm grant moe.shizuku.privileged.api android.permission.WRITE_SECURE_SETTINGS` [wiki] | yes: a granted development permission stays until uninstall or "clear data" (Android's permission model; not verified on the Realme) | MIUI needs "USB debugging (Security settings)"; ColorOS/Realme needs "Disable permission monitoring" [wiki] |
| Termux authorised in Shizuku | Shizuku → Authorized applications | yes (stored by Shizuku) | revoking it gives rish "Permission denied" [src] |
| adb authorisation timeout off | Developer options → "Disable adb authorization timeout", or Shizuku sets `adb_allowed_connection_time=0` when it starts with `WRITE_SECURE_SETTINGS` [src] | yes (a global setting) | otherwise adb keys not used for days expire and the next start fails [wiki] |
| Battery: Shizuku unrestricted, background allowed | Settings, or `cmd appops set moe.shizuku.privileged.api RUN_IN_BACKGROUND/RUN_ANY_IN_BACKGROUND allow` [wiki] | usually; OEMs may reset | the watchdog re-applies them through Shizuku every 30 min [sim] |

Termux, Termux:Boot and Termux:API are built with **targetSdk 28** [src termux-app/boot/api
`gradle.properties`]: Android 14–16 restrictions keyed to a newer targetSdk (foreground-service types,
boot-time foreground-service limits of Android 15) do not apply to them; Doze, App Standby, the
phantom-process killer and OEM killers do. Termux:Boot is not `directBootAware`: nothing of the server runs
before the first unlock [src].

## Recovery matrix

"Auto" = recovered without a person, when the listed conditions hold.

| Scenario | Detected by | Auto-recovered? | Minimum user action |
|---|---|---|---|
| Normal reboot, Android 13–16, fork, WSS granted, network authorised | watchdog (`state=`), `/historial` | **yes** — fork job after Wi-Fi [src]; [V] on Realme Android 16 (bot at 54–104 s) | — |
| Normal reboot, Android 13–16, official v13.6.0 | same | **one attempt only**; fails if Wi-Fi is not up within seconds of boot [src] | open Shizuku → Start |
| Normal reboot, Android 11–12(L) | same | **no**: the network must be re-allowed on every reboot [src] | unlock, tap **Allow**; Shizuku then starts |
| Reboot with PIN/pattern/password, before first unlock | nothing can run (Termux data encrypted) | **no** [doc] | unlock once |
| Shizuku service crashed / stopped | `shizuku.sh probe` → `not-running` [sim] | fork: its watchdog [src], and the server's START with `SHIZUKU_AUTH` (2, 5, 10, 30 min…) [sim]; official: no | official: open Shizuku → Start |
| Shizuku stopped on purpose by the user | same | the fork's watchdog/our START would restart it [wiki] | stop it with the STOP intent and `touch ~/server/no-shizuku-restart` [sim] |
| Shizuku app frozen / force-stopped | rish "Request timeout" → `app-unreachable` [sim] | START broadcast sent with `--include-stopped-packages` may wake it (fork) — unverified | open Shizuku once; battery unrestricted |
| Termux not authorised in Shizuku | rish "Permission denied" → `not-authorized` [sim] | no | Shizuku → Authorized applications → Termux |
| Permission dialog waiting on screen | rish hangs after "Entering shell" → `awaiting-permission` [sim] | no | unlock, tap Allow |
| Wireless debugging switched off (user, or Android after a network change) while Shizuku runs | doctor (`adb_wifi_enabled`), guard.sh | guard.sh (runs as the `shell` user, started through Shizuku) switches it back on every minute **while guard.sh itself is alive** [src of this project]; whether guard.sh and a running Shizuku service survive the switch-off is **unverified** | — |
| Network / IP / port change | — | the port is found by mDNS each start, no fixed IP or port [src]; a **new, not yet allowed network** blocks the start; on locked phones the fork waits for unlock [src] | allow the new network once |
| adb authorisation lost (revoked, expired, reset) | start fails silently in Shizuku; probe → `not-running` | no | re-pair Shizuku with wireless debugging |
| USB mode change (cable to a PC/hub, Android Auto) | probe → `not-running` | fork watchdog / our START [wiki][sim] | set *Default USB configuration* to "Charging only" |
| Termux stopped or killed | guard.sh (no `sshd` 2 min) | **yes with Shizuku**: guard.sh reopens Termux [V on Realme: 2 min 9 s] | — |
| Termux:Boot never opened / force-stopped | doctor (`stopped=`/`notLaunched=`) [sim] | **no** [doc] | open Termux:Boot once |
| `WRITE_SECURE_SETTINGS` missing | doctor (`dumpsys package`) [sim] | no | the `pm grant` command from a PC |
| Battery restrictions on Termux or Shizuku | doctor [sim] | re-applied every 30 min while Shizuku works [sim]; a refusal is reported once | Settings → Battery → Unrestricted |

By Android version:

| | Android 11 | Android 12–12L | Android 13–14 | Android 15–16 |
|---|---|---|---|---|
| Wireless debugging (Shizuku without PC) | yes | yes | yes | yes |
| Unattended start after reboot | no (tap Allow) | no (tap Allow) | fork: yes; official: one attempt | fork: yes [V Realme 16]; official: one attempt |
| Phantom-process killer | — | 12: limit (re-applied); 12L: setting | setting | setting; developer option "Disable child process restrictions" (14+) |
| Verified on a phone | — | — | — | Realme 12+ 5G, Android 16, fork 13.7.0 (project's guide) |

## What to collect on a phone (read-only, safe to share)

From a PC with adb (USB or wireless). These print versions and states only; **do not share**
`SHIZUKU_AUTH`, pairing codes, IP addresses, serial numbers or adb keys.

```bash
adb shell getprop ro.build.version.release; adb shell getprop ro.build.version.sdk
adb shell getprop ro.build.display.id                      # ROM build, e.g. RMX3867_...
adb shell "dumpsys package moe.shizuku.privileged.api | grep -E 'versionName|versionCode|WRITE_SECURE_SETTINGS'"
adb shell cmd appops get moe.shizuku.privileged.api RUN_ANY_IN_BACKGROUND
adb shell "dumpsys deviceidle whitelist | grep -E 'shizuku|termux'"
adb shell settings get global adb_wifi_enabled
adb shell settings get global adb_allowed_connection_time
adb shell "dumpsys package com.termux.boot | grep -E 'versionName|stopped=|notLaunched='"
adb shell "dumpsys package com.termux | grep -E 'versionName|targetSdk'"
```

With the server installed from the development branch, `tools/noroot-doctor.sh` shows most of this. Then,
to check recovery (each step reversible): (1) in Shizuku tap Stop, wait 3 min, run the doctor; (2) reboot
with the screen lock you normally use, note when Shizuku and the bot come back, unlock if needed;
(3) switch wireless debugging off for 2 min and see whether Shizuku and guard.sh recover.
