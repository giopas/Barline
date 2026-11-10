"""
Click track: a plain .wav with a click on every beat of a song.

Adapted from QLC+ Swiss Knife's core/click_track.py (same three sounds,
same synthesis, byte for byte: beep, wood block, tick, with a louder,
higher first beat of each bar). 0.16 adds four drum-kit sounds built the
same way (a few sines and seeded noise, no samples): ride bell, cowbell,
finger snap and side stick. Two changes for SSP:

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
import os
import sys
import wave

import timeline

RATE = 22050                   # Hz: a click is short, so this is plenty and keeps the file small
MAX_MS = 20 * 60 * 1000        # twenty minutes; a longer song is a mistake here
CLICK_MS = 25
HIGH_HZ, LOW_HZ = 1600, 1000
HIGH_AMP, LOW_AMP = 0.9, 0.6

SOUNDS = ("beep", "wood", "tick", "bell", "cowbell", "snap", "rim")
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


# -- 0.16: drum-kit sounds ------------------------------------------------------
# Mirrored line for line in web/static/audio.js. Each is built as floats,
# scaled so its loudest sample is `amp`, and faded out over its last 3 ms.
# Beat 1 is higher (about a minor third) and louder, like the others.


def _noise(n: int, seed: int = 12345) -> list:
    out = []
    for _ in range(n):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        out.append((seed / 0x3FFFFFFF) - 1.0)
    return out


def _resonate(x: list, freq: float, r: float) -> list:
    """Noise through a two-pole resonator: a band of noise around `freq`."""
    c = 2.0 * r * math.cos(2 * math.pi * freq / RATE)
    r2 = r * r
    y1 = y2 = 0.0
    out = []
    for v in x:
        y = v + c * y1 - r2 * y2
        out.append(y)
        y2, y1 = y1, y
    return out


def _finish(x: list, amp: float) -> array.array:
    peak = max(abs(v) for v in x) or 1.0
    n, fade = len(x), RATE * 3 // 1000
    out = array.array("h")
    for i, v in enumerate(x):
        f = min(1.0, (n - 1 - i) / fade) if i >= n - fade else 1.0
        out.append(round(32767 * amp * v / peak * f))
    return out


def _bell(accent: bool) -> array.array:
    """Ride cymbal bell: inharmonic partials that ring, plus the stick."""
    f, amp, ms = (760.0, 0.9, 240) if accent else (640.0, 0.7, 200)
    n = RATE * ms // 1000
    partials = ((1.0, 1.0, 5.0), (1.47, 0.7, 6.5), (2.09, 0.55, 8.0), (2.56, 0.4, 9.5), (3.42, 0.3, 12.0))
    noise = _noise(n, 777)
    x = []
    for i in range(n):
        t = i / RATE
        v = sum(a * math.sin(2 * math.pi * f * k * t) * math.exp(-d * i / n) for k, a, d in partials)
        x.append(v + 0.8 * noise[i] * math.exp(-i / (RATE * 0.002)))
    return _finish(x, amp)


def _cowbell(accent: bool) -> array.array:
    """Two square-ish tones a bit out of tune with each other (the classic
    drum-machine cowbell), a sharp hit then a short ring."""
    k, amp = (1.12, 0.9) if accent else (1.0, 0.7)
    n = RATE * 150 // 1000
    x = []
    for i in range(n):
        t = i / RATE
        v = 0.0
        for f in (540.0 * k, 800.0 * k):
            w = 2 * math.pi * f * t
            v += math.sin(w) + 0.33 * math.sin(3 * w) + 0.2 * math.sin(5 * w)
        x.append(v * (0.65 * math.exp(-i / (RATE * 0.008)) + 0.35 * math.exp(-i / (RATE * 0.045))))
    return _finish(x, amp)


def _snap(accent: bool) -> array.array:
    """Finger snap: a very short burst of bright noise."""
    f, amp = (2600.0, 0.9) if accent else (2100.0, 0.7)
    n = RATE * 60 // 1000
    band = _resonate(_noise(n, 4242), f, 0.93)
    x = []
    for i in range(n):
        env = min(1.0, i / (RATE * 0.0005)) * math.exp(-i / (RATE * 0.009))
        x.append(band[i] * env)
    return _finish(x, amp)


def _rim(accent: bool) -> array.array:
    """Side stick (cross-stick): a hard, woody knock off the snare rim."""
    f, amp = (1750.0, 0.9) if accent else (1450.0, 0.7)
    n = RATE * 50 // 1000
    body = _resonate(_noise(n, 999), 420.0, 0.96)
    peak = max(abs(v) for v in body) or 1.0
    x = []
    for i in range(n):
        t = i / RATE
        tone = math.sin(2 * math.pi * f * t) * math.exp(-i / (RATE * 0.006))
        x.append(0.65 * tone + 0.35 * body[i] / peak * math.exp(-i / (RATE * 0.01)))
    return _finish(x, amp)


def sounds(sound: str):
    """(first beat, other beats) samples for a sound name."""
    if sound in ("bell", "cowbell", "snap", "rim"):
        make = {"bell": _bell, "cowbell": _cowbell, "snap": _snap, "rim": _rim}[sound]
        return make(True), make(False)
    if sound == "wood":
        return _wood(True), _wood(False)
    if sound == "tick":
        return _tick(True), _tick(False)
    return _click(HIGH_HZ, HIGH_AMP), _click(LOW_HZ, LOW_AMP)


def check_sound(sound) -> str:
    sound = (str(sound).strip().lower() if sound not in (None, "") else DEFAULT_SOUND)
    if sound not in SOUNDS:
        raise ValueError("The click sound is one of: " + ", ".join(SOUNDS) + ".")
    return sound


VOICE_WORDS = ("one", "two", "three", "four")


def _voice_samples(voice_dir: str) -> dict:
    """The spoken count-in (web/static/voice/*.wav, 22050 Hz mono 16-bit),
    {1: samples, ...}; empty if the files aren't there."""
    out = {}
    for n, word in enumerate(VOICE_WORDS, 1):
        path = os.path.join(voice_dir or "", word + ".wav")
        try:
            with wave.open(path, "rb") as w:
                if w.getframerate() != RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
                    continue
                data = array.array("h", w.readframes(w.getnframes()))
                if sys.byteorder == "big":
                    data.byteswap()
                out[n] = data
        except (OSError, wave.Error, EOFError):
            continue
    return out


def _level(value, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def song_wav(song: dict, sound: str = DEFAULT_SOUND, count_in: bool = True, options: dict = None,
             voice_dir: str = None) -> bytes:
    """The whole song as a 16-bit WAV, clicks placed from the tempo map.

    `options` are the same per-device click choices as the live click
    (timeline.click_options: subdivision, voice, mode) plus levels
    (accent/beat/sub, 0..1) and channel ("both", "left", "right" -- left or
    right makes a stereo file with the click in one ear only).
    Raises ValueError in plain words for an empty or over-long song."""
    sound = check_sound(sound)
    options = options or {}
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

    levels = {"accent": _level(options.get("accent"), 1.0), "beat": _level(options.get("beat"), 1.0),
              "sub": _level(options.get("sub"), 0.45)}
    channel = options.get("channel") if options.get("channel") in ("left", "right") else "both"
    voice = _voice_samples(voice_dir) if timeline.click_options(options)["voice"] else {}
    total = round(tl["total_ms"] * RATE / 1000)
    mix = [0] * total
    high, low = sounds(sound)
    stick_high, stick_low = sounds("wood" if sound == "tick" else "tick")
    for ev in timeline.click_events(tl, options):
        bar = tl["bars"][ev["bar"]]
        sticks = bar["count_in"] and bar["count_in_style"] == "sticks"
        if ev["kind"] == "voice" and ev["n"] in voice:
            ring, gain = voice[ev["n"]], 1.0
        else:
            accent = ev["kind"] == "accent" or (ev["kind"] == "voice" and ev["n"] == 1)
            ring = (stick_high if accent else stick_low) if sticks else (high if accent else low)
            gain = levels["sub"] if ev["kind"] == "sub" else levels["accent"] if accent else levels["beat"]
        if gain <= 0:
            continue
        start = round(ev["t"] * RATE / 1000)
        for i in range(min(len(ring), total - start)):
            mix[start + i] += ring[i] * gain
    mono = array.array("h", (max(-32767, min(32767, round(v))) for v in mix))
    if channel == "both":
        pcm, channels = mono, 1
    else:
        pcm, channels = array.array("h", bytes(4 * total)), 2
        pcm[(0 if channel == "left" else 1)::2] = mono
    if sys.byteorder == "big":
        pcm.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def setlist_zip(setlist: dict, songs: dict, sound: str = DEFAULT_SOUND, options: dict = None,
                voice_dir: str = None) -> bytes:
    """Practice pack: one numbered click track per song of a setlist, in a
    .zip -- for playing along at home with no server, in any music player."""
    import zipfile  # only needed here

    buf = io.BytesIO()
    n = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for song_id in setlist.get("songs", []):
            song = songs.get(song_id)
            if not song:
                continue
            try:
                wav = song_wav(song, sound, True, options, voice_dir)
            except ValueError:
                continue  # an empty song has no click to practise to
            n += 1
            safe = "".join(c for c in song.get("title", "song") if c.isalnum() or c in " .,()+-_").strip()[:60]
            z.writestr(f"{n:02d} {safe or 'song'} ({song.get('default_bpm', '')} BPM).wav", wav)
    if not n:
        raise ValueError("None of the songs in this setlist has any bars yet.")
    return buf.getvalue()
