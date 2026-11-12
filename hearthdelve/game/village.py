"""Village life: NPC schedules, talking, gifting, shops, and tool upgrades."""
from __future__ import annotations

import bisect
import random
from dataclasses import dataclass

from ..data import content
from ..engine import constants as C
from ..entities import items
from ..entities.npc import NPC, MAX_HEARTS
from . import karma
from .state import GameState


@dataclass(frozen=True)
class ShopRow:
    """One row on a shop counter. `kind` names what Enter does; everything
    else lives in named fields, so the builders here, the renderer's cells
    and the purchase dispatch can never drift out of step on a shape.

    kinds: buy · meal · recipe · sellto · commission · housejob ·
           cancel_build · tradebuy · upgrade · contest · prize · order · room
    """
    kind: str
    label: str = ""            # left-column text (item / meal / job name)
    price: int = 0             # gold the row moves (a sellto pays the player)
    item: object = None        # the good bought or sold
    tool: object = None        # the tool an upgrade improves
    build: str = ""            # machine kind a commission raises / cancels
    mats: tuple = ()           # ((Item, qty), ...) a commission consumes
    stam: int = 0              # a tavern meal's stamina restore…
    hp: int = 0                # …and heal
    quality: int = 0           # star quality of the unit sold (sellto)
    name: str = ""             # recipe name / festival name
    key: str = ""              # stats key: a trader slot sold / a smith's weekly bar stock
    left: int = -1             # units left in a counted stock (-1: the counter never runs dry)


# --- schedule ---------------------------------------------------------------
def scheduled_spot(npc, hour: int, weather: str, season: str, day_of_season: int) -> str:
    """Which anchor a resident heads to, given the hour, weather and season.

    Keys resolve against ``npc.spots``: home | work | inn | temple | square.
    """
    role = npc.role
    bad = weather in ("Rain", "Storm", "Snow")
    storm = weather == "Storm"

    # Festival day: the whole village gathers in the square through the day
    # (unless a storm spoils it). Children roam it, adults mill about.
    if content.festival_on(season, day_of_season) and 9 <= hour < 19 and not storm:
        return "square"

    # Children: out playing around the square by day, home by dusk (and in when
    # the weather's foul). "square" triggers the roaming AI in update_npcs.
    if role == "child":
        if hour < 8 or hour >= 19 or hour == 13 or storm:
            return "home"
        return "square"

    # night & early morning: asleep / at home
    if hour < 8 or hour >= 22:
        return "home"
    # midday meal at home
    if hour == 13:
        return "home"
    # evening: the tavern fills up, unless a storm keeps everyone indoors
    if hour >= 19:
        return "home" if storm else "inn"

    # working hours (08–19, minus the 13:00 meal)
    if role == "innkeeper":
        return "inn"
    if role == "priest":
        return "temple"
    if role in ("farmer", "fisher", "forager", "forester"):
        # outdoor trades can't work through a storm, a downpour, or (for the
        # fields) a frozen winter — they wait it out at the inn or at home.
        if storm or (role == "farmer" and season == "Winter"):
            return "inn"
        if bad:
            return "home"
        return "work"
    # indoor tradesfolk keep their counter/forge/loom in any weather;
    # idle villagers loiter about the market square by day
    if role in ("shopkeeper", "blacksmith", "carpenter", "trader"):
        return "work"
    return "square"


SCHEDULE_DRIFT = 45     # minutes a resident runs early or late on any given day


