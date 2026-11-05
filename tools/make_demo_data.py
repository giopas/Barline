#!/usr/bin/env python3
"""Write the demo band into demo/ -- a fictional band, fictional songs.

    python3 tools/make_demo_data.py [OUT_DIR]

"The Paper Lanterns" and every title here are made up (PROJECT_CHARTER.md
section 3: no real band, venue or bandmate data in the repo). The songs
are chosen to show off what SSP does: tempo changes between sections,
count-ins in every style (including one mid-song after a stop), hints for
the whole band and hints aimed at one player, a recorded hint clip, two
setlists, and one unfinished song.

Same output every run (fixed ids, no clock), so screenshots, tests and the
committed demo/ folder never drift apart. The one "recorded" clip is a
synthesised wood-block fill (there's no microphone in a build script).
"""

from __future__ import annotations

import array
import hashlib
import io
import json
import os
import shutil
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import click_track  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "demo")
STAMP = 1793836800.0  # fixed "created" time: 2026-11-05


def fid(*parts) -> str:
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:12]


PLAYERS = [("Mia", "Vocals"), ("Theo", "Guitar"), ("Sam", "Bass"), ("Ruby", "Drums"), ("Jonas", "Keys")]
P = {name: fid("player", name) for name, _ in PLAYERS}
FILL_CLIP = fid("clip", "ruby-fill") + ".wav"

# (title, bpm, [(label, bars, bpm override, (count-in bars, style), [(text, who, clip)])])
SONGS = [
    ("Harbour Lights", 124, [
        ("Intro", 4, None, (1, "sticks"), [("Keys alone for 2 bars, guitar joins on bar 3", "Jonas", None)]),
        ("Verse 1", 8, None, None, [("Root notes only, follow the kick", "Sam", None),
                                   ("Keep it quiet, the vocal carries this", "all", None)]),
        ("Pre-chorus", 4, None, None, [("Build: open the hi-hat", "Ruby", None)]),
        ("Chorus", 8, None, None, [("Everyone in, full volume", "all", None),
                                  ("Harmony on the last line", "Theo", None)]),
        ("Verse 2", 8, None, None, [("Octave line this time", "Sam", None)]),
        ("Pre-chorus", 4, None, None, [("Fill into the chorus", "Ruby", FILL_CLIP)]),
        ("Chorus", 8, None, None, [("Everyone in, full volume", "all", None)]),
        ("Bridge", 8, 62, None, [("Half-time feel, watch Ruby", "all", None), ("Brushes", "Ruby", None)]),
        ("Chorus", 8, None, None, [("Last chorus: hold the final chord", "all", None)]),
        ("Outro", 4, None, None, [("Mia cuts us off", "all", None)]),
    ]),
    ("Paper Boats", 96, [
        ("Intro", 4, None, (1, "verbal"), [("Mia counts in, soft", "Mia", None),
                                          ("Fingerpicked, no pick", "Theo", None)]),
        ("Verse 1", 16, None, None, [("Bass waits until bar 9", "Sam", None)]),
        ("Chorus", 8, None, None, [("Rim clicks only", "Ruby", None)]),
        ("Verse 2", 16, None, None, []),
        ("Chorus", 8, None, None, [("Full kit now", "Ruby", None)]),
        ("Guitar solo", 8, None, None, [("Take your time, it's yours", "Theo", None),
                                       ("Pad under the solo", "Jonas", None)]),
        ("Chorus", 8, None, None, [("Drop to just vocals for the first 4 bars", "all", None)]),
        ("Outro", 2, None, None, [("Let it ring", "all", None)]),
    ]),
    ("Night Bus to Nowhere", 168, [
        ("Intro", 2, None, (1, "sticks"), [("Fast! Ruby counts it off", "all", None)]),
        ("Verse 1", 8, None, None, [("Palm-muted eighths", "Theo", None)]),
        ("Chorus", 8, None, None, [("Shout-along", "all", None)]),
        ("Verse 2", 8, None, None, []),
        ("Chorus", 8, None, None, []),
        ("Breakdown", 4, 84, None, [("Half speed, heavy", "all", None)]),
        ("Stop", 1, 84, None, [("Everyone stops dead", "all", None)]),
        ("Last chorus", 8, None, (1, "verbal"), [("Mia shouts the count back in", "Mia", None)]),
    ]),
    ("Slow Tide", 72, [
        ("Intro", 8, None, (1, "click"), [("Swell in from nothing", "Jonas", None)]),
        ("Verse 1", 8, None, None, [("Brushes, very light", "Ruby", None)]),
        ("Chorus", 8, None, None, []),
        ("Interlude", 4, 80, None, [("Pushes a little: 80 BPM", "all", None)]),
        ("Verse 2", 8, None, None, [("Back to 72", "all", None)]),
        ("Chorus", 8, None, None, [("Bass up an octave", "Sam", None)]),
        ("Outro", 8, None, None, [("Fade together, watch Jonas", "all", None)]),
    ]),
    ("Lantern Parade", 132, [
        ("Intro", 8, None, (2, "click"), [("Clap along with the crowd", "all", None)]),
        ("Verse 1", 8, None, None, []),
        ("Chorus", 8, None, None, [("Big unison riff", "all", None)]),
        ("Verse 2", 8, None, None, [("Slap bass this time", "Sam", None)]),
        ("Chorus", 8, None, None, []),
        ("Bridge", 8, None, None, [("Organ sound", "Jonas", None)]),
        ("Drum solo", 8, None, None, [("All yours, Ruby", "Ruby", None),
                                     ("Everyone back in on bar 1 of the chorus", "all", None)]),
        ("Chorus", 16, None, None, [("Double chorus, key change on bar 9", "all", None)]),
        ("Outro", 4, None, None, [("Big ending: three hits", "all", None)]),
    ]),
    ("Coffee at Midnight", 110, [
        ("Intro", 4, None, (1, "click"), [("New song, still working it out", "all", None)]),
        ("Verse 1", 8, None, None, [("Try the walking line", "Sam", None)]),
        ("Chorus", 8, None, None, [("Bridge idea: next rehearsal", "all", None)]),
    ]),
]

