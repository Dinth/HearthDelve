"""Modal & menu overlays — every full-screen panel the screen stack draws.

Split out of engine/rendering.py, which keeps the world viewport, HUD and the
per-frame world overlays (look/aim/fishing). These are the ui.Modal-based
menus: inventory, equipment, shops, the journal, dialogue, character sheet and
the rest. rendering.py re-exports them, so callers still say rendering.render_X.
"""
from __future__ import annotations

import numpy as np
import tcod.console

from . import constants as C
from . import ui
from ..data import content
from ..game.state import GameState

_HDR = ui.HDR
_KEY = (150, 200, 230)


def render_message_log(con: tcod.console.Console, state: GameState, scroll: int) -> None:
    """Full scrollback of the message log (newest at the bottom)."""
    msgs = state.log.messages
    w, h = 72, C.SCREEN_H - 6
    body = h - 4
    m = ui.Modal(con, w, h, "Message Log")
    total = len(msgs)
    max_scroll = max(0, total - body)
    scroll = max(0, min(scroll, max_scroll))
    start = max(0, total - body - scroll)
    for i, (text, color) in enumerate(msgs[start:start + body]):
        m.text(2, 2 + i, text[:w - 4], fg=color)
    m.arrows(scroll < max_scroll, scroll > 0, 2, h - 3)
    m.footer("↑↓ scroll · Esc close")


def render_mail(con: tcod.console.Console, state: GameState, sel: int) -> None:
    mail = state.mail
    body = mail[min(sel, len(mail) - 1)]["body"].split("\n") if mail else []
    w = 60
    list_h = min(10, max(1, len(mail)))          # cap the letter list; it scrolls
    h = list_h + len(body) + 8
    m = ui.Modal(con, w, h, "Post Box")
    if not mail:
        m.text(2, 2, "The post box is empty.", fg=C.DIM)

    def row(i, dy, selected, bg):
        letter = mail[i]
        tag = " ⚖ tax due" if letter.get("tax") else " ✉+gift" if letter.get("items") else " ✉"
        m.text(2, dy, ui.cur(selected) + f"From {letter['sender']}{tag}", fg=C.WHITE, bg=bg)

    m.list(2, list_h, len(mail), sel, row, arrow_top=2, arrow_bottom=1 + list_h)
    for j, bl in enumerate(body):                # the open letter's text below the list
        m.text(3, 3 + list_h + j, bl[:w - 6], fg=(210, 205, 190))
    m.footer("↑↓ select   Enter settle tax / take letter   Esc close"
             if any(le.get("tax") for le in mail)
             else "↑↓ select   Enter take letter   Esc close")


def render_requests(con: tcod.console.Console, state: GameState, sel: int,
                    village: str = "") -> None:
    """The village notice board: pinned favours, who wants what, and the pay —
    plus this village's restoration project, if one is open or rising."""
    from ..game import requests as gamereq, projects as gameproj
    from ..data import content
    from ..entities import items as I
    reqs = state.requests
    proj = gameproj.for_village(state, village) if village else None
    if proj is not None and proj["state"] == "done":
        proj = None
    w = 66
    h = max(9, len(reqs) * 3 + (5 if proj else 0) + 6)
    h = min(C.SCREEN_H - 4, h)
    m = ui.Modal(con, w, h, f"{village + ' ' if village else ''}Notice Board")
    if not reqs and not proj:
        m.text(2, 2, "The board is bare today — favours come and go.", fg=C.DIM)
    n_rows = len(reqs) + (1 if proj else 0)
    sel = max(0, min(sel, n_rows - 1)) if n_rows else 0
    row = 0
    for i, r in enumerate(reqs):
        it = I.by_name(r["item"])
        have = state.player.inventory.count(it) if it else 0
        can = gamereq.can_fulfil(state, r)
        bg = ui.SEL_BG if i == sel else ui.BASE_BG
        if i == sel:
            m.highlight(2 + row)
        days = r["expires"] - state.day
        m.text(2, 2 + row, ui.cur(i == sel) + f"{r['npc']}: {r['qty']} {r['item']}",
               fg=C.WHITE if can else C.DIM, bg=bg)
        m.text(w - 20, 2 + row, f"have {have:>2}",
               fg=(150, 210, 150) if can else (150, 110, 110), bg=bg)
        m.text(w - 10, 2 + row, f"{r['gold']}g", fg=C.GOLD_COLOR, bg=bg)
        row += 1
        m.text(4, 2 + row, f"\"{r['flavor']}\""[:w - 20], fg=C.DIM)
        m.text(w - 16, 2 + row, f"{days} day{'s' if days != 1 else ''} left",
               fg=(160, 150, 130))
        row += 2
    if proj is not None:
        d = content.PROJECTS[proj["id"]]
        i = len(reqs)
        m.text(2, 2 + row, f"── Village project: {d.name} "
               + "─" * max(0, w - 26 - len(d.name)), fg=_HDR)
        row += 1
        bg = ui.SEL_BG if i == sel else ui.BASE_BG
        if i == sel:
            m.highlight(2 + row)
        if proj["state"] == "building":
            mins = proj.get("ready_at", 0) - state.abs_minutes
            days = max(1, round(mins / 1440))
            m.text(2, 2 + row, ui.cur(i == sel)
                   + f"Beams are rising — finished in ~{days} day{'s' if days != 1 else ''}.",
                   fg=(200, 220, 160), bg=bg)
        else:
            gold_left, mats_left = gameproj.remaining(state, proj)
            need = " · ".join([f"{q} {it.name}" for it, q in mats_left[:3]]
                              + ([f"{gold_left}g"] if gold_left else []))
            m.text(2, 2 + row, ui.cur(i == sel)
                   + f"Contribute — needs {need}"[:w - 4], fg=C.WHITE, bg=bg)
        row += 1
        m.text(4, 2 + row, d.perk[:w - 8], fg=(232, 200, 120))
        row += 1
    m.footer(("↑↓ · Enter deliver/give (500g) · Space all-in gold · Esc" if proj
              else "↑↓ select   Enter deliver   Esc close")[:w - 4])


