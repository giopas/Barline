"""0.16: count-ins in one go, jumping to a section and nudging the click
mid-run, and the new click sounds.

    python3 -m unittest tests.test_016
"""

from __future__ import annotations

import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import click_track  # noqa: E402
import models  # noqa: E402
import timeline  # noqa: E402
from test_server import Listener, Server, demo_song  # noqa: E402


def sec(sid, order, bars=4, bpm=None, ci=(0, "none")):
    return {"id": sid, "label": sid.upper(), "order": order, "bars": bars, "bpm": bpm,
            "count_in": {"bars": ci[0], "style": ci[1]}, "hints": []}


def song(*sections, bpm=100):
    return {"id": "s", "title": "T", "default_bpm": bpm, "sections": list(sections)}


class CountInModel(unittest.TestCase):
    def test_start_only(self):
        s = song(sec("a", 0), sec("b", 1))
        self.assertEqual(models.apply_count_ins(s, start={"bars": 2, "style": "sticks"}), 1)
        self.assertEqual(s["sections"][0]["count_in"], {"bars": 2, "style": "sticks"})
        self.assertEqual(s["sections"][1]["count_in"], {"bars": 0, "style": "none"})

    def test_every_change_and_tempo_only(self):
        s = song(sec("a", 0), sec("b", 1), sec("c", 2, bpm=140), sec("d", 3, bpm=140), sec("e", 4))
        self.assertEqual(models.apply_count_ins(s, changes={"bars": 1, "style": "click"}, tempo_only=True), 2)
        got = [x["count_in"]["bars"] for x in s["sections"]]
        self.assertEqual(got, [0, 0, 1, 0, 1])  # 100 -> 140 and 140 -> 100 (default)
        s = song(sec("a", 0), sec("b", 1), sec("c", 2))
        self.assertEqual(models.apply_count_ins(s, start={"bars": 1, "style": "click"}, changes={"bars": 1, "style": "verbal"}), 3)

    def test_keep_existing_and_remove(self):
        s = song(sec("a", 0, ci=(2, "sticks")), sec("b", 1), sec("c", 2, ci=(1, "verbal")))
        n = models.apply_count_ins(s, start={"bars": 1, "style": "click"}, changes={"bars": 1, "style": "click"},
                                   keep_existing=True)
        self.assertEqual(n, 1)
        self.assertEqual([x["count_in"] for x in s["sections"]],
                         [{"bars": 2, "style": "sticks"}, {"bars": 1, "style": "click"}, {"bars": 1, "style": "verbal"}])
        n = models.apply_count_ins(s, start={"bars": 0, "style": "none"}, changes={"bars": 0, "style": "none"})
        self.assertEqual(n, 3)
        self.assertTrue(all(x["count_in"] == {"bars": 0, "style": "none"} for x in s["sections"]))

    def test_sections_in_play_order_not_list_order(self):
        s = song(sec("late", 1), sec("first", 0))
        models.apply_count_ins(s, start={"bars": 1, "style": "click"})
        self.assertEqual(s["sections"][1]["count_in"]["bars"], 1)
        self.assertEqual(s["sections"][0]["count_in"]["bars"], 0)

    def test_bad_choices(self):
        for bad in ({"bars": 9, "style": "click"}, {"bars": 1, "style": "cowbell"}, "two", {"bars": True}):
            with self.assertRaises(models.ValidationError):
                models.apply_count_ins(song(sec("a", 0)), start=bad)


class CountInApi(unittest.TestCase):
    def setUp(self):
        self.s = Server()

    def tearDown(self):
        self.s.close()

    def test_one_song_setlist_and_all(self):
        lst = Listener(self.s.base, "other")
        lst.wait_for("presence")
        one = demo_song(self.s, "Paper Boats")
        status, res = self.s.json("POST", "/api/count-ins", {"scope": {"song_id": one["id"]},
                                                            "start": {"bars": 2, "style": "sticks"}})
        self.assertEqual(status, 200)
        self.assertEqual(res["checked"], 1)
        first = min(res["songs"][0]["sections"], key=lambda x: x["order"])
        self.assertEqual(first["count_in"], {"bars": 2, "style": "sticks"})
        self.assertEqual(self.s.store.songs[one["id"]]["sections"], res["songs"][0]["sections"])
        lst.wait_for("song", cond=lambda m: m["data"]["id"] == one["id"])

        sl = next(x for x in self.s.store.setlists.values())
        status, res = self.s.json("POST", "/api/count-ins", {"scope": {"setlist_id": sl["id"]},
                                                            "start": {"bars": 1, "style": "click"}, "keep_existing": True})
        self.assertEqual(status, 200)
        self.assertEqual(res["checked"], len([i for i in sl["songs"] if i in self.s.store.songs]))
        for sid in sl["songs"]:
            first = min(self.s.store.songs[sid]["sections"], key=lambda x: x["order"])
            self.assertNotEqual(first["count_in"]["style"], "none")

        status, res = self.s.json("POST", "/api/count-ins", {"scope": {"all": True},
                                                            "start": {"bars": 0, "style": "none"},
                                                            "changes": {"bars": 0, "style": "none"}})
        self.assertEqual(status, 200)
        self.assertEqual(res["checked"], len(self.s.store.songs))
        for x in self.s.store.songs.values():
            self.assertTrue(all(c["count_in"]["style"] == "none" for c in x["sections"]))
        lst.close()

    def test_errors(self):
        self.assertEqual(self.s.json("POST", "/api/count-ins", {"scope": {"song_id": "nope"}, "start": {"bars": 1}})[0], 404)
        self.assertEqual(self.s.json("POST", "/api/count-ins", {"scope": {"all": True}})[0], 400)
        self.assertEqual(self.s.json("POST", "/api/count-ins", {"scope": "everything", "start": {"bars": 1}})[0], 400)
        self.assertEqual(self.s.json("POST", "/api/count-ins", {"scope": {"all": True}, "start": {"bars": 99}})[0], 400)