SETLISTS = [
    ("Friday at the Harbour Bar", ["Harbour Lights", "Night Bus to Nowhere", "Paper Boats",
                                   "Lantern Parade", "Slow Tide"]),
    ("Rehearsal: new songs", ["Coffee at Midnight", "Slow Tide"]),
]


def song_doc(title, bpm, sections):
    sid = fid("song", title)
    out = []
    for i, (label, bars, override, ci, hints) in enumerate(sections):
        sec = fid("section", title, str(i))
        out.append({
            "id": sec,
            "label": label,
            "order": i,
            "bars": bars,
            "bpm": override,
            "count_in": {"bars": ci[0], "style": ci[1]} if ci else {"bars": 0, "style": "none"},
            "hints": [{
                "id": fid("hint", sec, str(j)),
                "text": text,
                "audio": clip,
                "visibility": "all" if who == "all" else P[who],
            } for j, (text, who, clip) in enumerate(hints)],
        })
    return {"id": sid, "title": title, "default_bpm": bpm, "sections": out,
            "created_at": STAMP, "updated_at": STAMP}


def fill_clip() -> bytes:
    """A one-bar drum fill at 124 BPM: eight wood-block hits, accent on the last."""
    rate = click_track.RATE
    beat = 60.0 / 124
    total = int(rate * beat * 4.5)
    pcm = array.array("h", bytes(2 * total))
    for k in range(8):
        hit = click_track._wood(k == 7)
        start = int(rate * k * beat / 2)
        end = min(start + len(hit), total)
        pcm[start:end] = hit[: end - start]
    if sys.byteorder == "big":
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    for sub in ("songs", "setlists", "audio"):
        os.makedirs(os.path.join(OUT, sub))
    write_json(os.path.join(OUT, "band.json"), {
        "id": "band", "name": "The Paper Lanterns",
        "players": [{"id": P[n], "name": n, "role": r} for n, r in PLAYERS],
    })
    ids = {}
    for title, bpm, sections in SONGS:
        doc = song_doc(title, bpm, sections)
        ids[title] = doc["id"]
        write_json(os.path.join(OUT, "songs", doc["id"] + ".json"), doc)
    for name, titles in SETLISTS:
        sl = {"id": fid("setlist", name), "name": name, "songs": [ids[t] for t in titles]}
        write_json(os.path.join(OUT, "setlists", sl["id"] + ".json"), sl)
    with open(os.path.join(OUT, "audio", FILL_CLIP), "wb") as f:
        f.write(fill_clip())
    print(f"demo band written to {OUT}: {len(SONGS)} songs, {len(SETLISTS)} setlists")


if __name__ == "__main__":
    main()
