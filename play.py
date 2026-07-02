"""Entry point for running or packaging the game.

    python play.py            # run from source
    pyinstaller ... play.py   # build a standalone executable
"""
from hearthdelve.main import main

if __name__ == "__main__":
    main()
