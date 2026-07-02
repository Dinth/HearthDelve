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

    if recipe.kind == "build":
        if not _place_machine(state, recipe.machine):
            return False
    elif recipe.kind == "cook":
        p = state.player
        p.energy = min(p.max_energy, p.energy + recipe.energy)
        state.log.add(f"You cook and eat {recipe.name}. (+{recipe.energy} stamina)", (180, 230, 160))
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

    if m.kind == "sprinkler":
        state.log.add("The sprinkler waters the soil around it each morning.", C.DIM)
        return True

    if status == "done":
        state.player.inventory.add(m.loaded_output, 1)
        if m.loaded_output.kind == "artisan":
            state.bump("artisan_made")
        state.log.add(f"You collect {m.loaded_output.name} from the {mdef.name.lower()}.", (180, 230, 160))
        m.loaded_output = None
        m.ready_at = 0
        return True

    if status == "working":
        state.log.add(f"The {mdef.name.lower()} is working — {_fmt_remaining(m.ready_at - now)} left.", C.DIM)
        return True

    # empty -> load
    return _load_machine(state, m, mdef)


def _load_machine(state: GameState, m: Machine, mdef) -> bool:
    inv = state.player.inventory
    output = mdef.output

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

    elif mdef.accepts == "fruit":
        # Keg: only fruit becomes wine. Prefer grapes — their wine is the prize.
        if inv.count(items.GRAPE) > 0:
            crop_item = items.GRAPE
        else:
            crop_item = _best_crop(state, fruit_only=True)
        if crop_item is None:
            state.log.add(f"The {mdef.name.lower()} only ferments fruit (jam/pickle veg in a jar).", C.DIM)
            return True
        inv.remove(crop_item, 1)
        output = items.GRAPE_WINE if crop_item is items.GRAPE else items.WINE

    elif mdef.accepts == "crop":
        # Preserves Jar: fruit -> jam, vegetables -> pickles, eel -> jellied eel.
        candidates = [it for it, _ in inv.slots if it.kind == "crop" or it is items.EEL]
        if not candidates:
            state.log.add(f"The {mdef.name.lower()} needs a crop or an eel.", C.DIM)
            return True
        chosen = max(candidates, key=lambda it: it.value)
        inv.remove(chosen, 1)
        if chosen is items.EEL:
            output = items.JELLIED_EEL
        elif content.is_fruit(chosen):
            output = items.JAM
        else:
            output = items.PICKLES

    m.loaded_output = output
    m.ready_at = state.abs_minutes + mdef.minutes
    state.log.add(f"You load the {mdef.name.lower()} ({output.name}). Ready in {_fmt_remaining(mdef.minutes)}.")
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
    """Inventory entries that can be shipped (have a sell value)."""
    return [(it, q) for it, q in state.player.inventory.slots if it.value > 0]


def ship_item(state: GameState, item) -> None:
    """Move a whole stack of item from inventory into the shipping bin."""
    qty = state.player.inventory.count(item)
    if qty <= 0:
        return
    state.player.inventory.remove(item, qty)
    state.ship_bin.add(item, qty)
    state.log.add(f"You drop {qty} {item.name} in the bin.", C.DIM)


def sell_shipment(state: GameState) -> None:
    """Convert everything in the shipping bin to gold overnight."""
    total = sum(it.value * qty for it, qty in state.ship_bin.slots)
    if total > 0:
        state.player.gold += total
        state.bump("gold_earned", total)
        state.log.add(f"The shipping bin sold your goods for {total}g.", (240, 214, 120))
        state.ship_bin.slots.clear()
