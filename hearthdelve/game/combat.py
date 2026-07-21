"""Light bump-combat, monster AI, and the Bomb ability (M4 Stage 2)."""
from __future__ import annotations

import random

from ..data import content
from ..engine import constants as C
from ..entities import items
from ..world import tile
from .state import GameState


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


# --- status effects (damage over time) ---------------------------------------
# Each entry: per-turn damage, how many turns a fresh application lasts, the
# chance a landing hit inflicts it, and the display/log wording. Ticked once per
# action by turns.advance_time; cleared by a night's rest (farming.new_day).
# Per-turn damage is the larger of a flat ``dmg`` and ``pct`` of the victim's
# max HP — so a status is unchanged for a fragile newcomer (the flat value wins)
# yet keeps its teeth against a 160-HP veteran or a scaled deep monster (the
# percentage wins), instead of fading to a rounding error as HP grows.
STATUS = {
    "poison": {"dmg": 2, "pct": 0.018, "turns": 5, "chance": 0.45, "color": (150, 210, 120),
               "tag": "☠ Poisoned", "on": "The bite festers — you're poisoned!",
               "off": "The poison finally passes."},
    "bleed":  {"dmg": 2, "pct": 0.018, "turns": 4, "chance": 0.40, "color": (220, 120, 120),
               "tag": "≈ Bleeding", "on": "You're bleeding!",
               "off": "The bleeding stops."},
    "burn":   {"dmg": 3, "pct": 0.022, "turns": 3, "chance": 0.50, "color": (240, 150, 80),
               "tag": "♨ Burning", "on": "You're set alight — burning!",
               "off": "The burns cool."},
    # A lingering illness (not a wound): weak but long, and it saps your stamina.
    # The brimstone salve won't touch it — only a charcoal tincture or a panacea.
    "sick":   {"dmg": 1, "pct": 0.012, "turns": 8, "chance": 0.5, "stam": 4,
               "color": (170, 192, 120), "tag": "☣ Sick",
               "on": "A cold sweat takes you — you've caught something.",
               "off": "The sickness finally lifts."},
}


def _status_damage(holder, info: dict) -> int:
    """A DoT tick's damage on a holder: a flat floor, scaled up toward a small
    fraction of the victim's max HP so it stays relevant as HP grows."""
    return max(info["dmg"], round(getattr(holder, "max_hp", 0) * info.get("pct", 0.0)))


def apply_status(state: GameState, kind: str, turns: int = 0, target=None) -> None:
    """Lay a damage-over-time on a holder (the player by default, or a mob when
    ``target`` is given). Refreshing, never stacking beyond its full duration."""
    if kind not in STATUS:
        return
    holder = state.player if target is None else target
    dur = turns or STATUS[kind]["turns"]
    if target is None and state.player.sign == "serpent":
        dur = max(1, dur - 1)            # born in the dry heat: afflictions pass sooner
    holder.status[kind] = max(holder.status.get(kind, 0), dur)


def _tick_status(holder) -> list:
    """One turn of every DoT on a holder: each bites, then counts down. Returns
    the list of (kind, info) that expired this turn (for the caller to log)."""
    st = getattr(holder, "status", None)
    if not st:
        return []
    expired = []
    for kind in list(st.keys()):
        info = STATUS.get(kind)
        if info is None:
            del st[kind]
            continue
        holder.hp -= _status_damage(holder, info)
        stam = info.get("stam", 0)                       # illness also drags at stamina (player only)
        if stam and getattr(holder, "max_energy", None) is not None:
            holder.energy = max(0, holder.energy - stam)
        st[kind] -= 1
        if st[kind] <= 0:
            del st[kind]
            expired.append((kind, info))
    return expired


def tick_player_status(state: GameState) -> None:
    """Tick the player's DoTs. Damage shows in the HP bar and status pips; only
    the onset and the end are logged, so it doesn't spam. Called each action from
    turns.advance_time."""
    for _kind, info in _tick_status(state.player):
        state.log.add(info["off"], C.DIM)


