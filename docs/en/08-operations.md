# 08 · Operations: update, back up, restore, fix

Day-to-day commands, run from the repository on your PC.

| Task | Command |
|---|---|
| Push new code / settings / plugins and restart | `tools/deploy.sh` |
| Enable / disable the bot on this phone | `tools/enable-bot.sh` · `tools/enable-bot.sh off` |
| Edit the phone's settings | `tools/edit-conf.sh` |
| Back up configuration + secrets (to `backup/`, never commit) | `tools/backup.sh` |
| Restore that configuration | `tools/restore-config.sh backup/<date>` |
| Copy the whole Debian (no secrets) | `tools/make-image.sh` |
| Restore the whole Debian (new/damaged phone) | `tools/restore-full.sh backup/image-<date> [--force]` |
| Look at what is happening | `/salud`, `/historial`, `/bateria`, `/estado` in Telegram |

## No-root mode equivalents

| Root mode | No-root mode |
|---|---|
| `tools/deploy.sh` | `tools/noroot-deploy.sh` |
| `tools/enable-bot.sh [off]` | `tools/noroot-bot.sh enable\|disable` |
| `tools/set-token.sh`, `tools/set-api.sh` | `tools/noroot-bot.sh token\|api` |
| `tools/edit-conf.sh` | `ssh phone nano ~/server/server.conf` |
| `tools/backup.sh` / `restore-config.sh` | `tools/noroot-backup.sh` / `noroot-restore.sh` |
| `tools/make-image.sh` / `restore-full.sh` | `proot-distro backup bot` / `proot-distro restore` (in Termux) |
| `adb connect <ip>:5555` | `ssh phone`, and `tools/noroot-adb.sh` for wireless adb |

Backups are interchangeable between modes. **Migrating** (e.g. from a rooted old phone to a no-root modern one):
make a fresh backup on the old phone while it still runs → switch the bot **off** there → `tools/noroot-restore.sh
backup/<date>` on the new one (it copies token, API keys, cookies, owners, followed channels, cache, MTProto session,
likes/Last.fm state… and starts the bot) → check `/estado`, `/salud` and one link.

## Updating

* **yt-dlp / gallery-dl** update themselves every 24 h and on `/actualizar`. Sites change often;
  most "it stopped downloading" problems end here. If an update breaks something, pin the
  previous version inside the chroot:
  `adb shell su -c "/data/debian/enter.sh '/opt/bot/venv/bin/pip install yt-dlp==<version>'"`.
* **This project:** `git pull`, then `tools/deploy.sh`. It copies the files, byte-compiles them
  **on the phone** (a syntax error stops the deploy before the bot is touched), then kills
  `bot.sh` and `charge.sh` so each relaunches the other with the new code (~30–60 s).
* **Debian:** `adb shell su -c "/data/debian/enter.sh 'apt-get update && apt-get -y upgrade'"`.
  Do this occasionally; make an image first if you are nervous.

## Backups: what, why, how often

| What | Command | Contains | Keep it… |
|---|---|---|---|
| Configuration | `tools/backup.sh` | token, API keys, cookies, owners, followed channels, cache, `server.conf`, the Android-side files you changed, the list of disabled apps | **private** — it holds secrets |
| Whole Debian | `tools/make-image.sh` | the complete chroot (bot, venv, Whisper…) **without** secrets | shareable; about 1–1.5 GB |
| Code | git | this repository | public |

Repeat `backup.sh` after renewing cookies or changing anything, and the image after big changes.
`/salud` warns when the last backup is older than 30 days.

### Restoring

* **Lost configuration:** `tools/restore-config.sh backup/<date>` then `tools/deploy.sh`.
* **Damaged Debian:** `tools/restore-full.sh backup/image-<date> --force` (moves the broken one to
  `fs.old`), then `tools/install.sh scripts`, `tools/restore-config.sh …`, `tools/deploy.sh`.
* **Moving to another phone:**
  1. root it, set up `config.sh`, install busybox (`tools/install.sh busybox`), install the boot launcher
     (`tools/install.sh boot`), then `tools/restore-full.sh` (same CPU architecture) —
     or do a fresh install ([03](03-install.md)) if the architecture differs (the bot is pure
     Python and runs unchanged on arm64; only whisper.cpp must be recompiled);
  2. `tools/restore-config.sh backup/<date>`, adjust `server.conf` (battery driver differs per phone);
  3. **old phone first:** `tools/enable-bot.sh off`, *then* `tools/enable-bot.sh` on the new one.

## Troubleshooting

**The bot does not answer in Telegram.** First, the automatics: a frozen bot is killed after 5 min,
a crashed one is relaunched with growing delays, a dead `bot.sh` is relaunched by `charge.sh`
within a minute. Look at `/historial` when it comes back. If it stays silent:

1. Is the phone on, charged, on Wi-Fi? `ping <phone IP>`
2. `adb connect <phone IP>:5555` (or USB).
3. `adb shell su -c "tail -n 40 /data/debian/fs/opt/bot/service.log"`
4. Restart only the bot: `adb shell su -c "<busybox> pkill -f opt/bot/bot.py"` (`bot.sh` relaunches in 10 s).
   If there is no `bot.sh`: `tools/enable-bot.sh`.
5. Restart the phone: `/reiniciar confirmar`, or `adb reboot`.

**Telegram error 409 in `bot.log`.** Two instances use the same token (another phone, or a
leftover process). Disable the bot everywhere but one place.

**Cannot connect with adb over Wi-Fi.** [07 · Network](07-network.md), "Recovery ladder".

**A change broke the bot.** `git log --oneline` → `git checkout <good commit> -- bot/ phone/` →
`tools/deploy.sh`. Python packages: reinstall the versions in `bot/requirements.txt`.

**The phone does not start the server after a reboot.** Read `/data/debian/boot.log` (did
`start.sh` run?). KingRoot: check that `grep server-boot /system/bin/ddexe` still shows the hook.
Magisk: check that `/data/adb/service.d/server.sh` exists and is executable, and that no module
manager disabled `service.d`. A ROM update can remove all of it.

**RAM keeps shrinking.** Check `/estado`: the bot's own RSS should be 20–230 MB (more than ~100 MB
sustained at idle suggests a leak). Linux uses spare RAM as file cache; "available" matters, not "free".

**An app or the ROM updated itself.** Updating Android on a rooted phone usually removes root.
On a locked-bootloader phone this may be unrecoverable. Turn off automatic system updates
and do not install an OTA.

**Losing root.** With KingRoot on a locked bootloader: assume permanent. With an unlockable
bootloader: re-patch the boot image with Magisk. A stock-firmware reflash always restores the
phone itself.

**Undo everything:** `tools/enable-bot.sh off`, remove the boot launcher, delete `/data/debian`
(unmount `/data/debian/fs/{proc,sys,dev,dev/pts,dev/shm,sdcard}` first or reboot — deleting with
bind mounts active also deletes the phone's real `/dev` and storage contents!), re-enable the
apps you disabled (`pm enable <package>`; the list is in `backup/<date>/android/disabled-apps.txt`).

Next: [09 · Plugins](09-plugins.md).
