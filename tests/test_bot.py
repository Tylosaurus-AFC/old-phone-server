"""Tests of the bot without a phone or Telegram: plugin loading, command dispatch,
access rules, help/menus and pure helpers.   Needs only `pip install requests`.

Run:  python tests/test_bot.py        (or tests/run.sh)

The bot hardcodes /opt/bot (its place inside the phone's chroot). To import it on a PC the
sources are copied to a temp folder with that path rewritten.
"""
import importlib.util
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_tmp = Path(tempfile.mkdtemp(prefix="opsbot-"))
BASE = _tmp / "opt-bot"


def _prepare():
    BASE.mkdir(parents=True)
    (BASE / "plugins").mkdir()
    for f in (REPO / "bot").glob("*.py"):
        text = f.read_text(encoding="utf-8").replace("/opt/bot", BASE.as_posix())
        text = text.replace('"/opt/stt"', f'"{(_tmp / "opt-stt").as_posix()}"')
        (BASE / f.name).write_text(text, encoding="utf-8")
    for f in (REPO / "extras" / "plugins").glob("*.py"):
        text = f.read_text(encoding="utf-8").replace("/opt/bot", BASE.as_posix())
        (BASE / "plugins" / f.name).write_text(text, encoding="utf-8")
    (BASE / "token").write_text("123456:TEST-TOKEN\n")
    (BASE / "owners").write_text("1\n100\n")     # owner id 1; authorised chat 100


_prepare()
sys.path.insert(0, str(BASE))
_spec = importlib.util.spec_from_file_location("botmod", BASE / "bot.py")
bot = importlib.util.module_from_spec(_spec)
sys.modules["botmod"] = bot
_spec.loader.exec_module(bot)

SAID = []
bot.say = lambda chat, text, reply_to=None, parse_mode=None: SAID.append((chat, text)) or 1
bot.delete = lambda *a, **k: True
bot.edit = lambda *a, **k: None
bot.BOT.update(id=999, username="testbot", first_name="Test")
bot.load_plugins()


def msg(text, uid=1, chat=100, ctype="private", **extra):
    return {"message_id": 5, "chat": {"id": chat, "type": ctype},
            "from": {"id": uid, "first_name": "T"}, "text": text, **extra}


def run_and_wait(m):
    """on_message may hand the command to a thread; wait for the threads it started."""
    before = set(threading.enumerate())
    bot.on_message(m)
    for t in set(threading.enumerate()) - before:
        t.join(5)


class PluginLoading(unittest.TestCase):
    def test_all_example_plugins_load(self):
        self.assertEqual(
            set(bot.PLUGIN_COMMANDS),
            {"/foto_camaras", "/clip_camaras", "/alexa", "/sticker", "/scrobble", "/lastfm"})

    def test_helper_modules_are_not_plugins(self):
        # _camaras.py & co. start with "_" and must not be loaded as plugins
        self.assertFalse(any(k.startswith("/_") for k in bot.PLUGIN_COMMANDS))

    def test_sticker_is_for_everyone_the_rest_owner_only(self):
        self.assertFalse(bot.PLUGIN_COMMANDS["/sticker"]["owner"])
        for c in ("/alexa", "/foto_camaras", "/scrobble"):
            self.assertTrue(bot.PLUGIN_COMMANDS[c]["owner"])

    def test_loop_health_and_document_hooks_registered(self):
        self.assertEqual(len(bot.PLUGIN_LOOPS), 1)         # scrobbler
        self.assertEqual(len(bot.PLUGIN_HEALTH), 2)        # scrobbler + cameras
        self.assertEqual(len(bot.PLUGIN_DOCS), 1)

    def test_broken_plugin_does_not_stop_the_others(self):
        (BASE / "plugins" / "zz_broken.py").write_text("def setup(api):\n    raise RuntimeError('x')\n")
        n = len(bot.PLUGIN_COMMANDS)
        bot.load_plugins()
        self.assertEqual(len(bot.PLUGIN_COMMANDS), n)
        (BASE / "plugins" / "zz_broken.py").unlink()


class HelpAndMenus(unittest.TestCase):
    def test_owner_help_lists_plugin_commands_others_do_not(self):
        self.assertIn("/foto_camaras", bot.help_text(True))
        self.assertIn("/alexa", bot.help_text(True))
        self.assertNotIn("/foto_camaras", bot.help_text(False))

    def test_core_help_has_no_private_features(self):
        base = bot.HELP + bot.OWNER_HELP
        for word in ("alexa", "camaras", "cámaras", "scrobble", "lastfm"):
            self.assertNotIn(word, base.lower())

    def test_menu_includes_plugin_commands_for_owner(self):
        sent = []
        bot.tg = lambda method, **p: sent.append((method, p))
        bot.register_commands(1)
        owner_cmds = [p for m, p in sent if "scope" in p][0]["commands"]
        self.assertIn("alexa", owner_cmds)
        public_cmds = [p for m, p in sent if "scope" not in p][0]["commands"]
        self.assertNotIn("alexa", public_cmds)


