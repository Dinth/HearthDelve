"""Crafting, building machines, machine interaction, and selling.

Recipes either *build* a machine (placed on the faced tile) or *cook* a dish
(consumed immediately for energy). Placed machines process a loaded input over
in-game time; the player loads/collects by interacting (g) while facing them.
"""
from __future__ import annotations

from ..data import content
from ..data.content import MACHINES, Recipe
from ..engine import constants as C
from ..entities import items
from ..entities.machine import Machine
from ..world import tile
from .state import GameState


# --- helpers ----------------------------------------------------------------
def _resolve_any(inv, it, qty):
    """A concrete carried item satisfying a family input (cheapest cut first),
    the item itself when it's already concrete, or None when nothing fits."""
    if not isinstance(it, content.AnyOf):
        return it
    cands = sorted({e[0] for e in inv.slots
                    if e[0].family == it.family and inv.count(e[0]) >= qty},
                   key=lambda i: i.value)
    return cands[0] if cands else None


def resolve_inputs(inv, inputs):
    """Recipe inputs with every AnyOf pinned to a real carried item — so the
    rest of crafting (counts, quality, removal) never sees a family wildcard.
    None when some input can't be satisfied."""
    out = []
    for it, qty in inputs:
        r = _resolve_any(inv, it, qty)
        if r is None:
            return None
        out.append((r, qty))
    return out


def has_inputs(state: GameState, recipe: Recipe) -> bool:
    inv = state.player.inventory
    resolved = resolve_inputs(inv, recipe.inputs)
    return resolved is not None and all(inv.count(it) >= qty for it, qty in resolved)


def inputs_str(recipe: Recipe) -> str:
    return ", ".join(f"{qty} {it.name}" for it, qty in recipe.inputs)


def _fmt_remaining(minutes: int) -> str:
    if minutes <= 0:
        return "ready"
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


# --- crafting ---------------------------------------------------------------
def visible_recipes(state: GameState) -> list:
    """The recipes the craft menu shows: everything buildable/craftable, plus
    only the cook recipes the player has actually learned (see game.requests)."""
    def shown(r):
        if r.kind == "remedy":                     # remedies are brewed at the apothecary, not by hand
            return False
        if r.kind == "cook":                       # learned dishes only
            return r.name in state.known_recipes
        if r.kind == "upgrade":                    # only the next carry tier
            req, _ = content.PACK_UPGRADES.get(r.name, (0, 0))
            return getattr(state, "pack_bonus", 0) == req
        return True
    return [r for r in content.RECIPES if shown(r)]


def craft(state: GameState, recipe: Recipe) -> bool:
    """Execute a recipe. Returns True if it happened."""
    if recipe.kind == "remedy":
        state.log.add("Remedies are brewed at an apothecary bench, not by hand.", C.DIM)
        return False
    if recipe.kind == "cook" and recipe.name not in state.known_recipes:
        state.log.add("You don't know that recipe yet.", C.DIM)
        return False
    if not has_inputs(state, recipe):
        state.log.add(f"You need: {inputs_str(recipe)}.", C.DIM)
        return False
    # Pin any family inputs ("any meat") to real carried items before spending.
    inputs = resolve_inputs(state.player.inventory, recipe.inputs)

    from . import skills
    if recipe.kind == "build":
        if not _place_machine(state, recipe.machine):
            return False
        for it, qty in inputs:
            state.player.inventory.remove(it, qty)
    elif recipe.kind == "cook":
        # Cooking makes a carryable DISH whose quality inherits the average
        # ingredient quality, adjusted by the cook's skill. Eat it later.
        inv = state.player.inventory
        qs = [inv.pop_quality(it, qty) for it, qty in inputs]
        dish_q = skills.process_quality(sum(qs) / len(qs) if qs else 0, state, "Cooking")
        inv.add(recipe.output, recipe.out_qty, quality=dish_q)
        skills.gain(state, "Cooking", 14)
        state.bump("dishes_cooked")
        star = (" " + skills.stars(dish_q)) if dish_q else ""
        state.log.add(f"You cook {recipe.name}{star}.", (180, 230, 160))
        from . import requests
        requests.check_level_recipes(state)   # practice may spark a new recipe
    elif recipe.kind == "upgrade":
        # A carry upgrade: the craft itself raises capacity (no item to hold).
        _, new_bonus = content.PACK_UPGRADES[recipe.name]
        state.pack_bonus = new_bonus
        for it, qty in inputs:
            state.player.inventory.remove(it, qty)
        state.log.add(f"You stitch up the {recipe.output.name.lower()} — "
                      "you can shoulder a good deal more now.", (200, 220, 160))
    elif recipe.kind == "item":
        state.player.inventory.add(recipe.output, recipe.out_qty)
        state.log.add(f"You craft {recipe.out_qty}x {recipe.output.name}.")
        for it, qty in inputs:
            state.player.inventory.remove(it, qty)
    else:
        return False        # "choose" recipes are resolved via a chooser (see below)
    # Every craft takes a little time and effort at the bench — so bulk-converting
    # a stack (e.g. wood into arrows) costs a real slice of the day, not nothing.
    from . import turns
    state.player.energy = max(0, state.player.energy - C.CRAFT_COST[0])
    turns.advance_time(state, C.CRAFT_COST[1])
    return True


def arrow_choice_options(state: GameState) -> list:
    """Ore-tipped arrows the player can currently fletch: 1 Wood + 1 ore -> 5
    arrows of that metal. One entry per ore held (shape matches the machine
    chooser, so it reuses render_load_machine)."""
    inv = state.player.inventory
    if inv.count(items.WOOD) < 1:
        return []
    opts = []
    for ore, arrow in content.ARROW_FROM_ORE.items():
        if inv.count(ore) >= 1:
            opts.append({"inputs": [(items.WOOD, 1), (ore, 1)], "output": arrow, "out_qty": 5})
    for reagent, arrow in content.STATUS_ARROWS.items():   # brimstone/venom-tipped
        if inv.count(reagent) >= 1:
            opts.append({"inputs": [(items.WOOD, 1), (reagent, 1)], "output": arrow, "out_qty": 5})
    return opts