class JumpAndNudge(unittest.TestCase):
    def setUp(self):
        self.s = Server()
        _, self.song = self.s.json("POST", "/api/songs", {"title": "Jumpy", "default_bpm": 120, "sections": [
            sec("v", 0, bars=8), sec("c", 1, bars=8, ci=(2, "sticks")), sec("o", 2, bars=4, bpm=90)]})

    def tearDown(self):
        self.s.close()

    def post(self, body, client="drummer"):
        return self.s.json("POST", "/api/transport", body, client=client)

    def test_jump_lands_on_a_bar_line_without_count_in(self):
        self.post({"action": "cue", "song_id": self.song["id"]})
        _, run = self.post({"action": "start", "lead_ms": 200})
        time.sleep(1.0)  # past the first beat
        lst = Listener(self.s.base, "other")
        lst.wait_for("presence")
        now = time.time() * 1000
        status, snap = self.post({"action": "jump", "section_id": "c"})
        self.assertEqual(status, 200)
        self.assertEqual(snap["run"], run["run"])          # same run: nobody restarts
        self.assertEqual(snap["rev"], 1)
        self.assertEqual(snap["moved"]["kind"], "jump")
        self.assertEqual(snap["moved"]["label"], "C")
        self.assertEqual(snap["start_section_id"], "c")
        bars = snap["timeline"]["bars"]
        self.assertFalse(bars[0]["count_in"])               # straight onto bar 1
        self.assertEqual(bars[0]["section_id"], "c")
        self.assertEqual(bars[0]["song_bar"], 9)
        self.assertEqual(bars[-1]["section_id"], "o")
        # lands on one of the old run's bar lines (2 s bars at 120 BPM)
        offset = snap["started_at"] - run["started_at"]
        self.assertAlmostEqual(offset / 2000.0, round(offset / 2000.0), places=6)
        self.assertGreaterEqual(snap["started_at"], now + 400)
        m = lst.wait_for("transport", cond=lambda m: m["data"].get("rev") == 1)
        self.assertEqual(m["data"]["timeline"]["bars"][0]["section_id"], "c")
        # the bar announcements follow the new timeline
        m = lst.wait_for("position", timeout=6, cond=lambda m: m["data"]["section_id"] == "c")
        self.assertEqual(m["data"]["song_bar"], 9)
        lst.close()

    def test_jump_before_the_first_beat_is_a_fresh_start(self):
        self.post({"action": "cue", "song_id": self.song["id"]})
        _, run = self.post({"action": "start", "lead_ms": 3000})
        _, snap = self.post({"action": "jump", "section_id": "c"})
        self.assertEqual(snap["run"], run["run"] + 1)
        self.assertTrue(snap["timeline"]["bars"][0]["count_in"])  # its own 2-bar sticks count-in
        self.assertEqual(snap["timeline"]["bars"][0]["count_in_style"], "sticks")

    def test_jump_errors(self):
        self.post({"action": "cue", "song_id": self.song["id"]})
        self.assertEqual(self.post({"action": "jump", "section_id": "c"})[0], 400)  # stopped
        self.post({"action": "start", "lead_ms": 200})
        self.assertEqual(self.post({"action": "jump", "section_id": "zzz"})[0], 404)

    def test_nudge(self):
        self.post({"action": "cue", "song_id": self.song["id"]})
        _, run = self.post({"action": "start", "lead_ms": 200})
        _, a = self.post({"action": "nudge", "ms": 500})
        self.assertAlmostEqual(a["started_at"], run["started_at"] - 500)
        self.assertEqual(a["moved"], {"kind": "nudge", "by": a["moved"]["by"], "client_id": "drummer", "label": None, "ms": 500.0})
        _, b = self.post({"action": "nudge", "ms": -20})
        self.assertAlmostEqual(b["started_at"], run["started_at"] - 480)
        self.assertEqual(b["rev"], 2)
        _, c = self.post({"action": "nudge", "ms": 99999})
        self.assertAlmostEqual(c["started_at"], b["started_at"] - 10000)
        self.assertEqual(self.post({"action": "nudge", "ms": "lots"})[0], 400)
        self.post({"action": "stop"})
        self.assertEqual(self.post({"action": "nudge", "ms": 10})[0], 400)
        _, d = self.post({"action": "start", "lead_ms": 200})
        self.assertEqual((d["rev"], d["moved"]), (0, None))


