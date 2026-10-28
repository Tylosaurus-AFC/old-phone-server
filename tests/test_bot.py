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
BUTTONS = []      # inline buttons of the last say() that had them
bot.say = lambda chat, text, reply_to=None, parse_mode=None, buttons=None:     (BUTTONS.append(buttons) if buttons else None, SAID.append((chat, text)))[1] or 1
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
            {"/foto_camaras", "/clip_camaras", "/alexa", "/sticker", "/scrobble", "/lastfm", "/likes"})

    def test_helper_modules_are_not_plugins(self):
        # _camaras.py & co. start with "_" and must not be loaded as plugins
        self.assertFalse(any(k.startswith("/_") for k in bot.PLUGIN_COMMANDS))

    def test_sticker_is_for_everyone_the_rest_owner_only(self):
        self.assertFalse(bot.PLUGIN_COMMANDS["/sticker"]["owner"])
        for c in ("/alexa", "/foto_camaras", "/scrobble"):
            self.assertTrue(bot.PLUGIN_COMMANDS[c]["owner"])

    def test_loop_health_and_document_hooks_registered(self):
        self.assertEqual(len(bot.PLUGIN_LOOPS), 3)         # scrobbler + likes (loop, feeder)
        self.assertEqual(len(bot.PLUGIN_HEALTH), 2)        # scrobbler + cameras
        self.assertEqual(len(bot.PLUGIN_DOCS), 1)
        self.assertEqual(len(bot.PLUGIN_JOB_DONE), 1)      # likes: bulk queue progress
        self.assertIn("canciones", bot.ROLE_INFO)          # a plugin added a channel role

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

    def test_owner_help_has_quick_buttons(self):
        BUTTONS.clear()
        run_and_wait(msg("/help"))
        cmds = [d for row in (BUTTONS[-1] if BUTTONS else []) for _, d in row]
        self.assertIn("/estado", cmds)
        self.assertIn("/stats", cmds)
        self.assertNotIn("/foto_camaras", cmds)      # cameras are a plugin, not a core button

    def test_stats_with_empty_database(self):
        bot.db.DB = Path(tempfile.mkdtemp()) / "bot.db"
        self.assertIn("Aún no hay nada registrado", bot.stats_text(""))
        bot.db.descarga(100, 1, "T", "youtube", "u", "video", "ok", 2**20, 3)
        self.assertIn("youtube 1", bot.stats_text("hoy"))


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

    def test_clean_url_drops_trackers(self):
        self.assertEqual(bot.clean_url("https://www.instagram.com/reel/AbC/?igsh=xyz&img_index=2"),
                         "https://www.instagram.com/reel/AbC/")
        self.assertEqual(bot.clean_url("https://youtu.be/abcDEF12345?si=TRACK&t=30"),
                         "https://www.youtube.com/watch?v=abcDEF12345&t=30")
        self.assertEqual(bot.clean_url("https://www.youtube.com/shorts/abcDEF12345?feature=share"),
                         "https://www.youtube.com/shorts/abcDEF12345")

    def test_cache_key_instagram_ignores_every_param(self):
        self.assertEqual(bot.cache_key("https://www.instagram.com/p/AbC/?utm_source=ig&hl=es", "video"),
                         bot.cache_key("https://instagram.com/p/AbC/", "video"))

    def test_pdf_zip_path(self):
        d = Path("/tmp/x")
        self.assertEqual(bot.pdf_zip_path(d, "Mi PDF: (v2)"), d / "Mi_PDF_v2_.zip")
        self.assertEqual(bot.pdf_zip_path(d, ""), d / "pdf.zip")
        self.assertEqual(bot.pdf_zip_path(d, "x" * 100).name, "x" * 60 + ".zip")

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


