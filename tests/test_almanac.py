"""Villager birthdays, and the journal's almanac."""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _on_their_birthday(st, npc):
    from hearthdelve.engine import constants as C
    from hearthdelve.game import village
    season, day = village.birthdays(st)[npc.name]
    st.day = C.SEASONS.index(season) * C.SEASON_LEN + day - 1
    return st


class TestVillagersHaveBirthdays(unittest.TestCase):
    """Villagers had no birthdays: every day was the same to them."""

    def test_every_villager_has_one_and_no_two_share(self):
        from hearthdelve.data import content
        from hearthdelve.game import village
        st = fresh_state(2)
        days = village.birthdays(st)
        self.assertEqual(set(days), {n.name for n in st.surface.npcs})
        self.assertEqual(len(set(days.values())), len(days))
        for season, day in days.values():
            self.assertIsNone(content.festival_on(season, day), "a birthday on a festival")

    def test_they_come_from_the_seed_and_survive_a_reload(self):
        import os
        import tempfile
        from hearthdelve.engine import save
        from hearthdelve.game import village
        st = fresh_state(2)
        self.assertEqual(village.birthdays(st), village.birthdays(fresh_state(2)))
        self.assertNotEqual(village.birthdays(st), village.birthdays(fresh_state(3)))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "save.json")
            save.save(st, path)
            back = save.load(path)
        self.assertEqual(village.birthdays(back), village.birthdays(st))

    def test_a_kind_gift_on_their_birthday_means_three_times_as_much(self):
        from hearthdelve.game import village
        def gain(birthday):
            st = fresh_state(2)
            npc = st.surface.npcs[0]
            if birthday:
                _on_their_birthday(st, npc)
            else:
                _on_their_birthday(st, npc).day += 1
            item = npc.loves[0]
            st.player.inventory.add(item, 1)
            before = npc.friendship
            village.gift(st, npc, item)
            return npc.friendship - before, st
        plain, _ = gain(False)
        warm, st = gain(True)
        self.assertGreater(plain, 0)
        self.assertEqual(warm, min(village.MAX_HEARTS * 100, plain * village.BIRTHDAY_GIFT_MULT))
        self.assertTrue(any("birthday" in m for m, _c in st.log.messages))

    def test_they_tell_you_on_the_day(self):
        from hearthdelve.game import village
        st = fresh_state(2)
        npc = next(n for n in st.surface.npcs if n.role not in ("fisher", "forager", "forester", "elder"))
        _on_their_birthday(st, npc)
        self.assertIn("birthday", village.talk(st, npc).lower())

    def test_the_dawn_names_a_friend_s_birthday(self):
        from hearthdelve.game import farming
        st = fresh_state(2)
        npc = st.surface.npcs[0]
        npc.met = True
        _on_their_birthday(st, npc).day -= 1                  # the night before
        farming.sleep(st)
        self.assertTrue(any(f"{npc.name}'s birthday" in m for m, _c in st.log.messages))



if __name__ == "__main__":
    unittest.main()
