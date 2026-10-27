"""Tests of bot/alerts.py: the state-change alert logic, with a fake clock and a fake
Telegram (send() returns True = delivered, False/raise = not delivered).

Run:  python tests/test_alerts.py        (or tests/run.sh)
"""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))
import alerts  # noqa: E402

DISK = {"id": "disk", "level": "degraded", "title": "Poco espacio: 800 MB", "impact": "las descargas pueden fallar",
        "fix": "libera espacio"}
DISK_BROKEN = {**DISK, "level": "broken", "title": "Sin espacio: 120 MB"}
NET = {"id": "internet", "level": "broken", "title": "Sin Internet", "impact": "no hay descargas", "fix": "mira el router"}
SHZ = {"id": "shizuku", "level": "degraded", "title": "Shizuku parado", "fix": "abre Shizuku > Iniciar"}


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t

    def tick(self, s=300):
        self.t += s


class Channel:
    """Fake Telegram: records every attempt; `up` decides if it is delivered."""
    def __init__(self):
        self.up, self.sent, self.attempts = True, [], 0

    def __call__(self, text):
        self.attempts += 1
        if self.up == "raise":
            raise RuntimeError("telegram exploded")
        if self.up:
            self.sent.append(text)
        return bool(self.up)


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.clock, self.ch = Clock(), Channel()
        self.a = self.new()

    def new(self):
        return alerts.Alerts(self.dir / "alerts.json", self.ch, clean=lambda s: s.replace("SECRET", "<oculto>"),
                             now=self.clock)

    def run_for(self, minutes, problems, a=None):
        """Evaluate every 5 min for `minutes`, with the same problems each time."""
        for _ in range(minutes // 5):
            (a or self.a).update(problems)
            self.clock.tick(300)

    # ---- confirmation, dedup ------------------------------------------------------------
    def test_a_one_off_failure_is_never_sent(self):
        self.a.update([NET]); self.clock.tick(); self.run_for(60, [])
        self.assertEqual(self.ch.sent, [])

    def test_confirmed_only_after_two_checks_and_the_minimum_time(self):
        self.a.update([DISK]); self.clock.tick(); self.a.update([DISK])
        self.assertEqual(self.ch.sent, [], "degraded needs 10 min")
        self.clock.tick(); self.a.update([DISK])
        self.assertEqual(len(self.ch.sent), 1)
        self.assertIn("Poco espacio", self.ch.sent[0])
        self.assertIn("libera espacio", self.ch.sent[0])

    def test_same_problem_is_sent_once(self):
        self.run_for(180, [DISK])
        self.assertEqual(len(self.ch.sent), 1)

    def test_degraded_is_not_reminded_but_broken_is_every_12h(self):
        self.run_for(25 * 60, [DISK])
        self.assertEqual(len(self.ch.sent), 1)
        a2 = alerts.Alerts(self.dir / "b.json", self.ch, now=self.clock)
        self.ch.sent.clear()
        self.run_for(25 * 60, [NET], a=a2)
        self.assertEqual(len(self.ch.sent), 3, "first alert + reminders at 12 h and 24 h")
        self.assertIn("Sigue sin resolverse", self.ch.sent[1])

    # ---- transitions ----------------------------------------------------------------------
    def test_ok_degraded_broken_degraded_ok(self):
        self.run_for(30, [DISK])
        self.run_for(30, [DISK_BROKEN])
        self.run_for(30, [DISK])
        self.run_for(30, [])
        self.assertEqual(len(self.ch.sent), 4, self.ch.sent)
        self.assertTrue(self.ch.sent[0].startswith("🟡") and "antes: todo en orden" in self.ch.sent[0])
        self.assertTrue(self.ch.sent[1].startswith("🔴") and "Ha cambiado" in self.ch.sent[1])
        self.assertTrue(self.ch.sent[2].startswith("🟡") and "antes: con fallos" in self.ch.sent[2])
        self.assertTrue(self.ch.sent[3].startswith("✅") and "Resuelto" in self.ch.sent[3])

    def test_brief_dropout_of_a_known_problem_is_not_a_recovery(self):
        self.run_for(30, [SHZ])
        self.a.update([]); self.clock.tick(120)     # gone for 2 min only
        self.run_for(30, [SHZ])
        self.assertEqual(len(self.ch.sent), 1)

    def test_several_problems_go_in_one_message_worst_first(self):
        self.run_for(30, [SHZ, NET])
        self.assertEqual(len(self.ch.sent), 1)
        msg = self.ch.sent[0]
        self.assertLess(msg.index("Sin Internet"), msg.index("Shizuku parado"))

    # ---- channel down ---------------------------------------------------------------------
    def test_telegram_down_nothing_marked_as_sent_and_retries_back_off(self):
        self.ch.up = False
        self.run_for(180, [NET])
        self.assertEqual(self.ch.sent, [])
        self.assertLessEqual(self.ch.attempts, 12, "36 checks in 3 h, but retries back off")
        self.assertIn("no puedo avisar", self.a.summary())
        self.ch.up = True
        self.clock.tick(1800); self.a.update([NET])
        self.assertEqual(len(self.ch.sent), 1)
        self.assertIn("Aviso con retraso", self.ch.sent[0])
        self.run_for(60, [NET])
        self.assertEqual(len(self.ch.sent), 1, "no repeat after the late delivery")

    def test_what_happened_while_telegram_was_down_is_summed_up(self):
        self.ch.up = False
        self.run_for(30, [NET])                     # confirmed, never delivered
        self.run_for(10, [])                        # and gone
        self.ch.up = True
        self.clock.tick(1800); self.a.update([])
        self.assertEqual(len(self.ch.sent), 1)
        self.assertIn("mientras no podía avisar", self.ch.sent[0])
        self.assertIn("Sin Internet", self.ch.sent[0])

    def test_send_raising_is_a_failed_delivery_not_a_crash(self):
        self.ch.up = "raise"
        self.run_for(30, [NET])                     # must not raise
        self.assertTrue(self.a.state["pending_since"])

    # ---- restarts, persistence ----------------------------------------------------------
    def test_restart_does_not_repeat_alerts(self):
        self.run_for(30, [DISK])
        self.assertEqual(len(self.ch.sent), 1)
        self.run_for(60, [DISK], a=self.new())      # the bot restarted
        self.assertEqual(len(self.ch.sent), 1)
        self.run_for(30, [], a=self.new())          # restarted again, problem solved
        self.assertEqual(len(self.ch.sent), 2)
        self.assertIn("Resuelto", self.ch.sent[1])

    def test_restart_during_confirmation_keeps_counting(self):
        self.a.update([NET]); self.clock.tick()
        b = self.new(); b.update([NET]); self.clock.tick(); b.update([NET])
        self.assertEqual(len(self.ch.sent), 1)

    def test_corrupt_or_missing_state_file_starts_clean(self):
        (self.dir / "alerts.json").write_text("{not json")
        a = self.new()
        self.run_for(30, [DISK], a=a)
        self.assertEqual(len(self.ch.sent), 1)

    def test_unwritable_state_never_raises(self):
        a = alerts.Alerts(self.dir / "missing" / "dir" / "alerts.json", self.ch, now=self.clock)
        self.run_for(30, [DISK], a=a)
        self.assertEqual(len(self.ch.sent), 1)

    def test_state_file_is_written_atomically(self):
        self.run_for(30, [DISK])
        self.assertFalse((self.dir / "alerts.json.tmp").exists())
        self.assertIn("disk", json.loads((self.dir / "alerts.json").read_text())["problems"])

    # ---- content safety -------------------------------------------------------------------
    def test_secrets_are_cleaned_and_html_escaped(self):
        bad = {"id": "x", "level": "broken", "title": "token SECRET <b>", "fix": "a & b"}
        self.run_for(30, [bad])
        msg = self.ch.sent[0]
        self.assertNotIn("SECRET", msg)
        self.assertIn("&lt;b&gt;", msg)
        self.assertIn("a &amp; b", msg)

    def test_long_lists_are_capped(self):
        many = [{"id": f"p{i}", "level": "degraded", "title": "x" * 300} for i in range(40)]
        self.run_for(30, many)
        self.assertLessEqual(len(self.ch.sent[0]), 3800)

    def test_bad_input_is_ignored(self):
        self.run_for(30, [{"id": "", "level": "broken"}, {"id": "y", "level": "weird"}, DISK])
        self.assertEqual(len(self.ch.sent), 1)

    def test_concurrent_updates_send_once(self):
        self.a.update([NET]); self.clock.tick()
        ts = [threading.Thread(target=self.a.update, args=([NET],)) for _ in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(self.ch.sent), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
