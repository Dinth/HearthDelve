"""The in-game encyclopedia (the ? screen).

Help/reference pages assembled from the content registries, plus the paged
reader that draws one. Split out of engine/rendering.py: a self-contained
subsystem (build the pages, cache them until the world's signature changes,
render the current page).
"""
from __future__ import annotations

import tcod.console

from . import constants as C
from . import ui
from ..game.state import GameState

_HDR = ui.HDR
_KEY = (150, 200, 230)


def build_codex_pages(state: GameState):
    """Assemble the help/encyclopedia pages from the content registries.

    Returns a list of (title, rows) where each row is (text, color).
    """
    from ..data import content
    from ..world import tile

    pages: list[tuple[str, list[tuple[str, tuple]]]] = []

    # --- Page: Controls ------------------------------------------------------
    controls = [
        ("Movement", _HDR),
        ("  Arrow keys       move (up / down / left / right)", C.WHITE),
        ("  Numpad 1-9       move, including diagonals", C.WHITE),
        ("  Numpad 5  /  .   wait a turn (30s)", C.WHITE),
        ("  w then a dir     run until something / path ends / 50 tiles", C.WHITE),
        ("  w then .         rest until something happens (up to 1h)", C.WHITE),
        ("", C.WHITE),
        ("Commands", _HDR),
        ("  Space            use active tool on the highlighted tile", C.WHITE),
        ("                   (it turns green when the tool can act there)", C.DIM),
        ("  1-9              select hotbar tool / seed", C.WHITE),
        ("  g                gather / harvest / use a machine", C.WHITE),
        ("  t                aim & fire: a readied bow/sling, else a bomb", C.WHITE),
        ("  c                craft, build machines, cook dishes", C.WHITE),
        ("  p                site a carpenter building (opens aiming)", C.WHITE),
        ("  x                eat (restores stamina & health)", C.WHITE),
        ("  b                shipping bin (sell) — stand beside it", C.WHITE),
        ("                   (the market's cravings pay extra some days)", C.DIM),
        ("  Shift+C          talk to a villager / open a shop", C.WHITE),
        ("  f                give a villager a gift", C.WHITE),
        ("  g at ‡ board     village notice board — favours for gold &", C.WHITE),
        ("                   friendship, and the village's great project:", C.DIM),
        ("                   fund it in instalments for a lasting landmark", C.DIM),
        ("                   & perk (j → Projects shows them anywhere)", C.DIM),
        ("  > / <            descend / climb a dungeon (on stairs)", C.WHITE),
        ("  s                sleep in bed -> next day", C.WHITE),
        ("  i                inventory  (a-z select; Enter eats/equips;", C.WHITE),
        ("                   Tab filters by category; Shift+D drops the stack)", C.DIM),
        ("  e                equipment", C.WHITE),
        ("  m                world map (the whole region at a glance)", C.WHITE),
        ("  h                message log (scrollback)", C.WHITE),
        ("  v                character sheet (stats, combat numbers & skills)", C.WHITE),
        ("  j                journal (goals)", C.WHITE),
        ("  r                relationships", C.WHITE),
        ("  l                look around (read any tile)", C.WHITE),
        ("  ?                this help / encyclopedia", C.WHITE),
        ("  Esc              quit / close a screen", C.WHITE),
    ]
    pages.append(("Controls", controls))

    # --- Page: Land & Home ---------------------------------------------------
    landpg = [
        ("Land & Ownership", _HDR),
        ("", C.WHITE),
        ("Every patch of ground has an owner.", C.WHITE),
        ("", C.WHITE),
        ("  Your homestead", _KEY),
        ("      The land around your farm is granted freehold — yours,", C.WHITE),
        ("      and never taxed. Build and farm freely here.", C.DIM),
        ("  Village land", _KEY),
        ("      Cottages, farm plots and gardens belong to their", C.WHITE),
        ("      residents; shops and greens to the village. You may not", C.DIM),
        ("      build there, and taking a villager's crop, fruit or", C.DIM),
        ("      berries is theft — it costs karma and their regard.", C.DIM),
        ("      (You'll be asked to confirm before you take.)", C.DIM),
        ("  Wilderness", _KEY),
        ("      Ownerless. Till it, build on it, or fence it off to", C.WHITE),
        ("      CLAIM it as your own. Craft Fence Panels (c), then", C.DIM),
        ("      'Set Fence' to lay them — no need to close the ring:", C.DIM),
        ("      the fence outline bounds the plot (a U of 5-long sides", C.DIM),
        ("      claims the whole 5x5).", C.DIM),
        ("", C.WHITE),
        ("Land tax", _HDR),
        ("      The crown levies a small weekly tax on your claimed", C.WHITE),
        ("      wilderness. A notice arrives at your post box — open it", C.DIM),
        ("      (g at the box) to settle up. Ignoring the bill costs a", C.DIM),
        ("      little karma each week, but your gold and land are safe.", C.DIM),
    ]
    pages.append(("Land & Home", landpg))

    # --- Page: Tools & Equipment --------------------------------------------
    tools = [("Tools  (energy cost per use)", _HDR), ("", C.WHITE)]
    for it in content.ALL_TOOLS:
        s = content.TOOL_STATS[it]
        tools.append((f" {it.glyph}  {it.name}", _KEY))
        tstr = f"{s.seconds // 60}m" if s.seconds >= 60 else f"{s.seconds}s"
        tools.append((f"      {s.verb} {s.target} · {s.stamina} stamina · {tstr} · {s.yields}", C.WHITE))
        tools.append((f"      {it.desc}", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Weapons  (hold one; bump to attack)", _HDR))
    tools.append(("", C.WHITE))
    for it in content.ALL_WEAPONS:
        w = content.WEAPON_STATS[it]
        lo, hi = w.dmg
        tools.append((f" {it.glyph}  {it.name}   {w.category}  hit {w.to_hit:+d}  dmg {lo}-{hi}"
                      + (f"  DV {w.dv:+d}" if w.dv else ""), _KEY))
        tools.append((f"      {it.desc}", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Ranged  (equip in the ranged slot; aim & fire with t)", _HDR))
    tools.append(("", C.WHITE))
    for it in content.ALL_RANGED:
        rs = content.RANGED[it]
        lo, hi = rs.dmg
        tools.append((f" {it.glyph}  {it.name}   hit {rs.to_hit:+d}  dmg {lo}-{hi}"
                      f"  range {rs.rng}  ({rs.ammo.name.lower()}s)", _KEY))
        tools.append((f"      {it.desc}", C.DIM))
    tools.append(("Bombs need no bow — thrown by hand from the ammo slot.", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Any tool can fight too (badly); a weapon can do a tool's job", C.DIM))
    tools.append(("with penalties — a battle axe fells trees, a blade clears brush.", C.DIM))
    tools.append(("Combat: 1d20 + to-hit vs the foe's DV; damage - its PV. Armour", C.DIM))
    tools.append(("gives PV; Dodge & mastery give DV. Land hits to master a weapon.", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Materials & affixes", _HDR))
    tools.append(("Every weapon & armour is made of a material — copper..adamantium", C.DIM))
    tools.append(("for metal, leather/hide & cloth for soft gear, birch..composite", C.DIM))
    tools.append(("for bows. Finer material = better. Deeper dungeon loot trends to", C.DIM))
    tools.append(("finer stuff (with a pinch of luck), and may carry a prefix/suffix", C.DIM))
    tools.append(("(Fine, Masterwork, of Slaying, of Warding...). Smelt ore to bars,", C.DIM))
    tools.append(("then forge gear of that metal at an Anvil (build it with 'c').", C.DIM))
    tools.append(("", C.WHITE))
    tools.append(("Fuel, gems & jewellery", _HDR))
    tools.append(("Fuels have heat: wood < charcoal < coal < coke. A metal needs a", C.DIM))
    tools.append(("minimum heat to smelt at all, and hotter fuel smelts faster. A Kiln", C.DIM))
    tools.append(("chars wood into charcoal, or bakes coal into coke.", C.DIM))
    tools.append(("Mine rough gems (finer the deeper you dig) and crack Geodes; cut", C.DIM))
    tools.append(("them at a Gemcutting Station. At a Jeweller's Bench, set a cut gem", C.DIM))
    tools.append(("into a metal band for a Ring or Amulet (neck/ring slots), or embed", C.DIM))
    tools.append(("it into a weapon, armour, or tool. Ruby/Sapphire/Topaz aid combat;", C.DIM))
    tools.append(("Emerald/Amethyst aid your work; Diamond does a bit of everything.", C.DIM))
    pages.append(("Tools & Equipment", tools))

    # --- Page: Seeds & Crops -------------------------------------------------
    crops = [("Crops", _HDR), ("", C.WHITE)]
    for c in content.CROPS:
        regrow = "regrows" if c.regrows else "single harvest"
        crops.append((f" {c.glyph}  {c.name}", _KEY))
        crops.append((f"      {c.season}  ·  matures {c.days_to_mature}d  ·  {regrow}  ·  sells {c.sell_price}g",
                      C.WHITE))
        crops.append((f"      from {c.seed.name}.  {c.desc}", C.DIM))
    crops.append(("", C.WHITE))
    crops.append(("How to farm:", _HDR))
    crops.append(("  Till soil (Hoe) -> select seeds (6) -> Space to plant", C.WHITE))
    crops.append(("  -> water daily (Can) -> sleep -> harvest (g) when ripe.", C.WHITE))
    crops.append(("  Rain waters for you. Crops die out of season.", C.DIM))
    crops.append(("", C.WHITE))
    crops.append(("Orchard trees (buy saplings at the store):", _HDR))
    for t in content.TREES:
        crops.append((f"  {t.name} — bears {t.fruit.name.lower()} each {t.season}"
                      f" (~{t.days_to_mature}d to grow)", C.WHITE))
    crops.append(("  Plant a sapling (pouch), wait, then pick fruit (g).", C.DIM))
    pages.append(("Seeds & Crops", crops))

    # --- Page: Crafting & Machines ------------------------------------------
    craftp = [("Recipes  (press c)", _HDR), ("", C.WHITE),
              ("Cooking is learned: you start with the plain fare and pick up", C.WHITE),
              ("the rest around the Vale — friends share their favourite dish", C.DIM),
              ("at 3♥, taverns sell house recipes, practice sparks a few, and", C.DIM),
              ("a filled notice-board favour sometimes has one folded in.", C.DIM),
              ("", C.WHITE)]
    for r in content.RECIPES:
        ins = ", ".join(f"{q} {it.name}" for it, q in r.inputs)
        craftp.append((f" {r.name}", _KEY))
        if r.kind == "build":
            tag = "build"
        elif r.kind == "cook":
            from ..game import skills
            e = r.output.energy if r.output else 0
            bf = f", {skills.BUFFS[r.output.buff]}" if (r.output and r.output.buff in skills.BUFFS) else ""
            tag = f"cook (+{e} stamina{bf})"
        else:
            tag = "craft"
        craftp.append((f"      {tag}:  {ins}", C.WHITE))
    craftp.append(("", C.WHITE))
    craftp.append(("Machines  (g to load / collect)", _HDR))
    craftp.append(("", C.WHITE))
    for mdef in content.MACHINES.values():
        if mdef.kind == "site":
            continue                         # internal construction placeholder
        craftp.append((f" {mdef.glyph}  {mdef.name}", _KEY))
        extra = f"  (~{mdef.minutes // 60}h)" if mdef.minutes else ""
        craftp.append((f"      {mdef.desc}{extra}", C.DIM))
    craftp.append(("", C.WHITE))
    craftp.append(("Animals  (buy chicks/calves at the general store)", _HDR))
    craftp.append(("  Build a little coop yourself, or have Tomas the carpenter", C.DIM))
    craftp.append(("  raise a roomy coop, barn, or greenhouse (order it, press p to site it).", C.DIM))
    craftp.append(("  A greenhouse grows any crop year-round — winter farming!", C.DIM))
    craftp.append(("  Settle young animals with g; bump them to pet or collect.", C.DIM))
    craftp.append(("  Pet daily to keep them happy — happier beasts give finer", C.DIM))
    craftp.append(("  eggs & milk. Churn milk into cheese.", C.DIM))
    craftp.append(("  They graze free on grass in the growing seasons; in winter", C.DIM))
    craftp.append(("  (or a paved-in yard) they eat straw — scythe tall grass", C.DIM))
    craftp.append(("  (machete), dry it on a fair day, then fork it into the coop/", C.DIM))
    craftp.append(("  barn trough (g). They shelter by the coop in a storm.", C.DIM))
    craftp.append(("", C.WHITE))
    craftp.append(("Gather wood (axe), stone & ore+coal (pickaxe).", C.DIM))
    craftp.append(("Value ladder: raw crop < jam < wine.", C.DIM))
    pages.append(("Crafting & Machines", craftp))

    # --- Page: Fish ---------------------------------------------------------
    fishp = [("Fish  (face water, cast the rod)", _HDR), ("", C.WHITE)]
    for f in content.FISH:
        rarity = "common" if f.weight >= 25 else "uncommon" if f.weight >= 8 else "rare"
        when = "all year" if not f.seasons else "/".join(f.seasons)
        fishp.append((f" {f.item.glyph}  {f.item.name:<9} {f.item.value:>4}g  {rarity:<8} {when}", C.WHITE))
    fishp.append(("", C.WHITE))
    fishp.append(("Underground lakes  (fish while delving)", _HDR))
    for it, w in content.CAVE_FISH:
        rarity = "common" if w >= 25 else "uncommon" if w >= 8 else "rare"
        fishp.append((f" {it.glyph}  {it.name:<10} {it.value:>4}g  {rarity}", C.WHITE))
    fishp.append(("", C.WHITE))
    fishp.append(("Sell them, or cook Fish Stew / Grilled Trout for energy.", C.DIM))
    pages.append(("Fish", fishp))

    # --- Page: Terrain & Features -------------------------------------------
    notes = {
        "water": "fish with a rod", "tree": "passable; chop with an axe",
        "ore": "mine with a pickaxe", "wall": "impassable",
        "soil": "plant seeds here", "bed": "sleep to end the day",
        "bin": "drop goods to sell", "stairs": "enter a dungeon",
        "door": "an open doorway", "fence": "impassable",
        "foliage": "machete to clear (fibre)", "shrub": "machete to clear (fibre)",
        "shrub_berry": "pick berries (g); regrows in days",
    }
    terrain = [("Terrain & Features  ( · walkable / x blocked )", _HDR), ("", C.WHITE)]
    seen = set()
    for t in tile.TILES:
        if t.name in seen:
            continue
        seen.add(t.name)
        mark = "·" if t.walkable else "x"
        note = notes.get(t.kind, "")
        label = f" {t.glyph} {mark}  {t.name.replace('_', ' '):<13}"
        terrain.append((label + (f"  {note}" if note else ""), C.WHITE))
    pages.append(("Terrain & Features", terrain))

    # --- Page: Monsters ------------------------------------------------------
    _KIND_NAME = {"mine": "Mines", "grotto": "Grottoes", "barrow": "Barrows",
                  "tomb": "Tombs", "dwarfhold": "Dwarfhold"}

    def _haunt(kinds):
        return ", ".join(_KIND_NAME.get(k, k) for k in kinds) if kinds else "any dungeon"

    def _mon_lines(m, into):
        tags = _haunt(m.kinds)
        if m.inflicts:
            tags += f"  ·  inflicts {m.inflicts}"
        into.append((f" {m.glyph}  {m.name}   HP {m.hp}  DV {m.dv} PV {m.pv}  "
                     f"dmg {m.dmg[0]}-{m.dmg[1]}  from floor {m.min_depth}", _KEY))
        into.append((f"      {m.behavior}, {tags}. {m.desc}", C.DIM))
        drops = content.MONSTER_DROPS.get(m.name, ())
        if drops:
            into.append(("      drops: " + ", ".join(i.name.lower() for i, _ in drops),
                         (150, 182, 150)))
        n = state.bestiary.get(m.name, 0)
        if n:
            into.append((f"      slain {n}×", (196, 176, 130)))

    slain_total = sum(state.bestiary.values())
    kinds_known = len(state.bestiary)
    mon = [("Bestiary", _HDR),
           (f"  {slain_total} foes slain across {kinds_known} kinds.  "
            "Drops listed; a slain-count marks what you've faced.", C.DIM),
           ("", C.WHITE)]
    for m in content.MONSTERS:
        _mon_lines(m, mon)
    mon.append(("", C.WHITE))
    mon.append((" Bosses — lurking on the deep floors:", _HDR))
    for b in content.BOSSES:
        _mon_lines(b, mon)
    mon.append(("", C.WHITE))
    mon.append(("Bump to attack. Aim & throw a Bomb (t) to hit several at once.", C.DIM))
    mon.append(("Deeper down, elites appear — prefixed, brighter, tougher, and worth more.", C.DIM))
    mon.append(("Slain cave beasts may drop reagents (gel, wing, hide).", C.DIM))
    mon.append(("Faint in the dark → hauled home, minus loose loot & 10% gold.", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Underground", _HDR))
    mon.append((" ■  chests — open with g for gold, ore, gems", _KEY))
    mon.append((" τ  cave mushrooms — gather (g); cook a Mushroom Stew", _KEY))
    mon.append((" ^  traps — hidden until spotted; step around them", _KEY))
    mon.append((" ░  rubble — loose footing, slow to cross", _KEY))
    mon.append((" ♠î glimmerwood grove — rare glowing wispwood & glowcaps", _KEY))
    mon.append(("      (a peaceful find; glowcaps cook a rich Glowcap Broth)", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Going deep", _HDR))
    mon.append(("  The rock hardens with every band: veins past floor 1 suit a", C.WHITE))
    mon.append(("  Bronze pick, floor 4+ Iron, floor 6+ Steel, floor 8+ better", C.DIM))
    mon.append(("  still. A softer pick still bites — just slow, tiring, and", C.DIM))
    mon.append(("  prone to mangling the vein into rubble. Bron forges upgrades.", C.DIM))
    mon.append(("  And the dark weighs on you: work and fighting tire you more", C.DIM))
    mon.append(("  with each floor down — pack food, and jewellery that spares", C.DIM))
    mon.append(("  your strength.", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Foraging (surface)", _HDR))
    mon.append((" τ  field mushrooms — button & parasol, in open grass", _KEY))
    mon.append((" τ  forest mushrooms — bolete & chanterelle, under the woods", _KEY))
    mon.append(("      sprout in summer & autumn only; gather (g) to cook", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Wildlife (surface)", _HDR))
    for c in content.WILDLIFE:
        diet = {"crops": "raids crops", "berries": "eats berries"}.get(c.diet, "harmless")
        mon.append((f" {c.glyph}  {c.name}   {c.behavior}, {diet}", _KEY))
        mon.append((f"      {c.desc}", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("Fence your fields — critters can't reach crops behind a fence.", C.DIM))
    mon.append(("", C.WHITE))
    mon.append(("The Westreach (walk off the map's western edge)", _HDR))
    mon.append(("  Volcanic hill country: ore-rich crags, sulphur & nitre on the", C.WHITE))
    mon.append(("  mountain, and beasts that hunt on sight. No bed, no fields —", C.DIM))
    mon.append(("  an expedition, not a stroll. Walk east to come home.", C.DIM))
    for c in content.WEST_WILDLIFE:
        mon.append((f" {c.glyph}  {c.name}   {c.behavior}", _KEY))
        mon.append((f"      {c.desc}", C.DIM))
    pages.append(("Bestiary", mon))

    # --- Page: Dungeon Sites -------------------------------------------------
    from ..world import dungeon
    _SITE_INFO = {
        "mine":      ("Mines", "boulder-strewn shafts"),
        "dwarfhold": ("Dwarfholds", "the old dwarven deeps"),
        "cavern":    ("Caverns", "vast glittering halls"),
        "grotto":    ("Grottoes", "damp, fungal hollows"),
        "sea cave":  ("Sea Caves", "tide-flooded coastal caves"),
        "barrow":    ("Barrows", "grassed-over burial mounds"),
        "tomb":      ("Tombs", "sealed stone tombs"),
        "crypt":     ("Crypts", "trap-riddled undercrofts"),
    }

    def _richness(b):
        bits = [{5: "veined with ore", 4: "ore-rich", 3: "some ore", 2: "a little ore",
                 1: "scant metal", 0: "barren of metal"}.get(b["ore"], "some ore")]
        if b["gem"] >= 2:
            bits.append("glittering with gems")
        elif b["gem"] == 1:
            bits.append("the odd gem")
        if b["trap"] >= 1.8:
            bits.append("heavily trapped")
        elif b["trap"] >= 1.3:
            bits.append("trap-riddled")
        if b["lakes"] >= 3:
            bits.append("half-flooded")
        elif b["lakes"] == 2:
            bits.append("pooled with water")
        elif b["lakes"] == 1:
            bits.append("a pool or two")
        if b["chest"] >= 2:
            bits.append("rich in grave-goods")
        elif b["chest"] == 1:
            bits.append("the occasional chest")
        return "; ".join(bits)

    sites = [("Dungeon Sites  (where you delve shapes the reward)", _HDR), ("", C.WHITE)]
    for kind, bias in dungeon.KIND_BIAS.items():
        name, flavour = _SITE_INFO.get(kind, (kind.title(), ""))
        sites.append((f" {name} — {flavour}", _KEY))
        sites.append((f"      {_richness(bias)}", C.WHITE))
    sites.append(("", C.WHITE))
    sites.append(("Look (l) at an entrance to read which kind it is before you", C.DIM))
    sites.append(("commit. Every kind rewards a wooden pick — mines just reward a", C.DIM))
    sites.append(("steel one far more. The rock hardens as you descend, and the", C.DIM))
    sites.append(("dark tires you more with each floor: pack food and a good pick.", C.DIM))
    pages.append(("Dungeon Sites", sites))

    # --- Page: Villagers ----------------------------------------------------
    vp = [("Folk of Hollowmere Vale", _HDR), ("", C.WHITE)]
    for npc in state.world.npcs:
        role = {"general": "General Store", "blacksmith": "Blacksmith"}.get(npc.shop, "villager")
        vp.append((f" {npc.glyph}  {npc.name} — {role}", _KEY))
        loves = ", ".join(i.name for i in npc.loves) or "—"
        vp.append((f"      {'♥' * npc.hearts}{'·' * (10 - npc.hearts)}   loves: {loves}", C.DIM))
    vp.append(("", C.WHITE))
    vp.append(("Shift+C talk · f gift. Mossford is the hamlet; Cinderhope the outpost.", C.DIM))
    vp.append(("Gifts they love raise friendship most (one gift each per day).", C.DIM))
    pages.append(("Villagers", vp))

    return pages


_codex_cache: list | None = None
_codex_sig: tuple | None = None


def render_codex(con: tcod.console.Console, state: GameState, page: int, scroll: int) -> None:
    # The pages are almost entirely static content; only the Villagers page moves
    # (friendship hearts). Rebuild solely when that signature changes, rather than
    # re-walking every crop/tool/recipe/machine on every frame the help is open.
    global _codex_cache, _codex_sig
    # rebuild when friendships move (Villagers page) or a kill lands (Bestiary page)
    sig = (tuple((n.name, n.friendship) for n in state.world.npcs),
           sum(state.bestiary.values()), len(state.bestiary))
    if _codex_cache is None or sig != _codex_sig:
        _codex_cache, _codex_sig = build_codex_pages(state), sig
    pages = _codex_cache
    page %= len(pages)
    title, rows = pages[page]

    w, h = 66, 44
    body_h = h - 5
    m = ui.Modal(con, w, h, f"Encyclopedia — {title}")

    max_scroll = max(0, len(rows) - body_h)
    scroll = max(0, min(scroll, max_scroll))
    for i in range(body_h):
        idx = scroll + i
        if idx >= len(rows):
            break
        text, color = rows[idx]
        m.text(2, 2 + i, text[:w - 4], fg=color)
    m.arrows(scroll > 0, scroll < max_scroll, 2, h - 3)
    m.footer(f" ← → page {page + 1}/{len(pages)}   ↑ ↓ scroll   Esc close ")


# Inventory categories, in the order they're listed (ADOM-style grouping).
