"""The browser's tempo map (web/static/timing.js) must match the server's
(server/timeline.py) exactly, or tablets and the server would disagree on
where the band is. Runs both on every demo song, from the top and from
every section. Needs Node.js; skipped without it.

    python3 -m unittest tests.test_timing_parity
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import timeline  # noqa: E402

JS = r"""
const T = require(process.argv[1]);
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = cases.map(([song, from]) => {
  const tl = T.build(song, from);
  return { tl, probes: [0, 1000, 5000, 60000, tl.total_ms - 1, tl.total_ms].map((ms) => T.barAt(tl, ms)) };
});
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class TimingParity(unittest.TestCase):
    def test_demo_songs(self):
        cases = []
        for path in sorted(glob.glob(os.path.join(ROOT, "demo", "songs", "*.json"))):
            with open(path, encoding="utf-8") as f:
                song = json.load(f)
            cases.append([song, None])
            for s in song["sections"]:
                cases.append([song, s["id"]])
        res = subprocess.run(["node", "-e", JS, os.path.join(ROOT, "web", "static", "timing.js")],
                             input=json.dumps(cases), capture_output=True, text=True, check=True)
        js = json.loads(res.stdout)
        self.assertEqual(len(js), len(cases))
        for (song, start), got in zip(cases, js):
            want = timeline.build(song, start)
            self.assertEqual(len(got["tl"]["bars"]), len(want["bars"]), song["title"])
            self.assertAlmostEqual(got["tl"]["total_ms"], want["total_ms"], places=6)
            for a, b in zip(got["tl"]["bars"], want["bars"]):
                for k in b:
                    if isinstance(b[k], float):
                        self.assertAlmostEqual(a[k], b[k], places=6)
                    else:
                        self.assertEqual(a[k], b[k], (song["title"], k))
            probes = [timeline.bar_at(want, ms) for ms in (0, 1000, 5000, 60000, want["total_ms"] - 1, want["total_ms"])]
            self.assertEqual(got["probes"], probes)


if __name__ == "__main__":
    unittest.main()


CLICK_JS = r"""
const T = require(process.argv[1]);
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map(([song, opts]) => T.clickEvents(T.build(song), opts))));
"""

CLICK_OPTIONS = [
    {},
    {"subdivision": "8"},
    {"subdivision": "16", "voice": True},
    {"subdivision": "triplet", "mode": "countin"},
    {"voice": True, "mode": "countin"},
    {"subdivision": "bogus", "voice": "nope", "mode": "?"},
]


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class ClickEventParity(unittest.TestCase):
    def test_click_events_match(self):
        cases = []
        for path in sorted(glob.glob(os.path.join(ROOT, "demo", "songs", "*.json"))):
            with open(path, encoding="utf-8") as f:
                song = json.load(f)
            for opts in CLICK_OPTIONS:
                cases.append([song, opts])
        res = subprocess.run(["node", "-e", CLICK_JS, os.path.join(ROOT, "web", "static", "timing.js")],
                             input=json.dumps(cases), capture_output=True, text=True, check=True)
        js = json.loads(res.stdout)
        for (song, opts), got in zip(cases, js):
            want = timeline.click_events(timeline.build(song), opts)
            self.assertEqual(len(got), len(want), (song["title"], opts))
            for a, b in zip(got, want):
                self.assertAlmostEqual(a["t"], b["t"], places=6)
                self.assertEqual((a["kind"], a["n"], a["bar"]), (b["kind"], b["n"], b["bar"]))

    def test_voice_count_in_shape(self):
        song = {"default_bpm": 120, "sections": [
            {"id": "a", "order": 0, "bars": 2, "count_in": {"bars": 2, "style": "click"}}]}
        ev = timeline.click_events(timeline.build(song), {"voice": True, "subdivision": "8"})
        voice = [(e["bar"], e["n"]) for e in ev if e["kind"] == "voice"]
        # "one . two ." then "one two three four"
        self.assertEqual(voice, [(0, 1), (0, 2), (1, 1), (1, 2), (1, 3), (1, 4)])
        # the song's own bars click with eighth notes
        self.assertEqual(sum(1 for e in ev if e["kind"] == "sub"), 8)
        only = timeline.click_events(timeline.build(song), {"mode": "countin"})
        self.assertTrue(all(e["bar"] < 2 for e in only))
