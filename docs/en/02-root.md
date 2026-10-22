# 02 · Root

> **This is the riskiest step of the whole project, and the one this repository cannot automate.**
> Rooting is different for every model. It can erase the phone, void the warranty, and in the
> worst case leave it unbootable. Do it only on a phone you can afford to lose. This guide
> tells you which route to pick and what to check; the actual rooting instructions for your
> model live in its own community threads (XDA, the LineageOS wiki, the Magisk docs).

The rest of the project needs only one thing from this step: **a root shell that can run
`chroot`, `mount` and write to `/sys`**, reachable with `adb`.

## Choose a route

```
Can you unlock the bootloader?
(Settings → Developer options → "OEM unlocking", then the vendor's fastboot/download-mode procedure)
│
├─ YES ─► Does LineageOS (or another current ROM) support your model?   see wiki.lineageos.org
│          ├─ YES ─► flash it  ─► then Magisk (route A)          ← best: current Android, no vendor bloat
│          └─ NO  ─► keep the stock ROM, patch its boot image with Magisk (route A)
│
└─ NO (carrier-locked, e.g. many US Samsung/Verizon phones)
           ─► an exploit-based root that works on that exact firmware (route B)
```

### Route A — Magisk (recommended whenever possible)

[Magisk](https://github.com/topjohnwu/Magisk) is open source and the standard way to root a
phone whose bootloader can be unlocked. The generic procedure (read the official
[installation guide](https://topjohnwu.github.io/Magisk/install.html) first):

1. Unlock the bootloader (**wipes the phone**).
2. Get your firmware's boot image (`boot.img`, or `init_boot.img` on newer devices), patch it
   with the Magisk app, flash it back (`fastboot flash boot` / Odin for Samsung).
3. Open Magisk once. In *Superuser*, make sure **"Apps and ADB"** (shell) is allowed.

Used here on a Galaxy Tab A7 (LineageOS 23 / Android 16 + Magisk 30.7). Boot launcher:
`BOOT_MODE=magisk`.

### Route B — exploit-based root on a locked bootloader

This is how the Galaxy S4 mini (Verizon, Android 4.4.2, locked bootloader) was done, with
**KingRoot**. Be clear-eyed about it:

* KingRoot is **closed-source** and has a history of phoning home and installing extras. Use it
  **only on a wiped phone dedicated to this**, signed into **no** personal account, ever.
* **Never update Android, never uninstall KingRoot, never swap it for another root manager**
  on a locked-bootloader phone. If you lose root there may be no way back to root.
  A stock-firmware reflash (Odin) rescues the phone itself, but you may not be able to root it again.
* Check KingRoot's success on *your exact firmware/build* before relying on it.

Boot launcher: `BOOT_MODE=kingroot`.

### Route C — custom ROM with `adb root` (no `su`)

A LineageOS **userdebug** build gives `adb root` instead of a `su` binary. Used here on a
Moto X2 (LineageOS 18.1, Android 11, bootloader unlocked). Set `ROOT_MODE=adbroot` and
`BOOT_MODE=initrc`. Caveats: you must run `adb root` after each reboot (the scripts do it),
and `/` must be remounted writable to install files.

## Check that you have root

```bash
adb shell su -c id          # ROOT_MODE=su:     expect  uid=0(root) ...
adb root && adb shell id    # ROOT_MODE=adbroot: expect  uid=0(root) ...
```

With Magisk the first command pops a "Grant superuser to Shell?" prompt **on the phone's
screen**: accept it (tick *Remember*).

## Then, de-bloat (optional, do it later)

A server needs none of the preinstalled apps. Disabling them frees 300–500 MB of RAM
(measured: 698 MB → 1050 MB available on the tablet) and makes timings stable. But do it
**after** everything else works, one batch at a time, rebooting between batches:
[`phone/extras/debloat-candidates.txt`](../../phone/extras/debloat-candidates.txt) lists safe
candidates and the packages you must never disable (notably `com.android.permissioncontroller`:
disabling it made `system_server` crash-loop at boot on the Moto X2).

## If you cannot root

Plenty of phones cannot be rooted: carrier-locked bootloaders with no public exploit, vendors that no
longer unlock (the Realme 12+ used for the no-root mode has a locked bootloader and Realme offers no
"Deep Testing" unlock app for it; the root attempt failed). **That is not the end of the road:**
[12 · No-root mode](12-no-root.md) runs the same Debian and bot in Termux, using Shizuku for the few system
powers needed. You lose charger control (the maker's own limiter does that job) and the support for
Android older than ~11, and keep everything else.

Next: [03 · Install](03-install.md) (root mode), or [12 · No-root mode](12-no-root.md).
