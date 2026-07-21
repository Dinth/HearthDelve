"""Keyboard -> action mapping.

Movement is arrow keys (4-way) and the numeric keypad (8-way, with keypad-5
to wait). Letter keys are reserved for commands.

Actions are tiny tuples consumed by the main loop:
  ("move", dx, dy) · ("wait",) · ("look",) · ("help",) · ("inventory",)
  ("equipment",) · ("slot", n) · ("cancel",) · ("quit",)
"""
from __future__ import annotations

import tcod.event

K = tcod.event.KeySym

# Arrow keys: cardinal movement only.
_ARROWS: dict = {
    K.UP: (0, -1),
    K.DOWN: (0, 1),
    K.LEFT: (-1, 0),
    K.RIGHT: (1, 0),
}

# Numeric keypad: full 8-direction movement (and 5 = wait).
_KEYPAD: dict = {
    K.KP_8: (0, -1), K.KP_2: (0, 1), K.KP_4: (-1, 0), K.KP_6: (1, 0),
    K.KP_7: (-1, -1), K.KP_9: (1, -1), K.KP_1: (-1, 1), K.KP_3: (1, 1),
}

_MOVE = {**_ARROWS, **_KEYPAD}

_WAIT = {K.KP_5, K.PERIOD}

# Letter commands, matched by CHARACTER (not KeySym attribute) so they work
# whether this tcod build names letter keys KeySym.a (older) or KeySym.A
# (newer/SDL3 on Windows). Top-row digits 1-9 select hotbar slots.
_LETTER_CMD = {
    "l": ("look",), "g": ("grab",), "p": ("place",), "s": ("sleep",),
    "c": ("craft",), "b": ("ship",), "t": ("target",), "f": ("gift",),
    "w": ("runprefix",), "i": ("inventory",), "m": ("worldmap",),
    "h": ("messages",), "d": ("drop",), "e": ("equipment",),
    "j": ("journal",), "r": ("relations",), "v": ("character",),
    "q": ("quitgame",), "x": ("eat",),
}


# Actions that may safely auto-repeat when a key is held (walking, waiting).
# Everything else — especially sleep — must require a fresh key press, or a
# held key would fire many times (e.g. sleeping weeks ahead in one go).
_REPEATABLE = {"move", "wait"}


def _sym_to_action(event: tcod.event.KeyDown):
    sym = event.sym
    shift = bool(event.mod & tcod.event.Modifier.SHIFT)
    if sym in _MOVE:
        dx, dy = _MOVE[sym]
        return ("move", dx, dy)
    # '>' / '<' (shift+period / shift+comma) — must precede the wait handler
    if (sym == K.PERIOD and shift) or sym == getattr(K, "GREATER", object()):
        return ("descend",)
    if (sym == K.COMMA and shift) or sym == getattr(K, "LESS", object()):
        return ("ascend",)
    if sym in _WAIT:
        return ("wait",)
    if sym in (K.RETURN, K.KP_ENTER):
        return ("confirm",)
    if sym == K.SPACE:
        return ("use",)
    if sym == K.TAB:
        return ("swap",)         # in aim mode: toggle between loosing the bow and lobbing a bomb
    if sym == getattr(K, "PAGEUP", object()):
        return ("scroll", 1)     # page back through older messages / list rows
    if sym == getattr(K, "PAGEDOWN", object()):
        return ("scroll", -1)
    # '?' is its own keysym on some builds; also accept shift+'/' for robustness.
    if sym == getattr(K, "QUESTION", object()) or (sym == K.SLASH and shift):
        return ("help",)
    if sym == K.BACKSPACE:
        return ("discard",)
    if sym == K.ESCAPE:
        return ("cancel",)
    # Letters and digits by character value (version-proof across tcod builds).
    ch = chr(int(sym)) if 0x20 <= int(sym) <= 0x7E else ""
    if ch and ch in "123456789":
        return ("slot", int(ch) - 1)
    if ch == "0":
        return ("slot", 9)          # 10th hotbar slot / 10th equipment paperdoll slot
    if ch == "c" and shift:
        return ("talk",)             # Shift+C: chat with a villager / open a shop
    if ch == "m" and shift:
        return ("messages",)         # Shift+M: the full message history (also 'h')
    if ch == "u" and shift:
        return ("mutemusic",)        # Shift+U: mute / unmute the background music
    if ch in _LETTER_CMD:
        return _LETTER_CMD[ch]
    return None


def event_to_action(event: tcod.event.Event):
    if isinstance(event, tcod.event.Quit):
        return ("sysquit",)          # OS quit (Cmd+Q / window close): leave now
    if isinstance(event, tcod.event.KeyDown):
        action = _sym_to_action(event)
        if action is None:
            return None
        # Drop OS key-repeat for discrete actions so a held key fires once.
        if getattr(event, "repeat", False) and action[0] not in _REPEATABLE:
            return None
        return action
    return None