class ChannelRoles(unittest.TestCase):
    def test_channel_event_assigns_role_from_title_and_ignores_non_owner(self):
        bot.CHANNELS_FILE.unlink(missing_ok=True)
        SAID.clear()
        left = []
        real_tg = bot.tg
        bot.tg = lambda method, **p: left.append(method)
        try:
            ev = lambda who: {"chat": {"id": -100, "type": "channel", "title": "Mis Canciones"},
                              "new_chat_member": {"status": "administrator", "can_post_messages": True},
                              "from": {"id": who}}
            bot.channel_event(ev(2))                       # not the owner: the bot leaves
            self.assertIn("leaveChat", left)
            self.assertEqual(bot.load_channels()["list"], [])
            bot.channel_event(ev(1))                       # the owner
            d = bot.load_channels()
            self.assertEqual(d["roles"].get("canciones"), -100)
        finally:
            bot.tg = real_tg
            bot.CHANNELS_FILE.unlink(missing_ok=True)


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


class SafeUpdate(unittest.TestCase):
    """/actualizar and the daily auto-update: never leave broken downloaders behind."""
    def setUp(self):
        SAID.clear()
        self.calls = []
        self.orig = (bot.run, bot.tool_versions, bot.tools_work, bot.shutil.disk_usage)
        bot.shutil.disk_usage = lambda p: shutil._ntuple_diskusage(10 * 2**30, 0, 10 * 2**30)

    def tearDown(self):
        bot.run, bot.tool_versions, bot.tools_work, bot.shutil.disk_usage = self.orig

    def fake_run(self, rcs):
        def run(cmd, cwd, timeout=900):
            self.calls.append([str(c) for c in cmd])
            rc = rcs.pop(0) if rcs else 0
            return bot.subprocess.CompletedProcess(cmd, rc, "", "" if rc == 0 else "ERROR: boom")
        bot.run = run

    def test_success_reports_new_versions(self):
        self.fake_run([0])
        bot.tool_versions = lambda: {"yt-dlp": "2026.9.1", "gallery-dl": "1.33.0"}
        bot.tools_work = lambda: True
        bot.update_tools(7)
        self.assertEqual(len(self.calls), 1)
        self.assertIn("yt-dlp 2026.9.1", SAID[-1][1])

    def test_pip_failure_rolls_back_to_previous_versions(self):
        self.fake_run([1, 0])
        bot.tool_versions = lambda: {"yt-dlp": "2026.8.19", "gallery-dl": "1.32.17"}
        bot.tools_work = lambda: True
        bot.update_tools(7)
        self.assertEqual(len(self.calls), 2)
        self.assertIn("yt-dlp==2026.8.19", self.calls[1])
        self.assertIn("gallery-dl==1.32.17", self.calls[1])
        self.assertIn("vuelvo a las versiones de antes", SAID[-1][1])

    def test_broken_after_install_also_rolls_back(self):
        self.fake_run([0, 0])
        bot.tool_versions = lambda: {"yt-dlp": "2026.8.19"}
        works = iter([False, True])
        bot.tools_work = lambda: next(works)
        bot.update_tools(7)
        self.assertIn("yt-dlp==2026.8.19", self.calls[1])

    def test_low_disk_skips_pip(self):
        self.fake_run([])
        bot.shutil.disk_usage = lambda p: shutil._ntuple_diskusage(2**30, 2**30 - 2**20, 2**20)
        bot.update_tools(7)
        self.assertEqual(self.calls, [])
        self.assertIn("MB libres", SAID[-1][1])

    def test_exception_does_not_escape(self):
        def boom(*a, **k):
            raise bot.subprocess.TimeoutExpired("pip", 900)
        bot.run = boom
        bot.tool_versions = lambda: {}
        bot.update_tools(7)          # must not raise: the auto-update thread would die
        self.assertIn("falló", SAID[-1][1])


