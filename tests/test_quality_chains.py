"""A good's stars carry through every step of its chain.

The spinning wheel and the loom, and the keg and the still, all passed their
input's quality along (``quality_from``) — but a step whose output wasn't a
star-bearing kind always came out at 0 stars, and thread, yarn and grain mash
are plain materials. So a 5-star cotton crop spun 0-star thread and wove 0-star
cloth, and the finest barley distilled into ordinary vodka.
"""
from __future__ import annotations

import random
import unittest

from tests.common import fresh_state


def _process(st, kind, item, quality):
    """Load one ``item`` of ``quality`` into a fresh ``kind`` machine and return
    the quality its output will come out at."""
    from hearthdelve.data import content
    from hearthdelve.entities.machine import Machine
    from hearthdelve.game import crafting
    mdef = content.MACHINES[kind]
    st.player.inventory.add(item, 4, quality=quality)
    opt = next(o for o in crafting.machine_load_options(st, mdef)
               if o["inputs"][0][0] is item)
    m = Machine(kind=kind)
    crafting.load_machine_choice(st, m, mdef, opt)
    return m.loaded_output, m.out_quality


class TestStarsCarryThroughTheChain(unittest.TestCase):
    def setUp(self):
        random.seed(5)
        self.st = fresh_state(2)

    def test_fine_cotton_spins_fine_thread_and_weaves_fine_cloth(self):
        from hearthdelve.entities import items
        thread, q_thread = _process(self.st, "spinner", items.COTTON, 5)
        self.assertIs(thread, items.COTTON_YARN)
        self.assertGreaterEqual(q_thread, 4)
        cloth, q_cloth = _process(self.st, "loom", thread, q_thread)
        self.assertIs(cloth, items.COTTON_CLOTH)
        self.assertGreaterEqual(q_cloth, 3)

    def test_fine_barley_ferments_fine_mash_and_distils_fine_vodka(self):
        from hearthdelve.entities import items
        mash, q_mash = _process(self.st, "keg", items.BARLEY, 5)
        self.assertIs(mash, items.GRAIN_MASH)
        self.assertGreaterEqual(q_mash, 4)
        vodka, q_vodka = _process(self.st, "apothecary", mash, q_mash)
        self.assertIs(vodka, items.VODKA)
        self.assertGreaterEqual(q_vodka, 3)

    def test_a_plain_crop_still_makes_plain_thread(self):
        from hearthdelve.entities import items
        _thread, q = _process(self.st, "spinner", items.FLAX, 0)
        self.assertLessEqual(q, 1)

    def test_every_yarn_and_the_mash_bear_stars(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.game import skills
        for it in list(content.SPIN_RECIPES.values()) + [items.GRAIN_MASH]:
            self.assertTrue(skills.has_quality(it), it.name)


if __name__ == "__main__":
    unittest.main()