def craft_choice(state: GameState, opt) -> None:
    """Resolve a chosen craft option (e.g. metal-tipped arrows): spend the inputs,
    make ``out_qty`` of the output."""
    inv = state.player.inventory
    if not all(inv.count(it) >= q for it, q in opt["inputs"]):
        return
    for it, q in opt["inputs"]:
        inv.remove(it, q)
    qty = opt.get("out_qty", 1)
    inv.add(opt["output"], qty)
    state.log.add(f"You fletch {qty}x {opt['output'].name}.", (200, 220, 160))
    from . import turns
    state.player.energy = max(0, state.player.energy - C.CRAFT_COST[0])
    turns.advance_time(state, C.CRAFT_COST[1])


def _place_fence(state: GameState) -> bool:
    """Set a fence panel on the faced tile (placed like any built object). Wild
    ground it stands on — and any land a closed loop encloses — becomes a claim."""
    from . import land
    from ..world import tile
    p = state.player
    surf = state.world
    if surf.is_dungeon:
        state.log.add("There's nothing to fence off down here.", C.DIM)
        return False
    tx, ty = p.x + p.facing[0], p.y + p.facing[1]
    if not surf.in_bounds(tx, ty):
        state.log.add("There's nothing there to fence.", C.DIM)
        return False
    if land.owned_by_other(state, tx, ty):
        state.log.add(f"You can't fence {land.owner_label(state, tx, ty)} land.", C.DIM)
        return False
    if surf.tile_at(tx, ty).name not in land.FENCEABLE:
        state.log.add("A fence needs open ground to stand on.", C.DIM)
        return False
    if (tx, ty) in surf.crops or (tx, ty) in surf.trees or (tx, ty) in surf.machines:
        state.log.add("Something's in the way there.", C.DIM)
        return False
    surf.tiles[tx, ty] = tile.FENCE
    newly = land.note_claim(state, [(tx, ty)]) + land.note_claim(state, land.enclosed_tiles(state, (tx, ty)))
    if newly:
        state.log.add(f"You set a fence — {newly} tile(s) of wild land claimed.", (200, 220, 160))
    else:
        state.log.add("You set a fence.")
    return True


def _place_machine(state: GameState, kind: str) -> bool:
    p = state.player
    if kind == "fence":
        return _place_fence(state)
    if state.world.is_dungeon:
        # Machines (and the animals a coop would house) live only on the farm;
        # placed underground they'd be lost when the floor re-rolls.
        state.log.add(f"You can only set down a {MACHINES[kind].name.lower()} on the surface.", C.DIM)
        return False
    if state.world is not state.surface:
        # The Westreach is too far to tend — nothing left out there would keep.
        state.log.add(f"Too far from home — a {MACHINES[kind].name.lower()} needs "
                      "tending. Set it up back in the Vale.", C.DIM)
        return False
    tx, ty = p.x + p.facing[0], p.y + p.facing[1]
    if not state.world.in_bounds(tx, ty):
        state.log.add("There's no room to place that there.", C.DIM)
        return False
    if (tx, ty) in state.world.machines or (tx, ty) in state.world.crops:
        state.log.add("Something is already there.", C.DIM)
        return False
    if not state.world.walkable(tx, ty):
        state.log.add(f"You need open ground to place the {MACHINES[kind].name.lower()}.", C.DIM)
        return False
    from . import land
    if land.owned_by_other(state, tx, ty):
        state.log.add(f"You can't set that down on {land.owner_label(state, tx, ty)} land.", C.DIM)
        return False
    state.world.machines[(tx, ty)] = Machine(kind=kind)
    land.claim(state, [(tx, ty)])
    state.log.add(f"You set down a {MACHINES[kind].name.lower()}.")
    return True


# --- machine interaction (load / collect) -----------------------------------
def _grant_machine_xp(state: GameState, mdef, out, qty: int) -> None:
    """The skill XP (and stat bumps) a machine's output earns — shared by the
    collect path (passive machines) and the immediate resolve (active ones)."""
    from . import skills
    if mdef.kind in ("spinner", "loom"):
        skills.gain(state, "Farming", 7)             # spinning & weaving; cloth garments too
        if out.kind == "artisan":
            state.bump("artisan_made")
    elif out.kind in ("weapon", "armor"):
        skills.gain(state, "Smithing", 12)           # forging hones the smith
    elif out.kind == "gem":
        skills.gain(state, "Gemcutting", 32)         # gems are scarce — each cut teaches much
    elif mdef.kind in ("furnace", "kiln"):
        skills.gain(state, "Smithing", 8)            # smelting & fuel-making, too
    elif mdef.kind in ("quern", "windmill"):
        skills.gain(state, "Cooking", 6)             # milling is kitchen work
    elif mdef.kind == "apothecary":
        skills.gain(state, "Herbalism", 12)          # steeping & distilling deepen the craft
    elif mdef.kind == "oven":
        skills.gain(state, "Cooking", 10)            # a batch bake is real kitchen work
        state.bump("dishes_cooked", qty)
    elif out.kind == "artisan":
        state.bump("artisan_made")
        skills.gain(state, "Cooking", 8)             # processing hones the craft


# Stamina a stint at an active (worked-in-person) machine costs. Smithing is
# heavier than the close bench-work of gem-cutting; both draw on the day's bar.
_ACTIVE_STAMINA = {"anvil": 5, "gemcut": 3}