class Diagnostics(unittest.TestCase):
    def test_report_hides_secrets(self):
        (BASE / "api.txt").write_text("1234567\nabcdef0123456789abcdef\n")
        (BASE / "bot.log").write_text(
            "2026 INFO run: yt-dlp https://www.instagram.com/p/SECRETPATH/?igsh=x\n"
            "2026 WARNING poll: https://api.telegram.org/bot123456:TEST-TOKEN/getUpdates\n"
            "2026 INFO owner 1 chat -1001234567890 from 192.168.1.20\n"
            "2026 INFO other token 987654321:XYZabcdefghijklmnopqrstuvwxyz0123\n")
        (BASE / "cookies.txt").write_text(".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\tCOOKIEVALUE\n")
        try:
            text = bot.diag.report()
        finally:
            (BASE / "api.txt").unlink()
            (BASE / "cookies.txt").unlink()
        for secret in ("TEST-TOKEN", "abcdef0123456789abcdef", "1234567", "SECRETPATH",
                       "1001234567890", "192.168.1.20", "XYZabcdefghij", "COOKIEVALUE"):
            self.assertNotIn(secret, text)
        self.assertIn("https://www.instagram.com/…", text)
        self.assertIn("cookies.txt: sí", text)
        self.assertIn("versión del bot", text)

    def test_owner_only_and_private(self):
        SAID.clear()
        run_and_wait(msg("/diagnostico", uid=2))
        self.assertEqual(SAID, [])
        run_and_wait(msg("/diagnostico", chat=100, ctype="group"))
        self.assertTrue(any("privado" in t for _, t in SAID), SAID)

    def test_owner_gets_a_document(self):
        sent = []
        orig = bot.send_file
        bot.send_file = lambda chat, path, caption=None, as_doc=False, **k: sent.append(
            (chat, path.read_text(encoding="utf-8"), as_doc))
        try:
            run_and_wait(msg("/diagnostico"))
        finally:
            bot.send_file = orig
        self.assertEqual(len(sent), 1)
        self.assertTrue(sent[0][2])
        self.assertNotIn("TEST-TOKEN", sent[0][1])


class Buttons(unittest.TestCase):
    """Inline buttons: the order goes through on_message as if typed by whoever pressed."""
    def setUp(self):
        SAID.clear()
        self.queued, self.answered = [], []
        self.orig = (bot.tg, bot.enqueue)
        bot.tg = lambda method, **k: self.answered.append((method, k)) or {}
        bot.enqueue = lambda msg, chat, user, urls, text, mode="video": \
            self.queued.append((chat, user.get("id"), urls, mode))

    def tearDown(self):
        bot.tg, bot.enqueue = self.orig

    def cb(self, data, uid=1, chat=100, ctype="private"):
        video = {"message_id": 42, "chat": {"id": chat, "type": ctype},
                 "caption": "Título", "caption_entities": [
                     {"type": "text_link", "offset": 0, "length": 6, "url": "https://x.com/a/1"}]}
        return {"id": "cbid", "from": {"id": uid, "first_name": "T"}, "message": video, "data": data}

    def test_mp3_button_queues_the_link_of_the_video(self):
        bot.on_button(self.cb("/mp3"))
        self.assertEqual(self.queued, [(100, 1, ["https://x.com/a/1"], "mp3")])
        self.assertEqual(self.answered[0][0], "answerCallbackQuery")

    def test_owner_button_pressed_by_other_user_does_nothing(self):
        bot.on_button(self.cb("/stats hoy", uid=2))
        self.assertEqual(SAID, [])

    def test_button_from_unauthorised_chat_is_ignored(self):
        bot.on_button(self.cb("/mp3", chat=555, ctype="group"))
        self.assertEqual(self.queued, [])

    def test_button_without_message_is_only_answered(self):
        cb = self.cb("/mp3"); del cb["message"]
        bot.on_button(cb)
        self.assertEqual(self.queued, [])
        self.assertEqual(len(self.answered), 1)


