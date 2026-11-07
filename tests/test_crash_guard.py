"""A crash must not cost the player their day.

The main loop had no guard: an exception raised out of any screen skipped the
save-on-exit entirely, losing everything since the dawn autosave, and packaged
builds launched from a file manager left no trace of what went wrong.
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests.common import fresh_state


class TestRunGuarded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = fresh_state(7)

    def setUp(self):
        from hearthdelve import screens
        self.dir = tempfile.mkdtemp(prefix="hd-crash-")
        self.path = os.path.join(self.dir, "save.json")
        self.env = mock.patch.dict(os.environ, {"HEARTHDELVE_SAVE": self.path})
        self.env.start()
        self.err = contextlib.redirect_stderr(io.StringIO())   # the crash notice
        self.err.__enter__()
        self.st.player.gold = 4321
        self.ui = screens.UI(self.st)

    def tearDown(self):
        self.err.__exit__(None, None, None)
        self.env.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _boom(self):
        raise RuntimeError("a screen fell over")

    def _log(self) -> str:
        from hearthdelve import main
        with open(main.crash_report_path(), encoding="utf-8") as f:
            return f.read()

    def test_a_crash_still_saves_the_day_and_leaves_a_report(self):
        from hearthdelve import main
        from hearthdelve.engine import save
        with self.assertRaises(RuntimeError):
            main.run_guarded(self.ui, self._boom)
        self.assertEqual(save.load(self.path).player.gold, 4321)
        log = self._log()
        self.assertIn("RuntimeError: a screen fell over", log)
        self.assertIn("_boom", log)
        self.assertIn("saved on the way out", log)

    def test_quit_without_saving_is_still_honoured(self):
        from hearthdelve import main
        self.ui.save_on_exit = False
        with self.assertRaises(RuntimeError):
            main.run_guarded(self.ui, self._boom)
        self.assertFalse(os.path.isfile(self.path))
        self.assertIn("quit without saving", self._log())

    def test_a_clean_exit_saves_and_writes_no_report(self):
        from hearthdelve import main
        from hearthdelve.engine import save
        main.run_guarded(self.ui, lambda: None)
        self.assertEqual(save.load(self.path).player.gold, 4321)
        self.assertFalse(os.path.isfile(main.crash_report_path()))

    def test_ctrl_c_saves_without_calling_it_a_crash(self):
        from hearthdelve import main

        def interrupted():
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            main.run_guarded(self.ui, interrupted)
        self.assertTrue(os.path.isfile(self.path))
        self.assertFalse(os.path.isfile(main.crash_report_path()))

    def test_a_failed_rescue_save_is_reported_not_hidden(self):
        from hearthdelve import main
        from hearthdelve.engine import save
        with mock.patch.object(save, "save", side_effect=OSError("disk full")):
            with self.assertRaises(RuntimeError):      # the crash, not the save error
                main.run_guarded(self.ui, self._boom)
        self.assertIn("rescue save FAILED", self._log())
        self.assertIn("disk full", self._log())


if __name__ == "__main__":
    unittest.main()
