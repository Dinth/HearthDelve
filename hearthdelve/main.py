"""Hearthdelve — entry point and main loop.

The loop itself stays thin: it advances the topmost screen, renders, and
routes events. Everything stateful lives elsewhere — player commands in
game/commands.py, the per-mode UI in screens.py.
"""
from __future__ import annotations

import os
import sys
import time

import tcod.console
import tcod.context
import tcod.event

from . import screens
from .engine import audio
from .engine import constants as C
from .engine import font, input as game_input, rendering, save
from .entities.player import Player
from .game import farming
from .game.state import GameState, MessageLog
from .world import worldgen


def new_game(seed: int = 1337) -> GameState:
    world = worldgen.generate(seed)
    sx, sy = world.spawn
    player = Player(x=sx, y=sy)
    state = GameState(world=world, player=player, log=MessageLog(), seed=seed)
    state.surface = world
    farming.init_weather(state)
    farming.prime_seasonal_flora(state)     # bloom the opening season's flora

    state.log.add("A letter from your grandfather: the old farm is yours now.", (236, 226, 180))
    state.log.add(f"You wake in Hollowmere Vale. {state.date_str()}, {state.weather.lower()}.", C.WHITE)
    state.log.add("Hoe (1) the soil, plant seeds (6), water them (2), then sleep (s).", C.DIM)
    state.log.add("Chop/mine for materials, c to craft & build, b at the bin to sell.", C.DIM)
    state.log.add("Space uses the active tool. ? for help, l to look, g to gather.", C.DIM)
    state.log.add("Visit Mossford (SE) & Cinderhope (SW): Shift+C to talk/shop, f to gift.", C.DIM)
    state.log.add("Villagers pin favours to the ‡ notice board on each square — g to read.", C.DIM)
    state.intro_pending = True     # a fresh game opens on the intro page (see main)
    return state


# Stored as plain ints (SDL keycodes) so this doesn't depend on whether the
# installed tcod names letter keys KeySym.a (older) or KeySym.A (newer/Windows).
_K = tcod.event.KeySym
_KONAMI = [int(_K.UP), int(_K.UP), int(_K.DOWN), int(_K.DOWN),
           int(_K.LEFT), int(_K.RIGHT), int(_K.LEFT), int(_K.RIGHT),
           ord("b"), ord("a")]


def load_or_new() -> GameState:
    """Continue a saved game if one exists (unless '--new' was passed)."""
    if "--new" in sys.argv:
        save.delete()
        return new_game()
    if save.exists():
        try:
            state = save.load()
            state.log.add("Welcome back to Hollowmere Vale.", (236, 226, 180))
            state.log.add(f"{state.date_str()}, {state.weather.lower()}. (auto-saves each morning)", C.DIM)
            return state
        except save.IncompatibleSaveError:
            # A version mismatch shouldn't look like a mysterious fresh farm: keep
            # the old save aside and tell the player, in-game, why they're starting over.
            bak = save.backup()
            state = new_game()
            state.log.add("Your saved game is from a different version of Hearthdelve and "
                          "can't be opened by this build.", (240, 180, 120))
            state.log.add((f"The old save is kept safe at {bak}." if bak
                           else "The old save was left untouched.")
                          + " A fresh vale begins.", C.DIM)
            return state
        except Exception as e:  # noqa: BLE001 - corrupt save -> fresh start
            # Never let the morning autosave silently clobber a save we couldn't
            # read: set the old one aside first.
            bak = save.backup()
            where = f" (kept a copy at {bak})" if bak else ""
            print(f"Could not load save ({e}); starting a new game{where}.")
    return new_game()


def main() -> None:
    tileset = font.load_tileset(16)
    state = load_or_new()
    console = tcod.console.Console(C.SCREEN_W, C.SCREEN_H, order="F")

    with tcod.context.new(
        columns=C.SCREEN_W,
        rows=C.SCREEN_H,
        tileset=tileset,
        title="Hearthdelve — Hollowmere Vale",
        vsync=True,
    ) as context:
        # Headless smoke test (used to validate packaged builds): draw one
        # frame, present it, and exit successfully.
        if os.environ.get("HEARTHDELVE_SMOKETEST"):
            rendering.render_all(console, state, 0.0)
            context.present(console)
            print("smoketest ok")
            return

        # Background music: a looping chiptune, synthesised on start. Silent if
        # the machine has no audio device (start() swallows that).
        music = audio.Music()
        music.start()

        ui = screens.UI(state, music)
        if getattr(state, "intro_pending", False):
            state.intro_pending = False
            # A fresh life: the intro reads first, then the midwives ask your stars
            # (the zodiac sits under the intro on the stack).
            ui.push(screens.ZodiacScreen())
            ui.push(screens.IntroScreen())
        konami: list = []        # rolling buffer of recent keys
        start = time.perf_counter()
        while ui.running:
            anim_time = time.perf_counter() - start

            # Cheats: hold health / stamina pinned to full while frozen.
            if state.cheats.get("freeze_hp"):
                state.player.hp = state.player.max_hp
            if state.cheats.get("freeze_stamina"):
                state.player.energy = state.player.max_energy

            # Real-time work on the active screen: an in-progress run, rest or
            # long tool action on the world; the fishing minigame's physics.
            ui.top.tick(ui)

            rendering.render_all(console, state, anim_time)
            ui.top.render(ui, console)
            context.present(console)

            # A short timeout drives the ambient animation: when no key is
            # pressed, wait() returns after ~1/30s and we redraw the next frame.
            for event in tcod.event.wait(timeout=1.0 / 30.0):
                if isinstance(event, tcod.event.WindowEvent) and event.type == "WINDOWCLOSE":
                    ui.running = False
                    break

                # Konami code (↑↑↓↓←→←→ B A) opens the hidden cheat menu.
                if isinstance(event, tcod.event.KeyDown):
                    konami.append(int(event.sym))
                    del konami[:-len(_KONAMI)]
                    if konami == _KONAMI:
                        konami.clear()
                        ui.open_cheats()
                        state.log.add("A hidden door creaks open...", (250, 230, 140))
                        continue

                # The screen's raw pre-pass: the fishing rod's held arrows, the
                # inventory/equipment letter namespaces.
                if ui.top.on_raw(ui, event):
                    continue

                # For a beat after the fishing minigame closes, swallow presses
                # so a still-held arrow doesn't send the player walking off.
                if isinstance(event, tcod.event.KeyDown) and time.monotonic() < ui.input_lock_until:
                    continue

                # A fresh key press interrupts an in-progress run or rest — but
                # NOT OS key-repeat from still holding the direction that began
                # the run, which would cancel it almost immediately.
                if (isinstance(event, tcod.event.KeyDown) and not getattr(event, "repeat", False)
                        and ui.play.cancel_auto()):
                    continue

                action = game_input.event_to_action(event)
                if action is None:
                    continue
                cmd = action[0]

                # OS quit (Cmd+Q / window close via SDL): leave immediately
                # without saving, from any screen.
                if cmd == "sysquit":
                    ui.save_on_exit = False
                    ui.running = False
                    break

                # Mute / unmute the music from any screen (Shift+M).
                if cmd == "mutemusic":
                    off = music.toggle_mute()
                    state.log.add("Music muted." if off else "Music on.", C.DIM)
                    continue

                ui.top.handle(ui, cmd, action)

        music.stop()

        # Save on exit (unless the player chose to quit without saving).
        if ui.save_on_exit:
            try:
                save.save(state)
            except Exception as e:  # noqa: BLE001
                print(f"Could not save game: {e}")


if __name__ == "__main__":
    main()