def render_eat(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..game import skills
    from ..game.crafting import edible_items
    foods = edible_items(state)
    w, h = 50, min(C.SCREEN_H - 4, max(8, len(foods) + 6))
    body = h - 4
    m = ui.Modal(con, w, h, "Eat  (restores stamina & health)")
    if not foods:
        m.text(2, 2, "Nothing to eat — cook a dish (c) or gather eggs/milk.", fg=C.DIM)

    def row(i, dy, selected, bg):
        it, q, ql = foods[i]
        star = (" " + skills.stars(ql)) if ql else ""
        gain = round(it.energy * (1 + 0.12 * ql))
        hp = (max(1, gain // 6) if it.energy else 0) + it.heal
        # Show the boon up front, so a Hearty meal can be chosen on purpose.
        buff = f" ↯{skills.BUFFS[it.buff]}" if it.buff in skills.BUFFS else ""
        m.text(2, dy, ui.cur(selected) + f"{q:>2} {it.name}{star}{buff}"[:w - 22],
               fg=C.WHITE, bg=bg)
        m.text(w - 18, dy, f"+{gain} st  +{hp} hp", fg=(150, 210, 150), bg=bg)

    m.list(2, body, len(foods), sel, row, arrow_top=2, arrow_bottom=h - 3)
    m.footer("↑↓ select   Enter eat   Esc close")


def render_load_machine(con: tcod.console.Console, state: GameState, ctx) -> None:
    """Choose-what-to-make menu for an empty machine (jam vs pickles, which bar…).

    A chooser whose options carry a ``group`` is shown two-step: first the group
    names, then that group's options — so a hundred metal×base forge rows collapse
    to a short list you pick your way into, rather than one endless scroll."""
    if not ctx:
        return
    from ..game import crafting
    rows, is_group = crafting.load_rows(ctx)
    sel, name = ctx["sel"], ctx["name"]
    w, h = 66, min(C.SCREEN_H - 4, max(8, len(rows) + 6))
    body = h - 4
    group = ctx.get("group")
    title = (f"Load {name} — {group}" if group else f"Load {name}  (choose what to make)")
    m = ui.Modal(con, w, h, title)
    from_col = 30                # inputs column — clear of the (wider) label column
    price_col = w - 9

    if is_group:
        counts = {}
        for o in ctx["options"]:
            counts[o["group"]] = counts.get(o["group"], 0) + 1

        def row(i, dy, selected, bg):
            gname = rows[i]
            m.text(2, dy, ui.cur(selected) + gname[:from_col - 3], fg=C.WHITE, bg=bg)
            n = counts[gname]
            m.text(from_col, dy, f"{n} option{'s' if n != 1 else ''} →",
                   fg=(160, 180, 205), bg=bg)
        footer = "↑↓ select   Enter open   Esc cancel"
    else:
        def row(i, dy, selected, bg):
            opt = rows[i]
            out = opt["output"]
            ins = ", ".join(f"{q} {it.name}" for it, q in opt["inputs"])
            oq = opt.get("out_qty", 1)
            label = opt.get("label") or (f"{oq}x {out.name}" if oq > 1 else out.name)
            m.text(2, dy, ui.cur(selected) + label[:from_col - 3], fg=C.WHITE, bg=bg)
            m.text(from_col, dy, f"from {ins}"[:price_col - from_col - 1],
                   fg=(160, 180, 205), bg=bg)
            m.text(price_col, dy, f"{out.value}g", fg=C.GOLD_COLOR, bg=bg)
        footer = ("↑↓ select   Enter load   Esc back" if group
                  else "↑↓ select   Enter load   Esc cancel")
    m.list(2, body, len(rows), sel, row, arrow_top=2, arrow_bottom=h - 3)
    m.footer(footer)


def render_cheats(con: tcod.console.Console, state: GameState, sel: int, locations) -> None:
    c = state.cheats
    rows = [f"Freeze Health:  {'ON ' if c.get('freeze_hp') else 'off'}",
            f"Freeze Stamina: {'ON ' if c.get('freeze_stamina') else 'off'}",
            "Add 1000 gold",
            "Add 100 of each building material"]
    rows += [f"Teleport → {name}" for name, _ in locations]
    h = len(rows) + 6
    m = ui.Modal(con, 52, h, "★ Cheats (up up down down ...) ★")
    m.text(2, 1, "The Konami whisper opens a little door.", fg=C.DIM)
    for i, text in enumerate(rows):
        hot = (i == sel)
        m.text(2, 3 + i, ("→ " if hot else "  ") + text,
               fg=(250, 230, 140) if hot else (210, 210, 220))
    m.footer("↑↓ move · Enter select · Esc close")


def render_quit(con: tcod.console.Console, state: GameState) -> None:
    m = ui.Modal(con, 48, 9, "Leave Hollowmere Vale?")
    rows = [
        ("The game auto-saves each morning you sleep.", C.DIM),
        ("", C.WHITE),
        ("[S] / [Enter] / [Q]   Save and quit", (180, 230, 160)),
        ("[Backspace]           Quit without saving", (232, 178, 120)),
        ("[Esc]                 Keep playing", (210, 210, 220)),
    ]
    for i, (text, colour) in enumerate(rows):
        m.text(3, 2 + i, text, fg=colour)


def render_intro(con: tcod.console.Console, state: GameState) -> None:
    """The opening page shown when a new game begins — the premise and the
    handful of controls a new farmer needs before their first morning."""
    gold, key = (236, 226, 180), (150, 200, 230)
    w = min(C.SCREEN_W - 2, 68)
    h = min(C.SCREEN_H - 2, 27)
    m = ui.Modal(con, w, h, "Hearthdelve — Hollowmere Vale")
    y = 2
    letter = [
        "A letter, in a familiar hand:",
        "",
        "  \"The old farm in the Vale is yours now. The fields have gone",
        "   to grass and the tools to rust, but the soil is good and the",
        "   folk are kind. There's iron in the dark below, if you've the",
        "   nerve for it. Make something of the place. — your grandfather\"",
    ]
    for ln in letter:
        m.text(3, y, ln, fg=gold if ln.startswith("A letter") else C.DIM)
        y += 1
    y += 1
    for ln in (
        "By day, work the surface: till and plant, tend your beasts, chop",
        "and forage, and turn the harvest into goods worth trading.",
        "By dark, delve the dungeons below for ore, gems and coin — but",
        "mind the depth; it tires you, and it bites.",
        "Sell and gift it all back to the villages, and grow.",
    ):
        m.text(3, y, ln, fg=C.WHITE)
        y += 1
    y += 1
    m.text(3, y, "The essentials", fg=gold)
    y += 1
    for k, v in (
        ("Arrows / numpad", "move  (numpad 7 9 1 3 step diagonally)"),
        ("Space", "use the held tool on the tile you face"),
        ("g", "gather · harvest · open · interact"),
        ("1–9, 0", "pick a tool or seed     ·   s   sleep, end the day"),
        ("c  ·  b", "craft & build      ·   ship goods to sell"),
        ("l · Shift+C · f", "look · talk & shop · give a gift"),
        ("?", "the codex — full help, any time"),
    ):
        m.text(4, y, k, fg=key)
        m.text(4 + 18, y, v, fg=C.DIM)
        y += 1
    m.footer("Press any key to step onto the farm")


def render_storage(con: tcod.console.Console, state: GameState, side: str, sel: int) -> None:
    """Two columns — your pack on the left, the home chest on the right — with
    the active side's selection marked. Stored goods weigh nothing on your back."""
    from ..game import skills
    pack = state.player.inventory.slots
    store = state.storage.slots
    w = 66
    body = min(C.SCREEN_H - 7, max(6, len(pack), len(store)))
    m = ui.Modal(con, w, body + 5, "Storage Chest")
    colw = (w - 5) // 2
    x_pack, x_store = 2, 3 + colw
    apack = side == "pack"
    m.text(x_pack, 1, "YOUR PACK" + ("  ◂ on your back" if apack else ""),
           fg=ui.HDR if apack else C.DIM)
    m.text(x_store, 1, "CHEST" + ("  ◂ stored, weightless" if not apack else ""),
           fg=ui.HDR if not apack else C.DIM)

    def draw(slots, x0, active):
        if not slots:
            m.text(x0, 3, "(empty)", fg=C.DIM)
            return
        start, end = ui.window(sel, len(slots), body) if active else (0, min(len(slots), body))
        for r, (it, q, ql) in enumerate(slots[start:end]):
            selrow = active and (start + r) == sel
            cnt = f"x{q}" + ((" " + skills.stars(ql)) if ql else "")
            fg = C.WHITE if selrow else ((210, 208, 196) if active else C.DIM)
            m.text(x0, 3 + r, (ui.cur(selrow) if active else "  ") + it.name[:colw - len(cnt) - 3],
                   fg=fg)
            m.text(x0 + colw - len(cnt), 3 + r, cnt, fg=fg)

    draw(pack, x_pack, apack)
    draw(store, x_store, not apack)
    m.footer("↑↓ pick · ←→/Tab switch · Enter move · Space stow all · Esc close")


def render_confirm(con: tcod.console.Console, state: GameState,
                   title: str, prompt: str, detail: str = "") -> None:
    """A small yes/no prompt for an action that can't easily be undone."""
    lines = [prompt] + ([detail] if detail else [])
    w = min(C.SCREEN_W - 4, max(40, max(len(s) for s in lines) + 6))
    m = ui.Modal(con, w, 6 + (1 if detail else 0), title)
    m.text(3, 2, prompt, fg=C.WHITE)
    if detail:
        m.text(3, 3, detail, fg=(232, 200, 120))
    m.text(3, 4 + (1 if detail else 0), "[Y] / [Enter]  yes      [N] / [Esc]  no",
           fg=(180, 230, 160))


# Item categorisation / ordering / filtering is game logic — see game/inventory.py.
# These renderers just draw what it returns.
from ..game import inventory as _inv          # noqa: E402


def _inv_category(item) -> str:
    return _inv.category(item)


# ADOM-flavoured palette for the list screens.
_LETTER_FG = (224, 186, 108)      # item/slot selector letters
_SECTION_FG = (208, 146, 86)      # category / slot names
_BRACKET_FG = (140, 140, 152)     # right-hand [qty]/[tier] column
_CAP_FG = (150, 200, 150)         # the capacity/summary line
_FOOT_FG = (232, 192, 112)        # footer key hints
_INV_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def inv_letter(i: int) -> str:
    return _INV_LETTERS[i] if i < len(_INV_LETTERS) else " "


def _pack_detail(it) -> str:
    """A one-line 'what is this' for the highlighted pack item — the stats that
    matter for its kind, then its flavour. The pack used to show none of this."""
    stats = []
    ws = content.WEAPON_STATS.get(it)
    if ws:
        lo, hi = ws.dmg
        stats.append(f"dmg {lo}-{hi}, hit {ws.to_hit:+d}")
    ar = content.ARMOR_STATS.get(it)
    if ar:
        stats.append(f"DV {ar[0]:+d} PV {ar[1]:+d}")
    if getattr(it, "energy", 0):
        stats.append(f"+{it.energy} stamina")
    if getattr(it, "heal", 0):
        stats.append(f"heals {it.heal}")
    if getattr(it, "buff", ""):
        from ..game import skills
        stats.append(skills.BUFFS.get(it.buff, it.buff))
    stats.append(f"{it.value}g")
    head = " · ".join(stats)
    return f"{head}  —  {it.desc}" if it.desc else head


def render_inventory(con: tcod.console.Console, state: GameState, sel: int = 0,
                     filt: str | None = None) -> None:
    from ..game import skills
    from ..game import encumbrance as enc
    slots = state.player.inventory.slots
    visible = _inv.visible(state, filt)

    # Build the display list ADOM-style: a category header (with the group's
    # glyph in quotes) before each run of items, then the items themselves.
    rows: list = []                                  # ("head", cat, glyph) | ("item", vis_index)
    prev = None
    for v, i in enumerate(visible):
        it = slots[i][0]
        cat = _inv_category(it)
        if cat != prev:
            rows.append(("head", cat, it.glyph))
            prev = cat
        rows.append(("item", v))

    w, h = 62, min(C.SCREEN_H - 2, max(11, len(rows) + 6))
    body = h - 6
    m = ui.Modal(con, w, h, "PACK" + (f" — {filt}" if filt else ""))
    total = sum(q for _it, q, _ql in slots)
    etier = enc.tier(state)
    lbl = f"  ({enc.TIER_LABEL[etier]})" if etier else ""
    m.text(2, 1, f"Carrying {total} item(s)  ·  ⚖ {enc.carried_weight(state):.0f}/"
                 f"{enc.capacity(state):.0f}{lbl}",
           fg=(_CAP_FG, C.WARN_COLOR, C.DANGER_COLOR)[etier])
    gold = f"Gold: {state.player.gold}g"
    m.text(w - 2 - len(gold), 1, gold, fg=C.GOLD_COLOR)

    if not slots:
        m.text(2, 3, "(empty — grow and forage to fill it)", fg=C.DIM)
    elif not visible:
        m.text(2, 3, f"(nothing under {filt} — Tab cycles the filter)", fg=C.DIM)
    else:
        sel = max(0, min(sel, len(visible) - 1))
        sel_row = next((r for r, rw in enumerate(rows) if rw[0] == "item" and rw[1] == sel), 0)
        start, end = ui.window(sel_row, len(rows), body)
        for r in range(start, end):
            dy = 3 + (r - start)
            rw = rows[r]
            if rw[0] == "head":
                m.text(2, dy, f"{rw[1]}  ('{rw[2]}')", fg=_SECTION_FG)
                continue
            v = rw[1]
            it, qty, ql = slots[visible[v]]
            picked = (v == sel)
            bg = ui.SEL_BG if picked else ui.BASE_BG
            if picked:
                m.highlight(dy)
            m.text(3, dy, f"{inv_letter(v)} -", fg=_LETTER_FG, bg=bg)
            star = ("  " + skills.stars(ql)) if ql else ""
            m.text(8, dy, f"{it.glyph} {it.name}{star}", fg=C.WHITE, bg=bg)
            # ADOM-style right column: the stack count and its carried weight.
            qs = f"[x{qty} · {enc.weight_of(it) * qty:.0f}⚖]"
            m.text(w - 2 - len(qs), dy, qs, fg=_BRACKET_FG, bg=bg)
        m.arrows(start > 0, end < len(rows), 2, h - 3, dx=-3, glyphs=("↑", "↓"))
        it_sel, _q, ql_sel = slots[visible[sel]]      # detail line for the highlighted item
        m.text(2, h - 3, _pack_detail(it_sel)[:w - 6], fg=(188, 184, 168))
    m.footer("[a-z] pick  [Enter] use/equip  [⇧D] drop  [Tab] filter  [e] equipment",
             fg=_FOOT_FG)


_SLOT_LABEL = {"head": "Head", "body": "Body", "cloak": "Cloak", "hands": "Gauntlets",
               "waist": "Girdle", "legs": "Legs", "feet": "Feet", "shield": "Shield",
               "neck": "Amulet", "ring1": "Ring", "ring2": "Ring",
               "ranged": "Ranged", "ammo": "Ammo"}
# Worn slots in paperdoll order. Each is addressed on the equipment screen by a
# letter (a, b, …), continuing into the carried-gear list — one letter namespace
# for both take-off and equip. Shared with main's equipment-screen handler.
PAPERDOLL_SLOTS = ("head", "body", "cloak", "hands", "waist", "legs", "feet",
                   "shield", "neck", "ring1", "ring2", "ranged", "ammo")


def equippables(state: GameState) -> list:
    """Carried gear the equipment screen equips by letter: weapons, armour,
    jewellery, ranged launchers, and ammunition."""
    return [(it, q, ql) for it, q, ql in state.player.inventory.slots
            if it.kind in ("weapon", "armor", "jewelry", "ranged", "ammo", "bomb")]


def _jewel_desc(it, quality: int) -> str:
    """A short effect tag for a worn ring/amulet, scaled by its star quality."""
    from ..data import content
    from ..game import skills
    eff = content.JEWEL_EFFECT.get(it, {})
    qm = skills.value_mult(quality)
    def r(k):
        return eff.get(k, 0.0) * qm
    parts = []
    if r("dmg"):    parts.append(f"+{round(r('dmg'))} dmg")
    if r("to_hit"): parts.append(f"+{round(r('to_hit'))} hit")
    if r("dv"):     parts.append(f"+{round(r('dv'))} DV")
    if r("pv"):     parts.append(f"+{round(r('pv'))} PV")
    if r("crit"):   parts.append(f"+{round(r('crit') * 100)}% crit")
    if r("yield"):  parts.append(f"+{round(r('yield') * 100)}% yield")
    if r("energy"): parts.append(f"-{round(r('energy'))} stamina")
    return "[" + ", ".join(parts) + "]" if parts else ""


def render_equipment(con: tcod.console.Console, state: GameState) -> None:
    from ..data import content
    from ..game import combat, skills
    p = state.player
    gear = equippables(state)
    nslots = len(PAPERDOLL_SLOTS)
    w, h = 60, min(C.SCREEN_H - 2, 8 + nslots + len(gear))   # stats + in-hand + worn slots + 2 headers + gear + footer
    m = ui.Modal(con, w, h, "PERSONAL EQUIPMENT")

    dv, pv, th = combat.player_dv(state), combat.player_pv(state), combat.player_to_hit(state)
    m.text(2, 1, f"DV {dv}   PV {pv}   To-hit {th:+d}", fg=_CAP_FG)
    g = f"Gold: {p.gold}g"
    m.text(w - 2 - len(g), 1, g, fg=C.GOLD_COLOR)

    # what's in hand doubles as your weapon
    prof = combat.held_profile(state)
    lo, hi = prof.dmg
    ml = skills.mastery_level(state, prof.category)
    row = 3
    m.text(2, row, "In hand", fg=_SECTION_FG)
    m.text(12, row, f": {p.display_name(p.active_tool) if p.active_tool else '-'}"
           f"  ({prof.category} {lo}-{hi}, mastery {ml})"[:w - 14], fg=C.WHITE)
    row += 1
    # Worn paperdoll (armour, jewellery, ranged/ammo). Each slot is lettered; the
    # letters continue into the carried list below — one namespace for both.
    for i, slot in enumerate(PAPERDOLL_SLOTS):
        it = p.equipment.get(slot)
        if slot == "ammo":
            n = p.inventory.count(it) if it else 0
            val = f"{it.name} x{n}" if it else "-"
        elif slot == "ranged":
            rs = content.ranged_stat(it) if it else None
            val = f"{it.name}  [dmg {rs.dmg[0]}-{rs.dmg[1]}, range {rs.rng}]" if rs else (
                it.name if it else "- (none yet)")
        elif slot in ("neck", "ring1", "ring2"):
            q = p.equip_quality.get(slot, 0)
            star = (" " + skills.stars(q)) if q else ""
            val = f"{it.name}{star}  {_jewel_desc(it, q)}" if it else "-"
        else:
            st = content.ARMOR_STATS.get(it)
            val = f"{it.name}  [DV {st[0]:+d}, PV +{st[1]}]" if (it and st) else "-"
            if slot == "shield" and it and content.is_two_handed(p.active_tool):
                val += "  (unused — two-handed weapon)"
        m.text(2, row, f"{inv_letter(i)} {_SLOT_LABEL[slot]}", fg=_SECTION_FG if it else C.DIM)
        m.text(14, row, ": " + val, fg=C.WHITE if it else C.DIM)
        row += 1

    row += 1
    m.text(2, row, "Carried gear — press a letter to equip / take off:", fg=_HDR)
    row += 1
    for i, (it, _q, _ql) in enumerate(gear):
        if row >= h - 2:
            break
        st = content.ARMOR_STATS.get(it)
        rs = content.ranged_stat(it)
        if it.kind == "jewelry":
            tag = _jewel_desc(it, _ql)
        elif st:
            tag = f"[DV {st[0]:+d}, PV +{st[1]}]"
        elif rs:
            tag = f"ranged  dmg {rs.dmg[0]}-{rs.dmg[1]}, range {rs.rng}"
        elif it.kind in ("ammo", "bomb"):
            tag = "ammo"
        else:
            pr = content.profile_of(it)
            tag = f"{pr.category}, dmg {pr.dmg[0]}-{pr.dmg[1]}"
        m.text(3, row, f"{inv_letter(nslots + i)} - {it.glyph} {it.name}", fg=C.WHITE)
        m.text(34, row, tag, fg=_BRACKET_FG)
        row += 1
    m.footer("[letter] equip / take off  [i] pack  [Esc] close", fg=_FOOT_FG)


def render_craft(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..data import content
    from ..game import crafting

    recipes = crafting.visible_recipes(state)
    labels = [{"build": "Build", "cook": "Cook"}.get(r.kind, "Craft") for r in recipes]
    # Interleave category headers with the recipes into display rows, then show
    # a scrolling window — with every recipe learned the list far outgrows the
    # screen, and unscrolled rows used to clip silently past the frame.
    rows: list[tuple] = []            # ("hdr", label) | ("recipe", recipe, index)
    sel_row = 0
    last_label = None
    for i, r in enumerate(recipes):
        if labels[i] != last_label:
            last_label = labels[i]
            rows.append(("hdr", last_label))
        if i == sel:
            sel_row = len(rows)
        rows.append(("recipe", r, i))

    w = 56
    h = min(C.SCREEN_H - 2, len(rows) + 4)
    body = h - 4
    m = ui.Modal(con, w, h, "Craft  (build machines & cook)")
    start, end = ui.window(sel_row, len(rows), body)
    for row, entry in enumerate(rows[start:end]):
        dy = 2 + row
        if entry[0] == "hdr":
            m.text(2, dy, entry[1], fg=_HDR)
            continue
        _kind, r, i = entry
        ok = crafting.has_inputs(state, r)
        marker = "▸" if i == sel else " "
        color = C.WHITE if ok else C.DIM
        bg = ui.SEL_BG if i == sel else ui.BASE_BG
        if i == sel:
            m.highlight(dy)
        m.text(2, dy, f"{marker} {r.name}", fg=color, bg=bg)
        m.text(22, dy, f"[{crafting.inputs_str(r)}]"[:w - 24],
               fg=(160, 200, 150) if ok else (150, 110, 110), bg=bg)
    m.arrows(start > 0, end < len(rows), 2, h - 3)

    total_cook = sum(1 for r in content.RECIPES if r.kind == "cook")
    known = sum(1 for r in recipes if r.kind == "cook")
    hint = " — friends & taverns teach more" if known < total_cook else ""
    m.footer(f"↑↓ · Enter make · Esc · recipes {known}/{total_cook}{hint}"[:w - 4])


def render_ship(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..game import crafting

    from ..game import skills
    from ..game import requests as gamereq
    items_ = crafting.sellable_items(state)
    pending = sum(crafting.bin_value(state, it, ql) * q for it, q, ql in state.ship_bin.slots)
    boom = state.demand if state.demand and state.day < state.demand.get("until", 0) else {}
    w, h = 52, max(8, len(items_) + 7 + (1 if boom else 0))
    m = ui.Modal(con, w, h, "Shipping Bin  (sells overnight)")
    top = 2
    if boom:
        pct = int(round((boom["mult"] - 1) * 100))
        banner = f"★ The market craves {gamereq.DEMAND_KINDS[boom['kind']]} (+{pct}%)!"
        m.text(2, top, banner[:w - 4], fg=(232, 200, 120))
        top += 1

    if not items_:
        m.text(2, top, "Nothing to sell — grow and gather first.", fg=C.DIM)
    sel = max(0, min(sel, len(items_) - 1)) if items_ else 0   # keep the cursor on-list as it shrinks
    for i, (it, q, ql) in enumerate(items_):
        marker = "▸" if i == sel else " "
        bg = ui.SEL_BG if i == sel else ui.BASE_BG
        if i == sel:
            m.highlight(top + i)
        star = (" " + skills.stars(ql)) if ql else ""
        hot = boom and it.kind == boom["kind"]
        m.text(2, top + i, f"{marker} {q:>3}  {it.name}{star}", fg=C.WHITE, bg=bg)
        m.text(w - 12, top + i, f"{crafting.bin_value(state, it, ql)}g ea",
               fg=(250, 220, 110) if hot else C.GOLD_COLOR, bg=bg)

    m.text(2, h - 3, f"In bin (sells tonight): {pending}g", fg=C.GOLD_COLOR)
    m.footer("↑↓ select · Enter stack · Space all · Esc close")


_JOURNAL_TABS = ("Goals", "Favours", "Market", "Homestead", "Projects", "Collection")


def render_journal(con: tcod.console.Console, state: GameState, tab: int = 0) -> None:
    """The journal, in four pages (←→): quest goals, the open notice-board
    favours, the market's mood, and a homestead status overview — the planning
    surfaces that used to require a walk across the map."""
    from ..data import content
    from ..game import quests
    tab %= len(_JOURNAL_TABS)
    rows: list[tuple[int, str, tuple]] = []      # (indent, text, color)

    if tab == 0:
        for q in content.QUESTS:
            ok = q.id in state.quests_done
            mark = "✔" if ok else "○"
            note = "done" if ok else q.desc
            rows.append((0, f" {mark} {q.title:<20.20s}{note}  (+{q.gold}g)",
                         (150, 205, 150) if ok else C.WHITE))
    elif tab == 1:
        if not state.requests:
            rows.append((0, "The notice boards are bare today — favours come and go.", C.DIM))
        from ..game import requests as gamereq
        from ..entities import items as I
        for r in state.requests:
            it = I.by_name(r["item"])
            have = state.player.inventory.count(it) if it else 0
            can = gamereq.can_fulfil(state, r)
            days = r["expires"] - state.day
            rows.append((0, f"{r['npc']}: {r['qty']} {r['item']}  ·  {r['gold']}g  ·  "
                            f"{days} day{'s' if days != 1 else ''} left",
                         C.WHITE if can else C.DIM))
            rows.append((2, f"have {have}/{r['qty']} — deliver at a village notice board (g)",
                         (150, 210, 150) if can else C.DIM))
        rows.append((0, "", C.WHITE))
        rows.append((0, "Favours pay over the odds and warm a friendship.", C.DIM))
    elif tab == 2:
        from ..game.requests import DEMAND_KINDS
        d = state.demand
        if d and state.day < d.get("until", 0):
            pct = int(round((d["mult"] - 1) * 100))
            left = d["until"] - state.day
            rows.append((0, f"★ The market craves {DEMAND_KINDS[d['kind']]}: +{pct}% at the bin.",
                         (232, 200, 120)))
            rows.append((2, f"~{left} more day{'s' if left != 1 else ''} — ship while it lasts.",
                         C.WHITE))
        else:
            rows.append((0, "No particular craving — goods sell at their usual prices.", C.WHITE))
        rows.append((0, "", C.WHITE))
        rows.append((0, "Cravings come and go with the morning post; the shipping", C.DIM))
        rows.append((0, "bin pays the marked-up price the night you ship.", C.DIM))
    elif tab == 4:
        from ..game import projects as gameproj
        from ..data import content as _c
        for proj in state.projects:
            d = _c.PROJECTS[proj["id"]]
            if proj["state"] == "done":
                rows.append((0, f" ✔ {d.name}", (150, 205, 150)))
                rows.append((2, d.perk, (232, 200, 120)))
            elif proj["state"] == "building":
                days = max(1, round((proj.get("ready_at", 0) - state.abs_minutes) / 1440))
                rows.append((0, f" ▧ {d.name} — rising, ~{days} day{'s' if days != 1 else ''}",
                             (200, 220, 160)))
                rows.append((2, d.perk, C.DIM))
            else:
                gold_left, mats_left = gameproj.remaining(state, proj)
                need = " · ".join([f"{q} {it.name}" for it, q in mats_left[:3]]
                                  + ([f"{gold_left}g"] if gold_left else []))
                rows.append((0, f" ○ {d.name}  ({proj['village']})", C.WHITE))
                rows.append((2, f"needs {need}"[:56], C.DIM))
                rows.append((2, d.perk, C.DIM))
            rows.append((0, "", C.WHITE))
        rows.append((0, "Contribute at that village's notice board (g).", C.DIM))
    elif tab == 5:
        from ..game import collection as coll
        from ..data import content as _cc
        have, total = coll.total_progress(state)
        rows.append((0, f"Catalogued: {have}/{total} of the Vale's wonders", _HDR))
        if not coll.is_open(state):
            rows.append((2, "The Hall of Wonders isn't raised yet — fund it at Mossford.", C.DIM))
        rows.append((0, "", C.WHITE))
        for wing, (d, t) in coll.wing_progress(state).items():
            full = d == t
            rows.append((0, f" {'✔' if full else '○'} {wing}   {d}/{t}",
                         (150, 205, 150) if full else C.WHITE))
            if not full:
                miss = [it.name for it in _cc.COLLECTION[wing] if it.name not in state.donated]
                rows.append((2, "still seeking: " + ", ".join(miss[:5])
                             + ("…" if len(miss) > 5 else ""), C.DIM))
        rows.append((0, "", C.WHITE))
        rows.append((0, "Present finds (g) at a display case in the Hall of Wonders.", C.DIM))
    else:
        surf = state.surface
        now = state.abs_minutes
        if surf is None:
            rows.append((0, "No homestead yet.", C.DIM))
        else:
            from ..data.content import MACHINES
            ready, working, idle, soonest = [], 0, 0, None
            for m in surf.machines.values():
                mdef = MACHINES.get(m.kind)
                if mdef is None or m.kind in ("coop_small", "coop_big", "barn", "pen", "site"):
                    continue
                st = m.status(now)
                if st == "done":
                    ready.append(f"{mdef.name}: {m.loaded_output.name}")
                elif st == "working":
                    working += 1
                    if soonest is None or m.ready_at < soonest[0]:
                        soonest = (m.ready_at, mdef.name, m.loaded_output.name if m.loaded_output else "?")
                else:
                    idle += 1
            rows.append((0, "Machines", _HDR))
            for line in ready[:8]:
                rows.append((2, f"✔ {line} — ready!", (250, 220, 110)))
            if len(ready) > 8:
                rows.append((2, f"…and {len(ready) - 8} more ready.", (250, 220, 110)))
            rows.append((2, f"{working} working · {idle} idle", C.WHITE))
            if soonest is not None:
                from ..game.crafting import _fmt_remaining
                rows.append((2, f"next: {soonest[1]} ({soonest[2]}) in {_fmt_remaining(soonest[0] - now)}",
                             C.DIM))
            growing = ripe = dry = dead = 0
            for plot in surf.crops.values():
                if plot.dead:
                    dead += 1
                elif plot.mature:
                    ripe += 1
                else:
                    growing += 1
                    if not plot.watered and not plot.crop.paddy:
                        dry += 1
            rows.append((0, "", C.WHITE))
            rows.append((0, "Fields", _HDR))
            rows.append((2, f"{ripe} ripe · {growing} growing ({dry} need water)"
                            + (f" · {dead} withered" if dead else ""),
                         (224, 180, 120) if dry else C.WHITE))
            fruiting = sum(1 for tr in surf.trees.values() if tr.has_fruit)
            if surf.trees:
                rows.append((2, f"{fruiting} of {len(surf.trees)} trees bearing fruit", C.WHITE))
            if surf.animals:
                waiting = sum(1 for a in surf.animals if a.produce_ready)
                ill = sum(1 for a in surf.animals if a.sick)
                rows.append((0, "", C.WHITE))
                rows.append((0, "Animals", _HDR))
                rows.append((2, f"{len(surf.animals)} in your care · {waiting} with produce waiting",
                             C.WHITE))
                if ill:
                    rows.append((2, f"{ill} ill — dose with a Herbal Tonic!", (228, 150, 110)))

    done, total = quests.progress(state)
    title = (f"Journal — Goals ({done}/{total})" if tab == 0
             else f"Journal — {_JOURNAL_TABS[tab]}")
    w = 76
    h = min(C.SCREEN_H - 4, max(10, len(rows) + 6))
    m = ui.Modal(con, w, h, title)
    tabs = "   ".join((f"[{n}]" if i == tab else f" {n} ") for i, n in enumerate(_JOURNAL_TABS))
    m.text(2, 1, tabs[:w - 4], fg=(224, 204, 128))
    body = h - 5
    for row, (indent, text, color) in enumerate(rows[:body]):
        m.text(2 + indent, 3 + row, text[:w - 4 - indent], fg=color)
    m.footer("← → page   j / Esc close")


_SPOT_LABEL = {"home": "at home", "work": "at work", "inn": "at the inn",
               "temple": "at the temple", "square": "about the square"}


def render_relationships(con: tcod.console.Console, state: GameState, scroll: int = 0) -> None:
    from ..data import content
    from ..game import village
    met = [n for n in state.surface.npcs if n.met] if state.surface else []
    w = 62
    h = min(C.SCREEN_H - 4, max(8, len(met) * 4 + 5))
    m = ui.Modal(con, w, h, "Relationships")
    if not met:
        m.text(2, 2, "You haven't met anyone yet.", C.WHITE)
        m.text(2, 3, "Visit a village and talk (Shift+C).", C.DIM)
    body = h - 4
    hour = (state.time_minutes // 60) % 24
    lines: list[tuple[int, str, tuple]] = []
    for n in met:
        hearts = "♥" * n.hearts + "·" * (10 - n.hearts)
        spot = village.scheduled_spot(n, hour, state.weather, state.season,
                                      state.day_of_season)
        where = _SPOT_LABEL.get(spot, "out and about")
        prog = "" if n.hearts >= 10 else f" {n.friendship % 100:>2d}%"
        tag = "  ✓ gift" if getattr(n, "gifted_today", False) else ""
        lines.append((0, f" {n.glyph} {n.name:<13.13s}{hearts}{prog}{tag}   {where}"[:w - 2],
                      n.color))
        lines.append((2, f"{n.village} · {n.bio}"[:w - 8], C.DIM))
        loves = ", ".join(it.name for it in n.loves) or "—"
        lines.append((2, f"loves: {loves}"[:w - 8], (220, 170, 170)))
        # If a loved dish is a cookable recipe you don't know, they'll share it.
        teach = next((it.name for it in n.loves if it.kind == "food"
                      and (r := content.recipe_for_dish(it)) is not None
                      and r.name not in state.known_recipes), None)
        if teach:
            note = (f"will share their {teach.lower()} recipe (at 3♥)" if n.hearts < 3
                    else f"talk to them — they'll share their {teach.lower()} recipe!")
            lines.append((2, note[:w - 8], (232, 200, 120)))
        else:
            lines.append((2, "", C.DIM))
    scroll = max(0, min(scroll, max(0, len(lines) - body)))
    for row, (indent, text, color) in enumerate(lines[scroll:scroll + body]):
        if text:
            m.text(2 + indent, 2 + row, text, fg=color)
    m.arrows(scroll > 0, scroll + body < len(lines), 2, h - 3)
    m.footer("r / Esc to close")


def render_character(con: tcod.console.Console, state: GameState) -> None:
    from ..game import skills, karma, combat
    from ..game import attrs as A
    p = state.player
    w, h = 50, 17 + len(skills.SKILLS)          # stats, combat, attributes, skills
    m = ui.Modal(con, w, h, f"Character — Level {p.level}")
    nxt = skills.xp_to_next(p.level)
    xpbar = "█" * int(10 * p.xp / nxt) + "·" * (10 - int(10 * p.xp / nxt))
    m.text(2, 2, f"XP  {xpbar}  {p.xp}/{nxt}", fg=(210, 205, 150))
    m.text(2, 3, f"♥ HP      {p.hp}/{p.max_hp}", fg=C.HP_COLOR)
    m.text(2, 4, f"✦ Stamina {p.energy}/{p.max_energy}", fg=C.ENERGY_COLOR)
    m.text(2, 5, f"⛁ Gold    {p.gold}g", fg=C.GOLD_COLOR)
    m.text(2, 6, f"⚔ Weapon  {p.weapon.name if p.weapon else '-'}", fg=C.WHITE)
    ksign = f"+{p.karma}" if p.karma > 0 else str(p.karma)
    kcol = (160, 220, 160) if p.karma >= 8 else (220, 150, 140) if p.karma <= -8 else C.WHITE
    m.text(2, 7, f"☯ Karma   {ksign} ({karma.label(p.karma)})", fg=kcol)
    if p.sign:
        from ..data.content import ZODIAC
        z = next((z for z in ZODIAC if z[0] == p.sign), None)
        if z:
            m.text(2, 8, f"✶ Sign    {z[1]} — {z[4]}"[:w - 4], fg=(210, 200, 160))
    if p.attrs:                                 # birth attributes, ADOM-compact
        row1 = "   ".join(f"{k} {A.get(state, k):>2}" for k in A.ATTRS[:4])
        row2 = "   ".join(f"{k} {A.get(state, k):>2}" for k in A.ATTRS[4:])
        m.text(2, 9, row1, fg=(200, 195, 170))
        m.text(2, 10, row2, fg=(200, 195, 170))
    # Derived combat numbers — everything the dice see in a fight, so a new ring
    # or a better blade shows its worth without a trial by monster.
    m.text(2, 11, f"⛨ Defence  DV {combat.player_dv(state):<2}  PV {combat.player_pv(state)}",
           fg=(170, 190, 210))
    m.text(2, 12, f"⚔ Attack   to-hit {combat.player_to_hit(state):+d}"
                  f"   crit {combat.player_crit(state) * 100:.0f}%", fg=(210, 180, 160))
    m.text(2, 14, "Skills", fg=_HDR)
    for i, s in enumerate(skills.SKILLS):
        lvl = skills.skill_level(state, s)
        xp = p.skills.get(s, 0)
        if lvl >= skills.MAX_LEVEL:
            bar = "█" * 10
        else:
            into = xp - lvl * skills.XP_PER_LEVEL
            filled = int(10 * into / skills.XP_PER_LEVEL)
            bar = "█" * filled + "·" * (10 - filled)
        m.text(2, 15 + i, f"{s:<9} L{lvl:<2} {bar}", fg=C.WHITE if lvl else C.DIM)
    m.footer("v / Esc to close")


def render_dialogue(con: tcod.console.Console, state: GameState, npc, line: str) -> None:
    parts = line.split("\n")                          # blurbs may be multi-line verse
    w = min(72, max(54, max((len(p) for p in parts), default=0) + 6))
    h = len(parts) + 7
    m = ui.Modal(con, w, h, f"{npc.name}")
    hearts = "♥" * npc.hearts + "·" * (10 - npc.hearts)
    m.text(2, 2, hearts, fg=(220, 130, 150))
    for i, part in enumerate(parts):
        m.text(2, 4 + i, part[:w - 4], fg=C.WHITE)
    m.footer("f to gift · any key to close")


def render_shop(con: tcod.console.Console, state: GameState, npc, sel: int, line: str = "") -> None:
    from ..game import village
    from ..data import content
    from ..entities import items as I

    shop = village.npc_shop(state, npc)
    entries = village.shop_entries(shop, state, npc)
    title = {"general": "General Store", "blacksmith": "Blacksmith",
             "tavern": "Tavern", "carpenter": "Carpentry",
             "trader": "Wagon"}.get(shop, "Shop")
    header = line.split("\n") if line else []             # the keeper's greeting
    w = 68 if shop == "carpenter" else 56
    h = min(C.SCREEN_H - 4, len(entries) + 6 + len(header))
    m = ui.Modal(con, w, h, f"{npc.name}'s {title}")
    p = state.player
    top = 2
    for hl in header:                                     # innkeeper's greeting
        m.text(2, top, hl[:w - 4], fg=(210, 205, 190))
        top += 1
    body = (h - 2) - top                                  # rows for the (scrolling) list

    def row(i, dy, selected, rowbg):
        e = entries[i]
        pre = ui.cur(selected)
        afford = p.gold >= e.price
        if e.kind == "meal":
            gains = f"+{e.stam}st" + (f" +{e.hp}hp" if e.hp else "")
            m.text(2, dy, pre + e.label, fg=C.WHITE if afford else C.DIM, bg=rowbg)
            m.text(w - 20, dy, gains, fg=(150, 210, 150), bg=rowbg)
            m.text(w - 8, dy, f"{e.price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e.kind == "buy":
            m.text(2, dy, pre + e.item.name, fg=C.WHITE if afford else C.DIM, bg=rowbg)
            m.text(w - 10, dy, f"{e.price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e.kind == "contest":
            m.text(2, dy, pre + f"Enter the produce contest ({e.name})"[:w - 12],
                   fg=(232, 200, 120), bg=rowbg)
            m.text(w - 8, dy, "fair!", fg=(232, 200, 120), bg=rowbg)
        elif e.kind == "tradebuy":
            m.text(2, dy, pre + e.item.name[:w - 14],
                   fg=(232, 200, 120) if afford else C.DIM, bg=rowbg)
            m.text(w - 10, dy, f"{e.price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e.kind == "recipe":
            m.text(2, dy, pre + f"Recipe: {e.name}",
                   fg=(232, 200, 120) if afford else C.DIM, bg=rowbg)
            m.text(w - 10, dy, f"{e.price}g", fg=C.GOLD_COLOR if afford else C.DIM, bg=rowbg)
        elif e.kind == "sellto":
            from ..game import skills
            star = (" " + skills.stars(e.quality)) if e.quality else ""
            m.text(2, dy, pre + f"Sell {e.item.name}{star}", fg=(200, 220, 160), bg=rowbg)
            m.text(w - 10, dy, f"+{e.price}g", fg=C.GOLD_COLOR, bg=rowbg)
        elif e.kind == "cancel_build":
            m.text(2, dy, pre + "Cancel current order", fg=(224, 180, 120), bg=rowbg)
            m.text(w - 12, dy, "refund", fg=(190, 180, 150), bg=rowbg)
        elif e.kind in ("commission", "housejob"):
            matstr = ", ".join(f"{q} {it.name.split()[0].lower()}" for it, q in e.mats)
            can = afford and all(p.inventory.count(it) >= q for it, q in e.mats)
            m.text(2, dy, pre + e.label, fg=C.WHITE if can else C.DIM, bg=rowbg)
            m.text(28, dy, matstr[:w - 40], fg=(190, 180, 150) if can else C.DIM, bg=rowbg)
            m.text(w - 10, dy, f"{e.price}g", fg=C.GOLD_COLOR if can else C.DIM, bg=rowbg)
        else:  # upgrade
            tier = p.tool_tier.get(e.tool, 0)
            if tier >= len(C.TOOL_TIERS) - 1:
                txt, cost = f"{e.tool.name}: Mithril (max)", ""
                col = C.DIM
            else:
                gold, bar, count = village.upgrade_price(state, tier)
                txt = f"{e.tool.name}: {C.TOOL_TIERS[tier]}→{C.TOOL_TIERS[tier + 1]}"
                cost = f"{gold}g +{count} {bar.name.split()[0]}"
                affordable = p.gold >= gold and p.inventory.count(bar) >= count
                col = C.WHITE if affordable else C.DIM
            m.text(2, dy, pre + txt, fg=col, bg=rowbg)
            m.text(w - 16, dy, cost, fg=(200, 190, 150), bg=rowbg)

    m.list(top, body, len(entries), sel, row, arrow_top=top, arrow_bottom=h - 3)
    m.footer(f"Gold {p.gold}g   ↑↓ Enter buy/upgrade   Esc close")


def render_contest(con: tcod.console.Console, state: GameState, sel: int) -> None:
    """Pick one fine good to set on the Grange judging table — stars decide."""
    from ..game import village, skills
    goods = village.contest_items(state)
    w, h = 52, min(C.SCREEN_H - 4, max(8, len(goods) + 6))
    body = h - 5
    m = ui.Modal(con, w, h, "The Produce Contest")
    m.text(2, 1, "One entry — your finest. The judges love stars.", fg=C.DIM)
    if not goods:
        m.text(2, 3, "Nothing on you is fine enough to show.", fg=C.DIM)

    def row(i, dy, selected, bg):
        it, q, ql = goods[i]
        stars = skills.stars(ql) or "·"
        m.text(2, dy, ui.cur(selected) + f"{it.name}"[:w - 14], fg=C.WHITE, bg=bg)
        m.text(w - 10, dy, f"{stars:>5}", fg=(250, 220, 110), bg=bg)

    m.list(3, body, len(goods), sel, row, arrow_top=3, arrow_bottom=h - 3)
    m.footer("↑↓ select   Enter show it   Esc back")


# Dungeon-mouth marker colours on the world map, by site kind.
_MAP_DELVE_FG = {
    "mine": (214, 170, 110), "grotto": (110, 190, 190), "sea cave": (120, 200, 220),
    "cavern": (206, 186, 140), "barrow": (150, 122, 84), "crypt": (140, 150, 190),
    "tomb": (196, 186, 160), "dwarfhold": (176, 176, 188),
}


def render_world_map(con: tcod.console.Console, state: GameState) -> None:
    """The full-screen world map (m): the whole region downsampled to one view,
    with villages named, every known dungeon mouth marked by kind, the farm and
    your own position. Underground it shows the land above your head."""
    from ..world import tile as _t
    below = state.world.is_dungeon
    if below:
        base = state.west if getattr(state, "return_west", False) and state.west is not None \
            else state.surface
        px, py = state.return_pos
    else:
        base = state.world
        px, py = state.player.x, state.player.y
    if base is None:
        return
    W, H = base.width, base.height
    MW, MH = 76, 44
    x0, y0 = 2, 3                                    # map origin inside the frame

    title = "The Westreach" if base is state.west else "Hollowmere Vale"
    if below:
        title += "  —  (you are in the dark below)"
    m = ui.Modal(con, C.SCREEN_W, C.SCREEN_H, title)

    # Downsample: one sample per cell, plus offsets so thin water/roads still
    # register (priority: water > road > sampled ground).
    lut = np.array([t.bg for t in _t.TILES], dtype=np.uint8)
    kinds = [t.kind for t in _t.TILES]
    water_ids = np.array([i for i, k in enumerate(kinds) if k in ("water", "lava")])
    road_ids = np.array([i for i, k in enumerate(kinds) if k in ("road", "bridge")])
    xs = ((np.arange(MW) + 0.5) * W / MW).astype(int)
    ys = ((np.arange(MH) + 0.5) * H / MH).astype(int)
    grid = base.tiles[np.ix_(xs, ys)]
    water = np.isin(grid, water_ids)
    road = np.isin(grid, road_ids)
    for ox, oy in ((-1, -1), (1, 1), (-1, 1)):       # extra taps catch thin features
        gx = np.clip(xs + ox * max(1, W // (MW * 3)), 0, W - 1)
        gy = np.clip(ys + oy * max(1, H // (MH * 3)), 0, H - 1)
        g2 = base.tiles[np.ix_(gx, gy)]
        water |= np.isin(g2, water_ids)
        road |= np.isin(g2, road_ids)
    bg = lut[grid].astype(np.uint8)
    bg[water] = (24, 52, 88)
    con.rgb["ch"][x0:x0 + MW, y0:y0 + MH] = ord(" ")
    con.rgb["bg"][x0:x0 + MW, y0:y0 + MH] = bg
    rd = road & ~water
    con.rgb["ch"][x0:x0 + MW, y0:y0 + MH][rd] = ord("·")
    con.rgb["fg"][x0:x0 + MW, y0:y0 + MH][rd] = (188, 160, 116)

    def cell(wx, wy):
        return min(MW - 1, wx * MW // W), min(MH - 1, wy * MH // H)

    def mark(wx, wy, glyph, fg):
        cx, cy = cell(wx, wy)
        con.rgb["ch"][x0 + cx, y0 + cy] = ord(glyph)
        con.rgb["fg"][x0 + cx, y0 + cy] = fg

    # dungeon mouths, coloured by kind
    for (dx, dy) in getattr(base, "dungeons", ()):
        kind = base.dungeon_kind.get((dx, dy), "")
        mark(dx, dy, "▼", _MAP_DELVE_FG.get(kind, (200, 190, 170)))
    # villages: a block marker + the name beside it
    for name, (vx, vy) in getattr(base, "village_centers", {}).items():
        cx, cy = cell(vx, vy)
        mark(vx, vy, "■", (240, 214, 140))
        label = f" {name}"
        lx = cx + 1 if cx + 1 + len(label) <= MW else cx - len(label)
        m.text(x0 + lx, y0 + cy, label, fg=(240, 214, 140))
    # the farmstead
    bed = getattr(base, "bed", None)
    if bed:
        mark(bed[0], bed[1], "⌂", (150, 220, 150))
    # you
    mark(px, py, "@", (255, 255, 255))

    m.text(x0, y0 + MH + 1, "@ you   ⌂ farm   ■ village   ▼ delve (by kind)   · road",
           fg=C.DIM)
    m.footer("m / Esc close")


def render_chargen(con: tcod.console.Console, state: GameState, ctx: dict) -> None:
    """Character generation, ADOM-fashion: the midwives roll your stars and
    your eight attributes; roll another life at will, then begin for keeps."""
    from ..data.content import ZODIAC
    from ..game import attrs as A
    sign = next(z for z in ZODIAC if z[0] == ctx["sign"])
    rolled = ctx["attrs"]
    w, h = 66, 13 + len(A.ATTRS)
    m = ui.Modal(con, w, h, "Your birth, as the midwives tell it")
    m.text(2, 2, "The night you were born, the midwives read the sky", fg=C.DIM)
    m.text(2, 3, "and felt your grip — and this is what they wrote:", fg=C.DIM)
    m.text(2, 5, f"✶ Born under {sign[1]} — {sign[3]}.", fg=(232, 216, 150))
    m.text(4, 6, f"· {sign[4]}", fg=(190, 180, 140))
    total = sum(rolled.values())
    m.text(2, 8, f"Attributes  (3d6 apiece — {total} in all)", fg=_HDR)
    for i, key in enumerate(A.ATTRS):
        val = rolled[key]
        bar = "█" * round(10 * val / 18) + "·" * (10 - round(10 * val / 18))
        good = val >= 13
        poor = val <= 7
        fg = (170, 220, 170) if good else (220, 160, 140) if poor else C.WHITE
        m.text(2, 9 + i, f"{A.NAMES[key]:<11} {val:>2}  {bar}  {A.EFFECTS[key]}", fg=fg)
    m.footer("[r] roll another life   [Enter] begin — for keeps")


def render_donate(con: tcod.console.Console, state: GameState, sel: int) -> None:
    from ..game import collection, skills
    items_ = collection.donatable(state)
    have, tot = collection.total_progress(state)
    w, h = 54, min(C.SCREEN_H - 4, max(9, len(items_) + 6))
    body = h - 5
    m = ui.Modal(con, w, h, f"Hall of Wonders  —  {have}/{tot} catalogued")
    if not items_:
        m.text(2, 2, "Nothing new to present. Bring finds: fish, gems,", fg=C.DIM)
        m.text(2, 3, "herbs, crops and delved relics.", fg=C.DIM)

    def row(i, dy, selected, bg):
        it, ql = items_[i]
        wing = collection.wing_of(it.name) or ""
        star = (" " + skills.stars(ql)) if ql else ""
        m.text(2, dy, ui.cur(selected) + f"{it.name}{star}  · {wing}", fg=C.WHITE, bg=bg)

    m.list(2, body, len(items_), sel, row, arrow_top=2, arrow_bottom=h - 4)
    prog = collection.wing_progress(state)
    parts = [f"{wing.split()[0]} {d}/{t}" for wing, (d, t) in prog.items()]
    m.text(2, h - 3, "   ".join(parts), fg=(190, 180, 140))
    m.footer("↑↓ select   Enter present   Esc close")


def render_gift(con: tcod.console.Console, state: GameState, npc, sel: int) -> None:
    from ..game import village, skills
    gifts = village.giftable_items(state, npc)
    w, h = 48, min(C.SCREEN_H - 4, max(7, len(gifts) + 5))
    body = h - 4
    m = ui.Modal(con, w, h, f"Give a gift to {npc.name}")
    if not gifts:
        m.text(2, 2, "You have nothing to give.", fg=C.DIM)

    def row(i, dy, selected, bg):
        it, q, ql = gifts[i]
        # Match the same family-aware taste logic the gift actually uses, so the
        # tag never lies (a "loves Jam" NPC tags any jam variant as loved). Colour
        # reinforces the tag so taste reads at a glance, not by text alone.
        if npc._matches(it, npc.loves):
            tag, fg = " (loves!)", (150, 220, 150)
        elif npc._matches(it, npc.likes):
            tag, fg = " (likes)", (196, 220, 176)
        elif npc._matches(it, npc.dislikes):
            tag, fg = " (dislikes)", (222, 150, 140)
        else:
            tag, fg = "", C.WHITE
        star = (" " + skills.stars(ql)) if ql else ""
        m.text(2, dy, ui.cur(selected) + f"{q:>3} {it.name}{star}{tag}", fg=fg, bg=bg)

    m.list(2, body, len(gifts), sel, row, arrow_top=2, arrow_bottom=h - 3)
    m.footer("↑↓ select   Enter give   Esc close")