def stint_cost(state: GameState, kind: str) -> int:
    """What a stint at a worked-in-person machine costs in stamina. The anvil is
    brute work — a strong back (Strength) spends less wind on it."""
    cost = _ACTIVE_STAMINA.get(kind, C.CRAFT_COST[0])
    if kind == "anvil":
        from . import attrs
        # int() truncates toward zero, so a weak back pays no steeper than a
        # strong one saves (floor division would skew the penalty side).
        cost = max(2, cost - int(attrs.mod(state, "St") / 3))
    return cost

_TOMBOLA_COST = 25
_TREAT_COST = 15


def _play_tombola(state: GameState) -> bool:
    """A festival spin: 25g, every ticket wins something — usually small, now
    and then a gasp from the crowd. Seeded per spin, so no scumming."""
    import random as _r
    p = state.player
    if p.gold < _TOMBOLA_COST:
        state.log.add(f"The tombola is {_TOMBOLA_COST}g a spin — you're short.", C.DIM)
        return True
    p.gold -= _TOMBOLA_COST
    spins = state.stats["tombola_spins"] = state.stats.get("tombola_spins", 0) + 1
    rng = _r.Random(state.seed * 6421 + state.day * 977 + spins)
    roll = rng.random()
    if roll < 0.40:
        prize, qty = items.FIRECRACKER, 2
    elif roll < 0.65:
        prize, qty = rng.choice((items.CANDIED_FRUIT, items.COOKIES)), 1
    elif roll < 0.82:
        prize, qty = rng.choice((items.TULIP_SEEDS, items.PUMPKIN_SEEDS,
                                 items.SUNFLOWER_SEEDS)), 2
    elif roll < 0.94:
        prize, qty = content.random_gem(rng), 1
    elif roll < 0.98:
        prize, qty = items.BLAST_CHARGE, 1
    else:
        prize, qty = items.BEE_QUEEN, 1              # the crowd gasps
    p.inventory.add(prize, qty)
    got = f"{qty}x {prize.name}" if qty > 1 else prize.name
    big = roll >= 0.94
    state.log.add(("The wheel rattles… and the crowd GASPS — " if big
                   else "The wheel rattles… ") + f"you win {got}!",
                  (244, 210, 130) if big else (222, 200, 150))
    return True


def _buy_treat(state: GameState) -> bool:
    """Festival fare off the griddle: 15g for a warm treat into the pack."""
    import random as _r
    p = state.player
    if p.gold < _TREAT_COST:
        state.log.add(f"Treats are {_TREAT_COST}g — you're short.", C.DIM)
        return True
    p.gold -= _TREAT_COST
    buys = state.stats["fair_treats"] = state.stats.get("fair_treats", 0) + 1
    rng = _r.Random(state.seed * 3319 + state.day * 613 + buys)
    treat = rng.choice((items.CANDIED_FRUIT, items.COOKIES, items.SAUSAGE_ROLL))
    p.inventory.add(treat, 1)
    state.log.add(f"You buy a {treat.name.lower()}, warm off the stall.", (222, 200, 150))
    return True


def interact_machine(state: GameState, x: int, y: int) -> bool:
    m = state.world.machines.get((x, y))
    if m is None:
        return False
    mdef = MACHINES[m.kind]
    now = state.abs_minutes
    status = m.status(now)

    if m.kind == "beehive":
        return _tend_beehive(state, m, mdef, x, y)

    if m.kind in ("coop_small", "coop_big", "barn", "pen", "site"):
        from . import husbandry
        return husbandry.interact_building(state, m, x, y)

    if m.kind == "sprinkler":
        state.log.add("The sprinkler waters the soil around it each morning.", C.DIM)
        return True

    if m.kind == "chest":
        return {"storage": True}          # a home store — the player opens the chest UI

    if m.kind == "fair_games":
        return _play_tombola(state)

    if m.kind == "fair_treats":
        return _buy_treat(state)

    if m.kind == "weathervane":
        from . import farming, events
        state.log.add(f"The weathervane reads the coming sky: {farming.weather_saying(farming.forecast(state))}",
                      (200, 216, 232))
        om = events.omen(state)
        if om:
            state.log.add(f"  {om}", (200, 216, 232))
        return True

    if m.kind == "jeweller":
        # The bench works instantly (like a workbench): always offer its choices.
        opts = machine_load_options(state, mdef)
        if not opts:
            state.log.add(_needs_hint(mdef), C.DIM)
            return True
        return {"load": (x, y), "options": opts, "name": mdef.name, "jeweller": True}

    if m.kind == "butcher":
        # The block also resolves at once — it takes an animal, not an item.
        opts = _butcher_options(state)
        if not opts:
            state.log.add(_needs_hint(mdef), C.DIM)
            return True
        return {"load": (x, y), "options": opts, "name": mdef.name, "butcher": True}

    if status == "done":
        from . import skills
        out = m.loaded_output
        q = m.out_quality if skills.has_quality(out) else 0
        qty = max(1, m.out_qty)
        state.player.inventory.add(out, qty, quality=q)
        star = (" " + skills.stars(q)) if q else ""
        _grant_machine_xp(state, mdef, out, qty)
        got = f"{qty}x {out.name}" if qty > 1 else out.name
        state.log.add(f"You collect {got}{star} from the {mdef.name.lower()}.", (180, 230, 160))
        m.loaded_output = None
        m.ready_at = 0
        m.out_quality = 0
        m.out_qty = 1
        return True

    if status == "working":
        state.log.add(f"The {mdef.name.lower()} is working — {_fmt_remaining(m.ready_at - now)} left.", C.DIM)
        return True

    # empty -> offer the player a choice of what to load (see load_machine_choice)
    opts = machine_load_options(state, mdef)
    if not opts:
        state.log.add(_needs_hint(mdef), C.DIM)
        return True
    return {"load": (x, y), "options": opts, "name": mdef.name}