def weapon_inflict(state: GameState) -> str:
    """A status the held weapon leaves on a struck foe: a ruby-set blade burns,
    and so does any weapon while a Firebrand Elixir is in the blood. (Melee only —
    a burning blade, not a burning arrow.) Returns "" for none."""
    from . import skills
    if skills.active_buff(state) == "firebrand":
        return "burn"
    gems = getattr(state.player.active_tool, "gems", ())
    return "burn" if "ruby" in gems else ""


def mob_at(state: GameState, x: int, y: int):
    for m in state.world.monsters:
        if m.alive and m.x == x and m.y == y:
            # a critter that's out of season isn't really here
            if m.seasons and state.season not in m.seasons:
                continue
            return m
    return None


# --- kills --------------------------------------------------------------------
def _on_kill(state: GameState, m, award_combat: bool = True) -> None:
    """Resolve a slain mob: removal, karma/XP, kill-count, and drops.

    Shared by the sword (``player_attack``) and the bomb (``throw_bomb``) so
    both obey the same rules. Peaceful surface wildlife costs karma and yields
    no XP or loot; a dungeon monster gains Combat XP, bumps the slain count and
    rolls its reagent drops.
    """
    from . import skills
    p = state.player
    state.world.monsters = [x for x in state.world.monsters if x is not m]
    if getattr(m, "kind", "monster") == "wildlife":
        if not getattr(m, "hostile", False):
            from . import karma
            karma.adjust(state, -2)  # slaying a peaceful creature is unkind
        state.log.add(f"You put down the {m.name.lower()}.", (200, 180, 150))
        drops = content.wildlife_drops(m.name, random)
        for drop, qty in drops:
            p.inventory.add(drop, qty)
        if drops:
            got = ", ".join(f"{q} {d.name.lower()}" if q > 1 else d.name.lower()
                            for d, q in drops)
            state.log.add(f"  You take {got}.", (200, 180, 150))
    else:
        state.bump("monsters_slain")
        if award_combat:
            # Depth pays: a deep, tough kill is worth far more than a floor-1 slime,
            # and a boss is a windfall — so fighting downward actually levels Combat.
            lvl = getattr(m, "level", 1)
            xp = 12 + 6 * lvl + (60 if getattr(m, "boss", False) else 0)
            from . import collection                  # Hall of Wonders — completed Reliquary
            if collection.perk_earned(state, "Reliquary"):
                xp = round(xp * 1.2)
            skills.gain(state, "Combat", xp)
        state.log.add(f"You strike down the {m.name.lower()}!", (200, 220, 160))
        # drops & bestiary key on the structured base the spawn recorded, so an
        # elite's affix prefix ("Dire Boar") never has to be parsed back out
        base = getattr(m, "base", "") or m.name
        state.bestiary[base] = state.bestiary.get(base, 0) + 1   # kill record for the codex
        for drop in content.monster_drops(base, random, getattr(m, "level", 1)):
            p.inventory.add(drop, 1)
            state.log.add(f"  It drops {drop.name.lower()}.", C.DIM)


# --- combat stats (ADOM-style: to-hit vs DV, then damage - PV) ---------------
BASE_DV = 8              # a bare, unskilled defender's Defensive Value


def held_profile(state: GameState):
    """The combat profile of whatever the player is holding (a tool fights, but
    badly; a real weapon fights well; bare hands / seed pouch = unarmed)."""
    return content.profile_of(state.player.active_tool)


def _worn(state: GameState):
    p = state.player
    two_handed = content.is_two_handed(p.active_tool)   # both hands full — no shield
    dv = pv = 0
    for slot, it in p.equipment.items():
        if slot == "shield" and two_handed:
            continue
        stats = content.ARMOR_STATS.get(it)
        if stats:
            dv += stats[0]
            pv += stats[1]
    return dv, pv


def player_dv(state: GameState) -> int:
    from . import skills, jewelry
    prof = held_profile(state)
    wdv, _ = _worn(state)
    lvl = skills.mastery_level(state, prof.category)
    # Combat lends only half its level to Dodge (it also feeds to-hit & crit);
    # letting it add its full level here made a trained player near-unhittable.
    from . import attrs
    return (BASE_DV + skills.skill_level(state, "Combat") // 2   # Dodge
            + prof.dv + wdv + skills.mastery_parry(lvl)
            + round(jewelry.combat_bonus(state)["dv"])
            + attrs.mod(state, "Dx") // 3                           # born nimble
            + (3 if skills.active_buff(state) == "swift" else 0))   # Swiftness Tonic


