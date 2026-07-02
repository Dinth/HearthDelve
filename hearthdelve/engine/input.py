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

# Top-row digits 1..9 -> hotbar slot index 0..8.
_SLOTS = {
    K.N1: 0, K.N2: 1, K.N3: 2, K.N4: 3, K.N5: 4,
    K.N6: 5, K.N7: 6, K.N8: 7, K.N9: 8,
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
    if sym in _SLOTS:
        return ("slot", _SLOTS[sym])
    if sym == K.l:
        return ("look",)
    if sym == K.g:
        return ("grab",)
    if sym == K.p:
        return ("place",)
    if sym == K.s:
        return ("sleep",)
    if sym == K.c:
        return ("craft",)
    if sym == K.b:
        return ("ship",)
    if sym == K.t:
        return ("talk",)
    if sym == K.f:
        return ("gift",)
    if sym == K.w:
        return ("runprefix",)
    if sym == K.a:
        return ("ability",)
    if sym == K.i:
        return ("inventory",)
    if sym == K.e:
        return ("equipment",)
    if sym == K.j:
        return ("journal",)
    if sym == K.r:
        return ("relations",)
    if sym == K.v:
        return ("character",)
    # '?' is its own keysym; also accept shift+'/' for robustness.
    if sym == K.QUESTION or (sym == K.SLASH and event.mod & tcod.event.Modifier.SHIFT):
        return ("help",)
    if sym == K.q:
        return ("quitgame",)
    if sym == K.x:
        return ("eat",)
    if sym == K.ESCAPE:
        return ("cancel",)
    return None


def event_to_action(event: tcod.event.Event):
    if isinstance(event, tcod.event.Quit):
        return ("quit",)
    if isinstance(event, tcod.event.KeyDown):
        action = _sym_to_action(event)
        if action is None:
            return None
        # Drop OS key-repeat for discrete actions so a held key fires once.
        if getattr(event, "repeat", False) and action[0] not in _REPEATABLE:
            return None
        return action
    return None