class NoRootDoctor(unittest.TestCase):
    """doctor.txt (written hourly by the no-root charge.sh) in /salud and /diagnostico."""
    REPORT = ("RESULT: broken (1 fail, 1 warn) 2026-10-27 10:00\n"
              "OK   Android 14 (SDK 34), realme\n"
              "WARN 800 MB free\n     -> keep at least 1 GB free\n"
              "FAIL Termux is under battery optimisation: Android may freeze it\n"
              "     -> Settings > Apps > Termux > Battery > Unrestricted\n")

    def setUp(self):
        (BASE / "sys").mkdir(exist_ok=True)
        self.orig = bot.http.get
        def offline(*a, **k):
            raise bot.requests.ConnectionError("offline")
        bot.http.get = offline

    def tearDown(self):
        bot.http.get = self.orig
        (BASE / "sys" / "doctor.txt").unlink(missing_ok=True)

    def test_salud_shows_the_worst_problem_first(self):
        (BASE / "sys" / "doctor.txt").write_text(self.REPORT)
        line = [l for l in bot.health_text().splitlines() if "Android/Termux" in l][0]
        self.assertIn("❌", line)
        self.assertIn("battery optimisation", line)
        self.assertIn("+1 más", line)

    def test_salud_ok(self):
        (BASE / "sys" / "doctor.txt").write_text("RESULT: ok (0 fail, 0 warn) x\nOK   a\n")
        line = [l for l in bot.health_text().splitlines() if "Android/Termux" in l][0]
        self.assertIn("✅", line)

    def test_root_mode_has_no_line(self):
        self.assertFalse([l for l in bot.health_text().splitlines() if "Android/Termux" in l])

    def test_diagnostico_includes_the_report(self):
        (BASE / "sys" / "doctor.txt").write_text(self.REPORT)
        self.assertIn("under battery optimisation", bot.diag.report())


class ProblemCollection(unittest.TestCase):
    """collect_problems(): the real checks behind the state-change alerts."""
    def setUp(self):
        (BASE / "sys").mkdir(exist_ok=True)
        self.saved = (bot.health.internet_ok, bot.tools_work, bot.shutil.disk_usage)
        bot.health.internet_ok = lambda: (True, "")
        bot.tools_work = lambda: True
        bot._tools_ok.update(t=0, ok=True)
        bot.shutil.disk_usage = lambda p: shutil._ntuple_diskusage(10 * 2**30, 0, 10 * 2**30)

    def tearDown(self):
        bot.health.internet_ok, bot.tools_work, bot.shutil.disk_usage = self.saved
        for f in ("doctor.txt", "shizuku"):
            (BASE / "sys" / f).unlink(missing_ok=True)

    def ids(self):
        return {p["id"]: p for p in bot.collect_problems()}

    def shizuku(self, **kw):
        now = int(bot.time.time())
        d = {"state": "ok", "since": 0, "tries": 0, "auth": 1, "checked": now, "boot": now - 86400, **kw}
        (BASE / "sys" / "shizuku").write_text("".join(f"{k}={v}\n" for k, v in d.items()))

    def test_healthy_server_has_no_problems(self):
        self.shizuku()
        self.assertEqual(bot.collect_problems(), [])

    def test_no_internet_is_broken(self):
        bot.health.internet_ok = lambda: (False, "no resuelve nombres (DNS)")
        self.assertEqual(self.ids()["internet"]["level"], "broken")

    def test_disk_thresholds(self):
        bot.shutil.disk_usage = lambda p: shutil._ntuple_diskusage(2**30, 0, 800 * 2**20)
        self.assertEqual(self.ids()["disk"]["level"], "degraded")
        bot.shutil.disk_usage = lambda p: shutil._ntuple_diskusage(2**30, 0, 100 * 2**20)
        self.assertEqual(self.ids()["disk"]["level"], "broken")

    def test_downloaders_not_starting_is_broken_and_checked_at_most_every_30_min(self):
        calls = []
        bot.tools_work = lambda: calls.append(1) or False
        self.assertEqual(self.ids()["tools"]["level"], "broken")
        self.ids()
        self.assertEqual(len(calls), 1)

    def test_dead_watchdog_is_broken(self):
        self.shizuku(checked=int(bot.time.time()) - 1800)
        self.assertEqual(self.ids()["watchdog"]["level"], "broken")

    def test_shizuku_down_is_degraded_with_the_fix_and_auth_hint(self):
        now = int(bot.time.time())
        self.shizuku(state="not-running", since=now - 900, auth=0)
        p = self.ids()["shizuku"]
        self.assertEqual(p["level"], "degraded")
        self.assertIn("Iniciar", p["fix"])
        self.assertIn("SHIZUKU_AUTH", p["fix"])

    def test_shizuku_just_after_boot_is_not_a_problem(self):
        now = int(bot.time.time())
        self.shizuku(state="not-running", since=now - 400, boot=now - 400)
        self.assertNotIn("shizuku", self.ids())

    def test_doctor_lines_become_problems_without_duplicates(self):
        self.shizuku()
        (BASE / "sys" / "doctor.txt").write_text(
            "RESULT: broken (1 fail, 3 warn) x\n"
            "FAIL Termux is under battery optimisation\n     -> Settings > Apps > Termux > Battery\n"
            "WARN no Termux wake lock: the CPU may sleep\n     -> run termux-wake-lock\n"
            "WARN Shizuku lacks WRITE_SECURE_SETTINGS\n     -> adb shell pm grant ...\n"
            "WARN 800 MB free\n     -> keep at least 1 GB free\n")
        probs = bot.collect_problems()
        titles = {p["title"]: p for p in probs}
        self.assertEqual(titles["Termux is under battery optimisation"]["level"], "broken")
        self.assertEqual(titles["Termux is under battery optimisation"]["fix"], "Settings > Apps > Termux > Battery")
        self.assertIn("no Termux wake lock: the CPU may sleep", titles)
        self.assertFalse([t for t in titles if "Shizuku" in t or "MB free" in t], "watched elsewhere")

    def test_old_doctor_report_is_ignored(self):
        f = BASE / "sys" / "doctor.txt"
        f.write_text("RESULT: broken x\nFAIL something\n")
        old = bot.time.time() - 4 * 3600
        import os
        os.utime(f, (old, old))
        self.assertEqual([p for p in bot.collect_problems() if p["id"].startswith("doctor:")], [])

    def test_one_failing_check_does_not_hide_the_others(self):
        def boom():
            raise OSError("socket exploded")
        bot.health.internet_ok = boom
        bot.shutil.disk_usage = lambda p: shutil._ntuple_diskusage(2**30, 0, 100 * 2**20)
        self.assertIn("disk", self.ids())

    def test_end_to_end_one_message_then_recovery(self):
        sent = []
        clock = [bot.time.time()]
        a = bot.alerts.Alerts(Path(tempfile.mkdtemp()) / "a.json", lambda t: sent.append(t) or True,
                              clean=bot.diag.redact, now=lambda: clock[0])
        bot.health.internet_ok = lambda: (False, "sin salida a Internet")
        for _ in range(4):
            a.update(bot.collect_problems()); clock[0] += 300
        bot.health.internet_ok = lambda: (True, "")
        for _ in range(3):
            a.update(bot.collect_problems()); clock[0] += 300
        self.assertEqual(len(sent), 2, sent)
        self.assertIn("Sin conexión a Internet", sent[0])
        self.assertIn("Resuelto", sent[1])


