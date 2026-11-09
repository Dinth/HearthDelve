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
        self.assertEqual(set(days), {n.name for n in st.surface.npcs}
                         | {n.name for n in content.dwarf_npcs()})
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
        """Every one of them says so in as many words — whoever's day it is."""
        from hearthdelve.game import village
        for npc in fresh_state(2).surface.npcs:
            st = fresh_state(2)
            npc = next(n for n in st.surface.npcs if n.name == npc.name)
            _on_their_birthday(st, npc)
            with self.subTest(npc=npc.name):
                self.assertIn("birthday", village.talk(st, npc).lower())

    def test_the_dawn_names_a_friend_s_birthday(self):
        from hearthdelve.game import farming
        st = fresh_state(2)
        npc = st.surface.npcs[0]
        npc.met = True
        _on_their_birthday(st, npc).day -= 1                  # the night before
        farming.sleep(st)
        self.assertTrue(any(f"{npc.name}'s birthday" in m for m, _c in st.log.messages))



class TestTheDwarvesHaveBirthdaysToo(unittest.TestCase):
    """Only the surface villagers had birthdays; Khazgrim's dwarves, who take
    gifts and remember a friend like anyone, had none."""

    def _dwarves(self):
        from hearthdelve.data import content
        st = fresh_state(2)
        st.dwarves = content.dwarf_npcs()
        return st

    def test_every_dwarf_has_one_of_his_own(self):
        from hearthdelve.game import village
        st = self._dwarves()
        days = village.birthdays(st)
        for d in st.dwarves:
            self.assertIn(d.name, days)
        self.assertEqual(len(set(days.values())), len(days))       # still one to a day

    def test_they_re_fixed_before_you_ever_meet_them(self):
        from hearthdelve.game import village
        st = fresh_state(2)
        self.assertIsNone(st.dwarves)
        self.assertEqual(village.birthdays(st), village.birthdays(self._dwarves()))

    def test_a_gift_on_a_dwarf_s_birthday_counts_triple_and_he_says_so(self):
        from hearthdelve.game import village
        st = self._dwarves()
        dwarf = st.dwarves[0]
        _on_their_birthday(st, dwarf)
        self.assertIn("birthday", village.talk(st, dwarf).lower())
        item = dwarf.loves[0]
        st.player.inventory.add(item, 1)
        before = dwarf.friendship
        village.gift(st, dwarf, item)
        self.assertTrue(any("birthday" in m for m, _c in st.log.messages))
        self.assertGreater(dwarf.friendship - before, 0)

    def test_the_dawn_names_a_dwarf_friend_s_birthday(self):
        from hearthdelve.game import farming
        st = self._dwarves()
        dwarf = st.dwarves[1]
        dwarf.met = True
        _on_their_birthday(st, dwarf).day -= 1
        farming.sleep(st)
        self.assertTrue(any(f"{dwarf.name}'s birthday" in m and "Khazgrim" in m
                            for m, _c in st.log.messages))


class TestTheAlmanac(unittest.TestCase):
    """Festivals, birthdays and tomorrow's sky were scattered across chats and
    log lines that scrolled away. The journal now keeps an almanac."""

    def _almanac(self, st):
        from hearthdelve.engine import rendering
        tab = rendering._JOURNAL_TABS.index("Almanac")
        con = tcod.console.Console(80, 50, order="F")
        rendering.render_journal(con, st, tab)
        return "\n".join("".join(chr(c) for c in con.ch[:, y]) for y in range(50))

    def test_it_marks_the_season_s_festivals_and_what_s_coming(self):
        from hearthdelve.data import content
        from hearthdelve.engine import constants as C
        st = fresh_state(2)
        season, fests = next((s, f) for s, f in content.FESTIVALS.items() if f)
        day = fests[0][0]
        st.day = C.SEASONS.index(season) * C.SEASON_LEN + day - 4      # three days before
        text = self._almanac(st)
        self.assertIn("★", text)
        self.assertIn(f"{fests[0][1]} (in 3 days)", text)

    def test_it_lists_a_birthday_coming_up(self):
        from hearthdelve.game import village
        st = fresh_state(2)
        npc = st.surface.npcs[0]
        _on_their_birthday(st, npc).day -= 2
        self.assertIn(f"{npc.name}'s birthday (in 2 days)", self._almanac(st))

    def test_tomorrow_s_sky_shows_once_you_ve_read_it(self):
        from hearthdelve.game import farming, village
        st = fresh_state(2)
        saying = farming.weather_saying(farming.forecast(st))
        self.assertNotIn(saying[:30], self._almanac(st))
        elder = next(n for n in st.surface.npcs if n.role in ("fisher", "forager", "forester", "elder"))
        elder.talked_today = True
        village.talk(st, elder)
        self.assertIn(saying[:30], self._almanac(st))
        st.day += 1                                            # a new day: it's tomorrow's again
        self.assertIn("Unread", self._almanac(st))


if __name__ == "__main__":
    unittest.main()
