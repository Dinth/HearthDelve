"""Economy guard-rails: the >=25% margin rule and outlier ceilings."""
from __future__ import annotations

import unittest

from tests.common import shared_state


def _input_value(inputs) -> int:
    return sum(it.value * q for it, q in inputs)


class TestAlchemyMargins(unittest.TestCase):
    def test_every_remedy_clears_25_percent(self):
        from hearthdelve.data import content
        for r in content.RECIPES:
            if r.kind != "remedy":
                continue
            iv = _input_value(r.inputs)
            ov = r.output.value * r.out_qty
            self.assertGreaterEqual(ov, iv * 1.25,
                                    f"{r.name}: {iv} -> {ov} breaks the margin rule")

    def test_potions_and_vodka_chain(self):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        for inputs, out, oq, _lvl, _mins in content.APOTHECARY_POTIONS:
            iv = _input_value(inputs)
            self.assertGreaterEqual(out.value * oq, iv * 1.25 - 1,
                                    f"{out.name} margin too thin")
        self.assertGreater(items.GRAIN_MASH.value, items.POTATO.value * 1.25)
        self.assertGreater(items.VODKA.value, items.GRAIN_MASH.value * 1.25)

    def test_no_apothecary_gold_printer(self):
        """Guard the Mandrake Elixir regression: no bench good may out-earn the
        game's established top chains (~480 g/day for oil)."""
        from hearthdelve.data import content
        bench = content.MACHINES["apothecary"].minutes
        worst = ("", 0.0)
        for r in content.RECIPES:
            if r.kind != "remedy":
                continue
            gain = (r.output.value * r.out_qty - _input_value(r.inputs)) * 2  # double batch
            per_day = gain * (1440 / bench)
            if per_day > worst[1]:
                worst = (r.name, per_day)
        self.assertLessEqual(worst[1], 500, f"{worst[0]} prints {worst[1]:.0f} g/day")


class TestCraftMargins(unittest.TestCase):
    def test_every_craftable_clears_its_ingredients(self):
        """The value floor: no cook/bench/mill good is worth less than its
        ingredients + 25% (a wildcard input is priced at its cheapest member)."""
        from hearthdelve.data import content
        from hearthdelve.entities import items as I
        all_items = [v for v in vars(I).values() if isinstance(v, I.Item)]

        def fam_min(fam):
            vals = [x.value for x in all_items if getattr(x, "family", "") == fam and x.value > 0]
            return min(vals) if vals else 0

        def ing(inputs):
            return sum((fam_min(it.family) if isinstance(it, content.AnyOf) else it.value) * q
                       for it, q in inputs)

        entries = [(r.name, r.inputs, r.output, r.out_qty) for r in content.RECIPES
                   if r.kind in ("cook", "item", "craft", "remedy") and r.output and r.output.value > 0]
        entries += [(f"mill {s.name}", ((s, 1),), o, 1) for s, o in content.MILL_RECIPES.items()]
        for name, inputs, out, qty in entries:
            iv = ing(inputs)
            if iv <= 0:
                continue
            self.assertGreaterEqual(out.value * qty, iv * content.CRAFT_MARGIN - 0.5,
                                    f"{name}: {out.value}x{qty} < {iv} ingredients +25%")


class TestRequestBoard(unittest.TestCase):
    ROLES = ("innkeeper", "blacksmith", "carpenter", "forester", "forager", "priest",
             "farmer", "fisher", "child", "trader",
             "woodcarver", "bard", "mason", "diver", "trapper")

    def test_every_role_has_a_pool(self):
        from hearthdelve.game import requests
        st = shared_state()
        for role in self.ROLES:
            pool = requests._request_pool(st, role)
            self.assertTrue(pool, f"empty request pool for {role}")
            self.assertTrue(all(p.value > 0 for p in pool),
                            f"{role} pool holds a worthless item")

    def test_every_role_has_a_voice(self):
        from hearthdelve.game.requests import _FLAVOR
        for role in ("woodcarver", "bard", "mason", "diver", "trapper"):
            self.assertIn(role, _FLAVOR)


class TestCollection(unittest.TestCase):
    def test_catalogue_is_donatable_and_sinkable(self):
        from hearthdelve.data import content
        total = sum(len(v) for v in content.COLLECTION.values())
        self.assertEqual(total, len(content.COLLECTED_NAMES))
        self.assertGreaterEqual(total, 60)
        for wing, its in content.COLLECTION.items():
            for it in its:
                self.assertGreater(it.value, 0, f"{it.name} in {wing} is worthless")


class TestEveryWineAFavourAsksForCanBeMade(unittest.TestCase):
    """The diver pinned favours for plain "Wine". Every fruit ferments into its
    own named wine, so plain Wine is never made — a favour needs the exact item,
    and the only bottle that could ever fill it was one a villager gave you."""

    def test_no_favour_asks_for_a_wine_the_keg_never_makes(self):
        from hearthdelve.data import content
        from hearthdelve.engine import constants as C
        from hearthdelve.entities import items
        from hearthdelve.game import requests
        from tests.common import fresh_state
        st = fresh_state(1)
        made = set(content.FRUIT_WINE.values())
        roles = {n.role for n in st.surface.npcs} | {"diver"}
        for season_i, season in enumerate(C.SEASONS):
            st.day = season_i * C.SEASON_LEN
            for role in sorted(roles):
                wines = [it for it in requests._request_pool(st, role)
                         if it is items.WINE or it in made or it.name.endswith(" Wine")]
                with self.subTest(season=season, role=role):
                    self.assertNotIn(items.WINE, wines)
                    self.assertTrue(set(wines) <= made, [w.name for w in wines if w not in made])


class TestTheCellarIsTheQuickerWayToAgeMead(unittest.TestCase):
    """The keg could age mead from before the cellar existed, and at its own
    40-hour pace it beat the 3,500g cellar's 72 hours to the same bottle."""

    def _ages_in(self, kind):
        from hearthdelve.data import content
        from hearthdelve.entities import items
        from hearthdelve.entities.machine import Machine
        from hearthdelve.game import crafting
        from tests.common import fresh_state
        st = fresh_state(2)
        st.player.inventory.add(items.MEAD, 1)
        mdef = content.MACHINES[kind]
        opt = next(o for o in crafting.machine_load_options(st, mdef)
                   if o["output"] is items.AGED_MEAD)
        m = Machine(kind=kind)
        crafting.load_machine_choice(st, m, mdef, opt)
        return m.ready_at - st.abs_minutes

    def test_the_keg_still_can_but_the_cellar_is_quicker(self):
        self.assertGreater(self._ages_in("keg"), self._ages_in("cellar"))


if __name__ == "__main__":
    unittest.main()
