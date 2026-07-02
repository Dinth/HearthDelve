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


def _place_machine(state: GameState, kind: str) -> bool:
    p = state.player
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
    state.world.machines[(tx, ty)] = Machine(kind=kind)
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

    # empty -> load
    return _load_machine(state, m, mdef)


def _load_machine(state: GameState, m: Machine, mdef) -> bool:
    from . import skills
    inv = state.player.inventory
    output = mdef.output
    in_quality = 0.0

    if mdef.accepts == "ore":
        # smelt the most valuable bar the player can currently make
        best = None
        for bar, inputs in content.FURNACE_RECIPES:
            if all(inv.count(it) >= q for it, q in inputs.items()):
                if best is None or bar.value > best[0].value:
                    best = (bar, inputs)
        if best is None:
            state.log.add(f"The {mdef.name.lower()} needs ore and coal.", C.DIM)
            return True
        output, inputs = best
        for it, q in inputs.items():
            inv.remove(it, q)

    elif mdef.accepts == "wood":
        # Sawmill: saw a couple of logs into a plank.
        if inv.count(items.WOOD) < 2:
            state.log.add(f"The {mdef.name.lower()} needs at least 2 wood.", C.DIM)
            return True
        inv.remove(items.WOOD, 2)
        output = mdef.output                       # Timber Plank

    elif mdef.accepts == "oil":
        # Oil press: squeeze a couple of sunflowers into oil.
        if inv.count(items.SUNFLOWER) < 2:
            state.log.add(f"The {mdef.name.lower()} needs at least 2 sunflowers.", C.DIM)
            return True
        in_quality = inv.pop_quality(items.SUNFLOWER, 2)
        output = items.SUNFLOWER_OIL

    elif mdef.accepts == "fruit":
        # Keg: honey -> mead; mead -> aged mead; otherwise fruit -> wine.
        if inv.count(items.HONEY) > 0:
            in_quality = inv.pop_quality(items.HONEY, 1)
            output = items.MEAD
        elif inv.count(items.MEAD) > 0:
            in_quality = inv.pop_quality(items.MEAD, 1)
            output = items.AGED_MEAD
        else:
            crop_item = items.GRAPE if inv.count(items.GRAPE) > 0 else _best_crop(state, fruit_only=True)
            if crop_item is None:
                state.log.add(f"The {mdef.name.lower()} ferments fruit into wine, or honey into mead.", C.DIM)
                return True
            in_quality = inv.pop_quality(crop_item, 1)
            output = items.GRAPE_WINE if crop_item is items.GRAPE else items.WINE

    elif mdef.accepts == "crop":
        # Preserves Jar: fruit -> jam, vegetables -> pickles, eel -> jellied eel.
        # (Flowers aren't preserved.)
        candidates = [it for it, _q, _ql in inv.slots
                      if (it.kind == "crop" and content.PRODUCE_CATEGORY.get(it) != "flower")
                      or it is items.EEL]
        if not candidates:
            state.log.add(f"The {mdef.name.lower()} needs a crop or an eel.", C.DIM)
            return True
        chosen = max(candidates, key=lambda it: it.value)
        in_quality = inv.pop_quality(chosen, 1)
        if chosen is items.EEL:
            output = items.JELLIED_EEL
        elif content.is_fruit(chosen):
            output = items.JAM
        else:
            output = items.PICKLES

    m.loaded_output = output
    m.ready_at = state.abs_minutes + mdef.minutes
    m.out_quality = skills.process_quality(in_quality, state, "Cooking") if skills.has_quality(output) else 0
    state.log.add(f"You load the {mdef.name.lower()} ({output.name}). Ready in {_fmt_remaining(mdef.minutes)}.")
    return True


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


def _best_crop(state: GameState, fruit_only: bool = False):
    crops = [e[0] for e in state.player.inventory.slots
             if e[0].kind == "crop" and (not fruit_only or content.is_fruit(e[0]))]
    return max(crops, key=lambda it: it.value, default=None)


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
