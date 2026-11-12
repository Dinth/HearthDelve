"""Random keys through the real event path: whatever you press, wherever you
stand, the game must not raise — and what it leaves must save and load.

Each scenario is a seeded stream of key presses fed through ``main.route_event``
exactly as the main loop feeds them, with the top screen ticked and drawn in
between. Scenarios differ in where they keep putting the player (the farm, a
shop counter, a dungeon floor, the Westreach, Khazgrim), because random walking
alone almost never reaches a shopkeeper or a boss. A failure prints the seed,
the step and the last keys, so it replays exactly.

``HEARTHDELVE_FUZZ_STEPS`` sets the presses per scenario (default 4000);
``HEARTHDELVE_FUZZ_SEED`` shifts every scenario's seed, for a longer hunt.
"""
from __future__ import annotations

import collections
import os
import random
import tempfile
import traceback
import unittest

import tcod.console
import tcod.event

from tests.common import fresh_state

STEPS = int(os.environ.get("HEARTHDELVE_FUZZ_STEPS", "4000"))
SEED0 = int(os.environ.get("HEARTHDELVE_FUZZ_SEED", "0"))

K = tcod.event.KeySym


def _sym(name):
    return getattr(K, name, None) or getattr(K, name.upper(), None) or getattr(K, name.lower())


LETTERS = [_sym(c) for c in "abcdefghijklmnopqrstuvwxyz"]
MOVES = [K.UP, K.DOWN, K.LEFT, K.RIGHT, K.KP_1, K.KP_2, K.KP_3, K.KP_4, K.KP_5,
         K.KP_6, K.KP_7, K.KP_8, K.KP_9]
MISC = [K.SPACE, K.RETURN, K.ESCAPE, K.TAB, K.PERIOD, K.COMMA, K.LESS, K.SLASH,
        K.PAGEUP, K.PAGEDOWN, K.BACKSPACE, K.MINUS, K.EQUALS,
        K.N0, K.N1, K.N2, K.N3, K.N4, K.N5, K.N6, K.N7, K.N8, K.N9]


def _key(sym, shift=False):
    return tcod.event.KeyDown(scancode=tcod.event.Scancode(0), sym=sym,
                              mod=tcod.event.Modifier.SHIFT if shift else tcod.event.Modifier.NONE)


def _stock(st, rng) -> None:
    """A pack of all sorts, so the pack, gift, craft, eat and equip screens have
    something to act on, and gold enough to buy with."""
    from hearthdelve.entities import items
    pool = sorted((v for v in vars(items).values() if isinstance(v, items.Item)),
                  key=lambda i: i.name)
    for it in rng.sample(pool, min(70, len(pool))):
        st.player.inventory.add(it, rng.randint(1, 4), quality=rng.randint(0, 5))
    st.player.gold += 20_000
    st.known_recipes.update(r.name for r in __import__(
        "hearthdelve.data.content", fromlist=["RECIPES"]).RECIPES if r.kind == "cook")


def _beside(st, x, y, rng) -> bool:
    """Stand the player on a free tile next to (x, y), facing it."""
    w, p = st.world, st.player
    spots = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx or dy)
             and w.walkable(x + dx, y + dy)
             and not any((n.x, n.y) == (x + dx, y + dy) for n in w.npcs)]
    if not spots:
        return False
    dx, dy = rng.choice(spots)
    p.x, p.y, p.facing = x + dx, y + dy, (-dx, -dy)
    return True


GRAB, SHIP, GIFT = (_sym("g"), False), (_sym("b"), False), (_sym("f"), False)
TALK = (_sym("c"), True)


# --- where each scenario keeps putting the player --------------------------------
_YARD = ("keg", "furnace", "preserves_jar", "anvil", "apothecary", "smoker", "loom", "churn")