class Dispatch(unittest.TestCase):
    def setUp(self):
        SAID.clear()

    def test_owner_command_from_owner_reaches_plugin(self):
        run_and_wait(msg("/alexa hola"))
        # no voicemonkey.json -> the plugin answers with its own error, proving it ran
        self.assertTrue(any("Voice Monkey" in t for _, t in SAID), SAID)

    def test_owner_command_from_other_user_is_ignored(self):
        run_and_wait(msg("/alexa hola", uid=2))
        self.assertEqual(SAID, [])

    def test_owner_command_in_group_asks_for_private(self):
        # /scrobble is owner-only AND private-only (plugin default: anywhere=False)
        run_and_wait(msg("/scrobble", chat=100, ctype="group"))
        self.assertTrue(any("privado" in t for _, t in SAID), SAID)

    def test_unauthorised_chat_gets_nothing(self):
        run_and_wait(msg("/alexa hola", uid=1, chat=555, ctype="group"))
        self.assertEqual(SAID, [])

    def test_sticker_open_to_authorised_users(self):
        run_and_wait(msg("/sticker", uid=2))
        self.assertTrue(any("Uso:" in t for _, t in SAID), SAID)

    def test_core_command_still_works(self):
        run_and_wait(msg("/help"))
        self.assertTrue(any("Qué hago" in t for _, t in SAID), SAID)


class CoreHelpers(unittest.TestCase):
    def test_cache_key_ignores_tracking_params(self):
        a = bot.cache_key("https://www.tiktok.com/@x/video/1?utm_source=a&is_from_webapp=1", "video")
        b = bot.cache_key("https://tiktok.com/@x/video/1", "video")
        self.assertEqual(a, b)

    def test_cache_key_youtube_forms_match(self):
        k = {bot.cache_key(u, "video") for u in (
            "https://youtu.be/abcDEF12345", "https://www.youtube.com/watch?v=abcDEF12345&t=3",
            "https://youtube.com/shorts/abcDEF12345")}
        self.assertEqual(len(k), 1)

    def test_charge_paused_reads_file_written_by_charge_sh(self):
        (BASE / "charge_paused").write_text("1\n")
        self.assertEqual(bot.charge_paused(), "1")
        (BASE / "charge_paused").unlink()
        self.assertEqual(bot.charge_paused(), "0")

    def test_parse_cookies(self):
        sample = ".instagram.com\tTRUE\t/\tTRUE\t1999999999\tsessionid\tabc"
        self.assertEqual(bot.parse_cookies(sample), {"instagram.com": {"sessionid": 1999999999}})

    def test_status_and_about_do_not_crash_without_a_phone(self):
        class Done:       # stands in for `yt-dlp --version`, which does not exist on the PC
            stdout = "0.0-test"
        real = bot.run
        bot.run = lambda *a, **k: Done()
        try:
            self.assertIn("RAM", bot.status_text())
        finally:
            bot.run = real
        self.assertIn("Debian", bot.about_text(True))


class Scrobbler(unittest.TestCase):
    def test_new_plays_detection(self):
        import _scrobbler as s
        self.assertEqual(s.new_plays(["a", "b", "c"], ["x", "a", "b", "c"]), ["x"])
        self.assertEqual(s.new_plays(["a", "b", "c"], ["a", "b", "c"]), [])
        self.assertEqual(s.new_plays(["a", "b", "c"], ["c", "a", "b"]), ["c"])   # repeat moves up


class Cameras(unittest.TestCase):
    def test_parse_clip(self):
        import datetime as dt
        import _camaras as c
        now = dt.datetime(2026, 10, 20, 12, 0)
        cam, start, end = c.parse_clip("2 ayer 23:50 23:58", now)
        self.assertEqual((cam, start, end),
                         ("2", dt.datetime(2026, 10, 19, 23, 50), dt.datetime(2026, 10, 19, 23, 58)))
        with self.assertRaises(c.CamError):
            c.parse_clip("2 10:00 12:30", now)       # more than 60 minutes


def tearDownModule():
    shutil.rmtree(_tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
