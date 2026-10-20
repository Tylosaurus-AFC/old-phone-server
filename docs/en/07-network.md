# 07 · Network

Most "the server vanished" problems are network problems, and old Android has several
particular ones. This page collects them.

## The basics

* **Reserve a fixed IP** for the phone in your router (DHCP reservation by MAC). Put it in
  `PHONE_IP` in `config.sh`. The scripts use it for adb over Wi-Fi.
* **Outbound only.** The bot talks *to* Telegram; nothing connects *to* the phone from the
  Internet. You do **not** need port forwarding, DDNS or a public IP, and you should not
  create any. (The one open port is adb on :5555, on your LAN only; see below.)
* Prefer **5 GHz** where the signal allows (see "Pinning the band"); 2.4 GHz in a crowded
  apartment block can be many times slower. Measured on one tablet in the same room:
  5.5 Mbps on the crowded 2.4 GHz network vs ~82 Mbps on the 5 GHz one, even at −78 dBm.

## adb over Wi-Fi

`start.sh` enables it at boot (`setprop service.adb.tcp.port 5555` and restarts adbd). The
scripts use USB when plugged in and Wi-Fi otherwise. To connect by hand:

```bash
adb connect 192.168.1.50:5555
```

Things to know:

* It still requires the **RSA key you accepted** on the phone, so only authorised PCs get in.
  Do not expose :5555 to the Internet.
* **Android 4.4's adbd serves one network connection at a time** and hangs if the connection
  drops (e.g. the phone moved). Cure: send `/reiniciar adb` to the bot (it restarts adbd within
  a minute, bot untouched). Never run `stop adbd; start adbd` from an `adb shell` session: the
  `stop` kills your own session before `start` runs, and adb stays dead until reboot.
* Android 11+ also has native "Wireless debugging". The `setprop` method used here also worked on
  the Android 11 and Android 16 devices tested; there set `ADB_TCP_PROP=persist.adb.tcp.port` (11)
  or keep the default (16) and `ADB_RESTART="setprop ctl.restart adbd"`.

## Wi-Fi power-save: the phone "disappears" at night

With the screen off, the Wi-Fi chip goes to power-save and stops answering local-network
traffic (ARP). The bot still reaches Telegram (it initiates the traffic), but `ping` and adb from
your PC time out. `charge.sh` turns power-save off with `iw` every minute (Android turns it
back on when it reconnects) and announces the phone's address with a gratuitous ARP. The
`wifi_sleep_policy=2` setting in `start.sh` keeps Wi-Fi on while the screen is off.

## Sticky access points (old Android)

Android 4.4 joins the first access point it finds and **never switches to a stronger one**
while connected. After a reboot one phone sat at −84 dBm / 9 Mbps with a −69 dBm / 40–60 Mbps
network available. `charge.sh` handles it: if the signal stays below `WIFI_MIN` (default
−75 dBm) for 5 minutes, it cycles Wi-Fi, which forces a fresh scan.
If your only usable signal is weak, lower `WIFI_MIN` (e.g. `-85`) or it will keep reconnecting.

## Recovery ladder

When you cannot reach the phone:

1. Does the bot answer in Telegram? Then the phone is fine and has Internet.
2. `ping <phone IP>` — on Windows, only a reply with `TTL=` counts; *Destination host
   unreachable* is not a reply.
3. Ping answers but adb does not → `/reiniciar adb`.
4. Ping does not answer but the bot does → `/reiniciar wifi`.
5. Bot not answering either → check power, battery, Wi-Fi at the phone; then `/reiniciar confirmar`
   if you can reach the bot at all, or a physical power cycle.

## Android 11+: "Network is unreachable" as root

Android 11 no longer consults the `main` routing table for root processes, so the chroot (and
the bot) has no route out. Set `FIX_ROUTE=1` in `server.conf`: `charge.sh` keeps an
`ip rule … lookup <wlan table>` in place (it finds the table number itself, since `netd`
allocates it).

## Pinning the band (LineageOS / Android 12+, optional)

Android stays on 2.4 GHz whenever it can, because its join threshold for 5 GHz is −77 dBm.
`phone/extras/wifi-band.sh` removes auto-join from the 2.4 GHz network (it stays saved) by
editing `WifiConfigStore.xml`. Set `WIFI_2G_SSID` and `WIFI_5G_SSID` in `server.conf`, install
it with `tools/deploy.sh` (it travels with the scripts), and run
`adb shell su -c "sh /data/debian/wifi-band.sh 5g"`. If the phone cannot get Internet on 5 GHz
for 10 minutes, `charge.sh` calls `wifi-band.sh 2g` by itself. Every switch restarts Android's
framework (~1 min without network; the chroot and bot keep running). `2g` undoes it.

## Ethernet (USB-C or micro-USB hub)

Prepared but **not tested with real hardware yet**. Most kernels include the usual USB
Ethernet drivers (Realtek RTL8152/8153, ASIX AX88179, CDC-ECM/NCM) and Android names the
interface `eth0` or `usb0`. `charge.sh` notices the cable, logs it, and leaves Wi-Fi alone while
the link is up; the bot's `/velocidad` reports "Conectado por cable". Caveat: many phones
cannot charge **and** host a USB device through the same port; you may need a hub with
power pass-through. Check with your actual hub, and tell us how it went.

Next: [08 · Operations](08-operations.md).