def _to_farm(st, rng):
    """Home: the yard's machines (set down the first time), the post box with
    a letter in it, the bin, the farm chest, or just the doorstep."""
    from hearthdelve.data import content
    from hearthdelve.entities.machine import Machine
    from hearthdelve.game import commands
    commands._cheat_go(st, st.surface.spawn)
    surf = st.surface
    yard = [pos for pos, m in surf.machines.items() if m.kind in content.MACHINES]
    if not any(surf.machines[pos].kind in _YARD for pos in yard):
        sx, sy = surf.spawn
        free = [(sx + dx, sy + dy) for dx in range(-9, 10, 2) for dy in range(-9, 10, 2)
                if surf.walkable(sx + dx, sy + dy) and (sx + dx, sy + dy) not in surf.machines
                and (sx + dx, sy + dy) not in surf.crops and (dx or dy)]
        for kind, pos in zip([k for k in _YARD if k in content.MACHINES], free):
            surf.machines[pos] = Machine(kind=kind)
        yard = [pos for pos, m in surf.machines.items() if m.kind in content.MACHINES]
    pick = rng.random()
    if pick < 0.55 and yard:
        _beside(st, *rng.choice(yard), rng)
        return GRAB
    if pick < 0.70 and surf.post_box:
        if not st.mail:
            st.mail.append({"sender": "A neighbour", "body": "Thinking of you.\nCome by.",
                            "items": []})
        _beside(st, *surf.post_box, rng)
        return GRAB
    if pick < 0.80 and surf.bin:
        _beside(st, *surf.bin, rng)
        return SHIP
    return None


def _to_a_counter(st, rng):
    """Beside someone who trades — or a notice board, the bin, the post box."""
    from hearthdelve.game import commands
    from hearthdelve.world import tile
    import numpy as np
    commands._cheat_go(st, st.surface.spawn)
    surf = st.surface
    pick = rng.random()
    if pick < 0.7:
        folk = [n for n in surf.npcs] if pick < 0.25 else [
            n for n in surf.npcs if n.role in ("innkeeper", "shopkeeper", "blacksmith",
                                               "trader", "carpenter", "priest")]
        n = rng.choice(folk)
        n.met = True
        _beside(st, n.x, n.y, rng)
        return TALK if rng.random() < 0.7 else GIFT
    if pick < 0.85:
        boards = np.argwhere(surf.tiles == tile.NOTICE_BOARD)
        _beside(st, *map(int, boards[rng.randrange(len(boards))]), rng)
        return GRAB
    _beside(st, *surf.bin, rng)
    return SHIP


def _to_the_deeps(st, rng):
    from hearthdelve.game import commands, delve
    mouth = rng.choice(st.surface.dungeons)
    commands._cheat_go(st, mouth)
    for _ in range(rng.choice((0, 1, 2, 4, 9, 10, 19))):      # the tenths are sanctums
        delve.descend(st)
    foes = [m for m in st.world.monsters if m.alive]
    if foes and rng.random() < 0.6:                            # go and find the fight
        m = rng.choice(foes)
        _beside(st, m.x, m.y, rng)
        delve.update_fov(st)
    return None


def _to_the_west(st, rng):
    from hearthdelve.game import commands
    from hearthdelve.game import lift
    commands._cheat_go(st, rng.choice(("west:volcano", "west:khazgrim")))
    cage = lift.station(st.world) if st.world.is_dungeon else None
    if cage is not None and rng.random() < 0.3:
        st.stats["dwarfhold_deepest"] = max(st.stats.get("dwarfhold_deepest", 0), 25)
        _beside(st, *cage, rng)
        return GRAB
    if st.world.npcs and rng.random() < 0.8:
        n = rng.choice(st.world.npcs)
        _beside(st, n.x, n.y, rng)
        return TALK if rng.random() < 0.7 else GIFT
    return None


SCENARIOS = {"farm": _to_farm, "counter": _to_a_counter, "deeps": _to_the_deeps,
             "west": _to_the_west}
HOP_EVERY = {"farm": 90, "counter": 60, "deeps": 400, "west": 150}


