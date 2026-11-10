"""0.19: a song's click pattern (sounds and accents per beat).

    python3 -m unittest tests.test_pattern
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import click_track  # noqa: E402
import models  # noqa: E402
import timeline  # noqa: E402
from test_server import Server, demo_song  # noqa: E402

BACKBEAT = [{"sound": None, "accent": False}, {"sound": None, "accent": True},
            {"sound": None, "accent": False}, {"sound": None, "accent": True}]
MIXED = [{"sound": "wood", "accent": True}, {"sound": "beep", "accent": False},
         {"sound": "off", "accent": False}, {"sound": "beep", "accent": True}]


def song(pattern=None):
    s = {"id": "s", "title": "T", "default_bpm": 120,
         "sections": [{"id": "a", "label": "A", "order": 0, "bars": 2, "bpm": None,
                       "count_in": {"bars": 1, "style": "click"}, "hints": []}]}
    if pattern is not None:
        s["click_pattern"] = pattern
    return s


class PatternRules(unittest.TestCase):
    def test_default_is_no_pattern(self):
        self.assertIsNone(timeline.click_pattern(None))
        self.assertIsNone(timeline.click_pattern(timeline.DEFAULT_PATTERN))
        self.assertIsNone(timeline.click_pattern([{"sound": "bogus", "accent": True}] + [{}] * 3))
        self.assertIsNone(timeline.click_pattern(BACKBEAT[:3]))
        self.assertIsNone(models.clean_click_pattern("nope"))
        self.assertEqual(models.clean_click_pattern(BACKBEAT), BACKBEAT)
        self.assertEqual(timeline.build(song(BACKBEAT))["pattern"], BACKBEAT)
        self.assertIsNone(timeline.build(song())["pattern"])

    def test_events_follow_the_pattern(self):
        ev = timeline.click_events(timeline.build(song(MIXED)))
        count_in = [e for e in ev if e["bar"] == 0]
        self.assertEqual([e["kind"] for e in count_in], ["accent", "beat", "beat", "beat"])  # count-in untouched
        self.assertTrue(all("sound" not in e for e in count_in))
        bar1 = [e for e in ev if e["bar"] == 1]
        self.assertEqual([(e["n"], e["kind"], e.get("sound")) for e in bar1],
                         [(1, "accent", "wood"), (2, "beat", "beep"), (4, "accent", "beep")])  # beat 3 is silent
        bk = [e["kind"] for e in timeline.click_events(timeline.build(song(BACKBEAT))) if e["bar"] == 1]
        self.assertEqual(bk, ["beat", "accent", "beat", "accent"])

    def test_silent_beat_keeps_subdivisions(self):
        ev = timeline.click_events(timeline.build(song(MIXED)), {"subdivision": "8"})
        self.assertEqual(sum(1 for e in ev if e["bar"] == 1 and e["kind"] == "sub"), 4)

    def test_click_track_uses_the_pattern(self):
        plain = click_track.song_wav(song(), "wood")
        mixed = click_track.song_wav(song(MIXED), "wood")
        self.assertNotEqual(plain, mixed)
        self.assertEqual(len(plain), len(mixed))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class PatternParity(unittest.TestCase):
    def test_js_matches(self):
        js = r"""
const T = require(process.argv[1]);
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map((s) => { const tl = T.build(s); return { p: tl.pattern, ev: T.clickEvents(tl, {subdivision: "8"}) }; })));
"""
        cases = [song(), song(BACKBEAT), song(MIXED), song(MIXED[:2]), song([{"sound": "x", "accent": 1}] * 4)]
        res = subprocess.run(["node", "-e", js, os.path.join(ROOT, "web", "static", "timing.js")],
                             input=json.dumps(cases), capture_output=True, text=True, check=True)
        for s, got in zip(cases, json.loads(res.stdout)):
            tl = timeline.build(s)
            want = timeline.click_events(tl, {"subdivision": "8"})
            self.assertEqual(got["p"], tl["pattern"])
            self.assertEqual(len(got["ev"]), len(want))
            for a, b in zip(got["ev"], want):
                self.assertAlmostEqual(a["t"], b["t"], places=6)
                self.assertEqual((a["kind"], a["n"], a["bar"], a.get("sound")), (b["kind"], b["n"], b["bar"], b.get("sound")))


class PatternApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Server()

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    def test_saved_cleaned_and_cleared(self):
        sg = demo_song(self.s, "Paper Boats")
        body = dict(sg, click_pattern=MIXED)
        status, out = self.s.json("PUT", f"/api/songs/{sg['id']}", body)
        self.assertEqual(status, 200)
        self.assertEqual(out["click_pattern"], MIXED)
        self.assertEqual(self.s.store.songs[sg["id"]]["click_pattern"], MIXED)
        # an edit that doesn't mention it keeps it
        body2 = {k: v for k, v in out.items() if k != "click_pattern"}
        status, out2 = self.s.json("PUT", f"/api/songs/{sg['id']}", body2)
        self.assertEqual(out2["click_pattern"], MIXED)
        # the default (or nonsense) clears it
        status, out3 = self.s.json("PUT", f"/api/songs/{sg['id']}", dict(out2, click_pattern=timeline.DEFAULT_PATTERN))
        self.assertNotIn("click_pattern", out3)
        # the live transport carries it in its timeline
        status, out4 = self.s.json("PUT", f"/api/songs/{sg['id']}", dict(out3, click_pattern=BACKBEAT))
        status, st = self.s.json("POST", "/api/transport", {"action": "cue", "song_id": sg["id"]})
        self.assertEqual(status, 200)
        status, st = self.s.json("POST", "/api/transport", {"action": "start", "song_id": sg["id"]})
        self.assertEqual(st["timeline"]["pattern"], BACKBEAT)


if __name__ == "__main__":
    unittest.main()