def _needs_hint(mdef) -> str:
    return {
        "ore":   "The furnace needs ore and a fuel hot enough to smelt it.",
        "fuel":  "The kiln chars wood into charcoal, or bakes coal into coke.",
        "gem":   "The gemcutting station needs a rough gem or a geode.",
        "jewelcraft": "The jeweller's bench needs a metal bar + a cut gem, or gear + a cut gem to embed.",
        "mill":  "The mill grinds grain into flour, cane into sugar, or salt lumps into sea salt.",
        "smoke": "The smoker cures meat into jerky, or fish into smoked fish.",
        "hide":  "The tanning rack cures raw hides, boar hides & wolf pelts into leather.",
        "fiber": "The spinning wheel needs wool, cotton, flax or spider silk.",
        "weave": "The loom needs yarn to weave into cloth, or cloth to tailor into garments.",
        "wood":  "The sawmill needs at least 2 wood.",
        "oil":   "The press needs at least 2 sunflowers.",
        "dairy": "The churn needs milk.",
        "fruit": "The keg ferments fruit into wine, or honey into mead.",
        "crop":  "The jar needs a crop or an eel to preserve.",
        "bake":  "The oven bakes double batches of baked recipes you know — "
                 "you need twice the ingredients.",
        "age":   "The cellar ages wine, mead or cheese — bring a bottle or a wheel.",
        "brew":  "The apothecary steeps herbs into remedies you know — bring twice "
                 "the herbs for a batch — and distils potions at higher skill.",
        "butcher": "The block waits for a grown animal — you have none ready.",
    }.get(mdef.accepts, f"The {mdef.name.lower()} has nothing to work with.")


def _preserve_of(it):
    """What a Preserves Jar turns a given input into — a per-source jam/pickle
    (so a strawberry jam is worth more than a raspberry one)."""
    if it is items.EEL:
        return items.JELLIED_EEL
    if content.is_fruit(it):
        return content.FRUIT_JAM.get(it, items.JAM)
    return content.VEG_PICKLE.get(it, items.PICKLES)


def load_groups(opts: list) -> list:
    """Distinct group names among options, in first-seen order. Empty when the
    chooser is a plain flat list (no option carries a ``group``)."""
    seen, out = set(), []
    for o in opts:
        g = o.get("group")
        if g and g not in seen:
            seen.add(g)
            out.append(g)
    return out


def load_rows(ctx: dict):
    """The rows the load-machine chooser is currently showing, as
    ``(rows, is_group_level)``. A grouped chooser shows its group names first
    (``is_group_level`` True); once a group is chosen it shows that group's
    options. An ungrouped chooser is always its flat option list."""
    opts = ctx["options"]
    groups = load_groups(opts)
    if groups and ctx.get("group") is None:
        return groups, True
    if groups:
        return [o for o in opts if o.get("group") == ctx["group"]], False
    return opts, False


