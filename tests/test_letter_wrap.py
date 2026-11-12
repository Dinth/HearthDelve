"""A letter in the post box is shown whole."""
from __future__ import annotations

import unittest

import tcod.console

from tests.common import fresh_state


def _con():
    return tcod.console.Console(80, 50, order="F")


def _text(con) -> str:
    return "\n".join("".join(chr(c) for c in con.ch[:, y]) for y in range(con.height))


def _flat(s: str) -> str:
    return " ".join(s.replace("│", " ").split())


class TestALetterIsReadInFull(unittest.TestCase):
    """The post box cut each line of a letter at the window's edge."""

    def test_a_long_line_wraps(self):
        from hearthdelve.engine import rendering
        st = fresh_state(31)
        line = ("The Lighthouse is finished, and the whole village turned out to see the lamp "
                "lit; from tonight the sea gives up finer fish and the moonfish rise.")
        st.mail.append({"sender": "Saltmere", "body": "Friend,\n" + line, "items": []})
        con = _con()
        rendering.render_mail(con, st, len(st.mail) - 1)
        self.assertIn(line, _flat(_text(con)))

    def test_every_project_s_letter_shows_its_whole_perk(self):
        from hearthdelve.data import content
        from hearthdelve.engine import rendering
        from hearthdelve.game import projects
        for pid, d in content.PROJECTS.items():
            st = fresh_state(31)
            st.mail.clear()
            st.mail.append(projects.completion_letter(d))
            con = _con()
            rendering.render_mail(con, st, 0)
            with self.subTest(project=pid):
                self.assertIn(_flat(d.perk), _flat(_text(con)))

    def test_a_very_long_letter_still_fits_the_screen(self):
        from hearthdelve.engine import rendering
        st = fresh_state(31)
        for i in range(12):
            st.mail.append({"sender": f"Neighbour {i}", "body": "Hello.", "items": []})
        st.mail.append({"sender": "A windbag", "items": [],
                        "body": "\n".join(f"Line {i} of a very long letter." for i in range(60))})
        con = _con()
        rendering.render_mail(con, st, len(st.mail) - 1)   # must not draw off the console
        text = _text(con)
        self.assertIn("Line 0 of a very long letter.", text)
        self.assertIn("…", text)
        self.assertIn("Esc close", text)


if __name__ == "__main__":
    unittest.main()
