"""The menu widget kit: one modal skeleton instead of sixteen hand-rolled ones.

Every full-screen menu in the game is the same few parts — a centred framed
window, an optional scrolling list with a highlighted selection and ▲▼
overflow arrows, and a key-hint footer. This module owns that skeleton;
the render_* functions in rendering.py only paint their own row cells.

All Modal coordinates are window-relative: (0, 0) is the frame's top-left
corner, so layouts read as offsets into the window rather than screen math.
"""
from __future__ import annotations

from . import constants as C

BASE_BG = (20, 22, 32)     # a modal's resting background
SEL_BG = (54, 50, 36)      # the selected row's highlight bar
HDR = (236, 226, 180)      # section headers, frame titles, scroll arrows


def window(sel: int, total: int, height: int) -> tuple[int, int]:
    """First/last row index to show so `sel` stays visible in a `height`-row list."""
    if total <= height:
        return 0, total
    start = max(0, min(sel - height // 2, total - height))
    return start, start + height


def frame(con, x: int, y: int, w: int, h: int, title: str = "") -> None:
    """A single-line frame with its title centred on the top edge in inverted
    colours. tcod's own ``draw_frame(title=…)`` is deprecated — once it goes,
    every window would raise — so the title is printed here, cell for cell as
    tcod drew it (and a title too long for the frame no longer eats its
    corners)."""
    con.draw_frame(x, y, w, h, fg=HDR, bg=BASE_BG)
    if title:
        label = f" {title} "[:max(0, w - 2)]
        con.print(x + (w - len(label)) // 2, y, label, fg=BASE_BG, bg=HDR)


def wrap(text: str, width: int, indent: int = 0) -> list[str]:
    """Greedy word-wrap to `width` columns. Continuation lines are indented by
    `indent` spaces (still within `width`); a word too long for a line is
    split rather than allowed to run past it."""
    width = max(1, width)
    indent = min(indent, width - 1)
    lines: list[str] = []
    cur = ""

    def room() -> int:
        return width if not lines else width - indent

    def push(s: str) -> None:
        lines.append(s if not lines else " " * indent + s)

    for word in text.split():
        if cur and len(cur) + 1 + len(word) > room():
            push(cur)
            cur = ""
        while len(word) > room():
            r = room()
            push(word[:r])
            word = word[r:]
        cur = f"{cur} {word}" if cur else word
    if cur:
        push(cur)
    return lines


def wrap_parts(parts, width: int, sep: str = "  ") -> list[str]:
    """Join `parts` with `sep` into rows no wider than `width`, never breaking
    a part across rows (a tally like "Angler's 0/28" stays whole)."""
    rows: list[str] = []
    cur = ""
    for part in parts:
        if cur and len(cur) + len(sep) + len(part) > width:
            rows.append(cur)
            cur = part
        else:
            cur = f"{cur}{sep}{part}" if cur else part
    if cur:
        rows.append(cur)
    return rows


def wrap_messages(messages, width: int, indent: int = 2) -> list[tuple]:
    """Log messages as (line, colour) rows, each wrapped to `width` with its
    continuation lines indented — so no message is cut off at the edge."""
    return [(line, color) for text, color in messages
            for line in (wrap(text, width, indent) or [""])]


def log_tail(messages, width: int, rows: int, indent: int = 2) -> list[tuple]:
    """The newest `rows` wrapped lines of a log (wrapping only as far back as
    the rows need)."""
    out: list[tuple] = []
    for text, color in reversed(messages):
        out[:0] = [(line, color) for line in (wrap(text, width, indent) or [""])]
        if len(out) >= rows:
            break
    return out[-rows:] if rows > 0 else []


def cur(selected: bool) -> str:
    """The selection cursor prefix every list row carries."""
    return "▸ " if selected else "  "


class Modal:
    """A centred, framed window. Construction draws the frame; the helpers
    below fill it in window-relative coordinates."""

    def __init__(self, con, w: int, h: int, title: str) -> None:
        self.con = con
        self.w, self.h = w, h
        self.x = (C.SCREEN_W - w) // 2
        self.y = (C.SCREEN_H - h) // 2
        con.draw_rect(self.x, self.y, w, h, ch=ord(" "), fg=C.WHITE, bg=BASE_BG)
        frame(con, self.x, self.y, w, h, title)

    def text(self, dx: int, dy: int, s: str, fg=None, bg=None) -> None:
        self.con.print(self.x + dx, self.y + dy, s, fg=fg, bg=bg)

    def footer(self, s: str, fg=C.DIM) -> None:
        """The key-hint line on the frame's last interior row."""
        self.text(2, self.h - 2, s, fg=fg)

    def highlight(self, dy: int) -> None:
        """Paint the full-width selection bar under a row's cells."""
        self.con.draw_rect(self.x + 1, self.y + dy, self.w - 2, 1,
                           ch=ord(" "), bg=SEL_BG)

    def arrows(self, above: bool, below: bool, top: int, bottom: int,
               dx: int = -4, glyphs: tuple[str, str] = ("▲", "▼")) -> None:
        """Overflow markers: `above`/`below` say whether content continues past
        the visible window; `top`/`bottom` are the rows to mark."""
        if above:
            self.text(self.w + dx, top, glyphs[0], fg=HDR)
        if below:
            self.text(self.w + dx, bottom, glyphs[1], fg=HDR)

    def list(self, top: int, height: int, total: int, sel: int, draw_row,
             arrow_top: int | None = None, arrow_bottom: int | None = None,
             dx_arrow: int = -4, glyphs: tuple[str, str] = ("▲", "▼")) -> int:
        """The standard scrolling selection list: clamp the cursor, window the
        rows around it, paint the highlight bar, then hand each visible row to
        `draw_row(i, dy, selected, bg)` for its cells. Returns the clamped sel.
        """
        sel = max(0, min(sel, total - 1)) if total else 0
        start, end = window(sel, total, height)
        for r, i in enumerate(range(start, end)):
            dy = top + r
            selected = i == sel
            if selected:
                self.highlight(dy)
            draw_row(i, dy, selected, SEL_BG if selected else BASE_BG)
        if arrow_top is not None and arrow_bottom is not None:
            self.arrows(start > 0, end < total, arrow_top, arrow_bottom,
                        dx=dx_arrow, glyphs=glyphs)
        return sel
