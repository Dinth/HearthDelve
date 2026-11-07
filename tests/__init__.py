"""Test-package setup: runs before any test module imports the game.

Point the save file at a throwaway directory for the whole suite. Several tests
advance the day, and ``farming.new_day`` autosaves at dawn — without this, every
suite run overwrote the developer's real farm (``~/.hearthdelve_save.json``) and
its rolling ``.bak``. Always overridden, even if the variable is already set, so
a personal save location is never written to either.
"""
import atexit
import os
import shutil
import tempfile

_SAVE_DIR = tempfile.mkdtemp(prefix="hearthdelve-tests-")
os.environ["HEARTHDELVE_SAVE"] = os.path.join(_SAVE_DIR, "save.json")
atexit.register(shutil.rmtree, _SAVE_DIR, ignore_errors=True)
