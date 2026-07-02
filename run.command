#!/bin/bash
# Double-click on macOS (or run: bash run.command). Needs Python 3 installed.
# Creates a local virtual environment, installs deps, and launches the game.
cd "$(dirname "$0")" || exit 1
if [ ! -d .venv ]; then
    echo "Setting up (first run only)…"
    python3 -m venv .venv || { echo "Python 3 is required."; read -r; exit 1; }
fi
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -r requirements.txt
./.venv/bin/python -m hearthdelve
