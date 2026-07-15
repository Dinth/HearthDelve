"""Village life: NPC schedules, talking, gifting, shops, and tool upgrades."""
from __future__ import annotations

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
           cancel_build · tradebuy · upgrade · contest
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
    key: str = ""              # stats key marking a trader slot sold


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


def update_npcs(state: GameState) -> None:
    """Move each resident toward their scheduled anchor for the hour. Adults
    teleport to their spot; children roam and play around the square by day."""
    hour = (state.time_minutes // 60) % 24
    for npc in state.world.npcs:
        key = scheduled_spot(npc, hour, state.weather, state.season, state.day_of_season)
        if key == "square":
            _child_roam(state, npc)          # mill about (kids also chase to play)
        else:
            npc.x, npc.y = npc.spots.get(key) or npc.spots.get("home") or npc.work


_CHILD_RANGE = 9      # how far kids stray from the square while playing


def _child_roam(state: GameState, npc) -> None:
    """A lively amble: kids wander near the square and chase each other to play."""
    import random
    w = state.world
    anchor = npc.spots.get("square") or npc.spots.get("home") or (npc.x, npc.y)
    px, py = state.player.x, state.player.y
    # find a playmate to run toward, if one's a little way off
    mates = [n for n in w.npcs if n.role == "child" and n is not npc]
    mate = min(mates, key=lambda k: (k.x - npc.x) ** 2 + (k.y - npc.y) ** 2, default=None)

    tx = ty = None
    if mate is not None:
        d = max(abs(mate.x - npc.x), abs(mate.y - npc.y))
        if 2 < d < 16 and random.random() < 0.6:
            tx, ty = mate.x, mate.y                     # chase a friend
    if tx is None and max(abs(npc.x - anchor[0]), abs(npc.y - anchor[1])) > _CHILD_RANGE:
        tx, ty = anchor                                 # strayed too far — head back
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
    """The NPC on the faced tile, or an adjacent one (for talk/gift)."""
    p = state.player
    fx, fy = p.facing
    faced = (p.x + fx, p.y + fy)
    by_pos = {(n.x, n.y): n for n in state.world.npcs}
    if faced in by_pos:
        return by_pos[faced]
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if (p.x + dx, p.y + dy) in by_pos:
            return by_pos[(p.x + dx, p.y + dy)]
    return None


# --- talk & gift ------------------------------------------------------------
def talk(state: GameState, npc: NPC) -> str:
    first = not npc.talked_today
    npc.met = True
    if first:
        npc.talked_today = True
        gain = karma.scale(state.player.karma, 10)
        npc.friendship = min(MAX_HEARTS * 100, npc.friendship + gain)
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
        from . import farming
        return farming.weather_saying(farming.forecast(state))
    return npc.speak()


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
    gift pool. The forester's rare bee queen recurs at high friendship; other
    folk give a one-time token at 5 hearts and again at 8."""
    import random
    from ..entities import items
    p = state.player
    if not npc.gifts:
        return None

    # The forester passes on a bee queen (or a sapling) now and then, once close
    # — but the wood shares at its own pace, not every morning you drop by.
    if npc.role == "forester" and npc.hearts >= 6 and random.random() < 0.30:
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
    npc.friendship = max(0, min(MAX_HEARTS * 100, npc.friendship + points))
    npc.gifted_today = True
    if points > 0:
        karma.adjust(state, 1)  # a small kindness
    color = (180, 230, 160) if points >= 45 else (200, 160, 140) if points < 0 else C.WHITE
    state.log.add(line, color)


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
    — so the right gift is a keypress away, not a scroll through the pack."""
    out = [(it, q, ql) for it, q, ql in state.player.inventory.slots
           if it.kind in ("crop", "artisan", "material", "food", "fish", "animal")]
    if npc is not None:
        def taste(e):
            it = e[0]
            if npc._matches(it, npc.loves):
                return 0
            if npc._matches(it, npc.likes):
                return 1
            if npc._matches(it, npc.dislikes):
                return 3
            return 2
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


# --- the festival produce contest (held at the Grange Hall) -------------------
def _contest_key(state: GameState) -> str | None:
    fest = content.festival_on(state.season, state.day_of_season)
    return f"contest_{state.year}_{state.season}_{fest[0]}" if fest else None


def contest_open(state: GameState) -> str | None:
    """The festival whose produce contest awaits an entry today, or None —
    contests run only once the Grange Hall stands, once per festival."""
    from . import projects
    fest = content.festival_on(state.season, state.day_of_season)
    if (fest and projects.done(state, "grange_hall")
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


def enter_contest(state: GameState, item, ql: int) -> str:
    """Judge one entry at the Grange fair. The rivals and their scores are fixed
    the moment the festival dawns (seeded from seed+day — no re-rolling), and
    the field stiffens gently with the years. Prizes are prestige, not gold:
    the contest is where a 5-star good goes to mean something."""
    import random as _random
    from . import karma, requests as gamereq, skills
    fest = content.festival_on(state.season, state.day_of_season)
    state.stats[_contest_key(state)] = 1
    state.player.inventory.remove(item, 1, quality=ql)
    state.bump("contests_entered")
    rng = _random.Random((state.seed * 42_589 + state.day * 631) & 0x7FFFFFFF)
    grown = [n for n in state.surface.npcs if n.role != "child"]
    rivals = rng.sample(grown, min(3, len(grown)))
    rival_scores = sorted((rng.uniform(2.5, 5.5) + 0.35 * max(0, state.year - 1)
                           for _ in rivals), reverse=True)
    mine = ql * 1.6 + min(3.5, item.value / 140.0) + rng.uniform(0.0, 1.2)
    place = 1 + sum(1 for s in rival_scores if s > mine)
    star = (" " + skills.stars(ql)) if ql else ""
    entry = f"{item.name.lower()}{star}"

    if place == 1:
        state.bump("contests_won")
        state.player.inventory.add(items.FAIR_RIBBON, 1)
        for n in state.surface.npcs:
            if getattr(n, "village", "") == "Mossford":
                n.friendship = min(MAX_HEARTS * 100, n.friendship + 100)
        karma.adjust(state, 3)
        extra = ""
        if rng.random() < 0.4:
            pool = gamereq.unknown_recipes(state)
            if pool:
                gamereq.learn_recipe(state, rng.choice(pool), teacher="The judge")
                extra = "\nThere's a recipe card tucked under the ribbon, too."
        state.log.add(f"First prize at {fest[1]} — your {entry} takes the ribbon!",
                      (232, 200, 120))
        return (f"The judge holds your {entry} aloft — the square erupts!\n"
                f"\"FIRST PRIZE! Finest thing the Grange has seen in years.\"\n"
                f"A fair ribbon is pinned on you, to warm applause.{extra}")
    if place <= 3:
        judge = next((n for n in state.surface.npcs
                      if n.role == "innkeeper" and n.village == "Mossford"), None)
        if judge is not None:
            judge.friendship = min(MAX_HEARTS * 100, judge.friendship + 45)
        karma.adjust(state, 1)
        state.player.inventory.add(fest[3], 1)
        state.log.add(f"Your {entry} places {place}{'nd' if place == 2 else 'rd'} at the fair.",
                      (200, 220, 160))
        return (f"\"{place}{'nd' if place == 2 else 'rd'} place — well grown!\" says the judge,\n"
                f"pressing a {fest[3].name.lower()} into your hands.\n"
                f"{rivals[0].name}'s entry edges the field this year.")
    karma.adjust(state, 1)
    state.log.add("No ribbon this year — but the entering's half the fun.", C.DIM)
    return (f"The judge nods kindly over your {entry}.\n"
            f"\"Good, honest work — but {rivals[0].name}'s entry is a marvel.\n"
            "Bring me your finest next fair, eh?\"")


# --- shops ------------------------------------------------------------------
def npc_shop(state: GameState, npc: NPC) -> str | None:
    """The shop an NPC keeps *right now*. Derived, never stored on the NPC
    (NPCs are regenerated from content on every load): traders open their
    wagons by role, and Willa's only once the Fenwick causeway lets goods
    through."""
    if npc.shop:
        return npc.shop
    if npc.role == "trader":
        from . import projects
        if npc.name == "Willa" and not projects.done(state, "causeway"):
            return None
        return "trader"
    return None


def trader_window(seed: int, day: int) -> tuple[int, int]:
    """(window index, window seed) for the traders' rotating stock. Windows run
    3-6 days, their lengths drifting from the seed — fully derived from
    (seed, day), so the rotation needs no save field and never goes stale."""
    import random as _random
    n, start = 0, 0
    while True:
        length = 3 + _random.Random((seed * 611_953 + n * 2_741) & 0x7FFFFFFF).randint(0, 3)
        if day < start + length:
            return n, (seed * 887 + n * 104_729) & 0x7FFFFFFF
        start += length
        n += 1


def trader_entries(state: GameState, npc: NPC) -> list:
    """A trader's wagon this window: a few dear, rare things — the non-crafter's
    road to high-tier gear, priced at 3-4x its worth. Slots are drawn
    deterministically per (seed, window, trader); bought slots are remembered
    in stats so a wagon can sell out."""
    import random as _random
    import zlib
    window, wseed = trader_window(state.seed, state.day)
    rng = _random.Random(wseed ^ zlib.crc32(npc.name.encode()))
    deep = npc.name in ("Willa", "Kazrik")           # causeway & tunnel traders dig deeper
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
    sap = rng.choice((items.CHERRY_SAPLING, items.APPLE_SAPLING, items.PEACH_SAPLING))
    slots.append((sap, content._round5(700 * 1.5)))
    if deep:
        bar = rng.choice((items.GOLD_BAR, items.PLATINUM_BAR))
        slots.append((bar, content._round5(bar.value * 2.0)))
        slots.append((items.SILK_CLOTH, content._round5(items.SILK_CLOTH.value * 1.5)))
        if rng.random() < 0.25:
            slots.append((items.BEE_QUEEN, content._round5(items.BEE_QUEEN.value * 2.0)))

    out = []
    for i, (it, price) in enumerate(slots):
        key = f"trader_{npc.name}_{window}_{i}"
        if not state.stats.get(key):                 # sold slots stay sold this window
            out.append(ShopRow("tradebuy", label=it.name, item=it, price=price, key=key))
    # a recipe card, drawn unconditionally (determinism) but hidden once known
    card_pool = sorted(r.name for r in content.RECIPES
                       if r.kind == "cook"
                       and r.name not in dict(content.TAVERN_RECIPES)
                       and r.name not in content.STARTER_RECIPES)
    card = rng.choice(card_pool)
    if card not in state.known_recipes:
        out.append(ShopRow("recipe", name=card, price=260))
    return out


def shop_entries(shop: str, state: GameState | None = None,
                 npc: NPC | None = None) -> list[ShopRow]:
    """The rows on a shop's counter, in display order."""
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
                buys += [ShopRow("buy", label=b.name, item=b,
                                 price=content._round5(b.value * 2.0))
                         for b in content.DEEP_FORGE_BARS]
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
            fest_name = contest_open(state)
            if fest_name:
                meals = [ShopRow("contest", name=fest_name)] + meals
        # The house recipes: an innkeeper will part with one, for a price.
        cards = [ShopRow("recipe", name=name, price=price)
                 for name, price in content.TAVERN_RECIPES
                 if state is not None and name not in state.known_recipes]
        return meals + cards + (_inn_purchases(state) if state is not None else [])
    if shop == "carpenter":
        jobs = [ShopRow("commission", label=label, build=kind, price=gold, mats=tuple(mats))
                for (label, kind, gold, mats) in content.CARPENTER_JOBS]
        # Farmhouse fittings (oven, cellar) — auto-sited, hidden once owned or
        # already under Tomas's hammer.
        if state is not None and state.surface is not None:
            for label, kind, gold, mats in content.HOUSE_JOBS:
                owned = any(m.kind == kind or (m.kind == "site" and m.build_kind == kind)
                            for m in state.surface.machines.values())
                if not owned:
                    jobs.append(ShopRow("housejob", label=label, build=kind,
                                        price=gold, mats=tuple(mats)))
        # If an order is outstanding, offer to cancel it (with a full refund) so
        # you're never locked out of the carpenter by a build you can't site.
        if state is not None and state.pending_build:
            return [ShopRow("cancel_build", build=state.pending_build)] + jobs
        return jobs
    return []


def _job_for(kind: str):
    """The (label, gold, mats) of a carpenter job by its build kind, or None."""
    for label, k, gold, mats in content.CARPENTER_JOBS:
        if k == kind:
            return label, gold, mats
    return None


def purchase(state: GameState, row: ShopRow) -> None:
    """Perform a shop row's transaction. One dispatch, on named fields."""
    if row.kind == "buy":
        if state.player.gold < row.price:
            state.log.add("You can't afford that.", C.DIM)
            return
        state.player.gold -= row.price
        state.player.inventory.add(row.item, 1)
        state.log.add(f"Bought {row.item.name} for {row.price}g.")
    elif row.kind == "meal":
        p = state.player
        if p.gold < row.price:
            state.log.add("You can't afford that.", C.DIM)
            return
        p.gold -= row.price
        p.energy = min(p.max_energy, p.energy + row.stam)
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
        name = content.MACHINES[row.build].name.lower()
        state.log.add(f"Tomas sets to work on your {name} — ready in 2 mornings.",
                      (200, 220, 160))
    elif row.kind == "upgrade":
        upgrade_tool(state, row.tool)


def upgrade_price(state: GameState, tier: int):
    """(gold, bar, count) for a tool upgrade — the Deep Forge, once raised,
    takes a fifth off Bron's labour."""
    from . import projects
    gold, bar, count = content.upgrade_cost(tier)
    if projects.done(state, "deep_forge"):
        gold = round(gold * 0.8)
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