def machine_load_options(state: GameState, mdef) -> list:
    """Everything the player could load into an empty machine right now — one
    entry per distinct input. Each is {inputs, output, quality_from}."""
    inv = state.player.inventory
    a = mdef.accepts
    opts = []
    if a == "ore":
        # Smelt each metal whose ore(s) you hold, once per carried fuel hot enough
        # for it — hotter fuel smelts faster (see content.smelt_time).
        for bar, ores, min_heat, fuel_qty in content.FURNACE_RECIPES:
            if not all(inv.count(it) >= q for it, q in ores.items()):
                continue
            for fuel in content.FUELS_BY_HEAT:
                heat = content.FUELS[fuel]
                if heat < min_heat or inv.count(fuel) < fuel_qty:
                    continue
                mins = content.smelt_time(min_heat, heat)
                opts.append({"inputs": list(ores.items()) + [(fuel, fuel_qty)], "output": bar,
                             "quality_from": None, "minutes": mins, "group": bar.name,
                             "label": f"via {fuel.name}  ({_fmt_remaining(mins)})"})
    elif a == "fuel":
        if inv.count(items.WOOD) >= 2:
            opts.append({"inputs": [(items.WOOD, 2)], "output": items.CHARCOAL, "quality_from": None})
        if inv.count(items.COAL) >= 1:
            opts.append({"inputs": [(items.COAL, 1)], "output": items.COKE, "quality_from": None})
    elif a == "gem":
        for rough in content.ROUGH_GEMS:
            if inv.count(rough) >= 1:
                opts.append({"inputs": [(rough, 1)], "output": content.CUT_GEM[rough], "quality_from": None})
        if inv.count(items.GEODE) >= 1:
            opts.append({"inputs": [(items.GEODE, 1)], "output": items.GEODE, "quality_from": None,
                         "geode": True, "label": "Crack a Geode → a cut gem"})
    elif a == "jewelcraft":
        return _jeweller_options(state)
    elif a == "mill":
        for src, out in content.MILL_RECIPES.items():
            if inv.count(src) >= 1:
                opts.append({"inputs": [(src, 1)], "output": out, "quality_from": src})
    elif a == "wood":
        if inv.count(items.WOOD) >= 2:
            opts.append({"inputs": [(items.WOOD, 2)], "output": mdef.output, "quality_from": None})
    elif a == "oil":
        if inv.count(items.SUNFLOWER) >= 2:
            opts.append({"inputs": [(items.SUNFLOWER, 2)], "output": items.SUNFLOWER_OIL,
                         "quality_from": items.SUNFLOWER})
    elif a == "dairy":
        if inv.count(items.MILK) >= 1:
            opts.append({"inputs": [(items.MILK, 1)], "output": items.CHEESE, "quality_from": items.MILK})
            opts.append({"inputs": [(items.MILK, 1)], "output": items.YOGURT,
                         "quality_from": items.MILK, "minutes": 600})   # cultures faster than cheese ages
            opts.append({"inputs": [(items.MILK, 1)], "output": items.BUTTER,
                         "quality_from": items.MILK, "minutes": 400})   # churns quickest of the three
        if inv.count(items.GOAT_MILK) >= 1:
            opts.append({"inputs": [(items.GOAT_MILK, 1)], "output": items.GOAT_CHEESE,
                         "quality_from": items.GOAT_MILK})
    elif a == "smoke":
        for src, out in content.SMOKE_RECIPES:
            if inv.count(src) >= 1:
                opts.append({"inputs": [(src, 1)], "output": out, "quality_from": src})
        # The saltpeter cure: a whole ham, if you've pork and nitre both.
        if inv.count(items.PORK) >= 1 and inv.count(items.SALTPETER) >= 1:
            opts.append({"inputs": [(items.PORK, 1), (items.SALTPETER, 1)],
                         "output": items.CURED_HAM, "quality_from": items.PORK,
                         "minutes": 1440})              # a full day in the smoke
    elif a == "hide":
        for hide in (items.RAW_HIDE, items.BOAR_HIDE, items.WOLF_PELT):
            if inv.count(hide) >= 1:
                opts.append({"inputs": [(hide, 1)], "output": items.LEATHER,
                             "quality_from": None, "label": f"{hide.name} → Leather"})
    elif a == "fiber":
        for src, out in content.SPIN_RECIPES.items():
            if inv.count(src) >= 1:
                opts.append({"inputs": [(src, 1)], "output": out, "quality_from": src})
    elif a == "weave":
        for yarn, cloth in content.WEAVE_RECIPES.items():       # weave yarn into cloth
            if inv.count(yarn) >= 1:
                opts.append({"inputs": [(yarn, 1)], "output": cloth, "quality_from": yarn})
        for cloth, material in content.CLOTH_MATERIAL.items():  # tailor cloth into garments
            if inv.count(cloth) >= 1:
                for base in ("Hat", "Cloak", "Robe"):
                    opts.append({"inputs": [(cloth, 1)], "output": content.make_gear(base, material),
                                 "quality_from": None,
                                 "label": f"{material.capitalize()} {base}"})
        for cloth, decor in content.CLOTH_DECOR.items():        # tailor cloth into furnishings
            if inv.count(cloth) >= 2:
                opts.append({"inputs": [(cloth, 2)], "output": decor, "quality_from": cloth})
    elif a == "fruit":
        if inv.count(items.HONEY) > 0:
            opts.append({"inputs": [(items.HONEY, 1)], "output": items.MEAD, "quality_from": items.HONEY})
        if inv.count(items.MEAD) > 0:
            opts.append({"inputs": [(items.MEAD, 1)], "output": items.AGED_MEAD, "quality_from": items.MEAD})
        for it in {e[0] for e in inv.slots if e[0].kind == "crop" and content.is_fruit(e[0])}:
            out = content.FRUIT_WINE.get(it, items.WINE)      # wine inherits the fruit's value
            opts.append({"inputs": [(it, 1)], "output": out, "quality_from": it})
        for src, need in content.MASH_SOURCES.items():        # ferment grain/potato -> mash (step 1 of vodka)
            if inv.count(src) >= need:
                opts.append({"inputs": [(src, need)], "output": items.GRAIN_MASH,
                             "quality_from": src, "label": f"Grain Mash ({src.name})"})
    elif a == "bars":
        # Forge a piece of any base from the metal bars you carry (deeper metals
        # make finer gear). One entry per (metal, base) you can currently afford.
        for metal in content.FORGE_METALS:
            bar = content.MATERIALS[metal].bar
            forgeable = list(content.WEAPON_BASES) + [
                b for b in content.ARMOR_BASES if b not in content._SOFT_BASES]
            for base in forgeable:
                cost = content.forge_cost(base)
                if bar is not None and inv.count(bar) >= cost:
                    # Grouped by what you're forging: pick the piece, then the metal.
                    opts.append({"inputs": [(bar, cost)], "output": content.make_gear(base, metal),
                                 "quality_from": None, "group": base,
                                 "label": f"{metal.capitalize()}  ({cost} {bar.name})"})
    elif a == "crop":
        seen = set()
        for it, _q, _ql in inv.slots:
            if it in seen:
                continue
            if (it.kind == "crop" and content.PRODUCE_CATEGORY.get(it) not in ("flower", "grain", "fiber")) \
                    or it is items.EEL:
                seen.add(it)
                opts.append({"inputs": [(it, 1)], "output": _preserve_of(it), "quality_from": it})
    elif a == "bake":
        # A double batch of any BAKED recipe the player knows: twice the
        # ingredients in, two out, and a touch finer than the pan (+1 star).
        # Hand-cooking is untouched — the oven is bigger, never the only way.
        for r in content.RECIPES:
            if r.kind != "cook" or r.name not in content.BAKED_GOODS:
                continue
            if r.name not in state.known_recipes:
                continue
            doubled = resolve_inputs(inv, [(it, q * 2) for it, q in r.inputs])
            if doubled is not None and all(inv.count(it) >= q for it, q in doubled):
                qf = max(doubled, key=lambda e: e[0].value)[0]
                opts.append({"inputs": doubled, "output": r.output, "out_qty": 2,
                             "quality_from": qf, "quality_bonus": 1, "label": r.name})
    elif a == "brew":
        # Remedies are brewed only here (they can't be made by hand). A double
        # batch of any remedy the herbalist knows — twice the herbs in, two out,
        # +1 quality, steeped over hours while you get on with the day.
        for r in content.RECIPES:
            if r.kind != "remedy" or r.name not in state.known_recipes:
                continue
            doubled = resolve_inputs(inv, [(it, q * 2) for it, q in r.inputs])
            if doubled is not None and all(inv.count(it) >= q for it, q in doubled):
                qf = max(doubled, key=lambda e: e[0].value)[0]
                opts.append({"inputs": doubled, "output": r.output, "out_qty": r.out_qty * 2,
                             "quality_from": qf, "quality_bonus": 1, "group": "Remedies",
                             "label": r.name})
        # Distil a fermented mash into vodka (step 2 of the vodka chain).
        if inv.count(items.GRAIN_MASH) >= 1:
            opts.append({"inputs": [(items.GRAIN_MASH, 1)], "output": items.VODKA, "out_qty": 1,
                         "quality_from": items.GRAIN_MASH, "minutes": 600, "group": "Spirits",
                         "label": "Vodka"})
        # Station-only potions, distilled beyond a hand-brew's reach (skill-gated).
        from . import skills
        hlvl = skills.skill_level(state, "Herbalism")
        for inputs, out, oq, need, mins in content.APOTHECARY_POTIONS:
            if hlvl >= need and all(inv.count(it) >= q for it, q in inputs):
                qf = max(inputs, key=lambda e: e[0].value)[0]
                opts.append({"inputs": list(inputs), "output": out, "out_qty": oq,
                             "quality_from": qf, "minutes": mins, "group": "Potions",
                             "label": out.name})
    elif a == "age":
        for src, out in content.AGED_DRINK.items():
            if inv.count(src) >= 1:
                opts.append({"inputs": [(src, 1)], "output": out, "quality_from": src})
        if inv.count(items.MEAD) >= 1:
            opts.append({"inputs": [(items.MEAD, 1)], "output": items.AGED_MEAD,
                         "quality_from": items.MEAD})
        if inv.count(items.CHEESE) >= 1:
            opts.append({"inputs": [(items.CHEESE, 1)], "output": items.AGED_CHEESE,
                         "quality_from": items.CHEESE})
        if inv.count(items.GOAT_CHEESE) >= 1:
            opts.append({"inputs": [(items.GOAT_CHEESE, 1)], "output": items.AGED_GOAT_CHEESE,
                         "quality_from": items.GOAT_CHEESE})
    return opts