def player_pv(state: GameState) -> int:
    from . import jewelry, skills
    return (_worn(state)[1] + round(jewelry.combat_bonus(state)["pv"])
            + (3 if skills.active_buff(state) == "stoneskin" else 0))   # Stoneskin Draught


def player_to_hit(state: GameState) -> int:
    from . import skills, jewelry
    prof = held_profile(state)
    lvl = skills.mastery_level(state, prof.category)
    bonus = prof.to_hit + skills.skill_level(state, "Combat") // 2 + skills.mastery_to_hit(lvl)
    bonus += round(jewelry.combat_bonus(state)["to_hit"])
    buff = skills.active_buff(state)
    if buff == "hearty":
        bonus += 2
    elif buff == "clarity":
        bonus += 2                       # Clarity Draught: keener aim
    if state.player.sign == "wolf":      # born with winter in the blood
        bonus += 1
    return bonus


def player_crit(state: GameState) -> float:
    from . import skills, jewelry
    lvl = skills.mastery_level(state, held_profile(state).category)
    return (0.03 + skills.skill_level(state, "Combat") * 0.01 + skills.mastery_crit(lvl)
            + jewelry.combat_bonus(state)["crit"]
            + (0.10 if skills.active_buff(state) == "clarity" else 0.0))   # Clarity Draught


