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

    if m.kind in ("coop_small", "coop_big", "barn", "pen", "site"):
        from . import husbandry
        return husbandry.interact_building(state, m, x, y)

    if m.kind == "sprinkler":
        state.log.add("The sprinkler waters the soil around it each morning.", C.DIM)
        return True

    if m.kind == "jeweller":
        # The bench works instantly (like a workbench): always offer its choices.
        opts = machine_load_options(state, mdef)
        if not opts:
            state.log.add(_needs_hint(mdef), C.DIM)
            return True
        return {"load": (x, y), "options": opts, "name": mdef.name, "jeweller": True}

    if status == "done":
        from . import skills
        out = m.loaded_output
        q = m.out_quality if skills.has_quality(out) else 0
        state.player.inventory.add(out, 1, quality=q)
        star = (" " + skills.stars(q)) if q else ""
        if m.kind in ("spinner", "loom"):
            skills.gain(state, "Farming", 7)         # spinning & weaving; cloth garments too
            if out.kind == "artisan":
                state.bump("artisan_made")
        elif out.kind in ("weapon", "armor"):
            skills.gain(state, "Smithing", 12)       # forging hones the smith
        elif out.kind == "gem":
            skills.gain(state, "Gemcutting", 14)     # cutting hones the cutter
        elif m.kind in ("furnace", "kiln"):
            skills.gain(state, "Smithing", 8)        # smelting & fuel-making, too
        elif m.kind in ("quern", "windmill"):
            skills.gain(state, "Cooking", 6)         # milling is kitchen work
        elif out.kind == "artisan":
            state.bump("artisan_made")
            skills.gain(state, "Cooking", 8)         # processing hones the craft
        state.log.add(f"You collect {out.name}{star} from the {mdef.name.lower()}.", (180, 230, 160))
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
        "ore":   "The furnace needs ore and a fuel hot enough to smelt it.",
        "fuel":  "The kiln chars wood into charcoal, or bakes coal into coke.",
        "gem":   "The gemcutting station needs a rough gem or a geode.",
        "jewelcraft": "The jeweller's bench needs a metal bar + a cut gem, or gear + a cut gem to embed.",
        "mill":  "The mill grinds grain into flour, cane into sugar, or salt lumps into sea salt.",
        "smoke": "The smoker cures meat into jerky, or fish into smoked fish.",
        "fiber": "The spinning wheel needs wool, cotton, flax or spider silk.",
        "weave": "The loom needs yarn to weave into cloth, or cloth to tailor into garments.",
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
    elif a == "smoke":
        for src, out in content.SMOKE_RECIPES:
            if inv.count(src) >= 1:
                opts.append({"inputs": [(src, 1)], "output": out, "quality_from": src})
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
    m.loaded_output = output
    minutes = round(opt.get("minutes", mdef.minutes) * (skills.smith_speed_mult(state)
                    if mdef.kind in ("furnace", "anvil", "kiln") else 1.0))
    m.ready_at = state.abs_minutes + max(1, minutes)
    # Cut gems take their quality from the cutter's Gemcutting; other processed
    # goods inherit the input's quality nudged by the cook's skill.
    if skills.has_quality(output):
        m.out_quality = (skills.roll_quality(state, "Gemcutting") if output.kind == "gem"
                         else skills.process_quality(in_quality, state, "Cooking"))
        if mdef.kind == "quern":                       # the hand-mill grinds a touch coarse
            m.out_quality = max(0, m.out_quality - 1)
    else:
        m.out_quality = 0
    state.log.add(f"You load the {mdef.name.lower()} ({output.name}). Ready in {_fmt_remaining(minutes)}.")


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
        skills.gain(state, "Jewelcrafting", 16)
        star = (" " + skills.stars(outq)) if outq else ""
        state.log.add(f"You craft {opt['output'].name}{star}.", (230, 210, 140))
    elif kind == "embed_gear":
        for it, q in opt["inputs"]:
            inv.remove(it, q)
        inv.add(opt["output"], 1)
        skills.gain(state, "Jewelcrafting", 12)
        state.log.add(f"You set the gem — {opt['output'].name}.", (230, 210, 140))
    elif kind == "embed_tool":
        inv.remove(opt["inputs"][0][0], 1)
        tool = opt["tool"]
        state.player.tool_gem[tool] = tuple(state.player.tool_gem.get(tool, ())) + (opt["gemkey"],)
        skills.gain(state, "Jewelcrafting", 12)
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


def sell_shipment(state: GameState) -> None:
    """Convert everything in the shipping bin to gold overnight (quality-scaled)."""
    total = sum(slot_value(it, ql) * qty for it, qty, ql in state.ship_bin.slots)
    if total > 0:
        state.player.gold += total
        state.bump("gold_earned", total)
        state.log.add(f"The shipping bin sold your goods for {total}g.", (240, 214, 120))
        state.ship_bin.slots.clear()