def load_machine_choice(state: GameState, m: Machine, mdef, opt) -> None:
    """Load a machine with the option the player picked (see the load menu)."""
    import random
    from . import skills
    inv = state.player.inventory
    in_quality = 0.0
    qfrom = opt["quality_from"]
    if qfrom is not None:
        qty = dict(opt["inputs"]).get(qfrom, 1)
        in_quality = inv.pop_quality(qfrom, qty)      # carry the input's quality through
    for it, q in opt["inputs"]:
        if it is qfrom:
            continue                                  # already taken above
        inv.remove(it, q)
    output = opt["output"]
    if opt.get("geode"):                              # a cracked geode reveals (and cuts) a gem
        output = content.CUT_GEM[content.random_gem(random)]
    elif mdef.kind == "anvil":                        # a skilled smith may forge in a bonus affix
        lvl = skills.skill_level(state, "Smithing")
        kind = "weapon" if output.kind == "weapon" else "armor"
        pfx, sfx = content.roll_craft_affix(lvl, random, kind)
        if pfx or sfx:
            output = content.make_gear(content._GEAR_BASE[output], output.material, pfx, sfx,
                                       gems=output.gems)
    out_qty = opt.get("out_qty", 1)
    minutes = round(opt.get("minutes", mdef.minutes) * (skills.smith_speed_mult(state)
                    if mdef.kind in ("furnace", "anvil", "kiln") else 1.0))
    minutes = max(1, minutes)
    # Cut gems take their quality from the cutter's Gemcutting; other processed
    # goods inherit the input's quality nudged by the cook's skill.
    if skills.has_quality(output):
        _qskill = "Herbalism" if mdef.kind == "apothecary" else "Cooking"
        out_quality = (skills.roll_quality(state, "Gemcutting") if output.kind == "gem"
                       else skills.process_quality(in_quality, state, _qskill))
        if mdef.kind == "quern":                       # the hand-mill grinds a touch coarse
            out_quality = max(0, out_quality - 1)
        if output.kind == "gem":                       # Hall of Wonders — completed Lapidary
            from . import collection
            if collection.perk_earned(state, "Lapidary"):
                out_quality += 1
        # the oven bakes a touch finer than the pan
        out_quality = min(5, out_quality + opt.get("quality_bonus", 0))
    else:
        out_quality = 0

    if getattr(mdef, "active", False):
        # Worked in person: the smith/cutter finishes the piece here and now,
        # spending the day's own time and stamina rather than leaving a timer.
        from . import turns
        state.player.inventory.add(output, out_qty, quality=out_quality)
        _grant_machine_xp(state, mdef, output, out_qty)
        state.player.energy = max(0, state.player.energy - stint_cost(state, mdef.kind))
        turns.advance_time(state, minutes * 60)
        star = (" " + skills.stars(out_quality)) if out_quality else ""
        got = f"{out_qty}x {output.name}" if out_qty > 1 else output.name
        state.log.add(f"You work the {mdef.name.lower()} — {got}{star}. "
                      f"(took {_fmt_remaining(minutes)})", (180, 230, 160))
        return

    m.loaded_output = output
    m.out_qty = out_qty
    m.ready_at = state.abs_minutes + minutes
    m.out_quality = out_quality
    state.log.add(f"You load the {mdef.name.lower()} ({output.name}). Ready in {_fmt_remaining(minutes)}.")


def _butcher_options(state: GameState) -> list:
    """One entry per grown animal on the farm — its cuts, by its kind. Meat is
    typed (pork from the pig, beef from the cow), and a well-kept beast renders
    finer cuts, so the block is a real trade: a friend for a full larder."""
    from .husbandry import SPECIES, _is_adult
    opts = []
    for a in state.surface.animals:
        cut = content.MEAT_CUT.get(a.kind)
        if cut is None or not _is_adult(a):
            continue
        meat, qty = cut
        spec = SPECIES[a.kind]
        opts.append({"kind": "butcher", "animal": a, "inputs": [],
                     "output": meat, "out_qty": qty,
                     "label": f"{a.name} the {spec.grown_name} — {qty} {meat.name}"})
    return opts


