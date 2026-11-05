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
