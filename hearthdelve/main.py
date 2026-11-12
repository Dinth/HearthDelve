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


def fresh_seed() -> int:
    """The seed for a brand-new vale: ``$HEARTHDELVE_SEED`` when set (to share
    a world, or replay one), else drawn from the system's entropy — so each new
    life gets its own map, weather and deeps. Kept under a million: plenty of
    vales, and comfortably inside every seeded generator's range."""
    wanted = os.environ.get("HEARTHDELVE_SEED", "").strip()
    if wanted.lstrip("-").isdigit():
        return abs(int(wanted)) % 1_000_000 or 1
    import random
    return random.SystemRandom().randrange(1, 1_000_000)


def new_game(seed: int | None = None) -> GameState:
    if seed is None:
        seed = fresh_seed()
    world = worldgen.generate(seed)
    sx, sy = world.spawn
    player = Player(x=sx, y=sy)
    state = GameState(world=world, player=player, log=MessageLog(), seed=seed)
    state.surface = world
    farming.init_weather(state)
    farming.prime_seasonal_flora(state)     # bloom the opening season's flora

    state.log.add("A letter from your grandfather: the old farm is yours now.", (236, 226, 180))
    state.log.add(f"You wake in Hollowmere Vale. {state.date_str()}, {state.weather.lower()}.", C.WHITE)
    state.log.add("Hoe (1) the soil, plant seeds (7), water them (2), then sleep (s).", C.DIM)
    state.log.add("Chop/mine for materials, c to craft & build, b at the bin to sell.", C.DIM)
    state.log.add("Space uses the active tool. ? for help, l to look, g to gather.", C.DIM)
    state.log.add("Visit Mossford (SE) & Cinderhope (SW): Shift+C to talk/shop, f to gift.", C.DIM)
    state.log.add("Villagers pin favours to the ‡ notice board on each square — g to read.", C.DIM)
    state.chargen_pending = True   # a fresh game opens on the intro page (see open_screens)
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
            state, restored = save.load_or_backup()
            state.log.add("Welcome back to Hollowmere Vale.", (236, 226, 180))
            if restored:
                state.log.add("Your save file couldn't be read, so yesterday morning's "
                              "backup was restored — the broken file is kept beside it.",
                              (240, 180, 120))
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
    save.arm()               # this is the game itself: the real save is ours to write
    tileset = font.load_tileset(16)
    state = load_or_new()
    console = tcod.console.Console(C.SCREEN_W, C.SCREEN_H, order="F")

    # Headless smoke test, for build machines with no display: the font and
    # every module the packaged build bundles load, a world is generated and
    # one frame is drawn — the parts a broken package fails at — without
    # opening a window.
    if os.environ.get("HEARTHDELVE_SMOKETEST") == "headless":
        rendering.render_all(console, state, 0.0)
        print("smoketest ok")
        return

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
        open_screens(ui)
        try:
            run_guarded(ui, lambda: _loop(ui, state, console, context, music))
        finally:
            music.stop()


def open_screens(ui) -> None:
    """A life not yet begun — a fresh game, or one closed before the midwives
    finished — opens on the intro page, with character creation beneath it
    (the midwives roll your stars and attributes). Only accepting a life clears
    ``chargen_pending``, so quitting partway resumes here next launch."""
    if ui.state.chargen_pending:
        ui.push(screens.CharGenScreen())
        ui.push(screens.IntroScreen())


AUTO_STEP = 1.0 / 30.0      # real seconds between steps of a run, a rest, a long job


class Beat:
    """A steady clock for real-time work. The loop turns once per frame AND
    once per input event, so stepping a run on every turn of it made the run
    as fast as the events arriving: moving the mouse over the window doubled a
    run's pace on a 60Hz screen and quadrupled it on a 120Hz one."""

    def __init__(self, step: float = AUTO_STEP) -> None:
        self.step, self.next = step, None

    def due(self, now: float) -> bool:
        if self.next is not None and now < self.next:
            return False
        # Keep the cadence when the loop is quick; don't bank steps when it's slow.
        behind = self.next is None or now - self.next > self.step
        self.next = now + self.step if behind else self.next + self.step
        return True


def _loop(ui, state: GameState, console, context, music) -> None:
    """Advance the top screen, render, route events — until the UI stops."""
    konami: list = []        # rolling buffer of recent keys
    start = time.perf_counter()
    beat = Beat()
    while ui.running:
        anim_time = time.perf_counter() - start

        # Cheats: hold health / stamina pinned to full while frozen.
        if state.cheats.get("freeze_hp"):
            state.player.hp = state.player.max_hp
        if state.cheats.get("freeze_stamina"):
            state.player.energy = state.player.max_energy

        # Real-time work on the active screen: an in-progress run, rest or
        # long tool action on the world; the fishing minigame's physics. On
        # the beat, not on every pass: a pass also runs for each input event.
        if beat.due(time.perf_counter()):
            ui.top.tick(ui)

        rendering.render_all(console, state, anim_time)
        ui.top.render(ui, console)
        context.present(console)

        # A short timeout drives the ambient animation: when no key is
        # pressed, wait() returns after ~1/30s and we redraw the next frame.
        for event in tcod.event.wait(timeout=1.0 / 30.0):
            if not route_event(ui, event, konami):
                break


