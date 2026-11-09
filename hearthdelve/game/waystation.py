"""The deep couriers' waystations: one on every Deep Sanctum (each tenth floor).

A long delve fills your pack with ore and spoil it then has to haul back up,
and a faint down there costs you the loose loot you carry. Each sanctum keeps
a sealed coffer of the deep couriers by its stairs up: leave a load in it, pay
the fee, and they carry it up to your farm chest by morning. It lightens the
pack and banks the haul; it never carries anything down, and nothing's
locked behind it.
"""
from __future__ import annotations

from ..engine import constants as C
from .state import GameState

SANCTUM_STEP = 10           # a Deep Sanctum every tenth floor
COURIER_FEE = 5             # gold a load (a stack), whatever it weighs


def place(gm) -> None:
    """Stand a waystation beside a sanctum's stairs up."""
    if gm.stairs_up is None:
        return
    from ..entities.machine import Machine
    sx, sy = gm.stairs_up
    for dx, dy in ((-1, 0), (0, -1), (1, 0), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        x, y = sx + dx, sy + dy
        if gm.walkable(x, y) and (x, y) != gm.stairs_down and (x, y) not in gm.machines:
            gm.machines[(x, y)] = Machine(kind="waystation")
            return


def send(state: GameState, item, qty: int, quality: int) -> bool:
    """Leave a load in the coffer for the couriers: they take it up tonight."""
    p = state.player
    if p.gold < COURIER_FEE:
        state.log.add(f"The couriers' fee is {COURIER_FEE}g a load — you're short.", C.DIM)
        return False
    if not p.inventory.remove(item, qty, quality=quality):
        return False
    p.gold -= COURIER_FEE
    state.couriered.add(item, qty, quality=quality)
    state.log.add(f"You seal {qty} {item.name.lower()} in the coffer — it'll be in your chest "
                  f"by morning. ({COURIER_FEE}g)" if qty > 1 else
                  f"You seal the {item.name.lower()} in the coffer — it'll be in your chest "
                  f"by morning. ({COURIER_FEE}g)", (196, 170, 116))
    return True


def send_all(state: GameState) -> int:
    """Leave the whole pack, a load at a time, as far as the fees go."""
    sent = 0
    for it, q, ql in list(state.player.inventory.slots):
        if state.player.gold < COURIER_FEE:
            state.log.add("You're out of coin for the couriers' fees.", C.DIM)
            break
        if send(state, it, q, ql):
            sent += 1
    return sent


def deliver(state: GameState) -> None:
    """Dawn: the couriers set last night's loads in your farm chest."""
    loads = list(state.couriered.slots)
    if not loads:
        return
    for it, q, ql in loads:
        state.storage.add(it, q, quality=ql)
    state.couriered.slots.clear()
    n = sum(q for _it, q, _ql in loads)
    state.log.add(f"The deep couriers have brought {n} good{'s' if n != 1 else ''} up to your "
                  "chest in the night.", (196, 170, 116))
