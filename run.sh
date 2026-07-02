#!/usr/bin/env bash
# Linux/macOS terminal launcher. Needs Python 3 installed.
cd "$(dirname "$0")" || exit 1
[ -d .venv ] || python3 -m venv .venv || { echo "Python 3 is required."; exit 1; }
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -r requirements.txt
exec ./.venv/bin/python -m hearthdelve
