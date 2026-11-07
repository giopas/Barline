"""Fast entry (web/static/quick.js): reading pasted song lists, quick songs
and tap tempo. Needs Node.js; skipped without it.

    python3 -m unittest tests.test_quick
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JS = r"""
const Q = require(process.argv[1]);
const lines = JSON.parse(require("fs").readFileSync(0, "utf8"));
let n = 0;
const tap = new Q.TapTempo();
const taps = [0, 500, 1000, 1500].map((t) => tap.tap(t));
const restart = new Q.TapTempo();
[0, 400, 5000, 5300].forEach((t) => restart.tap(t));
process.stdout.write(JSON.stringify({
  parsed: lines.map(Q.parseLine),
  song: Q.quickSong({ title: "X", bpm: 128, seconds: 180 }, () => "id" + n++),
  plain: Q.quickSong({ title: "Y", bpm: null, seconds: null }, () => "id"),
  taps, restart: restart.bpm(),
}));
"""

CASES = {
    "Song A - 128": ("Song A", 128, None),
    "Song A, 128, 3:45": ("Song A", 128, 225),
    "3. Lantern Parade (128 bpm)": ("Lantern Parade", 128, None),
    "Song A\t128\t3:45": ("Song A", 128, 225),
    "99 Problems": ("99 Problems", None, None),
    "99 Problems - 90": ("99 Problems", 90, None),
    "Seven Nation Army – 124 – 3:52": ("Seven Nation Army", 124, 232),
    "1) Roxanne 134": ("Roxanne", 134, None),
    "Smells Like Teen Spirit 117bpm": ("Smells Like Teen Spirit", 117, None),
    "Hey Jude 7:11": ("Hey Jude", None, 431),
    "Summer of 69 - 139": ("Summer of 69", 139, None),
    "   ": None,
    "# a comment": None,
}


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class QuickEntry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        res = subprocess.run(["node", "-e", JS, os.path.join(ROOT, "web", "static", "quick.js")],
                             input=json.dumps(list(CASES)), capture_output=True, text=True, check=True)
        cls.out = json.loads(res.stdout)

    def test_lines(self):
        for (line, want), got in zip(CASES.items(), self.out["parsed"]):
            if want is None:
                self.assertIsNone(got, line)
            else:
                self.assertEqual((got["title"], got["bpm"], got["seconds"]), want, line)

    def test_quick_song(self):
        song = self.out["song"]
        self.assertEqual(song["default_bpm"], 128)
        self.assertEqual(len(song["sections"]), 1)
        self.assertEqual(song["sections"][0]["bars"], 96)  # 3:00 at 128 BPM in 4/4
        plain = self.out["plain"]
        self.assertEqual(plain["default_bpm"], 120)
        self.assertEqual(plain["sections"][0]["bars"], 120)  # 4:00 at 120

    def test_tap_tempo(self):
        self.assertEqual(self.out["taps"], [None, 120, 120, 120])
        self.assertEqual(self.out["restart"], 200)  # a long pause starts over


if __name__ == "__main__":
    unittest.main()
