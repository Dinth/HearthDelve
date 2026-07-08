"""Farm animals: buying, housing, roaming, daily care and produce.

The loop mirrors the rest of the farm but slower and gentler. You buy a chick
or calf, settle it into a coop or barn (a little coop you place yourself, a
roomy coop or a barn the carpenter raises), and it roams the yard nearby. Each
morning a grown, cared-for animal leaves produce; petting it daily keeps it
happy, and happiness lifts the quality of its eggs or milk. Neglect never
starves them — it just lets their spirits drift back to middling.

Construction of the carpenter's outbuildings also lives here: a commissioned
coop/barn goes up as a fenced-off site and finishes into a real building a
couple of mornings later.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from ..data.content import MACHINES
from ..engine import constants as C
from ..entities import items
from ..entities.animal import Animal
from ..entities.machine import Machine
from ..world import tile
from .state import GameState

DAY = 1440                      # in-game minutes in a day
BUILD_DAYS = 2                  # mornings the carpenter takes to finish an outbuilding
PET_BONUS = 12                  # happiness gained from a daily pet
NEGLECT_DRIFT = 6               # happiness lost on a day with no attention (floor 20)
HUNGER_DRIFT = 12               # happiness lost on a day with nothing to eat (floor 10)
FARM_RADIUS = 50                # how far from the homestead an outbuilding may be raised
PASTURE_RADIUS = 6              # a beast grazes if grass lies this close to its home


@dataclass(frozen=True)
class Species:
    kind: str
    glyph: str
    color: tuple[int, int, int]
    young_color: tuple[int, int, int]
    produce: object            # Item laid/given
    mature_days: int           # age at which it starts producing
    radius: int                # how far it strays from home
    speed: int                 # roam action points per tick (2 == player speed)
    young_name: str            # "chick" / "calf"
    grown_name: str            # "hen" / "cow"
    buy_item: object           # the livestock Item you settle in
    names: tuple


SPECIES = {
    "chicken": Species("chicken", "b", (245, 236, 205), (222, 216, 190),
                       items.EGG, 3, 5, 2, "chick", "hen", items.CHICK,
                       ("Hazel", "Pip", "Clucky", "Nugget", "Marigold", "Feathers",
                        "Dot", "Poppy", "Henrietta", "Sunny")),
    "cow":     Species("cow", "q", (216, 190, 152), (202, 180, 152),
                       items.MILK, 5, 7, 1, "calf", "cow", items.CALF,
                       ("Buttercup", "Clover", "Daisy", "Bess", "Maisie", "Bramble",
                        "Willow", "Rosie", "Primrose", "Moo")),
    "sheep":   Species("sheep", "y", (232, 230, 216), (216, 214, 200),
                       items.WOOL, 5, 6, 1, "lamb", "sheep", items.LAMB,
                       ("Woolly", "Snowy", "Cloud", "Nimbus", "Fluff", "Barley",
                        "Comet", "Pebble", "Tuft", "Dolly")),
}

_HOUSE_SPECIES = {"coop_small": "chicken", "coop_big": "chicken",
                  "barn": "cow", "pen": "sheep"}


# --- helpers ----------------------------------------------------------------
def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


def animal_at(state: GameState, x: int, y: int):
    for a in state.world.animals:
        if a.x == x and a.y == y:
            return a
    return None


def _occupied(state: GameState, x: int, y: int) -> bool:
    return animal_at(state, x, y) is not None or (state.player.x, state.player.y) == (x, y)


def _can_stand(state: GameState, x: int, y: int) -> bool:
    w = state.world
    return w.walkable(x, y) and not _occupied(state, x, y)


def _flock(state: GameState, home) -> list:
    return [a for a in state.world.animals if a.home == home]


def _name_for(state: GameState, spec: Species) -> str:
    taken = {a.name for a in state.world.animals}
    free = [n for n in spec.names if n not in taken]
    pool = free or list(spec.names)
    return pool[random.randrange(len(pool))]


def _free_tile_near(state: GameState, x: int, y: int):
    """A walkable, unoccupied tile at or beside (x, y) for a new animal."""
    for r in (1, 2, 3):
        spots = [(x + dx, y + dy)
                 for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                 if max(abs(dx), abs(dy)) == r]
        random.shuffle(spots)
        for sx, sy in spots:
            if _can_stand(state, sx, sy):
                return (sx, sy)
    return None


def _is_adult(a: Animal) -> bool:
    return a.age_days >= SPECIES[a.kind].mature_days


# --- placing / adding animals -----------------------------------------------
def interact_building(state: GameState, m: Machine, x: int, y: int) -> bool:
    """Grab-target on a coop/barn/site: settle a young animal, or report status."""
    from . import skills  # noqa: F401 (kept parallel with the rest of crafting)
    if m.kind == "site":
        now = state.abs_minutes
        name = _build_name(m.build_kind)
        if now < m.ready_at:
            days = max(1, (m.ready_at - now + DAY - 1) // DAY)
            state.log.add(f"Tomas is still raising your {name} — about {days} day(s) to go.", (200, 190, 150))
        else:
            state.log.add(f"Your {name} is finished — it stands ready.", (200, 220, 160))
        return True

    mdef = MACHINES[m.kind]
    species_key = _HOUSE_SPECIES[m.kind]
    spec = SPECIES[species_key]
    flock = _flock(state, (x, y))
    p = state.player

    has_young = p.inventory.count(spec.buy_item) > 0
    straw = p.inventory.count(items.STRAW)

    if has_young and len(flock) < mdef.capacity:
        spot = _free_tile_near(state, x, y)
        if spot is None:
            state.log.add("There's no room beside it for the little one.", C_DIM)
            return True
        p.inventory.remove(spec.buy_item, 1)
        nm = _name_for(state, spec)
        state.world.animals.append(Animal(kind=species_key, name=nm, glyph=spec.glyph,
                                          color=spec.color, x=spot[0], y=spot[1], home=(x, y)))
        state.bump("animals_raised")
        state.log.add(f"You settle {nm} the {spec.young_name} into the {mdef.name.lower()}.",
                      (200, 220, 160))
        return True

    # straw in hand — fork it into the building's trough for the animals to eat.
    # (Reachable even when the coop is full and you're also carrying a young one.)
    if straw > 0:
        p.inventory.remove(items.STRAW, straw)
        m.feed += straw
        state.log.add(f"You fork {straw} straw into the {mdef.name.lower()}'s trough "
                      f"({m.feed} in store).", (200, 220, 160))
        return True

    if has_young:                      # carrying a young one, but the coop was full
        state.log.add(f"The {mdef.name.lower()} is full ({mdef.capacity}).", C_DIM)
        return True

    # nothing in hand — report the flock and the trough
    grown = sum(1 for a in flock if _is_adult(a))
    state.log.add(f"{mdef.name}: {len(flock)}/{mdef.capacity} ({grown} grown), "
                  f"{m.feed} straw in the trough. Bring a {spec.young_name} to add one.",
                  (200, 200, 210))
    return True


# --- petting / collecting ---------------------------------------------------
def interact_animal(state: GameState, a: Animal) -> None:
    """Bumping an animal collects its produce if ready, else gives it a fond pat."""
    from . import skills
    spec = SPECIES[a.kind]
    p = state.player

    if a.produce_ready and _is_adult(a):
        q = _produce_quality(state, a)
        p.inventory.add(spec.produce, 1, quality=q)
        a.produce_ready = False
        if not a.petted_today:
            a.happiness = min(100, a.happiness + PET_BONUS // 2)
            a.petted_today = True
        skills.gain(state, "Farming", 8)
        state.bump("produce_collected")
        star = (" " + skills.stars(q)) if q else ""
        verb = {"chicken": "an egg", "cow": "a pail of milk",
                "sheep": "a fleece of wool"}.get(a.kind, "some produce")
        state.log.add(f"You collect {verb}{star} from {a.name}.", (232, 220, 150))
        return

    if not _is_adult(a):
        state.log.add(f"{a.name} the {spec.young_name} is still growing.", C_DIM)
        # a young one still enjoys the fuss
    if a.petted_today:
        state.log.add(f"{a.name} nuzzles you — already content today.", (200, 200, 190))
        return
    a.happiness = min(100, a.happiness + PET_BONUS)
    a.petted_today = True
    mood = "beams" if a.happiness >= 80 else "seems happier"
    state.log.add(f"You pet {a.name}; it {mood}.", (200, 220, 160))


def _produce_quality(state: GameState, a: Animal) -> int:
    from . import skills
    base = skills.roll_quality(state, "Farming")
    bonus = round((a.happiness - 50) / 25.0)     # -2 .. +2 from care
    return max(0, min(5, base + bonus))


# --- feeding ----------------------------------------------------------------
_PASTURE = {tile.GRASS, tile.TALL_GRASS, tile.MEADOW, tile.FOG_GRASS, tile.MOOR}


def _pasture_near(state: GameState, home) -> bool:
    """Whether open grass lies close enough to `home` for a beast to graze."""
    surf = state.surface
    hx, hy = home
    r = PASTURE_RADIUS
    for xx in range(hx - r, hx + r + 1):
        for yy in range(hy - r, hy + r + 1):
            if surf.in_bounds(xx, yy) and surf.tiles[xx, yy] in _PASTURE:
                return True
    return False


def _feed_animal(state: GameState, a: Animal, season: str) -> bool:
    """Feed one animal for the day. It grazes for free when there's pasture in a
    growing season; otherwise (winter, or a paved-in yard) it eats a straw from
    its building's trough (fork straw in with 'g'). Returns False if unfed."""
    if season != "Winter" and _pasture_near(state, a.home):
        return True
    m = state.surface.machines.get(a.home)
    if m is not None and m.feed > 0:
        m.feed -= 1
        return True
    return False