def _resolve(to_hit: int, dmg_range, dmg_bonus: int, crit_chance: float,
             target_dv: int, target_pv: int, min_dmg: int = 1):
    """One attack. Returns (damage, crit) if it lands, or None on a miss. A crit
    doubles the damage and ignores Protection.

    Protection soaks at most ~2/3 of any single blow, so at least a third always
    lands — heavy armour is a huge advantage but never total immunity (a fully
    plated hero still takes real chip damage from a deep monster), and a stoutly
    armoured foe is slow to fell but never invulnerable to a weak weapon. ``min_dmg``
    floors a landed hit at 1 by default."""
    if random.randint(1, 20) + to_hit < target_dv:
        return None
    dmg = random.randint(dmg_range[0], dmg_range[1]) + dmg_bonus
    if random.random() < crit_chance:
        return dmg * 2, True
    soak = min(target_pv, dmg * 2 // 3)
    return max(min_dmg, dmg - soak), False


# --- player attacks ----------------------------------------------------------
def player_attack(state: GameState, m) -> None:
    from . import skills, jewelry
    p = state.player
    prof = held_profile(state)
    # deep-floor fatigue: fighting in the airless dark costs more the further down
    p.energy = max(0, p.energy - C.ATTACK_COST[0] - state.world.depth // 3)
    from . import attrs
    dmg_bonus = skills.mastery_dmg(skills.mastery_level(state, prof.category))
    dmg_bonus += round(jewelry.combat_bonus(state)["dmg"]) + attrs.mod(state, "St") // 3
    res = _resolve(player_to_hit(state), prof.dmg, dmg_bonus, player_crit(state), m.dv, m.pv, min_dmg=1)
    wild = getattr(m, "kind", "monster") == "wildlife"

    if res is None:
        state.log.add(f"You swing at the {m.name.lower()} and miss.", C.DIM)
        if wild and m.behavior == "defensive":
            m.hostile = True
        m.awake = True
        return

    dmg, crit = res
    skills.gain_mastery(state, prof.category, 3)     # learn by doing
    m.awake = True
    if wild and m.behavior == "defensive":
        m.hostile = True
    m.hp -= dmg
    if m.hp <= 0:
        _on_kill(state, m)
        return
    kind = weapon_inflict(state)                 # a ruby-set blade sets foes alight
    if kind and kind not in m.status and random.random() < STATUS[kind]["chance"]:
        apply_status(state, kind, target=m)
        state.log.add(f"Your blade sears the {m.name.lower()} — it catches fire!",
                      STATUS[kind]["color"])
    if wild and not m.hostile:
        state.log.add(f"You hit the {m.name.lower()} for {dmg} — it bolts!", C.DIM)
    else:
        lead = "A critical hit! " if crit else ""
        state.log.add(f"{lead}You hit the {m.name.lower()} for {dmg}.",
                      (240, 220, 140) if crit else C.WHITE)
        if not wild:
            skills.gain(state, "Combat", 4)


# --- monster turns -----------------------------------------------------------
def monsters_act(state: GameState) -> None:
    w = state.world
    if not w.is_dungeon or not w.monsters:
        return
    from . import delve
    delve.update_fov(state)                     # act on an up-to-date FOV
    p = state.player
    for m in list(w.monsters):
        if not m.alive:
            continue
        if m.status:                             # poison/bleed/burn gnaws each turn
            expired = _tick_status(m)
            if not m.alive:
                if w.visible is not None and w.visible[m.x, m.y]:
                    state.log.add(f"The {m.name.lower()} succumbs to its wounds.", C.DIM)
                _on_kill(state, m)
                continue
            if expired and w.visible is not None and w.visible[m.x, m.y]:
                state.log.add(f"The {m.name.lower()}'s wounds close.", C.DIM)
        if not m.awake and w.visible is not None and w.visible[m.x, m.y]:
            m.awake = True
        if not m.awake:
            continue
        m.energy += m.speed
        while m.energy >= 2 and m.alive and p.hp > 0:
            m.energy -= 2
            _step(state, m)
    w.monsters = [m for m in w.monsters if m.alive]


def _can_move(state: GameState, m, dx: int, dy: int) -> bool:
    nx, ny = m.x + dx, m.y + dy
    p = state.player
    if not state.world.walkable(nx, ny) or (nx, ny) == (p.x, p.y):
        return False
    return mob_at(state, nx, ny) is None


def _dist(m, p) -> int:
    return max(abs(m.x - p.x), abs(m.y - p.y))


def _move_toward(state: GameState, m, away: bool = False) -> bool:
    p = state.player
    sx = _sign(p.x - m.x) * (-1 if away else 1)
    sy = _sign(p.y - m.y) * (-1 if away else 1)
    for ax, ay in ((sx, sy), (sx, 0), (0, sy)):
        if (ax or ay) and _can_move(state, m, ax, ay):
            m.x += ax
            m.y += ay
            return True
    return False


def _step(state: GameState, m) -> None:
    p = state.player
    if _dist(m, p) == 1:
        _attack_player(state, m)
        return
    # summoners raise the lesser dead while they hold ground, then close in
    if m.behavior == "summon":
        _try_summon(state, m)
    # ranged attackers fire from afar and kite to keep their distance
    reach = getattr(m, "reach", 0)
    if reach and _dist(m, p) <= reach:
        _ranged_attack(state, m)
        if _dist(m, p) <= 2:                 # too close for comfort — give ground
            _move_toward(state, m, away=True)
        return
    # bats flit erratically; wounded ones flee
    if m.behavior == "erratic" and random.random() < 0.45:
        dirs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        random.shuffle(dirs)
        for dx, dy in dirs:
            if _can_move(state, m, dx, dy):
                m.x += dx
                m.y += dy
                return
        return
    fleeing = m.behavior == "erratic" and m.hp <= m.max_hp * 0.35
    # a "charge" monster lunges — an extra stride when closing from nearby, so
    # it covers ground and reaches you fast once roused.
    strides = 2 if (m.behavior == "charge" and not fleeing and 2 <= _dist(m, p) <= 4) else 1
    for _ in range(strides):
        if _dist(m, p) == 1:
            _attack_player(state, m)
            return
        if not _move_toward(state, m, away=fleeing):
            return


def _attack_player(state: GameState, m) -> None:
    lo, hi = m.dmg
    res = _resolve(m.to_hit, m.dmg, 0, 0.0, player_dv(state), player_pv(state))
    if res is None:
        state.log.add(f"The {m.name.lower()} lunges — you dodge.", C.DIM)
        return
    dmg, _crit = res
    state.player.hp -= dmg
    # If armour turned most of the blow aside, say so — but it still stings.
    if dmg <= max(1, hi // 3) and player_pv(state) > 0:
        state.log.add(f"The {m.name.lower()} strikes — your armour holds, but it still bites for {dmg}.",
                      (210, 170, 140))
    else:
        state.log.add(f"The {m.name.lower()} hits you for {dmg}!", (224, 140, 120))
    _maybe_inflict(state, m)


def _maybe_inflict(state: GameState, m) -> None:
    """Roll a mob's on-hit status (poison/bleed/burn/sick), tempered by an herbal
    ward and the player's Willpower. Shared by melee and ranged attacks."""
    inflicts = getattr(m, "inflicts", "")
    if inflicts in STATUS and inflicts not in state.player.status:
        from . import skills, attrs
        chance = STATUS[inflicts]["chance"]
        if skills.active_buff(state) == "warded":     # herbal ward turns most aside
            chance *= 0.4
        chance *= max(0.2, 1.0 - 0.03 * attrs.mod(state, "Wi"))   # iron will resists
        if random.random() < chance:
            apply_status(state, inflicts)
            state.log.add(STATUS[inflicts]["on"], STATUS[inflicts]["color"])


def _ranged_attack(state: GameState, m) -> None:
    """A ranged mob strikes from a distance — the same to-hit vs DV and damage
    minus PV as a melee blow, but it can be answered only by closing or shooting
    back."""
    res = _resolve(m.to_hit, m.dmg, 0, 0.0, player_dv(state), player_pv(state))
    if res is None:
        state.log.add(f"The {m.name.lower()} looses at you — it goes wide.", C.DIM)
        return
    dmg, _crit = res
    state.player.hp -= dmg
    state.log.add(f"The {m.name.lower()} strikes you from afar for {dmg}!", (224, 150, 130))
    _maybe_inflict(state, m)


def _try_summon(state: GameState, m) -> None:
    """A summoner raises a fresh minion (its ``summons`` template, at that mob's
    own baseline so it's fodder, not a floor-native) on a cooldown, capped so a
    floor never floods."""
    w = state.world
    cd = getattr(m, "summon_cd", 0)
    if cd > 0:
        m.summon_cd = cd - 1
        return
    if sum(1 for o in w.monsters if o.alive) >= 8:
        return
    tmpl = next((t for t in content.MONSTERS if t.name == (m.summons or "Cave Slime")), None)
    if tmpl is None:
        return
    spots = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    random.shuffle(spots)
    for dx, dy in spots:
        if _can_move(state, m, dx, dy):
            minion = content.make_mob(tmpl, m.x + dx, m.y + dy, max(1, tmpl.min_depth), random)
            minion.awake = True
            w.monsters.append(minion)
            m.summon_cd = 5
            if w.visible is not None and w.visible[m.x, m.y]:
                state.log.add(f"The {m.name.lower()} calls up a {minion.name.lower()}!",
                              (200, 170, 210))
            return


# --- the Bomb ability --------------------------------------------------------
BOMB_DAMAGE = 8
BOMB_RANGE = 5                     # how far a bomb can be lobbed
_BREAKABLE = {"rock", "ore_vein", "gem_vein", "ruins_wall",
              "sulphur_deposit", "nitre_deposit"}

# What each bomb kind does: (blast radius in tiles, damage). The gunpowder
# charge is the delver's answer to deep rock — a wide blast that cracks veins
# no matter what pickaxe you carry.
BOMB_STATS = {items.BOMB: (1, 8), items.BLAST_CHARGE: (2, 16)}


def _carried_bomb(state: GameState):
    """The bomb a throw will spend: the one readied in the ammo slot if it's a
    bomb and still carried (so readying cheap bombs saves your charges),
    otherwise the plain bomb first, then a blast charge."""
    p = state.player
    ready = p.equipment.get("ammo")
    if ready is not None and ready.kind == "bomb" and p.inventory.count(ready) > 0:
        return ready
    for b in (items.BOMB, items.BLAST_CHARGE, items.FIRECRACKER):
        if p.inventory.count(b) > 0:
            return b
    return None


def _line(x0: int, y0: int, x1: int, y1: int):
    """Bresenham cells from (x0,y0) to (x1,y1), excluding the start."""
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx - dy
    x, y = x0, y0
    while (x, y) != (x1, y1):
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
        pts.append((x, y))
    return pts


def projectile_landing(state: GameState, tx: int, ty: int, rng: int) -> tuple[int, int]:
    """Where a projectile aimed at (tx, ty) actually lands: it flies along the
    line from the player, stopping at the first wall (thunking short), a mob it
    strikes, the aimed tile, or its maximum range."""
    p = state.player
    bx, by = p.x, p.y
    for nx, ny in _line(p.x, p.y, tx, ty):
        if (max(abs(nx - p.x), abs(ny - p.y)) > rng
                or not state.world.in_bounds(nx, ny)
                or not state.world.walkable(nx, ny)):
            break                               # can't fly past a wall / its range
        bx, by = nx, ny
        if mob_at(state, nx, ny) or (nx, ny) == (tx, ty):
            break
    return bx, by


def bomb_landing(state: GameState, tx: int, ty: int) -> tuple[int, int]:
    return projectile_landing(state, tx, ty, BOMB_RANGE)


def in_range(state: GameState, tx: int, ty: int, rng: int) -> bool:
    return max(abs(tx - state.player.x), abs(ty - state.player.y)) <= rng


def in_bomb_range(state: GameState, tx: int, ty: int) -> bool:
    return in_range(state, tx, ty, BOMB_RANGE)


def _detonate(state: GameState, bx: int, by: int, radius: int = 1,
              dmg: int = BOMB_DAMAGE) -> None:
    """Resolve the blast at (bx, by): damage mobs, shatter rock/ore/gems."""
    hit = []
    for x in range(bx - radius, bx + radius + 1):
        for y in range(by - radius, by + radius + 1):
            if not state.world.in_bounds(x, y):
                continue
            m = mob_at(state, x, y)
            if m:
                m.awake = True                  # the blast rouses survivors
                m.hp -= dmg
                hit.append(m)
            t = state.world.tile_at(x, y)
            if t.name in _BREAKABLE:
                _shatter(state, x, y, t)
    for m in hit:                               # snapshot: _on_kill mutates the list
        if not m.alive:
            _on_kill(state, m)


def throw_bomb_at(state: GameState, tx: int, ty: int) -> bool:
    """Lob a bomb at an aimed tile (see targeting mode). Returns True if thrown."""
    p = state.player
    bomb = _carried_bomb(state)
    if bomb is None:
        state.log.add("You have no bombs. (craft one: 1 Coal + 2 Fiber)", C.DIM)
        return False
    if p.energy < C.BOMB_COST[0]:
        state.log.add("You're too winded to throw.", C.DIM)
        return False
    if (tx, ty) == (p.x, p.y):
        state.log.add("Best not drop it at your own feet — aim away.", C.DIM)
        return False
    bx, by = bomb_landing(state, tx, ty)
    p.inventory.remove(bomb, 1)
    p.energy = max(0, p.energy - C.BOMB_COST[0])
    if bomb is items.FIRECRACKER:                # a bang, not a blast
        _crack(state, bx, by)
    else:
        radius, dmg = BOMB_STATS.get(bomb, (1, BOMB_DAMAGE))
        state.log.add("You set a blast charge flying — a THUNDERCLAP rolls through the rock!"
                      if bomb is items.BLAST_CHARGE else "You hurl a bomb — BOOM!",
                      (236, 180, 90))
        _detonate(state, bx, by, radius, dmg)
    from . import turns
    turns.advance_time(state, C.BOMB_COST[1])
    return True


def _crack(state: GameState, bx: int, by: int) -> None:
    """A firecracker: no blast, all noise. On the surface it sends every wild
    critter nearby bolting and keeps raiders off your land for days; in the
    dark it just tells everything exactly where you are."""
    if state.world.is_dungeon:
        roused = 0
        for m in state.world.monsters:
            if max(abs(m.x - bx), abs(m.y - by)) <= 12 and not m.awake:
                m.awake = True
                roused += 1
        state.log.add("CRACK-BANG! The report rolls through the dark"
                      + (f" — {roused} things stir." if roused else "."), (236, 180, 90))
        return
    fled = 0
    for m in list(state.world.monsters):
        if getattr(m, "kind", "") == "wildlife" and max(abs(m.x - bx), abs(m.y - by)) <= 12:
            state.world.monsters.remove(m)
            fled += 1
    state.stats["wildlife_calm_until"] = state.day + 3
    state.log.add("CRACK-BANG! " + (f"{fled} critter{'s' if fled != 1 else ''} bolt for "
                  "the treeline — " if fled else "")
                  + "the wildlife will keep clear of your fields a few days.", (236, 180, 90))


def throw_bomb(state: GameState) -> bool:
    """Lob straight ahead (kept for convenience / callers without a target)."""
    fx, fy = state.player.facing
    return throw_bomb_at(state, state.player.x + fx * BOMB_RANGE, state.player.y + fy * BOMB_RANGE)


# --- ranged weapons (bows & sling) -------------------------------------------
def equipped_ranged(state: GameState):
    """The (weapon, stat) in the ranged slot whose ammo you actually carry, or
    None — so a bow with an empty quiver falls back to hand-thrown bombs. Any
    arrow (plain or metal-tipped) feeds a bow; the shot spends your best one."""
    it = state.player.equipment.get("ranged")
    stat = content.ranged_stat(it) if it else None
    if stat is None:
        return None
    if content.best_ammo(state.player.inventory, content.ammo_family(stat)) is None:
        return None
    return it, stat


def can_shoot(state: GameState) -> bool:
    """True if a loaded ranged weapon (bow/sling + matching ammo) is readied."""
    return equipped_ranged(state) is not None


def can_throw(state: GameState) -> bool:
    """True if the player is carrying at least one bomb to lob."""
    return _carried_bomb(state) is not None


def can_fire(state: GameState) -> bool:
    """True if the player can loose a shot (bow+ammo) or throw a bomb."""
    return can_shoot(state) or can_throw(state)


def chosen_ammo(state: GameState, stat):
    """The ammo a shot will actually spend: the ammo you've readied in the ammo
    slot if it fits this launcher and you still carry it (so readying plain arrows
    really does save your finer ones), otherwise your best matching ammo."""
    p = state.player
    fam = content.ammo_family(stat)
    picked = p.equipment.get("ammo")
    pst = content.ammo_stat(picked) if picked else None
    if pst is not None and pst.family == fam and p.inventory.count(picked) >= 1:
        return picked
    return content.best_ammo(p.inventory, fam)


def aim_purpose(state: GameState) -> str:
    """The aim mode's opening intent: "shoot" if a loaded ranged weapon is readied,
    else "throw" (bombs). In aim mode the player can toggle between the two (if they
    carry both) so a readied bow never locks bombs away — see main's target mode."""
    return "shoot" if equipped_ranged(state) is not None else "throw"


def aim_range(state: GameState) -> int:
    ready = equipped_ranged(state)
    return ready[1].rng if ready else BOMB_RANGE


def aim_start(state: GameState) -> tuple[int, int]:
    """Where the reticle opens: back onto the last monster you fired at, if it
    survived and is still in range; otherwise the tile you're facing."""
    p = state.player
    m = state.aim_target
    if (m is not None and getattr(m, "alive", False)
            and any(x is m for x in state.world.monsters)
            and in_range(state, m.x, m.y, aim_range(state))):
        return m.x, m.y
    state.aim_target = None
    return p.x + p.facing[0], p.y + p.facing[1]


def _ranged_to_hit(state: GameState, stat) -> int:
    from . import skills, attrs
    lvl = skills.mastery_level(state, stat.category)
    bonus = (stat.to_hit + skills.skill_level(state, "Combat") // 2
             + skills.mastery_to_hit(lvl) + attrs.mod(state, "Dx") // 3)
    if skills.active_buff(state) == "hearty":
        bonus += 2
    return bonus


def fire_ranged_at(state: GameState, tx: int, ty: int) -> bool:
    """Loose the readied ranged weapon at an aimed tile: the shot flies to the
    first foe (or wall) in its path and strikes that one target."""
    from . import skills
    p = state.player
    ready = equipped_ranged(state)
    if ready is None:                          # quiver ran dry between aim & loose
        state.log.add("You've nothing to shoot.", C.DIM)
        return False
    weapon, stat = ready
    if p.energy < C.ATTACK_COST[0]:
        state.log.add("You're too winded to draw.", C.DIM)
        return False
    if (tx, ty) == (p.x, p.y):
        state.log.add("Aim away from yourself.", C.DIM)
        return False

    ammo = chosen_ammo(state, stat)
    astat = content.ammo_stat(ammo)
    p.inventory.remove(ammo, 1)
    p.energy = max(0, p.energy - C.ATTACK_COST[0] - state.world.depth // 3)

    # Resolve the shot against the world as it stands *now* — like a melee blow —
    # and only then let the world take its turn. (Advancing time first let erratic
    # movers step off the aimed tile before the arrow "landed", so shots at exactly
    # the foes bows are for flew wide with no to-hit roll and silently ate ammo.)
    _resolve_shot(state, stat, ammo, astat, tx, ty)
    from . import turns
    turns.advance_time(state, C.ATTACK_COST[1])
    return True


def _resolve_shot(state: GameState, stat, ammo, astat, tx: int, ty: int) -> None:
    """Fly the loosed shot to the first foe/wall in its path and strike it."""
    from . import skills
    lx, ly = projectile_landing(state, tx, ty, stat.rng)
    m = mob_at(state, lx, ly)
    if m is None:
        state.log.add(f"Your {ammo.name.lower()} flies wide and clatters down.", C.DIM)
        return
    state.aim_target = m                       # re-aim onto this foe next time (until it dies)

    dmg_bonus = skills.mastery_dmg(skills.mastery_level(state, stat.category)) + astat.dmg
    crit = 0.03 + skills.skill_level(state, "Combat") * 0.01 + skills.mastery_crit(
        skills.mastery_level(state, stat.category))
    res = _resolve(_ranged_to_hit(state, stat) + astat.to_hit, stat.dmg, dmg_bonus, crit,
                   m.dv, m.pv, min_dmg=1)
    wild = getattr(m, "kind", "monster") == "wildlife"
    m.awake = True
    if wild and m.behavior == "defensive":
        m.hostile = True

    if res is None:
        state.log.add(f"Your shot streaks past the {m.name.lower()}.", C.DIM)
        return
    dmg, was_crit = res
    skills.gain_mastery(state, stat.category, 3)
    m.hp -= dmg
    if m.hp <= 0:
        _on_kill(state, m)
        return
    kind = getattr(astat, "inflicts", "")        # a fire/venom-tipped arrow
    if kind in STATUS and kind not in m.status and random.random() < STATUS[kind]["chance"]:
        apply_status(state, kind, target=m)
        verb = {"burn": "bursts into flame", "poison": "is envenomed",
                "bleed": "is torn open"}.get(kind, "is afflicted")
        state.log.add(f"The {m.name.lower()} {verb}!", STATUS[kind]["color"])
    if wild and not m.hostile:
        state.log.add(f"You hit the {m.name.lower()} for {dmg} — it bolts!", C.DIM)
    else:
        lead = "A critical shot! " if was_crit else ""
        state.log.add(f"{lead}You shoot the {m.name.lower()} for {dmg}.",
                      (240, 220, 140) if was_crit else C.WHITE)
        if not wild:
            skills.gain(state, "Combat", 4)


def _shatter(state: GameState, x: int, y: int, t) -> None:
    """A bomb breaks rock/ore/gem, dropping materials."""
    inv = state.player.inventory
    if t.name == "gem_vein":
        inv.add(content.random_gem(random), 1)
    elif t.name == "ore_vein":
        inv.add(content.ore_for_depth(state.world.depth, random), 1)
        if random.random() < 0.5:
            inv.add(items.COAL, 1)
    elif t.name == "sulphur_deposit":
        inv.add(items.SULPHUR, 1)
    elif t.name == "nitre_deposit":
        inv.add(items.SALTPETER, 1)
    elif t.name in ("rock", "ruins_wall"):
        inv.add(items.STONE, 1)
    floor = (getattr(state.world, "floor_tile", 0) or tile.DUNGEON_FLOOR) \
        if state.world.is_dungeon else tile.GRASS
    state.world.tiles[x, y] = floor
