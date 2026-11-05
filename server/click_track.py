"""
Click track: a plain .wav with a click on every beat of a song.

Adapted from QLC+ Swiss Knife's core/click_track.py (same three sounds,
same synthesis, byte for byte: beep, wood block, tick, with a louder,
higher first beat of each bar). Two changes for SSP:

  * a song here can change tempo between sections and has count-ins, so
    the clicks are placed from the tempo map (server/timeline.py) instead
    of a single BPM;
  * the file is never written to disk on the server -- it's built in
    memory and handed to the browser as a download.

The browser's live metronome (web/static/audio.js) synthesises the very
same samples with the same formulas, so the practice file and the stage
click sound identical. Standard library only (wave, array, math).
"""

from __future__ import annotations

import array
import io
import math
import sys
import wave

import timeline

RATE = 22050                   # Hz: a click is short, so this is plenty and keeps the file small
MAX_MS = 20 * 60 * 1000        # twenty minutes; a longer song is a mistake here
CLICK_MS = 25
HIGH_HZ, LOW_HZ = 1600, 1000
HIGH_AMP, LOW_AMP = 0.9, 0.6

SOUNDS = ("beep", "wood", "tick")
DEFAULT_SOUND = "beep"


def _click(freq: int, amp: float) -> array.array:
    n = RATE * CLICK_MS // 1000
    return array.array("h", (round(32767 * amp * math.sin(2 * math.pi * freq * i / RATE) * math.exp(-6.0 * i / n))
                             for i in range(n)))


def _wood(accent: bool) -> array.array:
    f, amp = (1500, 0.95) if accent else (900, 0.65)
    n = RATE * 30 // 1000
    return array.array("h", (round(32767 * amp * (0.75 * math.sin(2 * math.pi * f * i / RATE)
                                                  + 0.25 * math.sin(2 * math.pi * f * 2.43 * i / RATE))
                                   * math.exp(-9.0 * i / n)) for i in range(n)))


def _tick(accent: bool) -> array.array:
    n = RATE * (40 if accent else 12) // 1000
    amp = 0.9 if accent else 0.5
    seed, out = 12345, []
    for i in range(n):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        noise = (seed / 0x3FFFFFFF) - 1.0
        body = 0.6 * math.sin(2 * math.pi * 220 * i / RATE) if accent else 0.0
        out.append(round(32767 * amp * (0.7 * noise + body) / 1.3 * math.exp(-7.0 * i / n)))
    return array.array("h", out)


def sounds(sound: str):
    """(first beat, other beats) samples for a sound name."""
    if sound == "wood":
        return _wood(True), _wood(False)
    if sound == "tick":
        return _tick(True), _tick(False)
    return _click(HIGH_HZ, HIGH_AMP), _click(LOW_HZ, LOW_AMP)


def check_sound(sound) -> str:
    sound = (str(sound).strip().lower() if sound not in (None, "") else DEFAULT_SOUND)
    if sound not in SOUNDS:
        raise ValueError("The click sound is beep, wood or tick.")
    return sound


def song_wav(song: dict, sound: str = DEFAULT_SOUND, count_in: bool = True) -> bytes:
    """The whole song as a mono 16-bit WAV, clicks placed from the tempo map.
    Raises ValueError in plain words for an empty or over-long song."""
    sound = check_sound(sound)
    tl = timeline.build(song, lead_in=count_in)
    if not count_in:
        tl["bars"] = [b for b in tl["bars"] if not b["count_in"]]
        if tl["bars"]:
            shift = tl["bars"][0]["start_ms"]
            for b in tl["bars"]:
                b["start_ms"] -= shift
            tl["total_ms"] -= shift
    if not tl["bars"]:
        raise ValueError("Give the song at least one section with some bars first.")
    if tl["total_ms"] > MAX_MS:
        raise ValueError("A click track is at most 20 minutes long.")

    total = round(tl["total_ms"] * RATE / 1000)
    pcm = array.array("h", bytes(2 * total))
    high, low = sounds(sound)
    for bar in tl["bars"]:
        for beat in range(bar["beats"]):
            start = round((bar["start_ms"] + beat * bar["beat_ms"]) * RATE / 1000)
            ring = high if beat == 0 else low
            end = min(start + len(ring), total)
            pcm[start:end] = ring[: end - start]
    if sys.byteorder == "big":
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