# --- daily cycle (called from farming.new_day) ------------------------------
def new_day(state: GameState) -> None:
    """Finish any construction, then age, feed and tend every animal for the morning."""
    _finish_construction(state)
    surf = state.surface
    season = state.season
    hungry = 0
    for a in surf.animals:
        was_adult = _is_adult(a)
        a.age_days += 1
        if not a.petted_today:
            a.happiness = max(20, a.happiness - NEGLECT_DRIFT)
        a.petted_today = False
        fed = _feed_animal(state, a, season)
        if not fed:
            a.happiness = max(10, a.happiness - HUNGER_DRIFT)
            hungry += 1
        if _is_adult(a):
            # A fed adult leaves produce; a hungry one gives nothing — but don't
            # wipe an egg/milk you simply hadn't collected yet.
            a.produce_ready = a.produce_ready or fed
            if not was_adult:              # just grew up — announce it even on a hungry morning
                spec = SPECIES[a.kind]
                state.log.add(f"{a.name} the {spec.young_name} has grown into a {spec.grown_name}.",
                              (200, 220, 160))
    if hungry:
        state.log.add(f"{hungry} of your animals went hungry — fork straw into the trough (g)!",
                      (228, 150, 110))


def _finish_construction(state: GameState) -> None:
    now = state.abs_minutes
    surf = state.surface
    done = [(pos, m) for pos, m in surf.machines.items()
            if m.kind == "site" and now >= m.ready_at]
    for (x, y), m in done:
        _raise_building(state, x, y, m.build_kind)


