"""A signpost and a notice board don't look alike."""
from __future__ import annotations

import unittest


class TestTheyAreToldApart(unittest.TestCase):
    """Both were drawn as a tan double dagger; the help and the opening
    message call the board by that glyph, so the signpost takes another."""

    def test_the_glyphs_differ(self):
        from hearthdelve.world import tile
        self.assertNotEqual(tile.TILES[tile.SIGNPOST].glyph, tile.TILES[tile.NOTICE_BOARD].glyph)
        self.assertEqual(tile.TILES[tile.NOTICE_BOARD].glyph, "‡")

    def test_the_font_can_draw_it(self):
        from hearthdelve.engine import font
        from hearthdelve.world import tile
        ts = font.load_tileset(16)
        self.assertTrue(ts.get_tile(ord(tile.TILES[tile.SIGNPOST].glyph)).any())


if __name__ == "__main__":
    unittest.main()
