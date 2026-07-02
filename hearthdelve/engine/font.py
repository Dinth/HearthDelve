"""Tileset loading.

tcod ships no default font, so we rasterize a monospace TTF into a 16x16
tileset. We prefer a font bundled with the game (so a packaged build is fully
self-contained), then fall back to common system monospace fonts on macOS,
Windows, and Linux.
"""
from __future__ import annotations

import os
import sys

import tcod.tileset


def _base_dir() -> str:
    # PyInstaller unpacks bundled data under sys._MEIPASS.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_CANDIDATES = (
    # a font shipped alongside the game (optional — drop one in assets/)
    os.path.join(_base_dir(), "assets", "font.ttf"),
    os.path.join(_base_dir(), "hearthdelve", "assets", "font.ttf"),
    # macOS
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Monaco.ttf",
    "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
    # Windows
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\lucon.ttf",
    r"C:\Windows\Fonts\cour.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
)


def load_tileset(size: int = 16) -> tcod.tileset.Tileset:
    last_err: Exception | None = None
    for path in _CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            return tcod.tileset.load_truetype_font(path, size, size)
        except Exception as e:  # noqa: BLE001 - try the next font
            last_err = e
            continue
    raise RuntimeError(
        "No usable monospace font found. Drop a .ttf at assets/font.ttf "
        f"to bundle one. Last error: {last_err}"
    )