# --- carpenter construction -------------------------------------------------
_GROUND = {tile.GRASS, tile.MEADOW, tile.TALL_GRASS, tile.DIRT_PATH, tile.SAND,
           tile.FOG_GRASS, tile.MOOR, tile.BUSH}

# The greenhouse isn't a machine (nothing to load) — it's a walled plot of soil
# where crops grow year-round. Its size/name live here rather than in MACHINES.
GREENHOUSE_FOOTPRINT = (7, 5)


def _build_wh(kind: str):
    return GREENHOUSE_FOOTPRINT if kind == "greenhouse" else MACHINES[kind].footprint


def _build_name(kind: str) -> str:
    return "greenhouse" if kind == "greenhouse" else MACHINES[kind].name.lower()


def _footprint(door, kind):
    """Rectangle (left, top, w, h) for an outbuilding whose door sits at `door`
    on the south edge, the building extending north."""
    w, h = _build_wh(kind)
    dx, dy = door
    left = dx - w // 2
    top = dy - (h - 1)
    return left, top, w, h


def placement_cells(kind: str, door) -> list:
    """Every tile an outbuilding of `kind` would occupy with its door at `door`."""
    left, top, w, h = _footprint(door, kind)
    return [(cx, cy) for cx in range(left, left + w) for cy in range(top, top + h)]


def can_place_building(state: GameState, door, kind: str):
    """Whether an outbuilding may be sited with its door at `door`.
    Returns (ok, cells, reason) — reason is a ready-to-log line when not ok."""
    surf = state.world
    cells = placement_cells(kind, door)
    sx, sy = surf.spawn
    if max(abs(door[0] - sx), abs(door[1] - sy)) > FARM_RADIUS:
        return False, cells, "That's too far from the homestead for Tomas to work."
    for cx, cy in cells:
        if not surf.in_bounds(cx, cy):
            return False, cells, "There isn't room there — try more open ground."
        if surf.tiles[cx, cy] not in _GROUND:
            return False, cells, "The ground there isn't clear — need open grass."
        if ((cx, cy) in surf.crops or (cx, cy) in surf.machines or (cx, cy) in surf.trees
                or animal_at(state, cx, cy) or (cx, cy) == (state.player.x, state.player.y)):
            return False, cells, "Something's in the way there."
    from . import land
    if any(land.owned_by_other(state, cx, cy) for cx, cy in cells):
        return False, cells, "That land belongs to someone else — you can't build there."
    return True, cells, ""


