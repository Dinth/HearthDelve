"""Three narrow regressions from the code audit.

PROJ-1  proj["ready_at"] was never written, so the notice board and the journal
        both reported "finished in ~1 day" every day of a build.
GIFT-1  "gem" was missing from the gift filter, so Kazrik's loved Cut Diamond
        could never appear in the gift menu.
WT-1    _KIND_WEIGHT covered 10 of the 20 item kinds; the rest fell to a 1.0
        default, so 100 arrows outweighed the entire base carry capacity.
"""
from __future__ import annotations

import unittest

from tests.common import fresh_state

from hearthdelve.data import content
from hearthdelve.entities import items


class ProjectReadyAtTest(unittest.TestCase):
    def test_staking_a_site_records_the_deadline_on_the_project(self):
        from hearthdelve.game import projects
        st = fresh_state(11)
        proj = st.projects[0]
        d = content.PROJECTS[proj["id"]]
        projects._stake_site(st, proj)
        if proj["state"] != "building":
            self.skipTest("no clear ground for this project on this seed")
        self.assertGreater(proj["ready_at"], st.abs_minutes,
                           "ready_at is still 0, so the UI reports ~1 day forever")
        days = round((proj["ready_at"] - st.abs_minutes) / 1440)
        self.assertEqual(days, d.build_days)

    def test_the_site_machine_and_the_record_agree(self):
        from hearthdelve.game import projects
        st = fresh_state(11)
        proj = st.projects[0]
        projects._stake_site(st, proj)
        if proj["state"] != "building":
            self.skipTest("no clear ground for this project on this seed")
        sites = [m for m in st.surface.machines.values()
                 if m.kind == "site" and m.build_kind == proj["id"]]
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].ready_at, proj["ready_at"])


class GiftableGemsTest(unittest.TestCase):
    def test_a_cut_gem_can_be_offered(self):
        from hearthdelve.game import village
        st = fresh_state(5)
        gem = items.by_name("Cut Diamond")
        st.player.inventory.add(gem, 1, quality=3)
        offered = {it.name for it, _q, _ql in village.giftable_items(st)}
        self.assertIn("Cut Diamond", offered)

    def test_every_taste_the_roster_names_is_actually_giftable(self):
        """A loved item the gift menu can't show is unreachable content."""
        from hearthdelve.game import village
        st = fresh_state(5)
        roster = list(st.world.npcs) + list(content.dwarf_npcs())
        unreachable = []
        for n in roster:
            for pool in (n.loves or (), n.likes or ()):
                for g in pool:
                    name = g if isinstance(g, str) else getattr(g, "name", None)
                    it = items.by_name(name) if name else None
                    if it is None:
                        continue
                    st.player.inventory.slots.clear()
                    st.player.inventory.add(it, 1)
                    if not village.giftable_items(st):
                        unreachable.append((n.name, it.name, it.kind))
        self.assertEqual(unreachable, [],
                         f"tastes naming an ungiftable item: {unreachable}")


class KindWeightTest(unittest.TestCase):
    def test_the_weight_table_is_total(self):
        from hearthdelve.game import encumbrance
        kinds = {it.kind for it in items.BY_NAME.values()}
        missing = sorted(kinds - set(encumbrance._KIND_WEIGHT))
        self.assertEqual(missing, [],
                         f"item kinds with no weight, silently defaulting to 1.0: {missing}")

    def test_a_quiver_is_not_heavier_than_the_player(self):
        from hearthdelve.game import encumbrance
        quiver = encumbrance.weight_of(items.ARROW) * 100
        self.assertLess(quiver, encumbrance.CARRY_BASE / 4,
                        f"100 arrows weigh {quiver}, against a base capacity of "
                        f"{encumbrance.CARRY_BASE}")

    def test_a_pumpkin_outweighs_a_minnow(self):
        from hearthdelve.game import encumbrance
        self.assertGreater(encumbrance.weight_of(items.PUMPKIN),
                           encumbrance.weight_of(items.MINNOW))

    def test_a_live_calf_is_the_heaviest_thing_you_can_pick_up(self):
        from hearthdelve.game import encumbrance
        calf = encumbrance.weight_of(items.CALF)
        self.assertGreater(calf, encumbrance.weight_of(items.IRON_BAR))
        self.assertGreater(calf, encumbrance.weight_of(items.PLATE_ARMOR))


if __name__ == "__main__":
    unittest.main()