def butcher_choice(state: GameState, opt) -> None:
    """Resolve a butchering at once. The animal is gone; its cuts (starred by
    how well it was kept) go to the pack — plus the fleece, for a sheep."""
    from . import skills, turns
    from .husbandry import SPECIES, _produce_quality
    a = opt["animal"]
    if a not in state.surface.animals:
        return
    state.surface.animals.remove(a)
    q = _produce_quality(state, a)
    state.player.inventory.add(opt["output"], opt["out_qty"], quality=q)
    got = [f"{opt['out_qty']} {opt['output'].name}"]
    if a.kind == "sheep":
        state.player.inventory.add(items.WOOL, 1, quality=q)
        got.append("1 Wool")
    state.bump("animals_butchered")
    skills.gain(state, "Farming", 6)
    star = (" " + skills.stars(q)) if q else ""
    state.log.add(f"You lead {a.name} to the block. (+{', +'.join(got)}{star}) "
                  "The farm is a little quieter tonight.", (216, 170, 150))
    state.player.energy = max(0, state.player.energy - C.CRAFT_COST[0])
    turns.advance_time(state, C.CRAFT_COST[1])


def _carried_cut_gems(inv) -> list:
    """Distinct cut gems the player carries (the inputs for jewellery/embedding)."""
    out, seen = [], set()
    for it, _q, _ql in inv.slots:
        if it.kind == "gem" and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _jeweller_options(state: GameState) -> list:
    """Everything the Jeweller's Bench can do right now: forge a ring/amulet, or
    set a cut gem into a carried weapon/armour piece or one of your tools. Each
    resolves immediately (see jeweller_choice)."""
    from . import skills
    inv = state.player.inventory
    cap = skills.socket_capacity(state)
    cuts = _carried_cut_gems(inv)
    opts = []
    # 1) forge jewellery from a metal bar + a cut gem
    for metal in content.JEWELRY_METALS:
        bar = content.MATERIALS[metal].bar
        if bar is None or inv.count(bar) < 1:
            continue
        for cut in cuts:
            gemkey = content.gem_key(cut)
            for base in ("Ring", "Amulet"):
                out = content.make_jewel(base, metal, gemkey)
                # Grouped by gem (which decides the jewel's effect): pick the gem,
                # then the metal + band that scales it.
                opts.append({"kind": "jewel", "inputs": [(bar, 1), (cut, 1)],
                             "output": out, "quality_from": cut,
                             "group": f"{content.GEM_TITLE[gemkey]} jewellery",
                             "label": f"{metal.capitalize()} {base}"})
    # 2) embed a gem into a carried weapon/armour piece (a free socket, right gem)
    for it, _q, _ql in inv.slots:
        domain = "weapon" if it.kind == "weapon" else ("armor" if it.kind == "armor" else "")
        if not domain or len(getattr(it, "gems", ())) >= cap:
            continue
        for cut in cuts:
            gemkey = content.gem_key(cut)
            if domain in content.GEM_DOMAIN.get(gemkey, ()):
                out = content.embed_gem(it, gemkey)
                if out is not None:
                    opts.append({"kind": "embed_gear", "inputs": [(it, 1), (cut, 1)], "output": out,
                                 "group": "Set a gem in gear",
                                 "label": f"Set {content.GEM_TITLE[gemkey]} in {it.name}"})
    # 3) embed a gem into one of your tools (stored per-tool, not a new item)
    p = state.player
    for tool in p.tool_tier:
        if len(p.tool_gem.get(tool, ())) >= cap:
            continue
        for cut in cuts:
            gemkey = content.gem_key(cut)
            if "tool" in content.GEM_DOMAIN.get(gemkey, ()):
                opts.append({"kind": "embed_tool", "inputs": [(cut, 1)], "output": tool,
                             "tool": tool, "gemkey": gemkey, "group": "Set a gem in a tool",
                             "label": f"Set {content.GEM_TITLE[gemkey]} in your {tool.name}"})
    return opts


def jeweller_choice(state: GameState, opt) -> None:
    """Resolve a Jeweller's Bench choice immediately (like bench crafting)."""
    from . import skills, turns
    inv = state.player.inventory
    if not all(inv.count(it) >= q for it, q in opt["inputs"]):
        return
    kind = opt["kind"]
    if kind == "jewel":
        qfrom = opt["quality_from"]
        inq = inv.pop_quality(qfrom, 1)               # the cut gem's quality carries through
        for it, q in opt["inputs"]:
            if it is not qfrom:
                inv.remove(it, q)
        outq = skills.process_quality(inq, state, "Jewelcrafting")
        inv.add(opt["output"], 1, quality=outq)
        skills.gain(state, "Jewelcrafting", 36)
        star = (" " + skills.stars(outq)) if outq else ""
        state.log.add(f"You craft {opt['output'].name}{star}.", (230, 210, 140))
    elif kind == "embed_gear":
        for it, q in opt["inputs"]:
            inv.remove(it, q)
        inv.add(opt["output"], 1)
        skills.gain(state, "Jewelcrafting", 26)
        state.log.add(f"You set the gem — {opt['output'].name}.", (230, 210, 140))
    elif kind == "embed_tool":
        inv.remove(opt["inputs"][0][0], 1)
        tool = opt["tool"]
        state.player.tool_gem[tool] = tuple(state.player.tool_gem.get(tool, ())) + (opt["gemkey"],)
        skills.gain(state, "Jewelcrafting", 26)
        state.log.add(f"You set the {opt['gemkey']} into your {state.player.display_name(tool)}.",
                      (230, 210, 140))
    state.player.energy = max(0, state.player.energy - C.CRAFT_COST[0])
    turns.advance_time(state, C.CRAFT_COST[1])


