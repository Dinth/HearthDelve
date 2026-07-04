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
def has_inputs(state: GameState, recipe: Recipe) -> bool:
    inv = state.player.inventory
    return all(inv.count(it) >= qty for it, qty in recipe.inputs)


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
def craft(state: GameState, recipe: Recipe) -> bool:
    """Execute a recipe. Returns True if it happened."""
    if not has_inputs(state, recipe):
        state.log.add(f"You need: {inputs_str(recipe)}.", C.DIM)
        return False

    from . import skills
    if recipe.kind == "build":
        if not _place_machine(state, recipe.machine):
            return False
        for it, qty in recipe.inputs:
            state.player.inventory.remove(it, qty)
    elif recipe.kind == "cook":
        # Cooking makes a carryable DISH whose quality inherits the average
        # ingredient quality, adjusted by the cook's skill. Eat it later.
        inv = state.player.inventory
        qs = [inv.pop_quality(it, qty) for it, qty in recipe.inputs]
        dish_q = skills.process_quality(sum(qs) / len(qs) if qs else 0, state, "Cooking")
        inv.add(recipe.output, recipe.out_qty, quality=dish_q)
        skills.gain(state, "Cooking", 14)
        state.bump("dishes_cooked")
        star = (" " + skills.stars(dish_q)) if dish_q else ""
        state.log.add(f"You cook {recipe.name}{star}.", (180, 230, 160))
    elif recipe.kind == "item":
        state.player.inventory.add(recipe.output, recipe.out_qty)
        state.log.add(f"You craft {recipe.out_qty}x {recipe.output.name}.")
        for it, qty in recipe.inputs:
            state.player.inventory.remove(it, qty)
    return True


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
def interact_machine(state: GameState, x: int, y: int) -> bool:
    m = state.world.machines.get((x, y))
    if m is None:
        return False
    mdef = MACHINES[m.kind]
    now = state.abs_minutes
    status = m.status(now)

    if m.kind == "beehive":
        return _tend_beehive(state, m, mdef, x, y)

    if m.kind in ("coop_small", "coop_big", "barn", "site"):
        from . import husbandry
        return husbandry.interact_building(state, m, x, y)

    if m.kind == "sprinkler":
        state.log.add("The sprinkler waters the soil around it each morning.", C.DIM)
        return True

    if status == "done":
        from . import skills
        q = m.out_quality if skills.has_quality(m.loaded_output) else 0
        state.player.inventory.add(m.loaded_output, 1, quality=q)
        star = (" " + skills.stars(q)) if q else ""
        if m.loaded_output.kind == "artisan":
            state.bump("artisan_made")
            skills.gain(state, "Cooking", 8)         # processing hones the craft
        state.log.add(f"You collect {m.loaded_output.name}{star} from the {mdef.name.lower()}.", (180, 230, 160))
        m.loaded_output = None
        m.ready_at = 0
        m.out_quality = 0
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
        "ore":   "The furnace needs ore and coal.",
        "wood":  "The sawmill needs at least 2 wood.",
        "oil":   "The press needs at least 2 sunflowers.",
        "dairy": "The churn needs milk.",
        "fruit": "The keg ferments fruit into wine, or honey into mead.",
        "crop":  "The jar needs a crop or an eel to preserve.",
    }.get(mdef.accepts, f"The {mdef.name.lower()} has nothing to work with.")


def _preserve_of(it):
    """What a Preserves Jar turns a given input into — a per-source jam/pickle
    (so a strawberry jam is worth more than a raspberry one)."""
    if it is items.EEL:
        return items.JELLIED_EEL
    if content.is_fruit(it):
        return content.FRUIT_JAM.get(it, items.JAM)
    return content.VEG_PICKLE.get(it, items.PICKLES)


def machine_load_options(state: GameState, mdef) -> list:
    """Everything the player could load into an empty machine right now — one
    entry per distinct input. Each is {inputs, output, quality_from}."""
    inv = state.player.inventory
    a = mdef.accepts
    opts = []
    if a == "ore":
        for bar, inputs in content.FURNACE_RECIPES:
            if all(inv.count(it) >= q for it, q in inputs.items()):
                opts.append({"inputs": list(inputs.items()), "output": bar, "quality_from": None})
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
    elif a == "fruit":
        if inv.count(items.HONEY) > 0:
            opts.append({"inputs": [(items.HONEY, 1)], "output": items.MEAD, "quality_from": items.HONEY})
        if inv.count(items.MEAD) > 0:
            opts.append({"inputs": [(items.MEAD, 1)], "output": items.AGED_MEAD, "quality_from": items.MEAD})
        for it in {e[0] for e in inv.slots if e[0].kind == "crop" and content.is_fruit(e[0])}:
            out = content.FRUIT_WINE.get(it, items.WINE)      # wine inherits the fruit's value
            opts.append({"inputs": [(it, 1)], "output": out, "quality_from": it})
    elif a == "bars":
        # Forge a piece of any base from the metal bars you carry (deeper metals
        # make finer gear). One entry per (metal, base) you can currently afford.
        for metal in content.FORGE_METALS:
            bar = content.MATERIALS[metal].bar
            for base in list(content.WEAPON_BASES) + list(content.ARMOR_BASES):
                cost = content.forge_cost(base)
                if bar is not None and inv.count(bar) >= cost:
                    opts.append({"inputs": [(bar, cost)], "output": content.make_gear(base, metal),
                                 "quality_from": None})
    elif a == "crop":
        seen = set()
        for it, _q, _ql in inv.slots:
            if it in seen:
                continue
            if (it.kind == "crop" and content.PRODUCE_CATEGORY.get(it) != "flower") or it is items.EEL:
                seen.add(it)
                opts.append({"inputs": [(it, 1)], "output": _preserve_of(it), "quality_from": it})
    return opts


def load_machine_choice(state: GameState, m: Machine, mdef, opt) -> None:
    """Load a machine with the option the player picked (see the load menu)."""
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
    m.loaded_output = output
    m.ready_at = state.abs_minutes + mdef.minutes
    m.out_quality = skills.process_quality(in_quality, state, "Cooking") if skills.has_quality(output) else 0
    state.log.add(f"You load the {mdef.name.lower()} ({output.name}). Ready in {_fmt_remaining(mdef.minutes)}.")


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
        if (not plot.dead and abs(cx - x) <= r and abs(cy - y) <= r
                and getattr(plot.crop, "category", "") == "flower"):
            n += 1
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
    one entry per (item, quality)."""
    return [(it, q, ql) for it, q, ql in state.player.inventory.slots if it.energy > 0]


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


def sell_shipment(state: GameState) -> None:
    """Convert everything in the shipping bin to gold overnight (quality-scaled)."""
    total = sum(slot_value(it, ql) * qty for it, qty, ql in state.ship_bin.slots)
    if total > 0:
        state.player.gold += total
        state.bump("gold_earned", total)
        state.log.add(f"The shipping bin sold your goods for {total}g.", (240, 214, 120))
        state.ship_bin.slots.clear()
