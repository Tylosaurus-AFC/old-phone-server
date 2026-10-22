# 04 · The Telegram bot

The example application. Once Debian is provisioned ([03](03-install.md)), the bot needs a
token, a deploy, and an owner.

> The bot's messages and commands are **in Spanish** (`/estado`, `/seguir`, `/permitir`…). The
> logic is language-neutral; translating means editing the strings in `bot/bot.py`. A proper
> i18n layer is a welcome contribution ([CONTRIBUTING](../../CONTRIBUTING.md)).

## 1. Create the bot and give the phone its token

1. In Telegram open **@BotFather**, send `/newbot`, choose a name and a username.
2. BotFather replies with a **token** (`123456789:AA…`). It is a password: anyone who has it controls
   the bot.
3. Put it on the phone (asked silently, stored with `chmod 600`):

```bash
tools/set-token.sh              # no-root mode: tools/noroot-bot.sh token
```

## 2. Optional: uploads up to 2 GB

The plain Bot API cannot upload more than 50 MB. A bot can reach 2 GB through MTProto if you give
it a Telegram application key:

1. Log in at <https://my.telegram.org> → *API development tools* → create an application.
2. Run `tools/set-api.sh` and enter the `api_id` and `api_hash`.

Without it everything works, but files over 50 MB fail (the bot tries lower resolutions first).

## 3. Deploy and enable

```bash
tools/deploy.sh          # copies bot/, plugins and phone scripts; checks syntax on the phone
tools/enable-bot.sh      # creates /data/debian/BOT_ENABLED and starts bot.sh
# no-root mode:  tools/noroot-deploy.sh  and  tools/noroot-bot.sh enable
```

The bot **only runs where `BOT_ENABLED` exists.** That file is a safety latch: the same token
must never run on two phones at once (Telegram answers *409 Conflict* and every download happens
twice). Moving the server to a new phone = `tools/enable-bot.sh off` on the old one first.

## 4. Become the owner — *do this immediately*

Open a **private chat with your bot** and send `/start`. **The first person to do so becomes the
owner** and is the only one who can use owner commands. Do it before you share the bot's
username with anybody.

Then:

| To… | Do |
|---|---|
| use it in a group | add the bot to the group **as the owner** (anyone else's attempt makes it leave). Make it an admin with *delete messages* so it can remove the link message |
| let a friend use it privately | they message the bot; you get a request with their id; send `/permitir ID` (`/quitar ID`, `/usuarios`) |
| follow a YouTube channel | `/seguir <channel link> [privado\|canal\|ambos]`; new videos are posted in 1080p, no Shorts, checked every 5 min (`/canales`, `/destino N …`, `/dejar N`) |
| post them to a Telegram **channel** | create a channel, add the bot as administrator with only *Post messages* (turn off *Sign messages* so its name does not appear) — the bot detects it by itself and tells you; `/canal` lists and assigns channels. If posting to the channel fails, the video is left in your private chat with a warning |

## 5. Using it

Just send a link. Commands:

| Command | Who | What |
|---|---|---|
| *link* | all | download and post; the link message is deleted |
| `/mp3 link` | all | audio only, MP3 192 kbps with cover and tags |
| `/original link` | all | photos/videos as files, uncompressed |
| `/pdf` | all | send a PDF with `/pdf` as the caption (or reply to one): one image per page; options `archivo`, `png`, `zip`, `10-25` |
| `/estado` `/velocidad` `/acerca` `/help` | all | status, speed test, about, help |
| `/cookies` (+ send a `.txt`) | owner | status/renew cookies for Instagram and Facebook |
| `/actualizar` | owner | update yt-dlp and gallery-dl now (also automatic every 24 h) |
| `/seguir` `/canales` `/destino` `/dejar` | owner | YouTube channels and where each one is posted (private chat, channel, or both) |
| `/canal` | owner | Telegram channels the bot posts to, and what each is for (`/canal videos N`, `/canal quitar N`; plugins add more uses) |
| `/permitir` `/quitar` `/usuarios` | owner | who may use it in private |
| `/salud` `/historial [N]` `/bateria` | owner | health checks, event log, battery detail and power cuts |
| `/reiniciar confirmar` · `adb` · `wifi` | owner | reboot the phone · restart only adb · reconnect Wi-Fi |
| `/transcribir on\|off\|modelo X` | owner | voice-note transcription in this chat |

### Instagram / Facebook / age-gated YouTube need cookies

These sites demand a logged-in session. Use a **secondary account**, never your main one:

1. Log in with that account in a desktop browser.
2. Export its cookies with an extension such as *Get cookies.txt LOCALLY* → a `cookies.txt` (Netscape format).
3. Send the file to the bot **in private**. It stores it (`chmod 600`) and **deletes your message**.

The bot tells you when they expire or the site blocks them, and `/salud` shows the expiry date.

**How the bot gets a link** (so you can predict failures): Instagram and Facebook are tried **first without
a session** (yt-dlp, then the page's own embed, then gallery-dl) and the cookies are used only if that fails —
a public post never touches your account. Footers are cleaned: the link under a video has no trackers
(`?si=`, `igsh`, `fbclid`, `img_index`…), YouTube links are canonical, and the cache treats the same post
with different trackers as one. Each job gets its own work folder, so two downloads can never overwrite
each other.

### Voice notes → text (optional)

```bash
tools/install.sh voice        # compiles whisper.cpp (10+ min on a 2-core phone) + Vosk
```

Set the language in `/opt/bot/stt.json` as `{"lang": "en"}` (default `es`) and use a matching Vosk
model (see the header of `phone/extras/setup-voice.sh`). Voice notes in authorised chats are then
transcribed on the phone: a fast Vosk draft first, then the better Whisper text replaces it.

## 6. Where to look when it misbehaves

| File (inside the phone, `/data/debian/fs/opt/bot/`) | Contents |
|---|---|
| `bot.log` | the bot (rotates at 1 MB) |
| `service.log` | `bot.sh` and `charge.sh` |
| `events.jsonl` | what `/historial` shows |
| `/data/debian/boot.log` | `start.sh` at boot |

```bash
adb shell su -c "tail -n 40 /data/debian/fs/opt/bot/service.log"
```

Next: [05 · Services and boot](05-services-and-boot.md).
