"""Bounties: the notice board asks for a culling as well as goods."""
from __future__ import annotations

import os
import random
import tempfile
import unittest

from tests.common import fresh_state


def _bounty(st, seed=1):
    from hearthdelve.game import requests
    for s in range(seed, seed + 50):
        b = requests._new_bounty(st, random.Random(s))
        if b:
            return b
    raise AssertionError("no bounty could be posted")


class TestBounties(unittest.TestCase):
    """The board only ever asked for goods; a fighter had nothing to answer."""

    def test_a_newcomer_is_sent_after_what_lives_on_the_first_floor(self):
        from hearthdelve.data import content
        st = fresh_state(211)
        first = {m.name for m in content.MONSTERS if m.min_depth <= 1}
        for seed in range(1, 30):
            self.assertIn(_bounty(st, seed)["bounty"], first)

    def test_a_deep_delver_is_asked_for_deep_things(self):
        from hearthdelve.data import content
        from hearthdelve.game import requests
        st = fresh_state(211)
        st.stats["deepest_depth"] = 10
        depth = {m.name: m.min_depth for m in content.MONSTERS}
        for seed in range(1, 30):
            d = depth[_bounty(st, seed)["bounty"]]
            self.assertTrue(10 - requests.BOUNTY_REACH <= d <= 10, d)

    def test_only_kills_after_it_was_pinned_count(self):
        from hearthdelve.game import requests
        st = fresh_state(211)
        st.bestiary["Bat"] = 40
        st.bestiary["Cave Slime"] = 40
        b = _bounty(st)
        self.assertEqual(requests.progress(st, b), 0)
        self.assertFalse(requests.can_fulfil(st, b))
        st.bestiary[b["bounty"]] += b["qty"] - 1
        self.assertFalse(requests.can_fulfil(st, b))
        st.bestiary[b["bounty"]] += 1
        self.assertTrue(requests.can_fulfil(st, b))

    def test_a_real_kill_moves_the_tally(self):
        from hearthdelve.entities.monster import Mob
        from hearthdelve.game import combat, requests
        st = fresh_state(211)
        b = _bounty(st)
        m = Mob(b["bounty"], "x", (200, 200, 200), 1, 1, 1, "chase", st.player.x + 1,
                st.player.y, base=b["bounty"])
        st.world.monsters.append(m)
        m.hp = 0
        combat._on_kill(st, m)
        self.assertEqual(requests.progress(st, b), 1)

    def test_reporting_it_pays_and_warms_the_poster(self):
        from hearthdelve.game import requests
        st = fresh_state(211)
        b = _bounty(st)
        st.requests.append(b)
        npc = requests._find_npc(st, b["npc"])
        gold, warmth = st.player.gold, npc.friendship
        self.assertFalse(requests.deliver(st, b))                # nothing slain yet
        self.assertIn(b, st.requests)
        st.bestiary[b["bounty"]] = b["from"] + b["qty"]
        self.assertTrue(requests.deliver(st, b))
        self.assertEqual(st.player.gold, gold + b["gold"])
        self.assertGreater(npc.friendship, warmth)
        self.assertNotIn(b, st.requests)

    def test_one_bounty_at_a_time(self):
        from hearthdelve.game import requests
        st = fresh_state(211)
        st.requests.append(_bounty(st))
        for seed in range(40):
            self.assertIsNone(requests._new_bounty(st, random.Random(seed)))

    def test_deeper_marks_pay_more(self):
        from hearthdelve.data import content
        shallow, deep = fresh_state(211), fresh_state(211)
        deep.stats["deepest_depth"] = 10
        per = lambda st: sum(_bounty(st, s)["gold"] / _bounty(st, s)["qty"] for s in range(1, 20))
        self.assertGreater(per(deep), per(shallow) * 2)

    def test_the_board_words_it_as_a_culling(self):
        from hearthdelve.game import requests
        st = fresh_state(211)
        b = _bounty(st)
        self.assertTrue(requests.want_text(b).startswith("slay "))
        self.assertEqual(requests.want_text({"qty": 2, "item": "Honey"}), "2 Honey")

    def test_goods_favours_are_as_they_were(self):
        from hearthdelve.entities import items
        from hearthdelve.game import requests
        st = fresh_state(211)
        req = {"npc": st.surface.npcs[0].name, "item": "Honey", "qty": 2, "gold": 100,
               "expires": 9, "flavor": ""}
        self.assertEqual(requests.progress(st, req), 0)
        st.player.inventory.add(items.HONEY, 2)
        self.assertEqual(requests.progress(st, req), 2)
        self.assertTrue(requests.can_fulfil(st, req))

    def test_a_bounty_survives_a_save(self):
        from hearthdelve.engine import save
        st = fresh_state(211)
        b = _bounty(st)
        st.requests.append(b)
        path = os.path.join(tempfile.mkdtemp(), "b.sav")
        save.save(st, path)
        back = save.load(path)
        self.assertEqual([r for r in back.requests if r.get("bounty")], [b])

    def test_the_board_draws_with_one_pinned(self):
        import tcod
        from hearthdelve.engine import constants as C, screens_render
        st = fresh_state(211)
        st.requests.append(_bounty(st))
        con = tcod.console.Console(C.SCREEN_W, C.SCREEN_H, order="F")
        screens_render.render_requests(con, st, 0, "Mossford")
        text = "".join(chr(c) for c in con.rgb["ch"].T.flatten())
        self.assertIn("slay", text)
        self.assertIn("slain", text)


if __name__ == "__main__":
    unittest.main()