def _flowers_near(state: GameState, x: int, y: int, r: int = 10) -> int:
    """Count blooming flowers within r tiles — wild flower tiles plus mature
    planted flower crops. Drives a beehive's yield."""
    surf = state.surface
    n = 0
    for xx in range(x - r, x + r + 1):
        for yy in range(y - r, y + r + 1):
            if surf.in_bounds(xx, yy) and surf.tile_at(xx, yy).kind == "flower":
                n += 1
    for (cx, cy), plot in surf.crops.items():
        if (not plot.dead and plot.mature and abs(cx - x) <= r and abs(cy - y) <= r
                and getattr(plot.crop, "category", "") == "flower"):
            n += 1                        # only blooms feed the bees, not fresh seedlings
    return n


def _tend_beehive(state: GameState, m, mdef, x: int, y: int) -> bool:
    """Install a queen, or harvest honey & wax (more the more flowers are near)."""
    inv = state.player.inventory
    now = state.abs_minutes
    if not m.has_queen:
        if inv.count(items.BEE_QUEEN) > 0:
            inv.remove(items.BEE_QUEEN, 1)
            m.has_queen = True
            m.loaded_output = items.HONEY
            m.ready_at = now + mdef.minutes
            state.log.add("You settle a bee queen into the hive — the colony begins!", (232, 200, 120))
        else:
            state.log.add("The beehive stands empty; it needs a bee queen.", C.DIM)
        return True
    if now < m.ready_at:
        state.log.add(f"The hive is filling — {_fmt_remaining(m.ready_at - now)} left.", C.DIM)
        return True
    from . import skills
    flowers = _flowers_near(state, x, y, 10)
    honey = 1 + flowers // 6                    # a little even with none; lots with a flower bed
    wax = flowers // 12
    # honey quality: foraging skill, lifted a touch by a rich flower bed
    q = min(5, skills.roll_quality(state, "Foraging") + (1 if flowers >= 24 else 0))
    inv.add(items.HONEY, honey, quality=q)
    if wax:
        inv.add(items.BEESWAX, wax)
    state.bump("artisan_made")
    tail = f" and {wax} beeswax" if wax else ""
    star = (" " + skills.stars(q)) if q else ""
    state.log.add(f"You harvest {honey} honey{star}{tail} ({flowers} flowers nearby).", (232, 200, 120))
    m.ready_at = now + mdef.minutes            # the colony keeps working
    return True


# --- morning processing -----------------------------------------------------
def run_sprinklers(state: GameState) -> None:
    """Sprinklers water adjacent crops at dawn."""
    for (mx, my), m in state.world.machines.items():
        if m.kind != "sprinkler":
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            plot = state.world.crops.get((mx + dx, my + dy))
            if plot is not None and not plot.dead and not plot.mature:
                plot.watered = True


def sellable_items(state: GameState):
    """Inventory stacks that can be shipped (value>0), one per (item, quality)."""
    return [(it, q, ql) for it, q, ql in state.player.inventory.slots if it.value > 0]


def edible_items(state: GameState):
    """Anything nourishing in the pack (cooked dishes plus raw eggs/milk/cheese),
    and remedies like the salve — one entry per (item, quality)."""
    return [(it, q, ql) for it, q, ql in state.player.inventory.slots
            if it.energy > 0 or it.heal > 0]


def slot_value(item, quality: int) -> int:
    """Sell price of one unit, scaled by its quality stars."""
    from . import skills
    return round(item.value * skills.value_mult(quality))


def ship_item(state: GameState, item, quality: int = 0) -> None:
    """Move a specific quality-stack of item from inventory into the bin."""
    qty = state.player.inventory.count(item, quality)
    if qty <= 0:
        return
    state.player.inventory.remove(item, qty, quality=quality)
    state.ship_bin.add(item, qty, quality=quality)
    from . import skills
    star = (" " + skills.stars(quality)) if quality else ""
    state.log.add(f"You drop {qty} {item.name}{star} in the bin.", C.DIM)


def ship_all(state: GameState) -> int:
    """Drop every sellable stack into the bin at once. Returns the number of
    distinct stacks moved (0 if there was nothing to ship)."""
    stacks = sellable_items(state)
    if not stacks:
        return 0
    units = 0
    for it, q, ql in stacks:
        state.player.inventory.remove(it, q, quality=ql)
        state.ship_bin.add(it, q, quality=ql)
        units += q
    state.log.add(f"You empty {units} goods across {len(stacks)} stacks into the bin.", C.DIM)
    return len(stacks)


def bin_value(state: GameState, item, quality: int) -> int:
    """What one unit fetches at the bin right now: quality-scaled, marked up while
    the market craves this kind of goods (requests.demand_mult), and again once
    Saltmere's Market Cross draws the coast trade in."""
    from . import requests, projects, events
    v = slot_value(item, quality) * requests.demand_mult(state, item)
    if projects.done(state, "market_cross"):
        v *= 1.10
    v *= events.ship_mult(state)          # a caravan in the valley buys handsomely
    if state.player.sign == "coin":       # born on a market day
        v *= 1.03
    return round(v)


def sell_shipment(state: GameState) -> None:
    """Convert everything in the shipping bin to gold overnight (quality-scaled,
    at the market's current prices)."""
    total = sum(bin_value(state, it, ql) * qty for it, qty, ql in state.ship_bin.slots)
    if total > 0:
        state.player.gold += total
        state.bump("gold_earned", total)
        state.log.add(f"The shipping bin sold your goods for {total}g.", (240, 214, 120))
        state.ship_bin.slots.clear()