class RobustReports(unittest.TestCase):
    """/diagnostico and /salud must answer even with odd files written by other processes."""
    def setUp(self):
        (BASE / "sys").mkdir(exist_ok=True)
        self.orig = bot.http.get
        def offline(*a, **k):
            raise bot.requests.ConnectionError("offline")
        bot.http.get = offline

    def tearDown(self):
        bot.http.get = self.orig
        (BASE / "sys" / "doctor.txt").unlink(missing_ok=True)
        bot.diag.BAT = Path("/sys/class/power_supply/battery")

    def test_diagnostico_with_non_numeric_battery_values(self):
        fake = Path(tempfile.mkdtemp())
        for f, v in (("temp", "null"), ("capacity", ""), ("status", "x")):
            (fake / f).write_text(v)
        bot.diag.BAT = fake
        self.assertIn("batería", bot.diag.report())

    def test_diagnostico_with_garbage_heartbeat_and_pending_files(self):
        (BASE / "heartbeat").write_text("1.2.3")
        (BASE / "pending_downloads.json").write_text('{"not": "a list"}')
        try:
            self.assertIn("señal de vida", bot.diag.report())
        finally:
            (BASE / "heartbeat").unlink()
            (BASE / "pending_downloads.json").unlink()

    def test_salud_with_a_truncated_doctor_report(self):
        for content in ("RESULT:", "RESULT:\n", "RESULT: weird", ""):
            (BASE / "sys" / "doctor.txt").write_text(content)
            self.assertIn("Salud del servidor", bot.health_text(), repr(content))


def tearDownModule():
    shutil.rmtree(_tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
