"""Only the running game writes the player's real save."""
from __future__ import annotations

import datetime
import os
import tempfile
import unittest
from unittest import mock

from tests.common import fresh_state


class TestOnlyTheGameWritesTheRealSave(unittest.TestCase):
    """A script that built a state and slept three nights autosaved over the
    player's real farm at each dawn — and the second dawn rolled the only
    ``.bak`` away with it."""

    def setUp(self):
        from hearthdelve.engine import save
        self.save = save
        self.dir = tempfile.mkdtemp(prefix="hd-real-")
        self.real = os.path.join(self.dir, "real.json")
        env = {k: v for k, v in os.environ.items() if k != "HEARTHDELVE_SAVE"}
        for p in (mock.patch.dict(os.environ, env, clear=True),
                  mock.patch.object(save, "SAVE_PATH", self.real),
                  mock.patch.object(save, "_ARMED", False)):
            p.start()
            self.addCleanup(p.stop)

    def test_a_dawn_outside_the_game_leaves_the_real_save_alone(self):
        from hearthdelve.game import farming
        with open(self.real, "w") as f:
            f.write("the player's farm")
        st = fresh_state(5)
        farming.new_day(st)
        farming.new_day(st)
        with open(self.real) as f:
            self.assertEqual(f.read(), "the player's farm")
        self.assertFalse(os.path.exists(self.real + ".bak"))
        self.assertFalse([m for m, _c in st.log.messages if "FAILED" in m])

    def test_saving_or_deleting_it_outright_is_refused(self):
        st = fresh_state(5)
        with self.assertRaises(self.save.SaveNotArmedError):
            self.save.save(st)
        with self.assertRaises(self.save.SaveNotArmedError):
            self.save.delete()
        self.assertFalse(os.path.exists(self.real))

    def test_the_game_itself_and_a_named_path_still_save(self):
        st = fresh_state(5)
        elsewhere = os.path.join(self.dir, "elsewhere.json")
        self.save.save(st, elsewhere)                    # a path given outright
        self.assertTrue(os.path.isfile(elsewhere))
        self.save.arm()                                  # what main() does
        self.save.save(st)
        self.assertEqual(self.save.load().seed, 5)

    def test_an_earlier_days_backup_is_set_aside_not_rolled_away(self):
        st = fresh_state(5)
        path = os.path.join(self.dir, "s.json")
        self.save.save(st, path)
        self.save.save(st, path)                         # now there is a .bak
        three_days_ago = datetime.datetime.now() - datetime.timedelta(days=3)
        os.utime(path + ".bak", (three_days_ago.timestamp(),) * 2)
        self.save.save(st, path)
        dated = f"{path}.bak.{three_days_ago.date().isoformat()}"
        self.assertTrue(os.path.isfile(dated))
        self.assertTrue(os.path.isfile(path + ".bak"))   # and today's rolls as ever
        self.save.save(st, path)                         # same day: nothing new set aside
        self.assertEqual(len([n for n in os.listdir(self.dir) if ".bak." in n]), 1)

    def test_only_the_newest_dated_backups_are_kept(self):
        st = fresh_state(5)
        path = os.path.join(self.dir, "s.json")
        self.save.save(st, path)
        for back in range(self.save.DATED_BACKUPS + 4, 0, -1):
            self.save.save(st, path)
            then = (datetime.datetime.now() - datetime.timedelta(days=back)).timestamp()
            os.utime(path + ".bak", (then, then))
        self.save.save(st, path)
        dated = sorted(n for n in os.listdir(self.dir) if ".bak." in n)
        self.assertEqual(len(dated), self.save.DATED_BACKUPS)
        newest = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        self.assertTrue(dated[-1].endswith(newest))


if __name__ == "__main__":
    unittest.main()
