"""The village request board & the market's moods — the demand side of the Vale.

Villagers pin favours to the notice board on each village square: so-many of a
thing they happen to need, paid over the odds, with friendship (and now and then
a recipe) folded in with the coin. Favours drift onto the board and expire on
their own clocks rather than refreshing on a schedule, and only ever ask for
things the player could plausibly lay hands on — in-season crops and fish,
dishes they know how to cook, goods their machines actually make.

Separately, the wider market takes cravings: for a few days one kind of goods
sells dear at the shipping bin. Both are rolled at dawn (see farming.new_day).
"""
from __future__ import annotations

import math
import random

from ..data import content
from ..engine import constants as C
from ..entities import items
from .state import GameState

MAX_OPEN = 4                  # the board holds only so many pinned favours
FRIEND_POINTS = 45            # a filled favour warms its poster about like a loved gift
RECIPE_CHANCE = 0.22          # ...and sometimes has a recipe folded in with the payment


# --- learning recipes ---------------------------------------------------------
def learn_recipe(state: GameState, name: str, teacher: str = "") -> bool:
    """Add a cook recipe to the player's repertoire. Returns True if it was new."""
    if name in state.known_recipes:
        return False
    state.known_recipes.add(name)
    who = f"{teacher} teaches you" if teacher else "You learn"
    state.log.add(f"{who} the recipe for {name}! (c to cook it)", (232, 200, 120))
    return True


def check_level_recipes(state: GameState) -> None:
    """Practice pays: some recipes simply come to a cook at a Cooking level, and
    to a herbalist at a Herbalism level."""
    from . import skills
    lvl = skills.skill_level(state, "Cooking")
    for need, name in content.COOKING_LEVEL_RECIPES.items():
        if lvl >= need and name not in state.known_recipes:
            state.known_recipes.add(name)
            state.log.add(f"It comes to you at the stove — you work out {name}!",
                          (232, 200, 120))
    hlvl = skills.skill_level(state, "Herbalism")
    for need, name in content.HERBALISM_LEVEL_RECIPES.items():
        if hlvl >= need and name not in state.known_recipes:
            state.known_recipes.add(name)
            state.log.add(f"You puzzle out a new remedy — {name} (brew it at an apothecary)!",
                          (200, 224, 150))


def unknown_recipes(state: GameState) -> list[str]:
    return [r.name for r in content.RECIPES
            if r.kind == "cook" and r.name not in state.known_recipes]


# --- what a villager might ask for ---------------------------------------------
def _known_dishes(state: GameState) -> list:
    return [r.output for r in content.RECIPES
            if r.kind == "cook" and r.name in state.known_recipes
            and r.output is not None and r.output.value > 0]


def _fish_pool(state: GameState) -> list:
    pool = [f.item for f in content.FISH
            if not f.seasons or state.season in f.seasons]
    pool += [it for it, _w in content.SEA_FISH]
    pool += [it for it, _w in content.CAVE_FISH]      # cave lakes fish year-round
    pool += [it for it, _w in content.MARSH_FISH]     # the fen and the ponds, likewise
    pool += [it for it, _w in content.LAKE_FISH]
    return pool