def place_commission_at(state: GameState, dx: int, dy: int) -> bool:
    """Site an ordered outbuilding: (dx, dy) becomes the doorway; the building
    rises north behind it. Returns True if the site was staked out."""
    kind = state.pending_build
    if not kind:
        state.log.add("You've nothing on order from the carpenter.", C_DIM)
        return False
    surf = state.world
    if surf.is_dungeon:
        state.log.add("You can only raise a building on the surface.", C_DIM)
        return False
    door = (dx, dy)
    ok, cells, reason = can_place_building(state, door, kind)
    if not ok:
        state.log.add(reason, C_DIM)
        return False
    for cx, cy in cells:                      # frame it off while it goes up
        surf.tiles[cx, cy] = tile.SCAFFOLD
    # Finish on the morning BUILD_DAYS mornings from now — anchored to dawn so
    # it lines up exactly with the new_day check (not a fractional day later).
    ready = (state.day + BUILD_DAYS) * DAY + C.DAY_START_MIN
    surf.machines[door] = Machine(kind="site", build_kind=kind, ready_at=ready)
    state.pending_build = ""
    state.log.add(f"Tomas sets to work. Your {_build_name(kind)} will be ready in {BUILD_DAYS} mornings.",
                  (200, 220, 160))
    return True


def place_commission(state: GameState) -> bool:
    """Site the ordered building at the faced tile (convenience wrapper)."""
    return place_commission_at(state, state.player.x + state.player.facing[0],
                               state.player.y + state.player.facing[1])


def _raise_building(state: GameState, x: int, y: int, kind: str) -> None:
    """Turn a finished site into a real building: walls, a door, and its
    interior. A coop/barn gets a housing anchor (a Machine); a greenhouse gets
    pre-tilled soil beds and no machine (crops there grow year-round — see
    farming.in_greenhouse). Registered so the look tool names it."""
    surf = state.surface
    left, top, w, h = _footprint((x, y), kind)
    interior = tile.TILLED if kind == "greenhouse" else tile.HOUSE_FLOOR
    for cx in range(left, left + w):
        for cy in range(top, top + h):
            if not surf.in_bounds(cx, cy):
                continue
            edge = cx in (left, left + w - 1) or cy in (top, top + h - 1)
            surf.tiles[cx, cy] = tile.HOUSE_WALL if edge else interior
    surf.tiles[x, y] = tile.DOOR
    del surf.machines[(x, y)]
    if kind != "greenhouse":                       # a greenhouse isn't a machine
        surf.machines[(x, y)] = Machine(kind=kind)
    surf.buildings.append({"x": left, "y": top, "w": w, "h": h,
                           "kind": kind, "village": "", "owner": None})
    from . import land
    land.invalidate(surf)
    land.claim(state, [(cx, cy) for cx in range(left, left + w) for cy in range(top, top + h)])
    state.log.add(f"Your {_build_name(kind)} is finished!", (200, 230, 170))


# --- roaming (called from turns.advance_time on the surface) ----------------
def _wander_home(state: GameState, a: Animal, spec: Species) -> None:
    hx, hy = a.home
    dist = max(abs(a.x - hx), abs(a.y - hy))
    if dist > spec.radius:                    # stray too far → amble back
        sx, sy = _sign(hx - a.x), _sign(hy - a.y)
        for ax, ay in ((sx, sy), (sx, 0), (0, sy)):
            if (ax or ay) and _can_stand(state, a.x + ax, a.y + ay):
                a.x += ax
                a.y += ay
                return
        return
    if random.random() > 0.5:                 # otherwise a lazy random step
        return
    dirs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    random.shuffle(dirs)
    for dx, dy in dirs:
        nx, ny = a.x + dx, a.y + dy
        if max(abs(nx - hx), abs(ny - hy)) <= spec.radius and _can_stand(state, nx, ny):
            a.x, a.y = nx, ny
            return


def _shelter(state: GameState, a: Animal) -> None:
    """Head back to the coop/barn and huddle by it (used in a storm)."""
    hx, hy = a.home
    if max(abs(a.x - hx), abs(a.y - hy)) <= 1:
        return                                  # sheltering at the door
    sx, sy = _sign(hx - a.x), _sign(hy - a.y)
    for ax, ay in ((sx, sy), (sx, 0), (0, sy)):
        if (ax or ay) and _can_stand(state, a.x + ax, a.y + ay):
            a.x += ax
            a.y += ay
            return


def act(state: GameState) -> None:
    """Amble every animal near the player. No-op underground. In a storm they
    make for home and shelter instead of wandering."""
    w = state.world
    if w.is_dungeon or not w.animals:
        return
    p = state.player
    storm = state.weather == "Storm"
    for a in w.animals:
        if max(abs(a.x - p.x), abs(a.y - p.y)) > 28:   # dormant off-screen
            a.energy = 0
            continue
        spec = SPECIES[a.kind]
        a.energy += spec.speed
        while a.energy >= 2:
            a.energy -= 2
            if storm:
                _shelter(state, a)
            else:
                _wander_home(state, a, spec)


C_DIM = (150, 150, 150)
