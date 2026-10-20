# 09 · Plugins

The core bot does one job (downloading, plus health and administration). Everything that only
suits some people lives in **plugins**: a `.py` file dropped in `/opt/bot/plugins/` is loaded at
startup. Four real examples ship in [`extras/plugins/`](../../extras/plugins/); they are
the private features of the original installation, generalised.

## Enabling the examples

List the ones you want in `config.sh` and deploy:

```bash
PLUGINS="cameras alexa stickers lastfm_scrobbler"
tools/deploy.sh
```

`deploy.sh` makes `/opt/bot/plugins/` contain **exactly** those (plus the helper modules whose
names start with `_`). A plugin that fails to load is logged and skipped; the rest keep working.

| Plugin | Commands | Needs | Notes |
|---|---|---|---|
| `cameras` | `/foto_camaras [cam]`, `/clip_camaras cam [date] start end` | `camaras.json`: `{"host","user","password"}` | **Dahua** XVR/NVR (CGI + RTSP). Create a read-only user for the bot on the recorder, never the admin. Other brands need `_camaras.py` adapted |
| `alexa` | `/alexa [@speaker] text` | `voicemonkey.json`: `{"token","device","language"}` | via [Voice Monkey](https://voicemonkey.io) (free tier: 200 calls/month) |
| `stickers` | `/sticker [emoji]` | `ffmpeg` with VP9 | turns a video/GIF into a Telegram video sticker in the user's own pack. Open to every authorised user |
| `lastfm_scrobbler` | `/scrobble`, `/lastfm` | cookies of music.youtube.com (sent as a `.txt` whose name contains `youtube`), Last.fm API key | scrobbles YouTube Music history to Last.fm every 3 min; the most complete example (background loop, health line, file handler) |

Put each plugin's config file in `/opt/bot/` on the phone (inside the chroot:
`/data/debian/fs/opt/bot/`), `chmod 600`. They contain passwords and are excluded from
`make-image.sh`; `backup.sh` saves them.

## Writing your own

A plugin is one file with a `setup(api)` function. `api` is the bot module itself: you can use
`api.say`, `api.edit`, `api.delete`, `api.tg` (raw Bot API call), `api.send_file`, `api.publish`
(handles albums and the 2 GB path), `api.alert` (private message to the owner, rate-limited),
`api.JOBS` (a temp folder), `api.BASE`, `api.log`, `api.load_owners`, `api.BOT`, `api.health.event`,
`api._check` (format a `/salud` line).

```python
# /opt/bot/plugins/hello.py   — /hola → "hola, <name>"
def setup(api):
    def hola(msg, chat, user, arg):
        api.say(chat, f"hola, {user.get('first_name', '')} {arg}".strip())

    return {
        "commands": {"hola": {
            "fn": hola,                      # fn(msg, chat, user, arg)
            "owner": False,                  # default True: only the owner may call it
            "anywhere": True,                # default False: owner commands work only in private
            "thread": True,                  # default True: run in its own thread
            "help": "/hola – says hello",    # line added to the owner's /help (HTML)
            "menu": "Say hello"}},           # description in Telegram's "/" menu
    }
```

`setup()` may also return any of:

| Key | Type | Purpose |
|---|---|---|
| `health` | list of `f() → str` | one line each for `/salud` (`api._check(name, True/None/False, detail)`) |
| `loops` | list of `f()` | background tasks, each in its own daemon thread (they should `while True` + `sleep`) |
| `documents` | list of `f(msg, doc, text) → bool` | called when the owner sends a `.txt` in private; return `True` if you took it |
| `about` | list of str | bullet lines for the owner's `/acerca` |

Rules of the road:

* A plugin runs **with the bot's privileges**. Only install code you have read.
* Files starting with `_` are helper modules: importable by plugins (`import _mylib`), never
  loaded as plugins.
* Keep secrets out of logs and of Telegram. The core replaces the bot token in log lines with `<token>`;
  do the same for yours.
* Test without a phone: `tests/test_bot.py` shows how to load plugins into a throw-away copy
  of the bot and send fake messages to `on_message`.
* Core access rules still apply first: unauthorised chats never reach a plugin; `owner` is
  checked against the first user who ran `/start`.