def _request_pool(state: GameState, role: str) -> list:
    """Things this villager might plausibly pin a favour for, by their trade."""
    season = state.season
    crops = [c.produce for c in content.CROPS if c.season == season]
    it = items
    drinks = sorted(set(content.FRUIT_WINE.values()), key=lambda i: i.name) + \
        [it.CIDER, it.PERRY, it.MEAD, it.VODKA]
    preserves = sorted(set(content.FRUIT_JAM.values()) | set(content.VEG_PICKLE.values()),
                       key=lambda i: i.name)
    mushrooms = [it.BUTTON_MUSHROOM, it.BOLETE, it.CHANTERELLE, it.PARASOL_MUSHROOM,
                 it.CAVE_MUSHROOM, it.GLOWCAP]
    herbs = [it.CHAMOMILE, it.YARROW, it.COMFREY, it.LAVENDER, it.SAGE, it.MANDRAKE]
    calming = [it.CHAMOMILE, it.LAVENDER, it.SAGE]
    parts = [it.SLIME_GEL, it.BAT_WING, it.LURKER_SCALE, it.WRAITH_ESSENCE,
             it.SPORE_SAC, it.GRAVE_DUST, it.EMBER_CORE, it.WYRM_SCALE]
    # Cured fish a taproom or fisher would plausibly ask for — the achievable
    # ones; the ultra-rare (smoked moonfish, caviar) stay sell/gift/collection.
    cured_fish = [c for f, c in content.FISH_CURED.items() if f.value <= 120]
    pools = {
        "innkeeper":  _known_dishes(state) + drinks + _fish_pool(state)
                      + cured_fish + [it.TRUFFLE, it.PORK, it.BEEF],
        # Nothing Bron himself sells (fuels, bars): a favour must never be
        # fillable at a profit straight off his own shelf.
        # ...including blasting powder for the mine crews (the miner's commission).
        "blacksmith": [it.COPPER_ORE, it.IRON_ORE, it.TIN_ORE, it.SULPHUR, it.SALTPETER,
                       it.GUNPOWDER],
        "carpenter":  [it.WOOD, it.TIMBER_PLANK, it.STONE],
        "forester":   [it.WOOD, it.TIMBER_PLANK] + mushrooms,
        "forager":    mushrooms + herbs + parts + [it.HONEY, it.ASTER] + crops,
        "priest":     [it.ASTER, it.TULIP, it.HONEY] + calming + preserves + parts,
        "farmer":     crops + [it.EGG, it.MILK, it.DUCK_EGG, it.GOAT_MILK, it.FERTILISER],
        "fisher":     _fish_pool(state) + cured_fish,
        "child":      [d for d in _known_dishes(state)
                       if d.name in ("Cookies", "Candied Fruit", "Frozen Yogurt",
                                     "Pancakes", "Berry Pie", "Cake")]
                      + [c for c in crops if content.is_fruit(c)],
        "trader":     preserves + drinks + [it.WOOLEN_CLOTH, it.COTTON_CLOTH,
                                            it.LINEN_CLOTH, it.DRAKE_SCALE,
                                            it.QUILT, it.WALL_TAPESTRY] + parts,
        # The working-age newcomers, each by their craft.
        "woodcarver": [it.WOOD, it.TIMBER_PLANK, it.HONEY, it.CAKE, it.ANTLER] + preserves,
        "bard":       _known_dishes(state) + drinks + [it.HONEY, it.CANDIED_FRUIT],
        "mason":      [it.STONE, it.TIMBER_PLANK, it.COAL, it.BEEF, it.BREAD,
                       it.SAUSAGE_ROLL, it.CHEESE],
        # Grape wine, not the generic "Wine": every fruit ferments into its own
        # named wine, so plain Wine is never made and the favour could only be
        # filled with a bottle some villager happened to give you.
        "diver":      _fish_pool(state) + [it.AMETHYST, it.TOPAZ, it.SAPPHIRE, it.GRAPE_WINE],
        "trapper":    [it.MEAT, it.RAW_HIDE, it.BOAR_HIDE, it.WOLF_PELT, it.JERKY, it.ANTLER] + mushrooms,
    }
    default = crops + preserves + _known_dishes(state) + [it.EGG, it.MILK, it.CHEESE]
    pool = pools.get(role, default) or default
    # A flower or crop request must still be growable/forageable — pools above
    # already season-filter crops; everything else is season-free.
    return [p for p in pool if p.value > 0 and _within_reach(state, p)]


def _within_reach(state: GameState, it) -> bool:
    """Whether a good can be made yet. A hybrid's jam, wine or pickle needs the
    hybrid: until the player has bred that cross, no villager has heard of it."""
    src = getattr(it, "source", None)
    crop = _HYBRID_OF_PRODUCE.get(src) or _HYBRID_OF_PRODUCE.get(it)
    return crop is None or crop in state.hybrids_bred


_HYBRID_OF_PRODUCE = {c.produce: c.name for c in content.HYBRIDS}


_FLAVOR = {
    "innkeeper":  "The pot's running low — {want} would see the taproom fed.",
    "blacksmith": "The forge is hungry. {want}, and I'll pay over the odds.",
    "carpenter":  "A commission calls for {want}, and my stock's spent.",
    "forester":   "The camp's short of {want}. Coin waiting, no questions.",
    "forager":    "I need {want} for a remedy that won't wait.",
    "priest":     "The shrine would be glad of {want}, for the season's blessing.",
    "farmer":     "Trade being what it is, I need {want} more than I need coin.",
    "fisher":     "My nets came up empty — {want} would save my week.",
    "child":      "Please please PLEASE — {want}! I've been saving my pennies!",
    "trader":     "A buyer out east is after {want}. Quietly, mind.",
    "woodcarver": "I've a piece half-carved and no good wood left — {want} would finish it.",
    "bard":       "I'm putting on a night of song; {want} would make it a feast to remember.",
    "mason":      "A wall won't raise itself — {want}, and I'll see it well set.",
    "diver":      "I'll dive for coin, but {want}'s quicker. Bring it and I'll pay from the haul.",
    "trapper":    "The fen's owed me a lean week. {want} would tide me over, no questions.",
}
_FLAVOR_DEFAULT = "I'd be glad of {want}, and I'll pay well for the favour."