class TimelineHelpers(unittest.TestCase):
    def test_first_count_in_off(self):
        s = song(sec("a", 0, ci=(2, "sticks")), sec("b", 1, ci=(1, "click")))
        self.assertEqual(len(timeline.build(s)["bars"]), 2 + 4 + 1 + 4)
        tl = timeline.build(s, first_count_in=False)
        self.assertEqual(len(tl["bars"]), 4 + 1 + 4)
        self.assertEqual(tl["bars"][0]["start_ms"], 0)
        self.assertFalse(tl["bars"][0]["count_in"])
        tl = timeline.build(s, "b", lead_in=False, first_count_in=False)
        self.assertEqual(len(tl["bars"]), 4)

    def test_next_boundary(self):
        tl = timeline.build(song(sec("a", 0, bars=2)), lead_in=False)  # bars at 0, 2400 (100 BPM)
        self.assertEqual(timeline.next_boundary(tl, -50), 0)
        self.assertEqual(timeline.next_boundary(tl, 1), 2400)
        self.assertEqual(timeline.next_boundary(tl, 2400), 2400)
        self.assertEqual(timeline.next_boundary(tl, 2401), 4800)  # the end of the song
        self.assertEqual(timeline.next_boundary(tl, 9000), 9000)


class NewSounds(unittest.TestCase):
    def test_every_sound_is_short_loud_enough_and_accent_differs(self):
        for name in click_track.SOUNDS:
            hi, lo = click_track.sounds(name)
            for samples in (hi, lo):
                self.assertGreater(len(samples), 100, name)
                self.assertLess(len(samples), click_track.RATE // 2, name)   # under half a second
                peak = max(abs(x) for x in samples)
                self.assertGreater(peak, 5000, name)
                self.assertLessEqual(peak, 32767, name)
                self.assertLess(abs(samples[-1]), 1500, name)  # dies away, no click at the end
            self.assertNotEqual(list(hi[:200]), list(lo[:200]), name)
            self.assertEqual(click_track.check_sound(name), name)

    def test_new_names(self):
        for name in ("bell", "cowbell", "snap", "rim"):
            self.assertIn(name, click_track.SOUNDS)
        with self.assertRaises(ValueError):
            click_track.check_sound("gong")


if __name__ == "__main__":
    unittest.main()


SOUND_JS = r"""
globalThis.window = globalThis;
require(process.argv[1]);
const out = {};
for (const s of window.SSPAudio.SOUNDS) out[s] = [true, false].map((a) => Array.from(window.SSPAudio.samplesFor(s, a, 22050)));
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipIf(__import__("shutil").which("node") is None, "node not installed")
class SoundParity(unittest.TestCase):
    """The live click (audio.js) and the .wav (click_track.py) are the same sound."""

    def test_every_sound_matches(self):
        import json
        import subprocess
        res = subprocess.run(["node", "-e", SOUND_JS, os.path.join(ROOT, "web", "static", "audio.js")],
                             capture_output=True, text=True, check=True)
        js = json.loads(res.stdout)
        self.assertEqual(sorted(js), sorted(click_track.SOUNDS))
        for name in click_track.SOUNDS:
            for got, want in zip(js[name], click_track.sounds(name)):
                self.assertEqual(len(got), len(want), name)
                worst = max(abs(g * 32767 - w) for g, w in zip(got, want))
                self.assertLessEqual(worst, 1.01, name)


JUMP_JS = r"""
const T = require(process.argv[1]);
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map(([song, from]) => {
  const tl = T.build(song, from, false, false);
  return { tl, b: [-5, 1, 3000, 1e9].map((ms) => T.nextBoundary(tl, ms)) };
})));
"""


@unittest.skipIf(__import__("shutil").which("node") is None, "node not installed")
class JumpParity(unittest.TestCase):
    """A jump in solo mode (timing.js) lands where the server's would."""

    def test_demo_songs(self):
        import glob
        import json
        import subprocess
        cases = []
        for path in sorted(glob.glob(os.path.join(ROOT, "demo", "songs", "*.json"))):
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
            cases += [[s, x["id"]] for x in s["sections"]]
        res = subprocess.run(["node", "-e", JUMP_JS, os.path.join(ROOT, "web", "static", "timing.js")],
                             input=json.dumps(cases), capture_output=True, text=True, check=True)
        for (s, start), got in zip(cases, json.loads(res.stdout)):
            want = timeline.build(s, start, lead_in=False, first_count_in=False)
            self.assertEqual(len(got["tl"]["bars"]), len(want["bars"]))
            self.assertAlmostEqual(got["tl"]["total_ms"], want["total_ms"], places=6)
            for g, ms in zip(got["b"], (-5, 1, 3000, 1e9)):
                self.assertAlmostEqual(g, timeline.next_boundary(want, ms), places=6)