def fuzz(scenario: str, seed: int, steps: int = STEPS):
    """Run one scenario. Returns None, or (step, traceback, recent keys)."""
    from hearthdelve import main, screens
    from hearthdelve.engine import constants as C, rendering, save
    from hearthdelve.game import farming
    rng = random.Random(seed)
    random.seed(seed)                                  # the game's own dice, pinned too
    st = fresh_state(5 + seed % 3)
    st.chargen_pending = False
    _stock(st, rng)
    ui = screens.UI(st, None)
    con = tcod.console.Console(C.SCREEN_W, C.SCREEN_H, order="F")
    path = os.path.join(tempfile.mkdtemp(prefix="hd-fuzz-"), "s.json")
    recent = collections.deque(maxlen=30)
    place, hop = SCENARIOS[scenario], HOP_EVERY[scenario]
    t = 0.0
    i = -1
    first = None
    try:
        for i in range(steps):
            if i % hop == 0:
                while len(ui.stack) > 1:               # back to the world before moving
                    ui.pop()
                first = place(st, rng)             # ...and the key that uses what's there
                recent.append(("-> placed", scenario, (st.player.x, st.player.y), st.depth))
            if i % 400 == 0:                           # keep the fuzz alive, fed and solvent
                st.player.hp, st.player.energy = st.player.max_hp, st.player.max_energy
            if i % 1300 == 1299 and not st.world.is_dungeon and st.world is st.surface:
                farming.sleep(st)                      # let days turn: dawn does a lot
                recent.append(("-> slept", st.day))
            r = rng.random()
            top = type(ui.top).__name__
            if first is not None:
                (sym, shift), first = first, None
            elif top != "PlayScreen" and r < 0.10:
                sym, shift = K.ESCAPE, False
            elif top != "PlayScreen" and r < 0.45:     # work the menu that's open
                sym, shift = rng.choice((K.RETURN, K.UP, K.DOWN, K.LEFT, K.RIGHT, K.TAB,
                                         K.RETURN, K.SPACE)), False
            elif r < 0.55:
                sym, shift = rng.choice(MOVES), False
            elif scenario != "deeps" and r < 0.70:     # talk, gift, grab, ship
                sym, shift = rng.choice(((_sym("c"), True), (_sym("f"), False),
                                         (_sym("g"), False), (_sym("g"), False),
                                         (_sym("b"), False)))
            elif r < 0.88:
                sym, shift = rng.choice(LETTERS), rng.random() < 0.12
            else:
                sym, shift = rng.choice(MISC), rng.random() < 0.2
            recent.append((top, sym.name, shift))
            main.route_event(ui, _key(sym, shift), [])
            ui.running = True                          # a quit is just another key here
            ui.input_lock_until = 0
            for _ in range(2):
                ui.top.tick(ui)
            if i % 5 == 0:
                t += 0.21
                rendering.render_all(con, st, t)
                ui.top.render(ui, con)
            if i % 900 == 899:                         # what it leaves must save and load
                save.save(st, path)
                again = save.load(path)
                save.save(again, path + ".2")
                recent.append(("-> saved and loaded",))
    except Exception:                                  # noqa: BLE001 - the whole point
        return i, traceback.format_exc(), list(recent)
    return None


class TestRandomKeysNeverCrashTheGame(unittest.TestCase):
    def _run(self, scenario, seed):
        seed += SEED0
        hit = fuzz(scenario, seed)
        if hit is not None:
            step, tb, recent = hit
            self.fail(f"fuzz '{scenario}' seed {seed} crashed at key {step} of {STEPS}:\n{tb}\n"
                      "the last keys (screen, key, shift):\n  "
                      + "\n  ".join(map(str, recent)))

    def test_about_the_farm(self):
        self._run("farm", 101)

    def test_at_every_counter_and_board(self):
        self._run("counter", 202)

    def test_down_in_the_deeps(self):
        self._run("deeps", 303)

    def test_out_west_and_in_khazgrim(self):
        self._run("west", 404)


if __name__ == "__main__":
    unittest.main()