def _qty_for(value: int, rng) -> int:
    if value < 40:
        return rng.randint(3, 5)
    if value < 120:
        return rng.randint(2, 3)
    if value < 300:
        return rng.randint(1, 2)
    return 1


def _new_request(state: GameState, rng) -> dict | None:
    npcs = list(getattr(state.surface, "npcs", ())) or []
    if not npcs:
        return None
    npc = rng.choice(npcs)
    pool = _request_pool(state, npc.role)
    # ...but never two open favours for the same thing, or from the same poster
    taken_items = {r["item"] for r in state.requests}
    taken_npcs = {r["npc"] for r in state.requests}
    pool = [p for p in pool if p.name not in taken_items]
    if not pool or npc.name in taken_npcs:
        return None
    item = rng.choice(pool)
    qty = _qty_for(item.value, rng)
    gold = int(math.ceil(item.value * qty * rng.uniform(1.5, 2.0) / 5.0)) * 5
    want = f"{qty} {item.name}" if qty > 1 else f"a {item.name}"
    return {"npc": npc.name, "item": item.name, "qty": qty, "gold": gold,
            "expires": state.day + rng.randint(5, 9),
            "flavor": _FLAVOR.get(npc.role, _FLAVOR_DEFAULT).format(want=want)}


# --- bounties ------------------------------------------------------------------
# Now and then the board asks for a culling instead of goods: so many of one
# kind of monster, counted from the day it was pinned (the bestiary keeps the
# tally). It asks for what haunts the floors you've actually walked — a
# newcomer is sent after slimes and bats, a deep delver after wights.
BOUNTY_CHANCE = 0.3           # of a fresh favour being a bounty (one open at a time)
BOUNTY_REACH = 4              # floors above your deepest a bounty may look back
_BOUNTY_POSTERS = ("blacksmith", "mason", "priest", "trapper", "innkeeper", "forester")
_BOUNTY_FLAVOR = "They've grown bold below. Put down {want} and it won't go unthanked."


def _bounty_marks(state: GameState) -> list:
    # No new kind of monster appears below the last one's floor, so a delver
    # past it is still asked for the deepest kinds. (Measured from the floor
    # itself, the window slid off the end of the roster: at floor 15 it was
    # empty, and the fallback sent a veteran after slimes and bats.)
    last = max(m.min_depth for m in content.MONSTERS)
    deepest = min(last, max(1, int(state.stats.get("deepest_depth", 0))))
    return [m for m in content.MONSTERS
            if deepest - BOUNTY_REACH <= m.min_depth <= deepest] or \
           [m for m in content.MONSTERS if m.min_depth <= 1]


def _new_bounty(state: GameState, rng) -> dict | None:
    posters = [n for n in getattr(state.surface, "npcs", ()) if n.role in _BOUNTY_POSTERS
               and n.name not in {r["npc"] for r in state.requests}]
    if not posters or any(r.get("bounty") for r in state.requests):
        return None
    npc, mark = rng.choice(posters), rng.choice(_bounty_marks(state))
    qty = rng.randint(3, 6)
    gold = int(math.ceil(qty * (25 + 20 * mark.min_depth) * rng.uniform(0.9, 1.2) / 5.0)) * 5
    plural = mark.name + ("es" if mark.name.endswith(("s", "ch")) else "s")
    return {"npc": npc.name, "item": plural, "qty": qty, "gold": gold,
            "bounty": mark.name, "from": int(state.bestiary.get(mark.name, 0)),
            "expires": state.day + rng.randint(7, 12),
            "flavor": _BOUNTY_FLAVOR.format(want=f"{qty} {plural.lower()}")}


def progress(state: GameState, req: dict) -> int:
    """How much of a favour is in hand: goods carried, or kills since a bounty
    was pinned."""
    if req.get("bounty"):
        return max(0, int(state.bestiary.get(req["bounty"], 0)) - int(req.get("from", 0)))
    it = items.by_name(req["item"])
    return sum(state.player.inventory.count(i) for i in _fills(state, it)) if it else 0


