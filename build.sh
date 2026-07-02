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
"$PY" -m PyInstaller --noconfirm --onefile --name hearthdelve --collect-all tcod play.py

echo
echo "Done. Standalone executable: dist/hearthdelve"
echo "Send that single file to testers — no Python needed (same OS only)."
