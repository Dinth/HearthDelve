"""The game starts: the same one-frame check the release builds run."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest


class TestTheGameStarts(unittest.TestCase):
    def test_a_headless_start_draws_a_frame(self):
        """HEARTHDELVE_SMOKETEST=headless loads the font and every module,
        builds a world and draws one frame without opening a window — what
        CI runs against each packaged binary before publishing it."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        save = os.path.join(tempfile.mkdtemp(prefix="hd-smoke-"), "s.json")
        env = dict(os.environ, HEARTHDELVE_SMOKETEST="headless", HEARTHDELVE_SAVE=save)
        run = subprocess.run([sys.executable, "-m", "hearthdelve"], cwd=root, env=env,
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        self.assertIn("smoketest ok", run.stdout)


if __name__ == "__main__":
    unittest.main()