def want_text(req: dict) -> str:
    """What a favour asks, as the board words it."""
    return (f"slay {req['qty']} {req['item']}" if req.get("bounty")
            else f"{req['qty']} {req['item']}")


def _year_finale():
    """(season, day, name) of the year's last festival — the fireworks night."""
    order = {s: i for i, s in enumerate(C.SEASONS)}
    best = None
    for season, fests in content.FESTIVALS.items():
        for f in fests:
            key = (order[season], f[0])
            if best is None or key > best[0]:
                best = (key, season, f[0], f[1])
    return best[1], best[2], best[3]


FIREWORKS_QTY = 8


def _fireworks_commission(state: GameState) -> None:
    """The standing annual order: in the run-up to the year's last festival,
    the innkeepers post for firecrackers to light the closing night. Fill it
    and the show goes up over the square — every year, a new order."""
    season, fday, fname = _year_finale()
    if state.season != season or not (fday - 10 <= state.day_of_season < fday):
        return
    if state.stats.get(f"fireworks_{state.year}"):
        return
    if any(r.get("annual") == "fireworks" for r in state.requests):
        return
    host = next((n for n in getattr(state.surface, "npcs", ())
                 if n.role == "innkeeper"), None)
    if host is None:
        return
    gold = int(items.FIRECRACKER.value * FIREWORKS_QTY * 2.2 / 5) * 5
    state.requests.append({
        "npc": host.name, "item": "Firecracker", "qty": FIREWORKS_QTY, "gold": gold,
        "expires": state.day + (fday - state.day_of_season),
        "flavor": f"{fname} closes the year — bring firecrackers and we'll light the sky!",
        "annual": "fireworks"})
    state.log.add(f"The innkeepers post the year's fireworks order: {FIREWORKS_QTY} "
                  f"firecrackers before {fname}!", (232, 200, 120))


def new_day(state: GameState) -> None:
    """Dawn tick: quietly retire stale favours, maybe pin fresh ones, and let
    the market's craving shift. Drifting chances, not a fixed cadence."""
    state.requests = [r for r in state.requests if r["expires"] > state.day]
    _fireworks_commission(state)
    for r in state.requests:
        if r["expires"] == state.day + 1:     # last chance — say so at dawn
            state.log.add(f"{r['npc']}'s favour ({want_text(r)}) comes down "
                          "from the board tomorrow.", (224, 180, 120))
    rng = random.Random((state.seed * 811 + state.day * 2903) & 0x7FFFFFFF)
    for chance in (0.45, 0.30):
        if len(state.requests) >= MAX_OPEN or rng.random() > chance:
            continue
        req = (_new_bounty(state, rng) if rng.random() < BOUNTY_CHANCE else None) \
            or _new_request(state, rng)
        if req:
            state.requests.append(req)
            state.log.add(f"A new favour is pinned to the village notice boards. ({req['npc']})",
                          (200, 220, 160))
    _roll_demand(state, rng)
    check_level_recipes(state)


# --- fulfilment -----------------------------------------------------------------
def _find_npc(state: GameState, name: str):
    for n in getattr(state.surface, "npcs", ()):
        if n.name == name:
            return n
    return None


def _fills(state: GameState, it) -> list:
    """What you carry that answers a favour for `it`: the thing itself, and —
    for a dish that is only ever cooked as a named variant (nobody can make
    plain "Sashimi"; the pan gives Tuna Sashimi, Minnow Sashimi…) — any of
    its kind, by family, the way tastes match. Cheapest first, so the humble
    plate goes over before the fine one."""
    kin = f"dish:{it.name}"
    held = {e[0] for e in state.player.inventory.slots
            if e[0] is it or e[0].family == kin}
    return sorted(held, key=lambda i: (i.value, i.name))


def can_fulfil(state: GameState, req: dict) -> bool:
    if req.get("bounty"):
        return progress(state, req) >= req["qty"]
    it = items.by_name(req["item"])
    if it is None:
        return False
    inv = state.player.inventory
    return sum(inv.count(i) for i in _fills(state, it)) >= req["qty"]


