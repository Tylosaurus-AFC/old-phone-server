# 13 · Media-server recipes (optional)

An old phone with a USB disk makes a perfectly good **NAS and media server** next to the bot.
These are recipes from the Realme 12+ install ([12 · No-root mode](12-no-root.md)), kept apart
because they are optional and device-flavoured. They live in
[`phone/noroot/extras/`](../../phone/noroot/extras/) and are started and supervised by the
no-root `charge.sh` through two settings in `~/server/server.conf`:

```sh
SERVICES="webdav dlna jellyfin"      # started when a USB disk is mounted, relaunched if they die
NIGHTLY="youtube-mirror.sh 3"        # once a day at 04:00
WEEKLY_BACKUP=1                      # Sundays 04:00: extras/backup.sh
```

`touch ~/server/no-<name>` switches one off without editing anything (`no-nightly` for the job).
Logs: `~/server/svc/<name>.log`. The root-mode phone can do the same by hand; there is no automatic
supervision for these in root mode.

> **LAN only.** WebDAV is plain HTTP with one shared password. Never forward these ports on your
> router.

## The USB disk

* A phone with USB-OTG and a powered hub (or a self-powered disk). Android mounts it as
  *public* storage; Termux sees it at `/storage/<UUID>` and `enter.sh` mounts it inside Debian at
  **`/mnt/disk`** (`charge.sh` finds the UUID with `sm list-volumes public`). `charge.sh` also leaves a
  `.nas` file in the disk's root: the mirror, the backup and the bot's `/guardar` only write when it is
  there, so with the disk unplugged they never fill the phone's own storage. Do not delete it.
* **Format it exFAT**, not NTFS: Android mounts exFAT with the kernel driver (NTFS goes through
  `ntfs-3g`/FUSE) and Windows, macOS, TVs and most devices read it. From the shell user
  (`~/server/sa.sh "sm list-disks; sm partition disk:<id> public"` — **this erases the disk**).
* Measured on a 2.5" disk behind a USB 2.0 adapter: exFAT write **38 MB/s** (the USB 2.0 ceiling),
  read ~57 MB/s, ~850 small files/s written; NTFS via FUSE wrote 36.5 MB/s; the phone's internal
  storage, 548 MB/s.

## NAS: WebDAV

`extras/webdav.sh` serves the disk with `rclone serve webdav` on port **8080**.

```bash
pkg install rclone                                   # in Termux
mkdir -p ~/.config/server && echo 'a-long-password' > ~/.config/server/webdav.pass
# server.conf:  SERVICES="webdav"      (user name: WEBDAV_USER, default "webdav")
```

From your PC: Windows *Map network drive* with `http://<phone-ip>:8080`, or any WebDAV client.
Measured over Wi-Fi: **~19 MB/s upload, ~12 MB/s download** (SFTP through `ssh phone`: 10–16 MB/s).

## DLNA

`extras/dlna.sh` (`rclone serve dlna`, name `DLNA_NAME`, default "Phone server", HTTP port 7879,
SSDP discovery on UDP 1900, read-only). It answers over HTTP. **Discovery by a TV/VLC was not
confirmed**: from the PC no SSDP answer arrived (from any device), probably the Windows firewall.
Test from the TV itself.

## Jellyfin

`extras/jellyfin.sh` runs Jellyfin (web UI + apps, port **8096**) *inside the Debian container*, with
data and cache in internal storage (`/opt/jellyfin`). Install it in the container following Jellyfin's
own instructions for Debian (their apt repository: `jellyfin` + `jellyfin-ffmpeg`); on the Realme it was
Jellyfin 12.2 on arm64.

* It starts in ~20 s. First time: open `http://<phone-ip>:8096`, run the wizard, add a library pointing at
  `/mnt/disk`.
* Transcoding 1080p → 720p ran at 1.2× real time: one stream at a time. Prefer direct play (H.264, which
  the mirror below produces).

## Weekly backup

`WEEKLY_BACKUP=1` runs `extras/backup.sh` on Sundays at 04:00 (or run it by hand): the bot's settings and
secrets (token, cookies, owners, followed channels, `bot.db`…) to `/mnt/disk/Backups/bot-YYYYMMDD.tgz`,
keeping the last 8. It holds the token, so the WebDAV and DLNA recipes do **not** serve `Backups/`.

## YouTube mirror

`extras/youtube-mirror.sh [N]` downloads the newest N videos of every channel the bot follows
(`/opt/bot/subs.json`) to `/mnt/disk/YouTube/<channel>/<date> - <title> [<id>].mp4` (+ thumbnail):
H.264 ≤ 1080p ≤ 30 fps (an Apple TV 3 cannot play 60 fps), no Shorts, no live streams. It keeps the 10
newest per channel (`KEEP=N`) and deletes older ones; they stay in `.archive.txt` so they are never
fetched again. Test run on three channels, 2 videos each: **6 videos, 9.6 GB in 48 minutes**. Run it by hand
or with `NIGHTLY="youtube-mirror.sh 3"`.

## AirPlay to an old Apple TV (untested against a real Apple TV)

`extras/airplay.sh scan` / `airplay.sh <apple-tv-ip> <path-on-disk>` serves one folder over HTTP and plays it with
[pyatv](https://pyatv.dev) (`python3 -m venv /opt/airplay && /opt/airplay/bin/pip install pyatv` inside the
container). pyatv 0.18 installed and ran; the Apple TV used for testing was switched off, so playback itself
is unverified.

## USB hubs: what went wrong

A USB-C hub charged the phone in host mode (`power_role=sink`, `data_role=host`), but with **Ethernet + disk +
charging together it dropped twice** (once fully, once only the data), and the **Ethernet adapter negotiated
only 10 Mbit/s** (8 Mbit/s real, 350 ms ping). Android prefers the cable, so the bot went out to the Internet at
8 Mbit/s until the Ethernet was removed. Without the Ethernet, the disk and the charging stayed stable.
Untested fixes: another cable or switch port, a self-powered disk, or a hub with its own power supply.
Lesson: measure `/velocidad` after plugging in anything that takes over the default route.
