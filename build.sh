#!/usr/bin/env bash
# Build a standalone, self-contained executable of Hearthdelve with PyInstaller.
# Output: dist/hearthdelve (or dist\hearthdelve.exe on Windows).
set -e
cd "$(dirname "$0")"

PY=./.venv/bin/python
[ -x "$PY" ] || PY=python3

echo "Ensuring build deps…"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt pyinstaller

echo "Building…"
# Bundle the game font if present, so the binary renders every glyph regardless
# of the host's installed system fonts.
FONT_ARG=()
if [ -f hearthdelve/assets/font.ttf ]; then
    FONT_ARG=(--add-data "hearthdelve/assets/font.ttf:hearthdelve/assets")
    echo "  (bundling hearthdelve/assets/font.ttf)"
fi
"$PY" -m PyInstaller --noconfirm --onefile --name hearthdelve --collect-all tcod "${FONT_ARG[@]}" play.py

echo
echo "Done. Standalone executable: dist/hearthdelve"
echo "Send that single file to testers — no Python needed (same OS only)."