def _claim_bounty(state: GameState, req: dict) -> bool:
    """Report a finished culling at the board: the fee, the poster's regard."""
    from . import karma, skills
    done = progress(state, req)
    if done < req["qty"]:
        state.log.add(f"{req['npc']} wants {req['qty']} {req['item'].lower()} put down — "
                      f"you've accounted for {done} so far.", C.DIM)
        return False
    if req in state.requests:
        state.requests.remove(req)
    state.player.gold += req["gold"]
    state.bump("gold_earned", req["gold"])
    state.bump("requests_filled")
    state.bump("bounties_claimed")
    karma.adjust(state, 1)
    npc = _find_npc(state, req["npc"])
    if npc is not None:
        from . import village
        village.befriend(state, npc, karma.scale(state.player.karma, FRIEND_POINTS))
        npc.met = True
    state.log.add(f"You report the culling to {req['npc']} — {req['gold']}g, and the Vale "
                  "sleeps easier.", (232, 200, 120))
    skills.gain_char_xp(state, 30)
    return True


def deliver(state: GameState, req: dict) -> bool:
    """Hand over a favour's goods at the board: premium gold, the poster's
    friendship, a nudge of karma — and now and then a recipe in the envelope."""
    from . import karma, skills
    if req.get("bounty"):
        return _claim_bounty(state, req)
    it = items.by_name(req["item"])
    inv = state.player.inventory
    if it is None or not can_fulfil(state, req):
        state.log.add(f"You don't have {req['qty']} {req['item']} to hand.", C.DIM)
        return False
    # Lowest-quality stock goes over first, but fine goods still earn their
    # stars: +20% of the fee per average star handed over.
    owed, stars = req["qty"], 0.0
    for held in _fills(state, it):
        take = min(owed, inv.count(held))
        stars += inv.pop_quality(held, take) * take
        owed -= take
        if not owed:
            break
    avg_q = stars / req["qty"]
    bonus = round(req["gold"] * 0.2 * avg_q)
    paid = req["gold"] + bonus
    if req in state.requests:
        state.requests.remove(req)
    state.player.gold += paid
    state.bump("gold_earned", paid)
    state.bump("requests_filled")
    karma.adjust(state, 1)
    npc = _find_npc(state, req["npc"])
    if npc is not None:
        from . import village
        village.befriend(state, npc, karma.scale(state.player.karma, FRIEND_POINTS))
        npc.met = True
    extra = f" (+{bonus}g for the quality)" if bonus else ""
    state.log.add(f"You fill {req['npc']}'s favour — {req['gold']}g{extra}, with thanks.",
                  (232, 200, 120))
    if req.get("annual") == "fireworks":
        state.stats[f"fireworks_{state.year}"] = 1
        state.log.add("The fireworks are promised — watch the sky on the festival night!",
                      (232, 200, 120))
    skills.gain_char_xp(state, 30)
    rng = random.Random((state.seed * 977 + state.day * 431
                         + state.stats.get("requests_filled", 0)) & 0x7FFFFFFF)
    pool = unknown_recipes(state)
    if pool and rng.random() < RECIPE_CHANCE:
        learn_recipe(state, rng.choice(pool), teacher=req["npc"])
    from . import quests
    quests.check(state)
    return True


# --- the market's cravings -------------------------------------------------------
DEMAND_KINDS = {
    "crop":    "farm crops",
    "food":    "cooked fare",
    "artisan": "artisan goods",
    "fish":    "fresh fish",
    "animal":  "animal produce",
}


DEMAND_RANGE = (1.35, 1.75)     # how hard the market craves a kind (bin multiplier)


def _roll_demand(state: GameState, rng) -> None:
    d = state.demand
    if d and state.day >= d.get("until", 0):
        state.log.add(f"The market's craving for {DEMAND_KINDS[d['kind']]} has passed.", C.DIM)
        state.demand = {}
        d = {}
    if not d and rng.random() < 0.22:
        kind = rng.choice(list(DEMAND_KINDS))
        mult = round(rng.uniform(*DEMAND_RANGE) * 20) / 20
        state.demand = {"kind": kind, "mult": mult,
                        "until": state.day + rng.randint(4, 8)}
        pct = int(round((mult - 1) * 100))
        state.log.add(f"Word from the market: {DEMAND_KINDS[kind]} fetch +{pct}% "
                      f"at the shipping bin for a few days!", (232, 200, 120))
    elif d:
        left = d["until"] - state.day
        pct = int(round((d["mult"] - 1) * 100))
        state.log.add(f"The market still craves {DEMAND_KINDS[d['kind']]} "
                      f"(+{pct}%, ~{left} more day{'s' if left != 1 else ''}).", C.DIM)


def demand_mult(state: GameState, item) -> float:
    """The market's multiplier for one item (1.0 outside a craving)."""
    d = state.demand
    if d and item.kind == d.get("kind") and state.day < d.get("until", 0):
        return d["mult"]
    return 1.0
