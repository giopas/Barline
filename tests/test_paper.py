"""Paper charts (server/paper.py): the layout rules, without a server.

    python3 -m unittest tests.test_paper

Standard library only; the songs are the demo band's (demo/).
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import models  # noqa: E402
import paper  # noqa: E402

DEMO = os.path.join(ROOT, "demo")


def load_demo():
    with open(os.path.join(DEMO, "band.json"), encoding="utf-8") as f:
        band = json.load(f)
    songs = {}
    for name in sorted(os.listdir(os.path.join(DEMO, "songs"))):
        with open(os.path.join(DEMO, "songs", name), encoding="utf-8") as f:
            song = json.load(f)
        songs[song["id"]] = song
    setlists = []
    for name in sorted(os.listdir(os.path.join(DEMO, "setlists"))):
        with open(os.path.join(DEMO, "setlists", name), encoding="utf-8") as f:
            setlists.append(json.load(f))
    return band, songs, setlists


def page_streams(pdf: bytes) -> list:
    out = []
    for m in re.finditer(rb"<< /Length (\d+) /Filter /FlateDecode >>\nstream\n", pdf):
        out.append(zlib.decompress(pdf[m.end():m.end() + int(m.group(1))]).decode("latin-1"))
    return out


class PaperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.band, cls.songs, cls.setlists = load_demo()
        cls.by_title = {s["title"]: s for s in cls.songs.values()}
        cls.sam = next(p["id"] for p in cls.band["players"] if p["name"] == "Sam")

    def test_helvetica_metrics(self):
        # H e l l o in Helvetica: 722 + 556 + 222 + 222 + 556 thousandths of an em
        self.assertAlmostEqual(paper.text_width("Hello", 10), 22.78)
        self.assertGreater(paper.text_width("Hello", 10, "B"), paper.text_width("Hello", 10))
        self.assertEqual(paper.text_width("", 10), 0)

    def test_wrap_stays_inside_the_width_and_keeps_no_break_spaces(self):
        runs = [("Sam: ", "B", paper.INK), ("Double chorus, key change on bar 9, then hold " * 3, "R", paper.INK)]
        for width in (60, 140, 300):
            for line in paper.wrap_runs(runs, width, 10):
                self.assertLessEqual(sum(paper.text_width(t, 10, f) for t, f, _ in line), width + 0.01)
        lines = paper.wrap_runs([("tempo 62 BPM", "B", paper.INK)], paper.text_width("tempo 62", 10, "B"), 10)
        self.assertEqual([t for ln in lines for t, _, _ in ln], ["tempo", "62 BPM"])
        # a word longer than the line is broken, never loops
        self.assertTrue(paper.wrap_runs([("x" * 200, "R", paper.INK)], 30, 10))
        self.assertTrue(paper.wrap_runs([("abc", "R", paper.INK)], -5, 10))

    def test_text_is_escaped_and_encoded(self):
        self.assertEqual(paper._pdf_str("a(b)c\\"), "a\\(b\\)c\\\\")
        self.assertEqual(paper._pdf_str("caffè → ok"), "caffè -> ok")  # WinAnsi has è
        self.assertEqual(paper._pdf_str("漢"), "?")  # nothing to draw it with

    def test_fit_fills_the_page_and_floor_goes_bigger(self):
        for song in self.songs.values():
            fit_s, orient, cols = paper.resolve(song, self.band)
            self.assertEqual((orient, cols), ("portrait", 1))
            self.assertTrue(paper.FIT_MIN <= fit_s <= paper.FIT_MAX)
            self.assertEqual(len(paper.song_pages(song, self.band)), 1, song["title"])  # every demo song: one sheet
            floor_s, _, _ = paper.resolve(song, self.band, size="floor")
            self.assertGreaterEqual(floor_s + 1e-6, fit_s, song["title"])
            self.assertEqual(len(paper.song_pages(song, self.band, size="floor")), 1)

    def test_a_long_song_takes_more_pages_and_never_splits_a_section(self):
        song = json.loads(json.dumps(self.by_title["Harbour Lights"]))
        base = song["sections"]
        song["sections"] = [dict(s, id=f"{s['id']}{k}", order=k * 100 + s["order"]) for k in range(4) for s in base]
        pages = paper._layout(song, self.band, None, paper.FIT_MIN, "portrait", "color", False)
        self.assertGreater(len(pages), 1)
        _, ch = paper._content("portrait")
        for n, placed in enumerate(pages):
            room = ch - (paper.CONT_HEAD if n else 0)
            for block, _, y in placed:
                self.assertLessEqual(y + block.height, room + 0.01)
        self.assertEqual(sum(len(p) for p in pages), 1 + len(song["sections"]))
        drawn = paper.song_pages(song, self.band)
        self.assertGreater(len(drawn), 1)
        self.assertIn(r"(Harbour Lights \(continued\))", drawn[1].ops[0])

    def test_one_player_sees_their_hints_and_the_bands(self):
        song = self.by_title["Harbour Lights"]
        whole = "\n".join(page_streams(paper.song_pdf(song, self.band)))
        sams = "\n".join(page_streams(paper.song_pdf(song, self.band, self.sam)))
        self.assertIn("Brushes", whole)
        self.assertNotIn("Brushes", sams)
        self.assertIn("Root notes only", sams)
        self.assertIn("(»)", sams)  # Sam's own hints are marked
        self.assertIn("Keep it quiet", sams)  # band-wide hint

    def test_black_and_white_uses_no_colour(self):
        song = self.by_title["Paper Boats"]
        streams = "\n".join(page_streams(paper.song_pdf(song, self.band, ink="bw")))
        for r, g, b in re.findall(r"([\d.]+) ([\d.]+) ([\d.]+) r[gG]", streams):
            self.assertTrue(r == g == b, f"colour {r} {g} {b} in a black-and-white chart")
        colour = "\n".join(page_streams(paper.song_pdf(song, self.band)))
        self.assertTrue(any(not (r == g == b) for r, g, b in re.findall(r"([\d.]+) ([\d.]+) ([\d.]+) rg", colour)))

    def test_setlist_sheet_one_page_and_long_sets_flow_on(self):
        friday = next(s for s in self.setlists if s["name"].startswith("Friday"))
        present = [self.songs[i] for i in friday["songs"]]
        self.assertEqual(len(paper.setlist_sheet(friday, present, self.band)), 1)
        many = [dict(present[k % len(present)], title=f"Song number {k}") for k in range(60)]
        pages = paper.setlist_sheet(dict(friday, songs=[]), many, self.band)
        self.assertGreater(len(pages), 1)
        self.assertEqual(len(paper.setlist_sheet(dict(friday, songs=[]), [], self.band)), 1)

    def test_the_song_rides_inside_its_pdf(self):
        song = self.by_title["Slow Tide"]
        bundle = {"ssp_export": 1, "song": song, "audio": {}}
        pdf = paper.song_pdf(song, self.band, bundle=bundle)
        self.assertEqual(paper.read_embedded(pdf), bundle)
        self.assertIn(b"/EmbeddedFiles", pdf)
        self.assertIsNone(paper.read_embedded(paper.song_pdf(song, self.band)))
        self.assertIsNone(paper.read_embedded(b"%PDF-1.4 not ours"))

    def test_pdf_structure(self):
        friday = next(s for s in self.setlists if s["name"].startswith("Friday"))
        pdf = paper.setlist_pdf(friday, self.songs, self.band, size="floor")
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        # the cross-reference table points at real objects
        xref = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
        self.assertTrue(pdf[xref:].startswith(b"xref"))
        for off in re.findall(rb"(\d{10}) 00000 n", pdf):
            self.assertRegex(pdf[int(off):int(off) + 12], rb"^\d+ 0 obj")
        with self.assertRaises(models.ValidationError):
            paper.song_pdf(self.by_title["Slow Tide"], self.band, size="poster")


if __name__ == "__main__":
    unittest.main()
