"""Merging two copies of a song (0.18): who wrote each hint, the merge rules
in web/static/files.js, and the server side of an import that merges.

    python3 -m unittest tests.test_merge

The merge rules are JavaScript (they run in the web app, on the band's
server and in Pocket alike), so those tests run them under node. Skipped
without node.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_server import ROOT, Server, demo_song  # noqa: E402

import models  # noqa: E402

FILES_JS = os.path.join(ROOT, "web", "static", "files.js")


def files_js(fn: str, *args):
    """Call one function of files.js under node and return its result."""
    script = ("const F = require(process.argv[1]); const args = JSON.parse(process.argv[2]);"
              f"process.stdout.write(JSON.stringify(F.{fn}(...args)));")
    res = subprocess.run(["node", "-e", script, FILES_JS, json.dumps(args)],
                         capture_output=True, text=True, timeout=30)
    if res.returncode:
        raise AssertionError(res.stderr)
    return json.loads(res.stdout)


def song(sections, **kw):
    out = {"id": "s1", "title": "Lantern", "default_bpm": 120, "tags": [], "sections": sections,
           "created_at": 1, "updated_at": 1}
    out.update(kw)
    return out


def section(sid, label, bars, order, hints=()):
    return {"id": sid, "label": label, "order": order, "bars": bars, "bpm": None,
            "count_in": {"bars": 0, "style": "none"}, "hints": list(hints)}


def hint(hid, text, t=1, author=None, visibility="all"):
    h = {"id": hid, "text": text, "audio": None, "visibility": visibility, "updated_at": t}
    if author:
        h["author"] = author
    return h


SAM = {"id": "p-sam", "name": "Sam", "role": "Bass"}
RUBY = {"id": "p-ruby", "name": "Ruby", "role": "Drums"}


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class MergeRules(unittest.TestCase):
    def setUp(self):
        self.local = song([
            section("a", "Intro", 4, 0, [hint("h1", "watch Ruby", 10)]),
            section("b", "Verse", 8, 1, [hint("h2", "quiet", 10)]),
            section("c", "Chorus", 8, 2),
        ])

    def test_new_hints_from_both_copies_and_nothing_lost(self):
        incoming = copy.deepcopy(self.local)
        incoming["sections"][2]["hints"].append(hint("h3", "big ending", 20, SAM))
        self.local["sections"][0]["hints"].append(hint("h4", "count off loud", 15, RUBY))
        out = files_js("mergeSong", self.local, incoming, "local")
        texts = [[h["text"] for h in s["hints"]] for s in out["song"]["sections"]]
        self.assertEqual(texts, [["watch Ruby", "count off loud"], ["quiet"], ["big ending"]])
        self.assertEqual(out["report"]["structure"], "same")
        self.assertEqual(out["report"]["added"], [{"author": SAM}])
        self.assertEqual(out["song"]["sections"][2]["hints"][0]["author"], SAM)

    def test_the_newer_change_wins(self):
        incoming = copy.deepcopy(self.local)
        incoming["sections"][1]["hints"][0].update(text="quiet, then build", updated_at=30, author=SAM)
        out = files_js("mergeSong", self.local, incoming, "local")
        self.assertEqual(out["song"]["sections"][1]["hints"][0]["text"], "quiet, then build")
        self.assertEqual(len(out["report"]["updated"]), 1)
        # and the other way round: this copy's is newer, so it stays
        self.local["sections"][1]["hints"][0].update(text="whisper", updated_at=40)
        out = files_js("mergeSong", self.local, incoming, "local")
        self.assertEqual(out["song"]["sections"][1]["hints"][0]["text"], "whisper")
        self.assertEqual(out["report"]["keptNewer"], 1)

    def test_a_hint_deleted_on_one_side_comes_back(self):
        incoming = copy.deepcopy(self.local)
        incoming["sections"][1]["hints"] = []
        out = files_js("mergeSong", self.local, incoming, "incoming")
        self.assertEqual([h["text"] for h in out["song"]["sections"][1]["hints"]], ["quiet"])

    def test_structure_choice(self):
        incoming = copy.deepcopy(self.local)
        incoming["sections"][1]["bars"] = 16
        incoming["sections"].append(section("d", "Outro", 4, 3, [hint("h5", "fade", 5, SAM)]))
        self.assertFalse(files_js("structureSame", self.local, incoming))
        self.assertIn("3 vs 4 sections", files_js("structureDiff", self.local, incoming))
        mine = files_js("mergeSong", self.local, incoming, "local")
        theirs = files_js("mergeSong", self.local, incoming, "incoming")
        self.assertEqual([s["bars"] for s in mine["song"]["sections"]], [4, 8, 8])
        self.assertEqual([s["bars"] for s in theirs["song"]["sections"]], [4, 16, 8, 4])
        # the Outro's hint has no Outro to go to in our structure: it moves
        # to the section in the same place (the last one), it isn't lost
        self.assertEqual(mine["report"]["moved"], 1)
        self.assertIn("fade", [h["text"] for h in mine["song"]["sections"][2]["hints"]])
        self.assertEqual(theirs["report"]["moved"], 0)

    def test_a_section_that_was_recreated_keeps_its_hints_by_name(self):
        incoming = copy.deepcopy(self.local)
        incoming["sections"][2] = section("z", "Chorus", 8, 2, [hint("h6", "harmony up", 9)])
        out = files_js("mergeSong", self.local, incoming, "local")
        self.assertEqual([h["text"] for h in out["song"]["sections"][2]["hints"]], ["harmony up"])

    def test_plan_matches_by_id_then_title_and_maps_players(self):
        here = {"songs": [self.local, song([], id="s2", title="Coffee")], "setlists": [{"id": "L1", "name": "Friday", "songs": ["s1"]}],
                "band": {"name": "Us", "players": [{"id": "p-sam", "name": "Sam", "role": "Bass"}]}}
        other = copy.deepcopy(self.local)
        other["sections"][0]["hints"].append(hint("h7", "for Sam", 50, {"id": "x-sam", "name": "Sam", "role": "Bass"}, "x-sam"))
        file = {"songs": [other, song([section("q", "All", 4, 0)], id="zz", title="  coffee "), song([], id="n1", title="New one")],
                "setlists": [{"id": "L9", "name": "Friday", "songs": ["s1"]}, {"id": "L2", "name": "Sunday", "songs": ["n1"]}],
                "band": {"name": "Us", "players": [{"id": "x-sam", "name": "Sam", "role": "Bass"}, {"id": "x-mia", "name": "Mia", "role": "Vocals"}]},
                "audio": {}}
        p = files_js("plan", file, here)
        self.assertEqual([i["kind"] for i in p["items"]], ["merge", "merge", "new"])
        self.assertEqual(p["items"][1]["local"]["id"], "s2")  # matched by title
        self.assertFalse(p["items"][1]["sameStructure"])
        # Sam is the same person here under another id: his hint points at him
        h = p["items"][0]["preview"]["local"]["song"]["sections"][0]["hints"][-1]
        self.assertEqual((h["visibility"], h["author"]["id"]), ("p-sam", "p-sam"))
        self.assertEqual([x["name"] for x in p["players"]], ["Mia"])
        self.assertEqual([(s["incoming"]["name"], bool(s["local"])) for s in p["setlists"]], [("Friday", True), ("Sunday", False)])

    def test_identical_copy_is_nothing_to_do(self):
        here = {"songs": [self.local], "setlists": [], "band": {"name": "Us", "players": []}}
        p = files_js("plan", {"songs": [copy.deepcopy(self.local)], "setlists": [], "band": None, "audio": {}}, here)
        self.assertEqual(p["items"][0]["kind"], "same")

    def test_file_formats(self):
        one = files_js("makeFile", {"songs": [self.local], "setlists": []}, {})
        self.assertEqual(one["ssp_export"], 1)
        many = files_js("makeFile", {"songs": [self.local], "setlists": [{"id": "L", "name": "x", "songs": ["s1"]}],
                                     "band": {"name": "Us", "players": []}}, {})
        self.assertEqual(many["ssp_export"], 2)
        for payload in (one, many, self.local):
            self.assertEqual(files_js("normalize", payload)["songs"][0]["id"], "s1")
        with self.assertRaises(AssertionError):
            files_js("normalize", {"hello": 1})

    def test_author_label(self):
        band = {"players": [{"id": "p-sam", "name": "Samuel", "role": "Bass"}]}
        self.assertEqual(files_js("authorLabel", SAM, band), "Samuel (Bass)")  # renamed since: today's name
        self.assertEqual(files_js("authorLabel", RUBY, band), "Ruby (Drums)")  # not in this band: as remembered
        self.assertEqual(files_js("authorLabel", None, band), "")


class ServerSide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Server()

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    def player(self, name):
        return next(p for p in self.s.store.band["players"] if p["name"] == name)

    def test_an_edit_says_who_wrote_the_hint(self):
        sam = self.player("Sam")
        self.assertEqual(self.s.json("POST", "/api/presence", {"client": "sams-phone", "player_id": sam["id"]})[0], 200)
        song = copy.deepcopy(demo_song(self.s, "Lantern Parade"))
        untouched = copy.deepcopy(song["sections"][0]["hints"])
        song["sections"][1]["hints"].append({"id": "newhint01", "text": "slide up", "audio": None, "visibility": "all"})
        status, saved = self.s.json("PUT", f"/api/songs/{song['id']}", song, client="sams-phone")
        self.assertEqual(status, 200)
        h = next(x for x in saved["sections"][1]["hints"] if x["id"] == "newhint01")
        self.assertEqual(h["author"], {"id": sam["id"], "name": "Sam", "role": sam["role"]})
        self.assertIsInstance(h["updated_at"], float)
        self.assertNotIn("updated_at", saved["sections"][1])  # a new hint isn't a new shape
        # hints nobody touched keep what they had, whatever the client sends
        self.assertEqual([x.get("author") for x in saved["sections"][0]["hints"]], [x.get("author") for x in untouched])
        song = copy.deepcopy(saved)
        song["sections"][1]["bars"] += 2
        _, saved = self.s.json("PUT", f"/api/songs/{song['id']}", song, client="sams-phone")
        self.assertIsInstance(saved["sections"][1]["updated_at"], float)  # its shape changed
        # a device that hasn't said who's holding it: the hint keeps its author
        song = copy.deepcopy(saved)
        next(x for x in song["sections"][1]["hints"] if x["id"] == "newhint01")["author"] = {"id": "forged", "name": "X"}
        status, saved = self.s.json("PUT", f"/api/songs/{song['id']}", song, client="someone")
        self.assertEqual(next(x for x in saved["sections"][1]["hints"] if x["id"] == "newhint01")["author"]["name"], "Sam")

    def test_a_merge_keeps_the_files_authors(self):
        song = copy.deepcopy(demo_song(self.s, "Coffee at Midnight"))
        song["sections"][0]["hints"].append({"id": "frompocket", "text": "from home", "audio": None, "visibility": "all",
                                             "updated_at": 123.0, "author": {"id": "elsewhere", "name": "Kim", "role": "Keys"}})
        status, saved = self.s.json("PUT", f"/api/songs/{song['id']}?merge=1", song)
        self.assertEqual(status, 200)
        h = next(x for x in saved["sections"][0]["hints"] if x["id"] == "frompocket")
        self.assertEqual((h["updated_at"], h["author"]["name"], h["author"]["role"]), (123.0, "Kim", "Keys"))

    def test_an_imported_setlist_keeps_its_id(self):
        ids = [s["id"] for s in self.s.store.songs.values()][:2]
        status, sl = self.s.json("POST", "/api/setlists", {"id": "fromafile01", "name": "From a file", "songs": ids})
        self.assertEqual((status, sl["id"]), (201, "fromafile01"))
        status, again = self.s.json("POST", "/api/setlists", {"id": "fromafile01", "name": "Again", "songs": []})
        self.assertNotEqual(again["id"], "fromafile01")  # taken: a new one

    def test_read_a_pdf_for_import(self):
        song = demo_song(self.s, "Lantern Parade")
        _, pdf, _ = self.s.call("GET", f"/export/song/{song['id']}")
        status, payload = self.s.json("POST", "/api/import/read", raw=pdf, ctype="application/pdf")
        self.assertEqual(status, 200)
        self.assertEqual(payload["song"]["id"], song["id"])
        status, err = self.s.json("POST", "/api/import/read", raw=b"%PDF-1.4 nothing", ctype="application/pdf")
        self.assertEqual(status, 400)

    def test_stamps_from_a_file_are_tidied(self):
        s = {"sections": [{"updated_at": "yesterday", "hints": [{"author": {"name": " Mia  B ", "role": "Bass"}, "updated_at": None},
                                                                 {"author": "Mia"}]}]}
        models.tidy_stamps(s)
        self.assertEqual(s["sections"][0], {"hints": [{"author": {"id": None, "name": "Mia B", "role": "Bass"}}, {}]})


if __name__ == "__main__":
    unittest.main()
