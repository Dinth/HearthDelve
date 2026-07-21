"""UI screens — one class per game mode, arranged on a stack.

Each screen owns its own cursor/scroll state and knows how to render itself
and react to input. The main loop only ever talks to the top of the stack:

    ui.top.tick(ui)          # per-frame real-time work (runs, rests, fishing)
    ui.top.render(ui, con)   # the screen's overlay (the world is drawn first)
    ui.top.on_raw(ui, ev)    # raw-event pre-pass (held keys, letter selection)
    ui.top.handle(ui, cmd, action)   # translated commands

The bottom of the stack is always PlayScreen; opening a menu pushes a screen,
Esc pops it. Screens that hand off sideways (dialogue -> gift, craft -> the
chooser) replace themselves so Esc still lands back on the world.
"""
from __future__ import annotations

import time

import tcod.event

from .engine import constants as C
from .engine import codex, rendering
from .entities import items
from .game import combat, crafting, delve, farming, fishing, inventory, quests, turns, village
from .game import commands as cmds


class UI:
    """The screen stack plus the few flags shared with the main loop."""

    def __init__(self, state, music=None) -> None:
        self.state = state
        self.music = music
        self.stack: list[Screen] = [PlayScreen()]
        self.running = True
        self.save_on_exit = True
        self.input_lock_until = 0.0     # brief post-minigame keypress lockout

    @property
    def top(self) -> Screen:
        return self.stack[-1]

    @property
    def play(self) -> PlayScreen:
        return self.stack[0]

    def push(self, screen: Screen) -> None:
        self.stack.append(screen)

    def pop(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()

    def replace(self, screen: Screen) -> None:
        """Swap the top screen for another (a sideways hand-off, not a push)."""
        self.pop()
        self.push(screen)

    def close_overlays(self) -> None:
        """Drop every overlay, back to the bare world."""
        del self.stack[1:]

    def open_cheats(self) -> None:
        if not isinstance(self.top, CheatScreen):
            self.push(CheatScreen())


class Screen:
    """Base screen: render an overlay and react to input. Subclasses override
    what they need; the defaults do nothing."""

    def render(self, ui: UI, con) -> None:
        pass

    def tick(self, ui: UI) -> None:
        """Advance per-frame real-time work. Called only while topmost."""

    def on_raw(self, ui: UI, event) -> bool:
        """Raw-event pre-pass, before command mapping. Return True to consume."""
        return False

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        """React to a translated command tuple from engine.input."""


class PlayScreen(Screen):
    """The world itself: walking, working, and every auto-action (an active
    run, a rest, a long chop/mine) that animates over frames."""

    def __init__(self) -> None:
        self.awaiting_run = False   # 'w' pressed, waiting for a direction or '.'
        self.run_ctx: dict | None = None
        self.rest_left = 0          # seconds left in an active rest
        self.busy_ctx: dict | None = None   # active long tool action (chop/mine)

    # --- auto-actions ---------------------------------------------------

    def auto_active(self) -> bool:
        return self.run_ctx is not None or self.rest_left > 0 or self.busy_ctx is not None

    def cancel_auto(self) -> bool:
        """Interrupt any in-progress run/rest/long action. True if one was."""
        if self.auto_active():
            self.run_ctx, self.rest_left, self.busy_ctx = None, 0, None
            return True
        return False

    def tick(self, ui: UI) -> None:
        state = ui.state
        if self.run_ctx is not None:
            if not cmds.run_step(state, self.run_ctx):
                reason = self.run_ctx.get("stop", "")
                self.run_ctx = None
                if reason:
                    state.log.add(reason, C.DIM)
                cmds.check_faint(state)
                quests.check(state)
        elif self.rest_left > 0:
            turns.advance_time(state, C.MOVE_SECONDS)
            if state.world.is_dungeon:
                delve.update_fov(state)
            self.rest_left -= C.MOVE_SECONDS
            note = cmds._notable_nearby(state)
            if note or self.rest_left <= 0:
                self.rest_left = 0
                state.log.add(f"You stop resting — {note}." if note else "You rest a while.",
                              C.DIM)
                cmds.check_faint(state)
                quests.check(state)
        elif self.busy_ctx is not None:
            threat = cmds._threat_near(state)
            if threat is not None:                   # a beast closes in — break off
                state.log.add(f"You break off — a {threat.name.lower()} is too close!",
                              C.WARN_COLOR)
                self.busy_ctx = None
            else:
                turns.advance_time(state, C.MOVE_SECONDS)
                if state.world.is_dungeon:
                    delve.update_fov(state)
                self.busy_ctx["left"] -= C.MOVE_SECONDS
                if self.busy_ctx["left"] <= 0:
                    cmds._finish_busy(state, self.busy_ctx)
                    self.busy_ctx = None
                    cmds.check_faint(state)
                    quests.check(state)

    # --- rendering & input ------------------------------------------------

    def render(self, ui: UI, con) -> None:
        rendering.render_facing(con, ui.state)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        if self.awaiting_run:
            self.awaiting_run = False
            if cmd == "move":
                self.run_ctx = cmds.start_run(state, action[1], action[2])
                if self.run_ctx is None:
                    state.log.add("You can't run that way.", C.DIM)
            elif cmd == "wait":
                self.rest_left = cmds.REST_MAX_SECONDS
            return
        if cmd == "runprefix":
            self.awaiting_run = True
            state.log.add("Run: press a direction — or . to rest a while.", C.DIM)
            return
        if cmd in ("quit", "cancel", "quitgame"):
            ui.push(QuitScreen())
            return
        elif cmd == "move":
            dx, dy = action[1], action[2]
            # First step off the western edge crosses into the lethal Westreach —
            # confirm it once (state.west is still None), so a stray press at the
            # map's edge can't drop a new farmer into volcano country.
            if (state.west is None and state.world is state.surface
                    and state.player.x + dx < 0):
                ui.push(ConfirmScreen(
                    "Cross into the Westreach?",
                    "The pass leads to volcano country — hunted, and far from home.",
                    lambda ui: cmds.try_move(ui.state, dx, dy),
                    "The beasts there don't wait to be provoked."))
            else:
                cmds.try_move(state, dx, dy)
        elif cmd == "wait":
            turns.advance_time(state, C.MOVE_SECONDS)
        elif cmd == "slot":
            cmds.select_slot(state, action[1])
        elif cmd == "look":
            cur = [state.player.x, state.player.y]
            state.cam_focus = tuple(cur)
            ui.push(LookScreen(cur))
            if not state.stats.get("look_intro"):
                state.stats["look_intro"] = 1
                state.log.add("Looking around — the arrow keys now move a cursor to "
                              "inspect tiles, not you. Press Esc or l to walk again.",
                              (200, 220, 160))
        elif cmd == "use":
            busy = cmds.use_tool(state)
            if isinstance(busy, dict) and "fishing" in busy:
                ui.push(FishingScreen(busy["fishing"]))
            elif busy is not None:
                self.busy_ctx = busy          # a long task begins — it animates
            else:
                cmds.check_faint(state)
        elif cmd == "grab":
            if cmds._at_postbox(state):
                if state.mail:
                    ui.push(MailScreen())
                else:
                    state.log.add("Your post box is empty.", C.DIM)
            elif cmds._at_board(state):
                req_village = cmds._board_village(state)
                from .game import projects as gameproj
                proj = gameproj.for_village(state, req_village)
                has_proj = proj is not None and proj["state"] != "done"
                if state.requests or has_proj:
                    ui.push(RequestsScreen(req_village))
                else:
                    state.log.add("The notice board is bare today — "
                                  "favours come and go.", C.DIM)
            else:
                req = cmds.do_grab(state)
                if isinstance(req, dict) and "donate" in req:
                    ui.push(DonateScreen())
                elif isinstance(req, dict) and "storage" in req:
                    ui.push(StorageScreen())
                elif isinstance(req, dict) and "load" in req:
                    ui.push(LoadMachineScreen({
                        "pos": req["load"], "options": req["options"],
                        "name": req["name"], "sel": 0,
                        "jeweller": req.get("jeweller", False),
                        "butcher": req.get("butcher", False)}))
                else:
                    cmds.check_faint(state)
        elif cmd == "place":
            if not state.pending_build:
                state.log.add("You've nothing on order from the carpenter.", C.DIM)
            elif state.world.is_dungeon:
                state.log.add("You can only raise a building on the surface.", C.DIM)
            else:
                fx, fy = state.player.facing
                cur = cmds.clamp_look(state, state.player.x + fx, state.player.y + fy)
                state.cam_focus = tuple(cur)
                ui.push(TargetScreen({"purpose": "build", "cursor": cur,
                                      "build_kind": state.pending_build}))
        elif cmd == "target":
            if not combat.can_fire(state):
                state.log.add("Nothing to loose or throw — equip a bow (+ arrows) "
                              "or craft a bomb (c).", C.DIM)
            else:
                cur = cmds.clamp_look(state, *combat.aim_start(state))
                state.cam_focus = tuple(cur)
                ui.push(TargetScreen({"purpose": combat.aim_purpose(state), "cursor": cur}))
        elif cmd == "descend":
            here = state.world.tile_at(state.player.x, state.player.y)
            if not state.world.is_dungeon and here.kind == "stairs":
                kind = state.world.dungeon_kind.get((state.player.x, state.player.y), "mine")
                delve.enter(state, kind)
            elif state.world.is_dungeon and here.kind == "stairs":
                delve.descend(state)
            else:
                state.log.add("There are no stairs down here.", C.DIM)
        elif cmd == "ascend":
            here = state.world.tile_at(state.player.x, state.player.y)
            if state.world.is_dungeon and here.kind == "stairs_up":
                delve.ascend(state)
            else:
                state.log.add("There are no stairs up here.", C.DIM)
        elif cmd == "sleep":
            if farming.can_sleep(state):
                farming.sleep(state)
            else:
                state.log.add("You can only sleep in your bed.", C.DIM)
        elif cmd == "craft":
            ui.push(CraftScreen())
        elif cmd == "eat":
            if crafting.edible_items(state):
                ui.push(EatScreen())
            else:
                state.log.add("You have nothing to eat. Cook (c) a dish or gather eggs/milk.",
                              C.DIM)
        elif cmd == "ship":
            if cmds.near_bin(state):
                ui.push(ShipScreen())
            else:
                state.log.add("Stand by the shipping bin to sell goods.", C.DIM)
        elif cmd == "journal":
            ui.push(JournalScreen())
        elif cmd == "relations":
            ui.push(RelationsScreen())
        elif cmd == "character":
            ui.push(CharacterScreen())
        elif cmd == "talk":
            npc = village.npc_near(state)
            if npc is None:
                state.log.add("There's no one here to talk to.", C.DIM)
            elif village.npc_shop(state, npc):
                # every shopkeeper still gets the daily greeting (friendship,
                # festival treats, heart gifts), then trades
                ui.push(ShopScreen(npc, village.talk(state, npc)))
            else:
                ui.push(DialogueScreen(npc, village.talk(state, npc)))
        elif cmd == "gift":
            npc = village.npc_near(state)
            if npc is None:
                state.log.add("There's no one here to give a gift to.", C.DIM)
            else:
                ui.push(GiftScreen(npc))
        elif cmd == "help":
            ui.push(HelpScreen())
        elif cmd == "inventory":
            state.player.inventory.slots.sort(
                key=lambda e: inventory.sort_key(e[0], e[2]))
            ui.push(InventoryScreen())
        elif cmd == "drop":                      # 'd' on the map: point to where drop lives
            state.log.add("Open your pack (i), then Shift+D to drop the highlighted stack.", C.DIM)
        elif cmd == "equipment":
            ui.push(EquipmentScreen())
        elif cmd == "messages":
            ui.push(LogScreen())
        elif cmd == "worldmap":
            ui.push(WorldMapScreen())
        if cmd in ("move", "wait"):
            cmds.check_faint(state)
        quests.check(state)              # re-check goals on any action


class WorldMapScreen(Screen):
    """The full-screen region map (m): terrain at a glance, villages named,
    dungeon mouths marked, the farm and your own position."""
    def render(self, ui: UI, con) -> None:
        rendering.render_world_map(con, ui.state)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd in ("cancel", "worldmap", "quit", "confirm"):
            ui.pop()


class LookScreen(Screen):
    def __init__(self, cursor: list[int]) -> None:
        self.cursor = cursor

    def render(self, ui: UI, con) -> None:
        rendering.render_look(con, ui.state, *self.cursor)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd in ("look", "cancel", "quit"):
            ui.state.cam_focus = None
            ui.pop()
        elif cmd == "move":
            self.cursor = cmds.clamp_look(ui.state, self.cursor[0] + action[1],
                                          self.cursor[1] + action[2])
            ui.state.cam_focus = tuple(self.cursor)


class TargetScreen(Screen):
    """Aiming a bow/bomb, or siting a commissioned building."""

    def __init__(self, ctx: dict) -> None:
        self.ctx = ctx

    def render(self, ui: UI, con) -> None:
        rendering.render_target(con, ui.state, self.ctx)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        if cmd in ("cancel", "target", "quit"):
            state.cam_focus = None
            ui.pop()
        elif cmd == "swap" and self.ctx["purpose"] in ("shoot", "throw"):
            # Tab toggles bow<->bomb when you carry both, so a readied launcher
            # never locks bombs (needed for ore/gem veins) away.
            if self.ctx["purpose"] == "shoot" and combat.can_throw(state):
                self.ctx["purpose"] = "throw"
                state.log.add("You ready a bomb to throw.", (200, 220, 160))
            elif self.ctx["purpose"] == "throw" and combat.can_shoot(state):
                self.ctx["purpose"] = "shoot"
                state.log.add("You draw your bow.", (200, 220, 160))
            else:
                state.log.add("You've nothing else to switch to.", C.DIM)
        elif cmd == "move":
            cur = cmds.clamp_look(state, self.ctx["cursor"][0] + action[1],
                                  self.ctx["cursor"][1] + action[2])
            self.ctx["cursor"] = cur
            state.cam_focus = tuple(cur)
        elif cmd in ("confirm", "use"):
            tx, ty = self.ctx["cursor"]
            if self.ctx["purpose"] == "throw":
                combat.throw_bomb_at(state, tx, ty)
                cmds.check_faint(state)
            elif self.ctx["purpose"] == "shoot":
                combat.fire_ranged_at(state, tx, ty)
                cmds.check_faint(state)
            else:
                from .game import husbandry
                husbandry.place_commission_at(state, tx, ty)
            state.cam_focus = None
            ui.pop()
            quests.check(state)


class LoadMachineScreen(Screen):
    """A machine's (or bench chooser's) "what to load?" menu."""

    def __init__(self, ctx: dict) -> None:
        self.ctx = ctx

    def render(self, ui: UI, con) -> None:
        rendering.render_load_machine(con, ui.state, self.ctx)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        opts = self.ctx["options"]
        rows, is_group = crafting.load_rows(self.ctx) if opts else ([], False)
        if cmd in ("grab", "quit") or not opts:
            ui.pop()
        elif cmd == "cancel":
            # In a group: step back to the group menu; at the top: close.
            if self.ctx.get("group") is not None:
                self.ctx["group"], self.ctx["sel"] = None, 0
            else:
                ui.pop()
        elif cmd == "move" and action[2] and rows:
            self.ctx["sel"] = (self.ctx["sel"] + action[2]) % len(rows)
        elif cmd == "confirm" and rows:
            pick = rows[min(self.ctx["sel"], len(rows) - 1)]
            if is_group:                     # descend into the chosen group
                self.ctx["group"], self.ctx["sel"] = pick, 0
            else:
                if self.ctx.get("craft"):    # a bench chooser (metal-tipped arrows)
                    crafting.craft_choice(state, pick)
                elif self.ctx.get("jeweller"):   # jeweller's bench (instant: make/embed)
                    crafting.jeweller_choice(state, pick)
                elif self.ctx.get("butcher"):    # the block (instant: an animal for its cuts)
                    crafting.butcher_choice(state, pick)
                else:
                    m = state.world.machines.get(self.ctx["pos"])
                    if m is not None:
                        crafting.load_machine_choice(state, m, crafting.MACHINES[m.kind], pick)
                ui.pop()
                quests.check(state)


class HelpScreen(Screen):
    """The codex: paged help/reference, ←→ pages, ↑↓ scrolls."""

    def __init__(self) -> None:
        self.page = 0
        self.scroll = 0

    def render(self, ui: UI, con) -> None:
        codex.render_codex(con, ui.state, self.page, self.scroll)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd in ("help", "cancel", "quit"):
            ui.pop()
        elif cmd == "move":
            if action[1]:
                self.page += action[1]
                self.scroll = 0
            if action[2]:
                self.scroll = max(0, self.scroll + action[2])


_EQUIP_KINDS = ("weapon", "armor", "jewelry", "ranged", "ammo", "bomb")


class InventoryScreen(Screen):
    def __init__(self) -> None:
        self.sel = 0
        self.filt: str | None = None      # Tab-cycled category filter (None = all)

    def render(self, ui: UI, con) -> None:
        rendering.render_inventory(con, ui.state, self.sel, self.filt)

    def _visible(self, state):
        return inventory.visible(state, self.filt)

    def _picked(self, state):
        """The (item, qty, quality) under the cursor, or None."""
        vis = self._visible(state)
        if not vis:
            return None
        self.sel = min(self.sel, len(vis) - 1)
        return state.player.inventory.slots[vis[self.sel]]

    def on_raw(self, ui: UI, event) -> bool:
        # ADOM-style: a bare letter picks an item directly — even keys that
        # would otherwise be commands act as selectors here.
        if not isinstance(event, tcod.event.KeyDown) or (event.mod & tcod.event.Modifier.SHIFT):
            return False
        s = int(event.sym)
        ch = chr(s) if ord("a") <= s <= ord("z") else ""
        if not ch or ch in ("i", "e"):
            return False
        if ord(ch) - ord("a") < len(self._visible(ui.state)):
            self.sel = ord(ch) - ord("a")
        return True

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        vis = self._visible(state)
        if cmd == "equipment":
            ui.replace(EquipmentScreen())
        elif cmd in ("cancel", "inventory", "quit"):
            ui.pop()
        elif cmd == "slot":
            cmds.select_slot(state, action[1])
        elif cmd == "swap":                      # Tab: cycle the category filter
            cats = inventory.categories(state)
            cycle = [None] + cats
            self.filt = cycle[(cycle.index(self.filt) + 1) % len(cycle)] \
                if self.filt in cycle else None
            self.sel = 0
        elif cmd == "move" and action[2] and vis:
            self.sel = (self.sel + action[2]) % len(vis)
        elif cmd == "confirm" and vis:           # Enter: eat a food/remedy, don gear
            it, _q, ql = self._picked(state)
            if it.energy > 0 or it.heal > 0:
                cmds._eat(state, it, ql)
            elif it.kind in _EQUIP_KINDS:
                cmds._equip(state, it)
            else:
                state.log.add(f"The {it.name.lower()} isn't something to use from the pack.",
                              C.DIM)
            self.sel = min(self.sel, max(0, len(self._visible(state)) - 1))
        elif cmd == "drop" and vis:
            # Shift+D drops the whole stack (as the help page says).
            it, q, ql = self._picked(state)
            if ql > 0 or getattr(it, "value", 0) >= 100:
                ui.push(ConfirmScreen(
                    "Toss it out?",
                    f"Throw away {q} {it.name.lower()}?" if q > 1
                    else f"Throw away the {it.name.lower()}?",
                    lambda ui: self._do_drop(ui.state, it, q, ql),
                    "It's starred or valuable — this can't be undone."))
            else:
                self._do_drop(state, it, q, ql)

    def _do_drop(self, state, it, q, ql) -> None:
        state.player.inventory.remove(it, q, quality=ql)
        state.log.add(f"You toss out {q} {it.name.lower()}." if q > 1
                      else f"You toss out a {it.name.lower()}.", C.DIM)
        self.sel = min(self.sel, max(0, len(self._visible(state)) - 1))


class EquipmentScreen(Screen):
    def render(self, ui: UI, con) -> None:
        rendering.render_equipment(con, ui.state)

    def on_raw(self, ui: UI, event) -> bool:
        # One letter namespace: a.. address the worn slots (take off), then the
        # carried gear list (equip).
        if not isinstance(event, tcod.event.KeyDown) or (event.mod & tcod.event.Modifier.SHIFT):
            return False
        s = int(event.sym)
        ch = chr(s) if ord("a") <= s <= ord("z") else ""
        if not ch or ch in ("i", "e"):
            return False
        idx = ord(ch) - ord("a")
        nslots = len(rendering.PAPERDOLL_SLOTS)
        if 0 <= idx < nslots:
            cmds._unequip(ui.state, rendering.PAPERDOLL_SLOTS[idx])
        else:
            gear = rendering.equippables(ui.state)
            gi = idx - nslots
            if 0 <= gi < len(gear):
                cmds._equip(ui.state, gear[gi][0])
        return True

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd == "inventory":
            ui.state.player.inventory.slots.sort(
                key=lambda e: inventory.sort_key(e[0], e[2]))
            ui.replace(InventoryScreen())
        elif cmd in ("cancel", "equipment", "quit"):
            ui.pop()
        # Take-off & equip are handled by the letter namespace in on_raw.


class CraftScreen(Screen):
    def __init__(self) -> None:
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_craft(con, ui.state, self.sel)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        shown = crafting.visible_recipes(state)
        if cmd in ("cancel", "craft", "quit"):
            ui.pop()
        elif cmd == "move" and action[2] and shown:
            self.sel = (self.sel + action[2]) % len(shown)
        elif cmd == "confirm" and shown:
            r = shown[min(self.sel, len(shown) - 1)]
            if r.kind == "choose":
                opts = crafting.arrow_choice_options(state)
                if opts:
                    ui.replace(LoadMachineScreen(
                        {"options": opts, "sel": 0, "name": r.name, "craft": True}))
                else:
                    state.log.add("You need 1 Wood and a metal ore to tip arrows.", C.DIM)
            else:
                crafting.craft(state, r)


class MailScreen(Screen):
    def __init__(self) -> None:
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_mail(con, ui.state, self.sel)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        if cmd in ("cancel", "grab", "quit") or not state.mail:
            ui.pop()
        elif cmd == "move" and action[2] and state.mail:
            self.sel = (self.sel + action[2]) % len(state.mail)
        elif cmd == "confirm" and state.mail:
            self.sel = min(self.sel, len(state.mail) - 1)
            letter = state.mail[self.sel]
            if letter.get("tax"):
                cmds.collect_letter(state, letter)   # settles & refreshes the notice
            else:
                cmds.collect_letter(state, state.mail.pop(self.sel))
            self.sel = 0
            if not state.mail:
                ui.pop()


class RequestsScreen(Screen):
    """The village notice board: favours plus the local restoration project."""

    def __init__(self, village_name: str) -> None:
        self.village = village_name
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_requests(con, ui.state, self.sel, self.village)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        from .game import requests as gamereq, projects as gameproj
        proj = gameproj.for_village(state, self.village)
        if proj is not None and proj["state"] == "done":
            proj = None
        n_rows = len(state.requests) + (1 if proj else 0)
        if cmd in ("cancel", "grab", "quit") or not n_rows:
            ui.pop()
        elif cmd == "move" and action[2]:
            self.sel = (self.sel + action[2]) % n_rows
        elif cmd in ("confirm", "use"):
            self.sel = min(self.sel, n_rows - 1)
            if self.sel < len(state.requests):
                if cmd == "confirm":
                    gamereq.deliver(state, state.requests[self.sel])
                    self.sel = 0
            elif proj is not None and proj["state"] == "open":
                # Enter = mats + a 500g instalment; Space = all-in gold
                gameproj.contribute(state, proj, all_in=(cmd == "use"))
            elif proj is not None:
                state.log.add("The frame is already rising — give it a few days.", C.DIM)
            if not state.requests and (proj is None or proj["state"] != "open"):
                ui.pop()


class EatScreen(Screen):
    def __init__(self) -> None:
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_eat(con, ui.state, self.sel)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        foods = crafting.edible_items(state)
        if cmd in ("cancel", "eat", "quit"):
            ui.pop()
        elif cmd == "move" and action[2] and foods:
            self.sel = (self.sel + action[2]) % len(foods)
        elif cmd == "confirm" and foods:
            self.sel = min(self.sel, len(foods) - 1)
            it, _q, ql = foods[self.sel]
            cmds._eat(state, it, ql)
            cmds.check_faint(state)
            if not crafting.edible_items(state):
                ui.pop()


class ShipScreen(Screen):
    def __init__(self) -> None:
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_ship(con, ui.state, self.sel)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        sellable = crafting.sellable_items(state)
        if cmd in ("cancel", "ship", "quit"):
            ui.pop()
        elif cmd == "move" and action[2] and sellable:
            self.sel = (self.sel + action[2]) % len(sellable)
        elif cmd == "use" and sellable:       # Space: empty the whole pack in
            def _ship_all(ui):
                crafting.ship_all(ui.state)
                self.sel = 0
            if any(e[2] > 0 or getattr(e[0], "value", 0) >= 200 for e in sellable):
                ui.push(ConfirmScreen(
                    "Ship everything?",
                    f"Send all {len(sellable)} kinds of goods to the bin overnight?",
                    _ship_all, "Some are starred or valuable — no taking them back."))
            else:
                _ship_all(ui)
        elif cmd == "confirm" and sellable:
            self.sel = min(self.sel, len(sellable) - 1)
            entry = sellable[self.sel]
            crafting.ship_item(state, entry[0], entry[2])


class StorageScreen(Screen):
    """The home chest: move stacks between your pack and storage. Stored goods
    weigh nothing on your back (see game.encumbrance)."""

    def __init__(self) -> None:
        self.side = "pack"          # which column is active: "pack" | "store"
        self.sel = 0

    def _slots(self, ui: UI) -> list:
        return (ui.state.player.inventory.slots if self.side == "pack"
                else ui.state.storage.slots)

    def render(self, ui: UI, con) -> None:
        rendering.render_storage(con, ui.state, self.side, self.sel)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        pack, store = state.player.inventory, state.storage
        slots = self._slots(ui)
        if cmd in ("cancel", "quit", "grab"):
            ui.pop()
        elif cmd == "swap" or (cmd == "move" and action[1]):      # Tab or ←/→ switch side
            self.side = "store" if self.side == "pack" else "pack"
            self.sel = 0
        elif cmd == "move" and action[2] and slots:
            self.sel = (self.sel + action[2]) % len(slots)
        elif cmd == "confirm" and slots:
            self.sel = min(self.sel, len(slots) - 1)
            it, q, ql = slots[self.sel]
            src, dst = (pack, store) if self.side == "pack" else (store, pack)
            src.remove(it, q, quality=ql)
            dst.add(it, q, quality=ql)
            verb = "stow" if self.side == "pack" else "take out"
            state.log.add(f"You {verb} {q} {it.name.lower()}." if q > 1
                          else f"You {verb} the {it.name.lower()}.", C.DIM)
            self.sel = min(self.sel, max(0, len(self._slots(ui)) - 1))
        elif cmd == "use" and self.side == "pack":               # Space: stow the whole pack
            n = sum(q for _it, q, _ql in pack.slots)
            for it, q, ql in list(pack.slots):
                pack.remove(it, q, quality=ql)
                store.add(it, q, quality=ql)
            if n:
                state.log.add(f"You stow {n} goods in the chest.", C.DIM)
            self.sel = 0


class DialogueScreen(Screen):
    def __init__(self, npc, line: str) -> None:
        self.npc = npc
        self.line = line

    def render(self, ui: UI, con) -> None:
        rendering.render_dialogue(con, ui.state, self.npc, self.line)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        # Only a deliberate key closes the panel — a reflexive arrow-press
        # shouldn't swallow a line of dialogue.
        if cmd == "gift":
            ui.replace(GiftScreen(self.npc))
        elif cmd in ("cancel", "confirm", "talk", "quit", "use"):
            ui.pop()


class ShopScreen(Screen):
    def __init__(self, npc, line: str) -> None:
        self.npc = npc
        self.line = line
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_shop(con, ui.state, self.npc, self.sel, self.line)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        entries = village.shop_entries(village.npc_shop(state, self.npc), state, self.npc)
        if cmd in ("cancel", "talk", "quit"):
            ui.pop()
        elif cmd == "move" and action[2] and entries:
            self.sel = (self.sel + action[2]) % len(entries)
        elif cmd == "confirm" and entries:
            picked = entries[min(self.sel, len(entries) - 1)]
            if picked.kind == "contest":     # the fair: pick an entry to judge
                ui.push(ContestScreen(self.npc))
            else:
                village.purchase(state, picked)


class ContestScreen(Screen):
    """The festival produce contest: pick a quality good to put before the judges."""

    def __init__(self, npc) -> None:
        self.npc = npc
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_contest(con, ui.state, self.sel)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        goods = village.contest_items(state)
        if cmd in ("cancel", "quit") or not goods:
            ui.pop()                          # back to the shop counter
            if isinstance(ui.top, ShopScreen):
                ui.top.sel = 0
            if not goods:
                state.log.add("You've nothing fine enough to enter — "
                              "bring quality produce.", C.DIM)
        elif cmd == "move" and action[2]:
            self.sel = (self.sel + action[2]) % len(goods)
        elif cmd == "confirm":
            it, _q, ql = goods[min(self.sel, len(goods) - 1)]
            line = village.enter_contest(state, it, ql)
            ui.pop()                          # the contest chooser…
            ui.pop()                          # …and the shop behind it
            ui.push(DialogueScreen(self.npc, line))


class GiftScreen(Screen):
    def __init__(self, npc) -> None:
        self.npc = npc
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_gift(con, ui.state, self.npc, self.sel)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        gifts = village.giftable_items(state, self.npc)
        if cmd in ("cancel", "gift", "quit"):
            ui.pop()
        elif cmd == "move" and action[2] and gifts:
            self.sel = (self.sel + action[2]) % len(gifts)
        elif cmd == "confirm" and gifts:
            git, _gq, gql = gifts[min(self.sel, len(gifts) - 1)]

            def _give(ui):
                village.gift(ui.state, self.npc, git, gql)
                ui.close_overlays()
            if gql > 0 or getattr(git, "value", 0) >= 150:
                ui.push(ConfirmScreen(
                    "Give this gift?",
                    f"Give {self.npc.name} your {git.name.lower()}?",
                    _give, "It's starred or valuable."))
            else:
                _give(ui)


class DonateScreen(Screen):
    """The Hall of Wonders: present carried finds to the curator, one by one."""
    def __init__(self) -> None:
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_donate(con, ui.state, self.sel)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        from .game import collection
        state = ui.state
        items_ = collection.donatable(state)
        if cmd in ("cancel", "gift", "quit") or not items_:
            ui.pop()
        elif cmd == "move" and action[2]:
            self.sel = (self.sel + action[2]) % len(items_)
        elif cmd == "confirm":
            it, _ql = items_[min(self.sel, len(items_) - 1)]
            collection.donate(state, it)
            if not collection.donatable(state):
                ui.pop()
            else:
                self.sel = min(self.sel, len(collection.donatable(state)) - 1)


class JournalScreen(Screen):
    def __init__(self) -> None:
        self.tab = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_journal(con, ui.state, self.tab)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd in ("cancel", "journal", "quit"):
            ui.pop()
        elif cmd == "move" and action[1]:
            self.tab = (self.tab + action[1]) % len(rendering._JOURNAL_TABS)


class RelationsScreen(Screen):
    def __init__(self) -> None:
        self.scroll = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_relationships(con, ui.state, self.scroll)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd in ("cancel", "relations", "quit"):
            ui.pop()
        elif cmd == "move" and action[2]:
            self.scroll = max(0, self.scroll + action[2])


class CharacterScreen(Screen):
    def render(self, ui: UI, con) -> None:
        rendering.render_character(con, ui.state)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd in ("cancel", "character", "quit"):
            ui.pop()


class LogScreen(Screen):
    """Full scrollback of the message log."""

    def __init__(self) -> None:
        self.scroll = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_message_log(con, ui.state, self.scroll)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd in ("cancel", "messages", "quit"):
            ui.pop()
        elif cmd == "move" and action[2]:
            self.scroll = max(0, self.scroll - action[2])   # up = older


class CharGenScreen(Screen):
    """Character generation: the midwives roll your birth sign and your eight
    attributes (3d6 apiece). Roll another life at will; no escape — a birth is
    not a menu you can back out of."""
    def __init__(self) -> None:
        self.ctx = self._roll()

    @staticmethod
    def _roll() -> dict:
        import random as _r
        from .data.content import ZODIAC
        from .game import attrs as A
        return {"sign": _r.choice(ZODIAC)[0], "attrs": A.roll(_r)}

    def render(self, ui: UI, con) -> None:
        rendering.render_chargen(con, ui.state, self.ctx)

    def on_raw(self, ui: UI, event) -> bool:
        # r rerolls the whole life (sign and attributes together)
        if not isinstance(event, tcod.event.KeyDown) or (event.mod & tcod.event.Modifier.SHIFT):
            return False
        s = int(event.sym)
        ch = chr(s) if 0x20 <= s <= 0x7E else ""
        if ch == "r":
            self.ctx = self._roll()
            return True
        return False

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        from .data.content import ZODIAC
        state = ui.state
        if cmd == "confirm":
            self._accept(state)
            ui.pop()

    def _accept(self, state) -> None:
        from .data.content import ZODIAC
        p = state.player
        p.sign = self.ctx["sign"]
        p.attrs = dict(self.ctx["attrs"])
        # the one-time constitutions: Toughness, and the sturdy/starlit signs
        to_mod = p.attrs.get("To", 10) - 10
        p.max_hp = max(20, p.max_hp + to_mod)
        p.hp = p.max_hp
        if p.sign == "star":
            p.max_energy += 12
            p.energy += 12
        elif p.sign == "oak":
            p.max_hp += 6
            p.hp += 6
        sid, name, _g, told, boon = next(z for z in ZODIAC if z[0] == p.sign)
        state.log.add(f"You were born under {name} — {told}. ({boon})", (232, 216, 150))


class IntroScreen(Screen):
    """The opening page for a new game — the premise and the core controls.
    Any key steps onto the farm."""

    def render(self, ui: UI, con) -> None:
        rendering.render_intro(con, ui.state)

    def on_raw(self, ui: UI, event) -> bool:
        if isinstance(event, tcod.event.KeyDown):
            ui.pop()
            return True
        return False


class ConfirmScreen(Screen):
    """A yes/no gate for an action that can't easily be undone. ``on_yes(ui)``
    runs on confirm; either way the prompt closes."""

    def __init__(self, title: str, prompt: str, on_yes, detail: str = "") -> None:
        self.title, self.prompt, self.on_yes, self.detail = title, prompt, on_yes, detail

    def render(self, ui: UI, con) -> None:
        rendering.render_confirm(con, ui.state, self.title, self.prompt, self.detail)

    def _yes(self, ui: UI) -> None:
        ui.pop()
        self.on_yes(ui)

    def on_raw(self, ui: UI, event) -> bool:
        if isinstance(event, tcod.event.KeyDown):
            s = int(event.sym)
            ch = chr(s).lower() if 0x20 <= s <= 0x7E else ""
            if ch == "y":
                self._yes(ui)
                return True
            if ch == "n":
                ui.pop()
                return True
        return False

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd == "confirm":
            self._yes(ui)
        elif cmd in ("cancel", "quit", "quitgame"):
            ui.pop()


class QuitScreen(Screen):
    def render(self, ui: UI, con) -> None:
        rendering.render_quit(con, ui.state)

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        if cmd == "cancel":
            ui.pop()                         # Esc — keep playing
        elif cmd in ("sleep", "confirm", "quitgame"):  # S / Enter / Q — save & quit
            ui.running = False               # (Q is safe so a reflexive qq can't lose the day)
        elif cmd == "discard":               # Backspace — quit WITHOUT saving
            ui.save_on_exit = False
            ui.running = False


class CheatScreen(Screen):
    """The hidden Konami menu: toggles, windfalls, and far-place teleports."""

    def __init__(self) -> None:
        self.sel = 0

    def render(self, ui: UI, con) -> None:
        rendering.render_cheats(con, ui.state, self.sel, cmds._cheat_locations(ui.state))

    def handle(self, ui: UI, cmd: str, action: tuple) -> None:
        state = ui.state
        locs = cmds._cheat_locations(state)
        n = 4 + len(locs)
        if cmd in ("cancel", "quitgame"):
            ui.close_overlays()
        elif cmd == "move" and action[2]:
            self.sel = (self.sel + action[2]) % n
        elif cmd == "confirm":
            if self.sel == 0:
                state.cheats["freeze_hp"] = not state.cheats.get("freeze_hp")
            elif self.sel == 1:
                state.cheats["freeze_stamina"] = not state.cheats.get("freeze_stamina")
            elif self.sel == 2:
                state.player.gold += 1000
                state.log.add("A purse of 1000g appears.", (244, 216, 110))
            elif self.sel == 3:
                for mat in (items.WOOD, items.STONE, items.TIMBER_PLANK,
                            items.COPPER_BAR, items.BEESWAX):
                    state.player.inventory.add(mat, 100)
                state.log.add("Building materials rain down (+100 each).", (200, 200, 240))
            else:
                cmds._cheat_go(state, locs[self.sel - 4][1])
                state.log.add("You blink across the Vale.", (200, 180, 240))
                ui.close_overlays()


class FishingScreen(Screen):
    """The reel-it-in minigame: real-time, driven by held ←/→ arrows. It
    swallows every event so nothing leaks into the normal command mapping."""

    LEFT_KEYS = (tcod.event.KeySym.LEFT, tcod.event.KeySym.KP_4)
    RIGHT_KEYS = (tcod.event.KeySym.RIGHT, tcod.event.KeySym.KP_6)

    def __init__(self, ctx: dict) -> None:
        self.ctx = ctx
        self.reel_left = False
        self.reel_right = False

    def render(self, ui: UI, con) -> None:
        rendering.render_fishing(con, ui.state, self.ctx)

    def tick(self, ui: UI) -> None:
        move_dir = (-1 if (self.reel_left and not self.reel_right)
                    else (1 if (self.reel_right and not self.reel_left) else 0))
        res = fishing.update(ui.state, self.ctx, move_dir)
        if res != "running":
            fishing.resolve(ui.state, self.ctx, caught=(res == "caught"))
            self._close(ui)
            cmds.check_faint(ui.state)
            quests.check(ui.state)

    def _close(self, ui: UI) -> None:
        ui.pop()
        # For a beat after the minigame closes, swallow keypresses so a
        # still-held ←/→ (or the key that landed the fish) doesn't send the
        # player walking off unintentionally.
        ui.input_lock_until = time.monotonic() + 0.35

    def on_raw(self, ui: UI, event) -> bool:
        if isinstance(event, tcod.event.KeyDown):
            if event.sym in self.LEFT_KEYS:
                self.reel_left = True
            elif event.sym in self.RIGHT_KEYS:
                self.reel_right = True
            elif event.sym == tcod.event.KeySym.ESCAPE:   # cut the line
                fishing.resolve(ui.state, self.ctx, caught=False)
                self._close(ui)
        elif isinstance(event, tcod.event.KeyUp):
            if event.sym in self.LEFT_KEYS:
                self.reel_left = False
            elif event.sym in self.RIGHT_KEYS:
                self.reel_right = False
        return True          # nothing leaks through while the rod is bent