def npc_hour(state: GameState, npc) -> int:
    """The hour by a resident's own clock today. Each runs up to SCHEDULE_DRIFT
    minutes early or late, drawn from the seed, the day and their name — so the
    village doesn't all down tools and head home on the stroke of 13:00 and
    turn up at the inn on the stroke of 19:00, the same in every world."""
    import random
    import zlib
    rng = random.Random((state.seed * 48_271 + state.day * 16_807
                         + zlib.crc32(npc.name.encode())) & 0x7FFFFFFF)
    drift = rng.randint(-SCHEDULE_DRIFT, SCHEDULE_DRIFT)
    return ((state.time_minutes + drift) // 60) % 24


def update_npcs(state: GameState) -> None:
    """Move each resident toward their scheduled anchor for the hour by their
    own clock. Adults go straight to their spot; children roam and play
    around the square by day."""
    for npc in state.world.npcs:
        key = scheduled_spot(npc, npc_hour(state, npc), state.weather, state.season,
                             state.day_of_season)
        if key == "square":
            _child_roam(state, npc)          # mill about (kids also chase to play)
        else:
            npc.x, npc.y = npc.spots.get(key) or npc.spots.get("home") or npc.work


_CHILD_RANGE = 9      # how far kids stray from the square while playing
# How far a walk to the square may detour beyond the straight box between the
# two ends: a tight window first, a wide one if the door faces the wrong way.
_ROUTE_MARGINS = (12, 32)


def _route(w, start, goal, near: int = 2) -> list:
    """The shortest walkable way (8-way) from ``start`` to within ``near`` tiles
    of ``goal``, as the cells to step onto in order — [] if there is none.
    Searched breadth-first inside a window around both ends, so it stays cheap
    on a world-sized map: out of a cottage door and round the houses, which a
    straight-line step can't do."""
    for margin in _ROUTE_MARGINS:
        path = _route_within(w, start, goal, near, margin)
        if path:
            return path
    return []


def _route_within(w, start, goal, near: int, margin: int) -> list:
    from collections import deque
    (sx, sy), (gx, gy) = start, goal
    x0, x1 = min(sx, gx) - margin, max(sx, gx) + margin
    y0, y1 = min(sy, gy) - margin, max(sy, gy) + margin
    came = {start: None}
    todo = deque([start])
    while todo:
        x, y = todo.popleft()
        if max(abs(x - gx), abs(y - gy)) <= near:
            path = []
            while (x, y) != start:
                path.append((x, y))
                x, y = came[(x, y)]
            return path[::-1]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if (n in came or not (x0 <= n[0] <= x1 and y0 <= n[1] <= y1)
                        or not w.walkable(*n)):
                    continue
                came[n] = (x, y)
                todo.append(n)
    return []


def _head_for(state: GameState, npc, goal) -> None:
    """Take one step along the way to ``goal``, following the cached route and
    finding a fresh one whenever its next step is gone (a fence went up, or the
    villager was moved). The player is never walked through — they wait."""
    w = state.world
    r = npc.route
    if not (r and max(abs(r[0][0] - npc.x), abs(r[0][1] - npc.y)) == 1 and w.walkable(*r[0])):
        r = npc.route = _route(w, (npc.x, npc.y), goal)
    if r and r[0] != (state.player.x, state.player.y):
        npc.x, npc.y = r.pop(0)


def _child_roam(state: GameState, npc) -> None:
    """A lively amble about the square — kids also chase each other to play.
    Anyone who has strayed (or is just setting out from home) walks back first,
    by a real route: a straight-line step couldn't get out of a cottage door,
    which left most of a village wedged at home all day and festivals empty."""
    import random
    w = state.world
    anchor = npc.spots.get("square") or npc.spots.get("home") or (npc.x, npc.y)
    px, py = state.player.x, state.player.y
    if max(abs(npc.x - anchor[0]), abs(npc.y - anchor[1])) > _CHILD_RANGE:
        _head_for(state, npc, anchor)                   # strayed too far — head back
        return
    npc.route = []

    tx = ty = None
    if npc.role == "child":
        # find a playmate to run toward, if one's a little way off
        mates = [n for n in w.npcs if n.role == "child" and n is not npc]
        mate = min(mates, key=lambda k: (k.x - npc.x) ** 2 + (k.y - npc.y) ** 2, default=None)
        if mate is not None:
            d = max(abs(mate.x - npc.x), abs(mate.y - npc.y))
            if 2 < d < 16 and random.random() < 0.6:
                tx, ty = mate.x, mate.y                 # chase a friend
    if random.random() < 0.35 and tx is None:
        return                                          # pause a beat

    if tx is not None:
        sx = (tx > npc.x) - (tx < npc.x)
        sy = (ty > npc.y) - (ty < npc.y)
        options = [(sx, sy), (sx, 0), (0, sy)]
    else:
        options = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        random.shuffle(options)
    for dx, dy in options:
        nx, ny = npc.x + dx, npc.y + dy
        if (dx or dy) and w.walkable(nx, ny) and (nx, ny) != (px, py):
            npc.x, npc.y = nx, ny
            return


def npc_near(state: GameState):
    """The NPC on the faced tile, or an adjacent one (for talk/gift).

    Several residents can share a tile — a schedule sends them to the same
    fireside or tavern spot, and a village with nowhere to build once put all
    seven on the square. This used to be a ``{pos: npc}`` comprehension, so the
    last one in the list won and everybody behind them was unreachable: no talk,
    no gift, no heart line, and in Fenwick's case a tavern and a trading counter
    that could never be opened. Prefer whoever still has business today, so
    speaking to a crowd cycles through it instead of hitting one person over
    and over."""
    p = state.player
    fx, fy = p.facing
    by_pos: dict = {}
    for n in state.world.npcs:
        by_pos.setdefault((n.x, n.y), []).append(n)

    def pick(here: list):
        return next((n for n in here if not n.talked_today or not n.gifted_today), here[0])

    faced = (p.x + fx, p.y + fy)
    if faced in by_pos:
        return pick(by_pos[faced])
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        here = by_pos.get((p.x + dx, p.y + dy))
        if here:
            return pick(here)
    return None


# --- talk & gift ------------------------------------------------------------
# --- birthdays ------------------------------------------------------------------
BIRTHDAY_GIFT_MULT = 3      # a kind gift on someone's birthday means three times as much
_BIRTHDAYS: dict = {}       # (seed, roster) -> birthdays: derived, so never saved

_BIRTHDAY_LINES = (
    "It's my birthday today! Fancy you stopping by — or did you know?",
    "Another year older today, and not a day wiser. Still — it's my birthday!",
    "My birthday, would you believe. The kettle's on if you're passing.",
    "It's my birthday — a year older this morning. Don't you dare say I look it.",
)


_DWARF_NAMES: tuple = ()


def _dwarf_names() -> tuple:
    """Khazgrim's folk, by name — known from the start, so their birthdays
    are fixed before you ever meet them."""
    global _DWARF_NAMES
    if not _DWARF_NAMES:
        _DWARF_NAMES = tuple(n.name for n in content.dwarf_npcs())
    return _DWARF_NAMES


def birthdays(state: GameState) -> dict:
    """Every villager's birthday as (season, day of season), Khazgrim's
    dwarves too: drawn from the world's seed, one to a day and none on a
    festival. The world is rebuilt from its seed on every load, so they come
    out the same every time and nothing new is saved."""
    roster = tuple(sorted({n.name for n in state.surface.npcs} | set(_dwarf_names())))
    memo = _BIRTHDAYS.get((state.seed, roster))
    if memo is not None:
        return memo
    taken = {(season, fest[0]) for season, fests in content.FESTIVALS.items() for fest in fests}
    out = {}
    for name in roster:
        i = random.Random(f"{state.seed}:birthday:{name}").randrange(C.YEAR_LEN)
        for _ in range(C.YEAR_LEN):
            day = (C.SEASONS[i // C.SEASON_LEN], i % C.SEASON_LEN + 1)
            if day not in taken:
                break
            i = (i + 1) % C.YEAR_LEN               # someone has it: the next free day
        taken.add(day)
        out[name] = day
    _BIRTHDAYS[(state.seed, roster)] = out
    return out


def is_birthday(state: GameState, npc: NPC) -> bool:
    return birthdays(state).get(npc.name) == (state.season, state.day_of_season)


def birthdays_today(state: GameState) -> list:
    folk = list(state.surface.npcs) + list(state.dwarves or ())
    return [n for n in folk if is_birthday(state, n)]


def befriend(state: GameState, npc: NPC, points: int) -> None:
    """Warm (or cool) a villager by `points`, within friendship's bounds. A
    heart won shows: a burst of them around the villager, wherever the
    friendship came from — a chat, a gift, a favour, the whole village
    turning out for a raising."""
    before = npc.hearts
    npc.friendship = max(0, min(MAX_HEARTS * 100, npc.friendship + points))
    if npc.hearts > before and any(n is npc for n in getattr(state.world, "npcs", ())):
        state.happen("hearts", npc.x, npc.y, hearts=npc.hearts)   # shown where they are


def talk(state: GameState, npc: NPC) -> str:
    first = not npc.talked_today
    npc.met = True
    if first:
        npc.talked_today = True
        from . import attrs
        gain = karma.scale(state.player.karma, 10) * _warmth(state, npc)
        gain = round(gain * (1 + 0.04 * attrs.mod(state, "Ch")))   # easy company
        befriend(state, npc, gain)
    scene = _heart_event(state, npc)         # a once-per-tier scripted moment
    if scene:
        return scene
    if first and is_birthday(state, npc):   # it's their day, and they'll tell you
        return _BIRTHDAY_LINES[sum(map(ord, npc.name)) % len(_BIRTHDAY_LINES)]
    if first:
        treat = _festival_treat(state, npc)  # a nibble at the fair
        if treat:
            return treat
        reward = _heart_reward(state, npc)   # gifts from a good friend
        if reward:
            return reward
        taught = _teach_recipe(state, npc)   # a friend shares their favourite dish
        if taught:
            return taught
    # The outdoors folk read the sky: talk to a fisher, forager, forester or the
    # village elder and they'll foretell tomorrow's weather in folk lore.
    if npc.role in ("fisher", "forager", "forester", "elder"):
        from . import farming, events
        state.stats["forecast_seen"] = state.day          # the almanac notes it down
        saying = farming.weather_saying(farming.forecast(state))
        om = events.omen(state)                 # the weather-wise read more than sky
        return saying + ("\n" + om if om else "")
    return npc.speak(state.seed)


def _heart_event(state: GameState, npc: NPC):
    """A one-time scripted scene at a friendship tier — a real moment that pays
    off the villager's story, shown once when you've grown close enough. Each
    seals a little closer (a bond of friendship and a nudge of karma)."""
    for hearts, text in getattr(npc, "heart_events", ()):
        key = f"{npc.name}:{hearts}"
        if npc.hearts >= hearts and key not in state.seen_events:
            state.seen_events.add(key)
            befriend(state, npc, 50)
            karma.adjust(state, 1)
            return text
    return None


def _teach_recipe(state: GameState, npc: NPC):
    """Once you're proper friends (3 hearts), a villager shares the recipe for
    their own favourite dish — the loved-dish list doubles as a cookbook."""
    if npc.hearts < 3:
        return None
    from . import requests
    for it in npc.loves:
        if it.kind != "food":
            continue
        r = content.recipe_for_dish(it)
        if r is not None and r.name not in state.known_recipes:
            requests.learn_recipe(state, r.name, teacher=npc.name)
            return (f"{npc.name} leans in, conspiratorial: \"Between friends —\n"
                    f"here's how I make {it.name.lower()}. Don't go telling.\"")
    return None


def _warmth(state: GameState, npc: NPC) -> int:
    """Friendship-gain multiplier with `npc`: doubled at their own village's
    fete, or on a festival day (every village keeps the festivals; the two
    never stack — a warm day is a warm day)."""
    from . import events
    mult = events.friendship_mult(state, npc)
    if content.festival_on(state.season, state.day_of_season):
        mult = max(mult, 2)
    return mult


_FAIR_KINDS = ("fair_games", "fair_treats")


def fair_stalls(state: GameState) -> None:
    """Raise the festival stalls: a tombola and a treat stand on every village
    square for the day (struck again at the next dawn)."""
    from ..entities.machine import Machine
    surf = state.surface
    for name, (vx, vy) in getattr(surf, "village_centers", {}).items():
        kinds = list(_FAIR_KINDS)
        for r in range(2, 8):
            if not kinds:
                break
            for x in range(vx - r, vx + r + 1):
                for y in range(vy - r, vy + r + 1):
                    if not kinds:
                        break
                    if max(abs(x - vx), abs(y - vy)) != r:
                        continue
                    if not surf.in_bounds(x, y) or not surf.walkable(x, y):
                        continue
                    if (x, y) in surf.machines or (x, y) in surf.crops:
                        continue
                    if any(n.x == x and n.y == y for n in surf.npcs):
                        continue
                    surf.machines[(x, y)] = Machine(kind=kinds.pop(0))


def clear_fair_stalls(state: GameState) -> None:
    """Strike yesterday's festival stalls, wherever they stood."""
    surf = state.surface
    if surf is not None:
        surf.machines = {pos: m for pos, m in surf.machines.items()
                         if m.kind not in _FAIR_KINDS}


def _festival_treat(state: GameState, npc: NPC):
    """At a festival, the first villager you greet presses a themed treat on
    you — once per festival."""
    fest = content.festival_on(state.season, state.day_of_season)
    if not fest:
        return None
    key = f"festival_{state.year}_{state.season}_{fest[0]}"
    if state.stats.get(key):
        return None
    state.stats[key] = 1
    treat = fest[3]
    state.player.inventory.add(treat, 1)
    name = fest[1][0].upper() + fest[1][1:]
    # Log it too: a shop greeting opens the trade panel, which may not surface
    # the line, and a once-per-festival treat must never be silently pocketed.
    state.log.add(f"{npc.name} presses a {treat.name.lower()} on you for the {fest[1]}.",
                  (232, 200, 120))
    return (f"\"{name}! So glad you came,\" says {npc.name}.\n"
            f"\"Here — a {treat.name.lower()} for the day. Enjoy!\"")


def _heart_reward(state: GameState, npc: NPC):
    """A good friend may give the player something from their OWN, in-character
    gift pool. Yew's rare bee queen recurs at high friendship; other folk give
    a one-time token at 5 hearts and again at 8."""
    import random
    from ..entities import items
    p = state.player
    if not npc.gifts:
        return None

    # Yew, warden of the Wildwood, passes on a bee queen (or a sapling) now and
    # then, once close — but the wood shares at its own pace, not every morning
    # you drop by. The camp's woodcutters share the forester role (they read the
    # sky like him) but not this: theirs are the two keepsakes below.
    if npc.name == "Yew" and npc.hearts >= 6 and random.random() < 0.30:
        key = f"forestgift_day_{npc.name}"
        if state.day - state.stats.get(key, -99) < 7:
            return None
        state.stats[key] = state.day
        gift = random.choice(npc.gifts)
        p.inventory.add(gift, 1)
        state.log.add(f"{npc.name} gives you a {gift.name.lower()}.", (200, 220, 160))
        if gift is items.BEE_QUEEN:
            return ("Yew cups his hands and hums low; something within them stirs:\n"
                    "\"A queen for a friend — go raise her a hall of gold!\"")
        return (f"Yew tucks a {gift.name.lower()} into your pack with a wink:\n"
                "\"The wood shares with them as shares with the wood!\"")

    # One-time tokens of friendship at heart milestones, from their own pool
    # (ascending, so the 5-heart token always lands before the 8-heart one).
    for th in (5, 8):
        key = f"heartgift_{npc.name}_{th}"
        if npc.hearts >= th and not state.stats.get(key):
            state.stats[key] = 1
            gift = random.choice(npc.gifts)
            p.inventory.add(gift, 1)
            # Log it too — the gift may arrive via a shop greeting whose panel
            # doesn't show the line.
            state.log.add(f"{npc.name} gives you a {gift.name.lower()}.", (200, 220, 160))
            return (f"{npc.name} presses a {gift.name.lower()} into your hands.\n"
                    "\"For a good friend. I mean it — take it.\"")
    return None


def gift(state: GameState, npc: NPC, item, quality: int = 0) -> None:
    if npc.gifted_today:
        state.log.add(f"{npc.name} has already had a gift today.", C.DIM)
        return
    points, line = npc.gift_reaction(item)
    # Give the exact stack the player picked (the menu is per-quality), and let
    # a finer gift please a little more.
    state.player.inventory.remove(item, 1, quality=quality)
    if points > 0:
        points += quality
    points = karma.scale(state.player.karma, points)
    if points > 0:                       # a fete or festival warms a kind gift double
        from . import attrs
        points = round(points * _warmth(state, npc) * (1 + 0.04 * attrs.mod(state, "Ap")))
    birthday = points > 0 and is_birthday(state, npc)
    if birthday:                         # remembered on their day, it means all the more
        points *= BIRTHDAY_GIFT_MULT
    befriend(state, npc, points)
    npc.gifted_today = True
    taste = npc.taste(item)
    if taste == "loves":                              # it shows on their face
        state.happen("emote", npc.x, npc.y, glyph="♥", colour=(255, 128, 168))
    elif taste == "dislikes":
        state.happen("emote", npc.x, npc.y, glyph="…", colour=(170, 170, 176))
    if points > 0:
        karma.adjust(state, 1)  # a small kindness
    color = (180, 230, 160) if points >= 45 else (200, 160, 140) if points < 0 else C.WHITE
    state.log.add(line, color)
    if birthday:
        state.log.add(f"It's {npc.name}'s birthday — your gift means all the more today.",
                      (240, 190, 210))


def anger_owner(state: GameState, owner: str, amount: int) -> None:
    """Sour a landowner's regard after theft or vandalism. A named resident
    takes the full slight; village-communal property (shops, wells, the square)
    sours the whole village a little instead."""
    surf = state.surface or state.world
    npcs = getattr(surf, "npcs", [])
    named = next((n for n in npcs if n.name == owner), None)
    if named is not None:
        named.friendship = max(0, named.friendship + karma.scale(state.player.karma, -amount))
        return
    share = max(1, amount // 4)
    for n in npcs:
        if getattr(n, "village", "") == owner:
            n.friendship = max(0, n.friendship + karma.scale(state.player.karma, -share))


def giftable_items(state: GameState, npc: NPC | None = None):
    """Inventory items that can be given (anything but tools/weapon/livestock).
    Given an NPC, their loved things float to the top, then liked, then the rest
    — so the right gift is a keypress away, not a scroll through the pack.

    Cut gems are giftable: Kazrik *loves* the Cut Diamond, and while "gem" was
    missing from this filter his favourite gift was the one thing he could never
    be given."""
    out = [(it, q, ql) for it, q, ql in state.player.inventory.slots
           if it.kind in ("crop", "artisan", "material", "food", "fish", "animal", "gem")]
    if npc is not None:
        def taste(e):
            return {"loves": 0, "likes": 1, "": 2, "dislikes": 3}[npc.taste(e[0])]
        out.sort(key=taste)
    return out


# The innkeeper buys the farm's artisan goods (wine, mead, jam, pickles, cheese…)
# at a small premium — a gold sink that closes the loop between your kegs/jars/
# churn and the village.
INN_PREMIUM = 1.2


def _inn_purchases(state: GameState):
    """Offers to buy each artisan good the player is carrying (lowest-quality
    unit first, priced by quality with a specialty-buyer premium)."""
    from . import skills
    inv = state.player.inventory
    out, seen = [], set()
    for it, _q, _ql in inv.slots:
        if it.kind != "artisan" or it in seen:
            continue
        seen.add(it)
        stacks = sorted((e for e in inv.slots if e[0] is it), key=lambda e: e[2])
        q = stacks[0][2]
        price = round(it.value * skills.value_mult(q) * INN_PREMIUM)
        out.append(ShopRow("sellto", label=it.name, item=it, price=price, quality=q))
    return out


# --- the house order ----------------------------------------------------------
# Each week every innkeeper has one dish they want for the house table, and
# pays well over the bin for it — a few servings, then the table's full. A
# cooked dish had nowhere to go but your own mouth or the bin; this is its
# market. Which dish is the luck of the week, never the same at two inns.
ORDER_PREMIUM = 1.5         # over the dish's quality-scaled value
ORDER_SERVINGS = 4          # servings an inn takes of its order each week


def _order_pool() -> list:
    """Dishes an inn might ask for: every cooked dish that is a meal in itself
    (not a staple that only goes into other dishes)."""
    staples = {it for r in content.RECIPES if r.kind == "cook" for it, _q in r.inputs}
    return sorted((r.output for r in content.RECIPES
                   if r.kind == "cook" and r.output is not None
                   and r.output.value > 0 and r.output not in staples),
                  key=lambda it: it.name)


def _order_week(state: GameState) -> int:
    return state.day // 7


def tavern_order(state: GameState, npc: NPC):
    """The dish this innkeeper wants this week."""
    import random as _random
    pool = _order_pool()
    rng = _random.Random((state.seed * 15_485_863 + _order_week(state) * 32_452_843) & 0x7FFFFFFF)
    rng.shuffle(pool)
    keepers = sorted({n.name for n in (state.surface.npcs if state.surface else [])
                      if n.role == "innkeeper"} | {npc.name})
    return pool[keepers.index(npc.name) % len(pool)]


def _order_key(state: GameState, npc: NPC) -> str:
    return f"inn_order_{_order_week(state)}_{npc.name}"


def order_left(state: GameState, npc: NPC) -> int:
    return max(0, ORDER_SERVINGS - int(state.stats.get(_order_key(state, npc), 0)))


def fills_order(item, dish) -> bool:
    """Whether ``item`` is the ordered dish — or that dish made with a named
    ingredient (a tuna sashimi fills an order for sashimi, and pays as tuna)."""
    return item is dish or getattr(item, "family", "") == f"dish:{dish.name}"


def order_rows(state: GameState, npc: NPC) -> list:
    """The order on the counter: a row per carried serving that fills it (each
    kind and star grade), or one row that just says what is wanted."""
    from . import skills
    dish, left = tavern_order(state, npc), order_left(state, npc)
    rows = []
    if left > 0:
        for it, n, ql in state.player.inventory.slots:
            if n > 0 and fills_order(it, dish):
                price = round(it.value * skills.value_mult(ql) * ORDER_PREMIUM)
                rows.append(ShopRow("order", label=dish.name, item=it, price=price,
                                    quality=ql, left=left))
        rows.sort(key=lambda r: -r.price)
    return rows or [ShopRow("order", label=dish.name, left=left)]


def _fill_order(state: GameState, row: ShopRow, npc: NPC | None) -> None:
    from . import skills
    p = state.player
    if row.item is None:
        state.log.add(f"\"The house table's full of {row.label.lower()} for this week — thank you.\""
                      if row.left <= 0 else
                      f"\"Bring me {row.label.lower()} this week and I'll pay half again "
                      f"what the bin would. I can take {row.left}.\"", (222, 200, 150))
        return
    if npc is None or order_left(state, npc) <= 0 \
            or p.inventory.count(row.item, row.quality) <= 0:
        return
    p.inventory.remove(row.item, 1, quality=row.quality)
    p.gold += row.price
    state.bump("gold_earned", row.price)
    key = _order_key(state, npc)
    for old in [k for k in state.stats if k.startswith("inn_order_") and
                not k.startswith(f"inn_order_{_order_week(state)}_")]:
        del state.stats[old]                           # last week's tallies
    state.stats[key] = int(state.stats.get(key, 0)) + 1
    befriend(state, npc, 15)
    star = (" " + skills.stars(row.quality)) if row.quality else ""
    state.log.add(f"{npc.name} takes your {row.item.name.lower()}{star} for the house table: "
                  f"{row.price}g.", (240, 214, 120))


# --- a ribbon's worth ---------------------------------------------------------
# A first-prize ribbon can be handed back to any innkeeper (they judge the
# contest) for something off the prize table: things that otherwise come by
# luck. The table turns over with the week, so it's never the same three.
_PRIZE_SAPLINGS = (items.CHERRY_SAPLING, items.PEACH_SAPLING, items.APPLE_SAPLING,
                   items.PEAR_SAPLING, items.ORANGE_SAPLING)
GRANGE_CASE_EDGE = 0.5      # what a ribbon in the Hall of Wonders adds to an entry's score


def prize_rows(state: GameState) -> list:
    """What a carried ribbon could be traded for today — nothing without one."""
    import random as _random
    from . import requests as gamereq
    if state.player.inventory.count(items.FAIR_RIBBON) <= 0:
        return []
    rng = _random.Random((state.seed * 7_919 + (state.day // 7) * 104_729) & 0x7FFFFFFF)
    rows = []
    pool = sorted(gamereq.unknown_recipes(state))
    if pool:
        rows.append(ShopRow("prize", label="a recipe card", name=rng.choice(pool)))
    rows.append(ShopRow("prize", label="a live bee queen", item=items.BEE_QUEEN))
    rows.append(ShopRow("prize", label="a fruit sapling", item=rng.choice(_PRIZE_SAPLINGS)))
    return rows


def _claim_prize(state: GameState, row: ShopRow) -> None:
    inv = state.player.inventory
    if not inv.remove(items.FAIR_RIBBON, 1):
        return
    if row.item is not None:
        inv.add(row.item, 1)
        state.log.add(f"The innkeeper takes your ribbon back for the Grange and hands over "
                      f"the {row.item.name.lower()}.", (232, 200, 120))
    else:
        from . import requests as gamereq
        if not gamereq.learn_recipe(state, row.name, teacher="The innkeeper"):
            inv.add(items.FAIR_RIBBON, 1)                 # known since the table was read


# --- the festival produce contest (held at the Grange Hall) -------------------
def _contest_key(state: GameState) -> str | None:
    fest = content.festival_on(state.season, state.day_of_season)
    return f"contest_{state.year}_{state.season}_{fest[0]}" if fest else None


CONTEST_HOME = "Mossford"      # where the fair's contest is held before the Grange stands


def contest_open(state: GameState, npc: NPC | None = None) -> str | None:
    """The festival whose produce contest ``npc`` (an innkeeper) will take an
    entry for today, or None. One entry per festival. Mossford has always
    judged its own produce on a trestle outside the inn; raising the Grange
    Hall makes it the Vale's contest, held at every inn and with the grange
    elders' prizes. (There used to be no contest at all until the hall stood.)"""
    from . import projects
    fest = content.festival_on(state.season, state.day_of_season)
    held = (projects.done(state, "grange_hall")
            or getattr(npc, "village", "") == CONTEST_HOME)
    if (fest and held
            and state.world is state.surface        # the fair is up in the sunlight
            and not state.stats.get(_contest_key(state))):
        return fest[1]
    return None


def contest_items(state: GameState) -> list:
    """What can go on the judging table: any quality-bearing produce carried."""
    from . import skills
    return [(it, q, ql) for it, q, ql in state.player.inventory.slots
            if skills.has_quality(it) and it.value > 0
            and it.kind in ("crop", "artisan", "food", "fish", "animal")]


def enter_contest(state: GameState, item, ql: int, judge: NPC | None = None) -> str:
    """Judge one entry at the Grange fair. The rivals and their scores are fixed
    the moment the festival dawns (seeded from seed+day — no re-rolling), and
    the field stiffens gently with the years. Prizes are prestige, not gold:
    the contest is where a 5-star good goes to mean something.

    ``judge`` is the innkeeper who took the entry (every surface tavern holds
    the contest); the warmth goes to them and their village. It used to go
    to Mossford whoever judged, and the field's leader was named at random."""
    import random as _random
    from . import karma, requests as gamereq, skills
    fest = content.festival_on(state.season, state.day_of_season)
    state.stats[_contest_key(state)] = 1
    state.player.inventory.remove(item, 1, quality=ql)
    state.bump("contests_entered")
    rng = _random.Random((state.seed * 42_589 + state.day * 631) & 0x7FFFFFFF)
    grown = [n for n in state.surface.npcs if n.role != "child"]
    rivals = rng.sample(grown, min(3, len(grown)))
    field = sorted(((rng.uniform(2.5, 5.5) + 0.35 * max(0, state.year - 1), n)
                    for n in rivals), key=lambda e: e[0], reverse=True)
    rival_scores = [score for score, _n in field]
    leader = field[0][1]                         # the best of the rest, by name
    if judge is None:                            # (no innkeeper in hand: the Grange's own)
        judge = next((n for n in state.surface.npcs
                      if n.role == "innkeeper" and n.village == "Mossford"), None)
    home = getattr(judge, "village", "") or "Mossford"
    mine = ql * 1.6 + min(3.5, item.value / 140.0) + rng.uniform(0.0, 1.2)
    from . import collection
    if collection.perk_earned(state, "Grange Case"):     # a ribbon in the Hall of Wonders
        mine += GRANGE_CASE_EDGE
    place = 1 + sum(1 for s in rival_scores if s > mine)
    star = (" " + skills.stars(ql)) if ql else ""
    entry = f"{item.name.lower()}{star}"

    if place == 1:
        state.bump("contests_won")
        state.player.inventory.add(items.FAIR_RIBBON, 1)
        for n in state.surface.npcs:
            if getattr(n, "village", "") == home:
                befriend(state, n, 100)
        karma.adjust(state, 3)
        extra = ""
        from . import projects
        grand = projects.done(state, "grange_hall")   # the elders' prizes come with the hall
        if rng.random() < 0.4 and grand:
            pool = gamereq.unknown_recipes(state)
            if pool:
                gamereq.learn_recipe(state, rng.choice(pool), teacher="The judge")
                extra = "\nThere's a recipe card tucked under the ribbon, too."
        if rng.random() < 0.2 and grand:          # a rare grand-prize treat (very occasional)
            treat = rng.choice(content.ATTRIBUTE_TREATS)
            state.player.inventory.add(treat, 1)
            extra += f"\nThe grange elders press a rare {treat.name} into your hands."
        state.log.add(f"First prize at {fest[1]} — your {entry} takes the ribbon!",
                      (232, 200, 120))
        return (f"The judge holds your {entry} aloft — the square erupts!\n"
                f"\"FIRST PRIZE! Finest thing the Grange has seen in years.\"\n"
                f"A fair ribbon is pinned on you, to warm applause.{extra}")
    if place <= 3:
        if judge is not None:
            befriend(state, judge, 45)
        karma.adjust(state, 1)
        state.player.inventory.add(fest[3], 1)
        state.log.add(f"Your {entry} places {place}{'nd' if place == 2 else 'rd'} at the fair.",
                      (200, 220, 160))
        return (f"\"{place}{'nd' if place == 2 else 'rd'} place — well grown!\" says the judge,\n"
                f"pressing a {fest[3].name.lower()} into your hands.\n"
                f"{leader.name}'s entry edges the field this year.")
    karma.adjust(state, 1)
    state.log.add("No ribbon this year — but the entering's half the fun.", C.DIM)
    return (f"The judge nods kindly over your {entry}.\n"
            f"\"Good, honest work — but {leader.name}'s entry is a marvel.\n"
            "Bring me your finest next fair, eh?\"")


# --- shops ------------------------------------------------------------------
def npc_shop(state: GameState, npc: NPC) -> str | None:
    """The shop an NPC keeps *right now*. Derived, never stored on the NPC
    (NPCs are regenerated from content on every load): traders open their
    wagons by role. (Willa's too — before the Fenwick causeway she comes with
    less and asks more; see trader_entries.)"""
    if npc.shop:
        return npc.shop
    if npc.role == "trader":
        return "trader"
    return None


def _window_len(seed: int, n: int) -> int:
    """How many days window ``n`` runs for (3-6, drifting from the seed)."""
    import random as _random
    return 3 + _random.Random((seed * 611_953 + n * 2_741) & 0x7FFFFFFF).randint(0, 3)


# First day of each window, per seed, grown on demand: _WINDOW_STARTS[seed][n] is
# the day window n opens, so window n runs [starts[n], starts[n+1]). Windows are
# 3-6 days, so this is ~1 int per 4.5 days played — a few hundred over a long
# life — and each window's length is rolled ONCE ever, rather than on every
# lookup (see trader_window).
_WINDOW_STARTS: dict[int, list[int]] = {}


def trader_window(seed: int, day: int) -> tuple[int, int]:
    """(window index, window seed) for the traders' rotating stock. Windows run
    3-6 days, their lengths drifting from the seed — fully derived from
    (seed, day), so the rotation needs no save field and never goes stale.

    The window boundaries are memoized because this is read while a trader's
    counter is drawn, i.e. every frame: walking the whole calendar from day 0
    each time cost ~1ms a call by year 9 and grew without bound. The answer is
    unchanged — only the work is."""
    starts = _WINDOW_STARTS.setdefault(seed, [0])
    while starts[-1] <= day:                 # extend just past the day asked for
        starts.append(starts[-1] + _window_len(seed, len(starts) - 1))
    n = bisect.bisect_right(starts, day) - 1
    return n, (seed * 887 + n * 104_729) & 0x7FFFFFFF


# The recipe cards a wagon might carry: every cook recipe that isn't a starter
# and isn't already over an innkeeper's bar. Static content, so it's built once
# — the draw below is read every frame while a counter is open.
_CARD_POOL: tuple[str, ...] = tuple(sorted(
    r.name for r in content.RECIPES
    if r.kind == "cook"
    and r.name not in dict(content.TAVERN_RECIPES)
    and r.name not in content.STARTER_RECIPES))


FLOOD_ROAD_MARKUP = 1.25    # what Willa adds while her road still floods


def trader_entries(state: GameState, npc: NPC) -> list:
    """A trader's wagon this window: a few dear, rare things — the non-crafter's
    road to high-tier gear, priced at 3-4x its worth. Slots are drawn
    deterministically per (seed, window, trader); bought slots are remembered
    in stats so a wagon can sell out."""
    import random as _random
    import zlib
    window, wseed = trader_window(state.seed, state.day)
    rng = _random.Random(wseed ^ zlib.crc32(npc.name.encode()))
    # Willa's wagon has one road in, and it floods: until the Fenwick causeway
    # is laid she gets through with a lighter load and asks more for it. (She
    # used not to trade at all before it.)
    from . import projects
    mired = npc.name == "Willa" and not projects.done(state, "causeway")
    deep = npc.name in ("Willa", "Kazrik") and not mired   # causeway & tunnel traders dig deeper
    slots: list[tuple] = []                          # ("tradebuy", item, price) pre-key

    for _ in range(2):                               # high-tier gear, sometimes affixed
        base = rng.choice(sorted(content.WEAPON_BASES))
        metal = rng.choice(("mithril", "adamantium"))
        pfx, sfx = ("", "")
        if rng.random() < 0.4:
            pfx, sfx = content.roll_craft_affix(10, rng, "weapon")
        it = content.make_gear(base, metal, pfx, sfx)
        slots.append((it, content._round5(it.value * rng.uniform(3.0, 4.0))))
    gem = rng.choice(sorted(content.CUT_GEM.values(), key=lambda i: i.name))
    slots.append((gem, content._round5(gem.value * 2.0)))
    slots.append((items.GEODE, content._round5(items.GEODE.value * 1.5)))
    # Every general store sells every sapling, so the wagon's is a convenience
    # for a farmer far from one, at the store's own price — it used to ask
    # 1,050g for the cherry the store sells at 600.
    sap = rng.choice((items.CHERRY_SAPLING, items.APPLE_SAPLING, items.PEACH_SAPLING))
    slots.append((sap, dict(content.GENERAL_STOCK)[sap]))
    if deep:
        bar = rng.choice((items.GOLD_BAR, items.PLATINUM_BAR))
        slots.append((bar, content._round5(bar.value * 2.0)))
        slots.append((items.SILK_CLOTH, content._round5(items.SILK_CLOTH.value * 1.5)))
        if rng.random() < 0.25:
            slots.append((items.BEE_QUEEN, content._round5(items.BEE_QUEEN.value * 2.0)))

    out = []
    for i, (it, price) in enumerate(slots):
        if mired and it.kind != "sapling":           # (a sapling stays at the store's price)
            price = content._round5(price * FLOOD_ROAD_MARKUP)
        key = f"trader_{npc.name}_{window}_{i}"
        if not state.stats.get(key):                 # sold slots stay sold this window
            out.append(ShopRow("tradebuy", label=it.name, item=it, price=price, key=key))
    # a recipe card, drawn unconditionally (determinism) but hidden once known
    card = rng.choice(_CARD_POOL)
    if card not in state.known_recipes:
        out.append(ShopRow("recipe", name=card, price=260))
    return out


# What the player pays for (buy_mult) vs is paid for (sell_mult) — the rest
# (civic commissions, house jobs, contest entry) are unaffected by reputation.
_PAY_KINDS = {"buy", "meal", "recipe", "tradebuy", "upgrade", "room"}


def shop_entries(shop: str, state: GameState | None = None,
                 npc: NPC | None = None) -> list[ShopRow]:
    """The rows on a shop's counter, priced with the player's standing folded in
    (a hero haggles well; a villain pays over the odds).

    Whatever the list price and however good the haggle, a good for sale costs
    more than the bin could ever pay for it (crafting.bin_ceiling): list prices
    cleared the item's worth, but not a craving, a caravan, the Market Cross and
    the Coin sign stacked, nor a saint's discount on top — a bought piglet
    posted straight back paid 161g, Willa's silk 361g."""
    rows = _shop_entries(shop, state, npc)
    if state is None:
        return rows
    import dataclasses
    from . import crafting, karma
    bm, sm = karma.buy_mult(state.player.karma), karma.sell_mult(state.player.karma)
    out = []
    for r in rows:
        if r.price > 0 and r.kind in _PAY_KINDS:
            price = max(1, round(r.price * bm))
            if r.kind in ("buy", "tradebuy") and r.item is not None:
                price = max(price, crafting.bin_ceiling(r.item) + 1)
            r = dataclasses.replace(r, price=price)
        elif r.price > 0 and r.kind in ("sellto", "order"):
            r = dataclasses.replace(r, price=max(1, round(r.price * sm)))
        out.append(r)
    return out


def _shop_entries(shop: str, state: GameState | None = None,
                  npc: NPC | None = None) -> list[ShopRow]:
    """The rows on a shop's counter, in display order (base prices)."""
    if shop == "trader":
        return trader_entries(state, npc) if state is not None and npc is not None else []
    if shop == "general":
        return [ShopRow("buy", label=it.name, item=it, price=price)
                for it, price in content.GENERAL_STOCK]
    if shop == "blacksmith":
        ups = [ShopRow("upgrade", tool=t) for t in items.TIERED_TOOLS]
        buys = [ShopRow("buy", label=it.name, item=it, price=price)
                for it, price in content.blacksmith_stock()]
        # With the Deep Forge raised, Bron works the deep metals too — bars at
        # the usual doubled rate, finished pieces at a steep premium (the
        # non-crafter's path to endgame gear, paid in dungeon gold). Thrunn of
        # Khazgrim has never stopped working them.
        if state is not None:
            from . import projects
            if (projects.done(state, "deep_forge")
                    or (npc is not None and getattr(npc, "village", "") == "Khazgrim")):
                buys += _deep_bar_rows(state, npc)
                buys += [ShopRow("buy", label=it.name, item=it,
                                 price=content._round5(it.value * 2.8))
                         for m in content.DEEP_FORGE_METALS
                         for it in (content.make_gear(b, m) for b in content.WEAPON_BASES)]
        return ups + buys
    if shop == "tavern":
        meals = [ShopRow("meal", label=label, price=price, stam=stam, hp=hp)
                 for (label, price, stam, hp) in content.TAVERN_MENU]
        # On a fair day (with the Grange standing), the innkeeper judges the
        # produce contest — one entry per festival.
        if state is not None:
            fest_name = contest_open(state, npc)
            if fest_name:
                meals = [ShopRow("contest", name=fest_name)] + meals
        # The house recipes: an innkeeper will part with one, for a price.
        cards = [ShopRow("recipe", name=name, price=price)
                 for name, price in content.TAVERN_RECIPES
                 if state is not None and name not in state.known_recipes]
        if state is None:
            return meals + cards
        order = order_rows(state, npc) if npc is not None else []
        # A bed for the night — the Vale's inns only (the night is reckoned on
        # the Vale's map; see farming.can_sleep_rough).
        from . import farming
        room = ([ShopRow("room", label="A room for the night", price=farming.INN_ROOM_PRICE)]
                if farming.can_sleep_rough(state) else [])
        return prize_rows(state) + order + meals + room + cards + _inn_purchases(state)
    if shop == "carpenter":
        jobs = [ShopRow("commission", label=label, build=kind, price=gold, mats=tuple(mats))
                for (label, kind, gold, mats) in content.CARPENTER_JOBS]
        # Farmhouse fittings (oven, cellar) — auto-sited, hidden once owned or
        # already under Tomas's hammer.
        if state is not None and state.surface is not None:
            for label, kind, gold, mats in content.HOUSE_JOBS:
                owned = any(m.kind == kind or (m.kind == "site" and m.build_kind == kind)
                            for m in state.surface.machines.values())
                if kind == "extension" and state.stats.get("house_extended"):
                    owned = True                      # one second room is a house enough
                if not owned:
                    jobs.append(ShopRow("housejob", label=label, build=kind,
                                        price=gold, mats=tuple(mats)))
        # If an order is outstanding, offer to cancel it (with a full refund) so
        # you're never locked out of the carpenter by a build you can't site.
        if state is not None and state.pending_build:
            return [ShopRow("cancel_build", build=state.pending_build)] + jobs
        return jobs
    return []


# Each smith sells only so many deep bars a week. Enough for a tool upgrade (the
# dearest takes six), but a master smith's forge averaged well over what the
# bars cost — an adamantium greatsword cleared ~990g on an ordinary day — so an
# open till let bought bars be flipped through the anvil without end.
DEEP_BARS_PER_WEEK = 8


def _deep_bar_rows(state: GameState, npc) -> list[ShopRow]:
    """This week's deep bars on a smith's counter, each row counting down its
    stock (a sold-out bar leaves the counter until the week turns)."""
    who = npc.name if npc is not None else "smith"
    rows = []
    for b in content.DEEP_FORGE_BARS:
        key = f"deepbars_{who}_{state.day // 7}_{b.name}"
        left = DEEP_BARS_PER_WEEK - state.stats.get(key, 0)
        if left > 0:
            rows.append(ShopRow("buy", label=b.name, item=b,
                                price=content._round5(b.value * 2.0), key=key, left=left))
    return rows


def _job_for(kind: str):
    """The (label, gold, mats) of a carpenter job by its build kind, or None."""
    for label, k, gold, mats in content.CARPENTER_JOBS:
        if k == kind:
            return label, gold, mats
    return None


def purchase(state: GameState, row: ShopRow, npc: NPC | None = None) -> None:
    """Perform a shop row's transaction. One dispatch, on named fields. ``npc``
    is who stands behind the counter, for the rows that are theirs alone."""
    if row.kind == "order":
        _fill_order(state, row, npc)
    elif row.kind == "buy":
        if row.key and state.stats.get(row.key, 0) >= DEEP_BARS_PER_WEEK:
            state.log.add("That's all of those until the week turns.", C.DIM)
            return
        if state.player.gold < row.price:
            state.log.add("You can't afford that.", C.DIM)
            return
        state.player.gold -= row.price
        state.player.inventory.add(row.item, 1)
        if row.key:                                   # a counted stock (deep bars)
            state.stats[row.key] = state.stats.get(row.key, 0) + 1
        state.log.add(f"Bought {row.item.name} for {row.price}g.")
    elif row.kind == "meal":
        p = state.player
        if p.gold < row.price:
            state.log.add("You can't afford that.", C.DIM)
            return
        p.gold -= row.price
        p.gain_energy(row.stam)
        p.hp = min(p.max_hp, p.hp + row.hp)
        state.bump("meals_eaten")
        from . import turns
        from ..engine import constants as _C
        turns.advance_time(state, _C.USE_SECONDS)
        gains = f"+{row.stam} stamina" + (f", +{row.hp} HP" if row.hp else "")
        state.log.add(f"You tuck into {row.label.lower()}. ({gains})", (180, 230, 160))
    elif row.kind == "recipe":
        p = state.player
        if row.name in state.known_recipes:
            return
        if p.gold < row.price:
            state.log.add("You can't afford that.", C.DIM)
            return
        p.gold -= row.price
        from . import requests
        requests.learn_recipe(state, row.name, teacher="The innkeeper")
    elif row.kind == "sellto":
        p = state.player
        if p.inventory.count(row.item, row.quality) <= 0:
            return
        p.inventory.remove(row.item, 1, quality=row.quality)
        p.gold += row.price
        state.bump("gold_earned", row.price)
        from . import skills
        star = (" " + skills.stars(row.quality)) if row.quality else ""
        state.log.add(f"The innkeeper takes your {row.item.name.lower()}{star} for {row.price}g.",
                      (240, 214, 120))
    elif row.kind == "room":
        from . import farming
        p = state.player
        if not farming.can_sleep_rough(state):
            return
        if p.gold < row.price:
            state.log.add("You can't afford that.", C.DIM)
            return
        p.gold -= row.price
        farming.sleep_at_inn(state)
    elif row.kind == "prize":
        _claim_prize(state, row)
    elif row.kind == "cancel_build":
        job = _job_for(row.build)
        if not state.pending_build or job is None:
            return
        label, gold, mats = job
        p = state.player
        p.gold += gold
        for it, q in mats:
            p.inventory.add(it, q)
        state.pending_build = ""
        state.log.add(f"Tomas tears up the order for the "
                      f"{label.split('(')[0].strip().lower()} and returns your {gold}g and materials.",
                      (200, 220, 160))
    elif row.kind == "commission":
        p = state.player
        if state.pending_build:
            state.log.add("You already have a building on order — set it down first.", C.DIM)
            return
        if p.gold < row.price:
            state.log.add("You can't afford that.", C.DIM)
            return
        missing = [f"{q}x {it.name}" for it, q in row.mats if p.inventory.count(it) < q]
        if missing:
            state.log.add(f"Tomas needs materials: {', '.join(missing)}.", C.DIM)
            return
        p.gold -= row.price
        for it, q in row.mats:
            p.inventory.remove(it, q)
        state.pending_build = row.build
        state.log.add(f"Tomas shakes on it. \"Head home and show me where the "
                      f"{row.label.split('(')[0].strip().lower()} should go — press p to set the spot.\"",
                      (200, 220, 160))
    elif row.kind == "tradebuy":
        if state.player.gold < row.price:
            state.log.add("You can't afford that.", C.DIM)
            return
        state.player.gold -= row.price
        state.player.inventory.add(row.item, 1)
        state.stats[row.key] = 1                      # this slot is sold this window
        state.log.add(f"Bought {row.item.name} for {row.price}g — the trader wraps it carefully.")
    elif row.kind == "housejob":
        p = state.player
        from . import husbandry
        from ..entities.machine import Machine
        from ..world import tile
        spot = husbandry.find_house_spot(state, row.build)
        if spot is None:
            state.log.add("Tomas scratches his head — no clear spot for it. "
                          "Tidy up around the farmhouse first.", C.DIM)
            return
        if p.gold < row.price:
            state.log.add("You can't afford that.", C.DIM)
            return
        missing = [f"{q}x {it.name}" for it, q in row.mats if p.inventory.count(it) < q]
        if missing:
            state.log.add(f"Tomas needs materials: {', '.join(missing)}.", C.DIM)
            return
        p.gold -= row.price
        for it, q in row.mats:
            p.inventory.remove(it, q)
        surf = state.surface
        surf.tiles[spot] = tile.SCAFFOLD
        surf.machines[spot] = Machine(kind="site", build_kind=row.build,
                                      ready_at=(state.day + 2) * 1440 + C.DAY_START_MIN)
        name = (content.HOUSE_JOB_NAMES.get(row.build)
                or content.MACHINES[row.build].name.lower())
        state.log.add(f"Tomas sets to work on your {name} — ready in 2 mornings.",
                      (200, 220, 160))
    elif row.kind == "upgrade":
        upgrade_tool(state, row.tool)


def upgrade_price(state: GameState, tier: int):
    """(gold, bar, count) for a tool upgrade — the Deep Forge, once raised,
    takes a fifth off Bron's labour, and the smith's fee answers to your name
    like every other counter's (the ±10% karma haggle). Upgrade rows carry no
    list price, so shop_entries never priced them and the smith's dearest work
    ignored karma altogether. The screen and the purchase both price here."""
    from . import karma, projects
    gold, bar, count = content.upgrade_cost(tier)
    if projects.done(state, "deep_forge"):
        gold = round(gold * 0.8)
    gold = max(1, round(gold * karma.buy_mult(state.player.karma)))
    return gold, bar, count


def upgrade_tool(state: GameState, tool) -> None:
    p = state.player
    tier = p.tool_tier.get(tool, 0)
    if tier >= len(C.TOOL_TIERS) - 1:
        state.log.add(f"Your {C.TOOL_TIERS[tier]} {tool.name} can't be improved further.", C.DIM)
        return
    gold, bar, count = upgrade_price(state, tier)
    if p.gold < gold or p.inventory.count(bar) < count:
        state.log.add(f"Bron needs {gold}g + {count} {bar.name} for that upgrade.", C.DIM)
        return
    p.gold -= gold
    p.inventory.remove(bar, count)
    p.tool_tier[tool] = tier + 1
    state.log.add(f"Bron forges your {tool.name} into {C.TOOL_TIERS[tier + 1]}!", (200, 220, 160))