def route_event(ui, event, konami: list) -> bool:
    """Route one input event, exactly as the main loop does: the window
    closing, the Konami code, the top screen's raw pre-pass, the post-fishing
    lockout, a key press interrupting a run or rest, then the key map's
    action — the few that work from any screen (quit, mute) here, the rest
    handed to the top screen. ``konami`` is the loop's rolling buffer of
    recent keys. Returns False when the game is closing and the rest of this
    batch of events should be dropped. (Out of the loop so tests can press
    real keys through the same path.)"""
    state = ui.state
    # The window's close button stops the game and saves it on the way out.
    # tcod 21 names this event "WindowClose" (older builds said "WINDOWCLOSE"),
    # and checking only the old name meant it never matched: closing the window
    # fell through to the OS quit that follows it, which leaves WITHOUT saving,
    # and the day since the morning's autosave was lost.
    if isinstance(event, tcod.event.WindowEvent) and event.type in ("WindowClose", "WINDOWCLOSE"):
        ui.running = False
        return False

    # Konami code (↑↑↓↓←→←→ B A) opens the hidden cheat menu.
    if isinstance(event, tcod.event.KeyDown):
        konami.append(int(event.sym))
        del konami[:-len(_KONAMI)]
        if konami == _KONAMI:
            konami.clear()
            ui.open_cheats()
            state.log.add("A hidden door creaks open...", (250, 230, 140))
            return True

    # The screen's raw pre-pass: the fishing rod's held arrows, the
    # inventory/equipment letter namespaces.
    if ui.top.on_raw(ui, event):
        return True

    # For a beat after the fishing minigame closes, swallow presses
    # so a still-held arrow doesn't send the player walking off.
    if isinstance(event, tcod.event.KeyDown) and time.monotonic() < ui.input_lock_until:
        return True

    # A fresh key press interrupts an in-progress run or rest — but
    # NOT OS key-repeat from still holding the direction that began
    # the run, which would cancel it almost immediately.
    if (isinstance(event, tcod.event.KeyDown) and not getattr(event, "repeat", False)
            and ui.play.cancel_auto()):
        return True

    action = game_input.event_to_action(event)
    if action is None:
        return True
    cmd = action[0]

    # OS quit (Cmd+Q / window close via SDL): leave immediately
    # without saving, from any screen.
    if cmd == "sysquit":
        ui.save_on_exit = False
        ui.running = False
        return False

    # Mute / unmute the music from any screen (Shift+U).
    if cmd == "mutemusic":
        if ui.music is not None:
            off = ui.music.toggle_mute()
            state.log.add("Music muted." if off else "Music on.", C.DIM)
        return True

    ui.top.handle(ui, cmd, action)
    return True


def run_guarded(ui, loop) -> None:
    """Run the main loop and keep the day however it ends — the window closing,
    Ctrl+C in the terminal, or a bug raising out of some screen. The game saves
    on the way out unless the player chose to quit without saving; the previous
    save rotates into ``.bak`` as always, so a bad rescue still has a fallback.
    A crash also leaves a report beside the save (packaged builds launched from
    a file manager have no console to read a traceback from), then re-raises."""
    crash: Exception | None = None
    try:
        loop()
    except Exception as exc:
        crash = exc
        raise
    finally:
        save_error = None
        if ui.save_on_exit:
            try:
                save.save(ui.state)
            except Exception as e:  # noqa: BLE001 - report it, never mask the crash
                save_error = e
                print(f"Could not save game: {e}", file=sys.stderr)
        if crash is not None:
            report = write_crash_report(crash, ui.save_on_exit, save_error)
            kept = ("Nothing was saved (you chose to quit without saving)." if not ui.save_on_exit
                    else "Your game could NOT be saved." if save_error
                    else "Your game was saved on the way out.")
            print(f"Hearthdelve crashed. {kept}"
                  + (f" Details: {report}" if report else ""), file=sys.stderr)


def crash_report_path() -> str:
    """The crash log lives beside the save (``…_save.json.crash.log``)."""
    return save.default_path() + ".crash.log"


def write_crash_report(exc: BaseException, tried_save: bool, save_error) -> str | None:
    """Append the traceback, with when and where it ran, to the crash log.
    Returns its path, or None if even that couldn't be written."""
    import datetime
    import platform
    import traceback
    path = crash_report_path()
    if not tried_save:
        outcome = "The player had chosen to quit without saving; nothing was saved."
    elif save_error is not None:
        outcome = f"The rescue save FAILED: {save_error!r}"
    else:
        outcome = "The game was saved on the way out (the previous save is in .bak)."
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"=== {datetime.datetime.now().isoformat(timespec='seconds')} · "
                    f"Python {platform.python_version()} · {platform.platform()}\n")
            f.write("".join(traceback.format_exception(exc)))
            f.write(outcome + "\n\n")
        return path
    except OSError:
        return None


if __name__ == "__main__":
    main()
