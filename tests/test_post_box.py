"""The farm has a post box, and its letters can be opened."""
from __future__ import annotations

import os
import tempfile
import unittest

import numpy as np

from tests.common import fresh_state


class TestTheFarmHasAPostBox(unittest.TestCase):
    """The road home arrives right where the post box stands, and paved over
    it — in every world. With no box, no letter could ever be opened:
    festival invitations, friends' gifts, the tax notice you settle there."""

    def test_it_stands_where_the_world_says_it_does(self):
        from hearthdelve.world import tile, worldgen
        for seed in (5, 1337):
            gm = worldgen.generate(seed)
            with self.subTest(seed=seed):
                self.assertEqual([tuple(map(int, p)) for p in np.argwhere(gm.tiles == tile.POST_BOX)],
                                 [gm.post_box])
                x, y = gm.post_box
                self.assertTrue(any(gm.walkable(x + dx, y + dy)
                                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)))

    def test_a_letter_opens_from_it(self):
        from hearthdelve import main, screens
        from tests.test_fuzz import GRAB, _beside, _key
        import random
        st = fresh_state(5)
        st.chargen_pending = False
        st.mail.append({"sender": "A neighbour", "body": "Come by.", "items": []})
        self.assertTrue(_beside(st, *st.surface.post_box, random.Random(1)))
        ui = screens.UI(st, None)
        main.route_event(ui, _key(*GRAB), [])
        self.assertIsInstance(ui.top, screens.MailScreen)

    def test_an_old_save_gets_its_box_back(self):
        from hearthdelve.engine import save
        from hearthdelve.world import tile
        st = fresh_state(5)
        box = st.surface.post_box
        st.surface.tiles[box] = tile.ROAD                # as every older world had it
        path = os.path.join(tempfile.mkdtemp(prefix="hd-box-"), "s.json")
        save.save(st, path)
        self.assertEqual(save.load(path).surface.tiles[box], tile.POST_BOX)

    def test_but_never_over_something_the_player_put_there(self):
        from hearthdelve.engine import save
        from hearthdelve.world import tile
        st = fresh_state(5)
        box = st.surface.post_box
        st.surface.tiles[box] = tile.FENCE
        path = os.path.join(tempfile.mkdtemp(prefix="hd-box-"), "s.json")
        save.save(st, path)
        self.assertEqual(save.load(path).surface.tiles[box], tile.FENCE)


if __name__ == "__main__":
    unittest.main()
