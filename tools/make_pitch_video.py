#!/usr/bin/env python3
"""
Barline pitch video: a vertical (9:16) MP4 that sells Barline to a band in
about a minute and a half, ready to drop into a WhatsApp chat (or an
Instagram / TikTok story).

What it makes, from the repo's own screenshots and GIFs:

  * 11 slides with the real screens, animated (GIFs play at their own pace,
    screenshots and feature cards slide in), story-style progress bar on top
    and Barline's four beat dots pulsing in time with the music;
  * a spoken voice-over (macOS `say`, `espeak-ng`, or `edge-tts`), with
    burned-in captions so it also works with the sound off;
  * a 120 BPM backing groove built from Barline's own click sounds
    (server/click_track.py: wood block, side stick, ride bell, cowbell),
    with bass and pads, ducked smoothly under the voice. Slide changes land
    on a beat, like Barline's Jump lands on the next bar line.

Usage (from anywhere; paths are found from this file):

    python3 tools/make_pitch_video.py                 # dist/marketing/Barline_Pitch.mp4
    python3 tools/make_pitch_video.py --stills        # also one PNG per slide + a PDF deck
    python3 tools/make_pitch_video.py --hd            # 1080x1920 instead of 720x1280
    python3 tools/make_pitch_video.py --only 5        # just slide 5, for a quick look
    python3 tools/make_pitch_video.py --list-voices   # voices `say` has on this Mac
    python3 tools/make_pitch_video.py --voice "Daniel" --rate 175
    python3 tools/make_pitch_video.py --tts edge      # Microsoft neural voice (online), much less robotic
    python3 tools/make_pitch_video.py --tts edge --voice en-GB-RyanNeural
    python3 -m edge_tts --list-voices                 # all edge voices

Needs Pillow and ffmpeg (the Barline server itself needs neither):

    python3 -m pip install --user Pillow       # or a venv, see the error text
    brew install ffmpeg                         # macOS; apt install ffmpeg on Linux

Optional, for a more natural voice: `pip install edge-tts`, then --tts edge
(needs internet while generating; nothing else in Barline goes online). On a
Mac, better `say` voices are a free download: System Settings > Accessibility
> Read & Speak (Spoken Content before macOS 26) > System voice menu > Manage
Voices... (e.g. "Zoe (Premium)").

To change what the video says, edit SLIDES below. Each slide's screenshots
come from screenshots/ (retake them with tools/shots.py); a missing file is
skipped with a warning, so the video still builds.
"""

from __future__ import annotations

import argparse
import array
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    sys.exit(
        "This tool needs Pillow (the Barline server doesn't, only this marketing tool).\n\n"
        "Install it with:\n"
        "    python3 -m pip install --user Pillow\n\n"
        "If pip refuses with \"externally-managed-environment\" (Homebrew's Python), either:\n"
        "    python3 -m pip install --user --break-system-packages Pillow\n"
        "or use a virtual environment, once:\n"
        "    python3 -m venv .venv && .venv/bin/pip install Pillow\n"
        "and then run:  .venv/bin/python tools/make_pitch_video.py"
    )

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHOTS = os.path.join(ROOT, "screenshots")
ICONS = os.path.join(ROOT, "packaging", "icons")
OUT_DIR = os.path.join(ROOT, "dist", "marketing")

RATE = 22050          # same rate as Barline's click sounds and spoken count-in
BPM = 120
BEAT = 60.0 / BPM     # 0.5 s
FPS = 30
XFADE = 0.35          # crossfade between slides, seconds

# Barline's colours (web/static/style.css)
BG = (18, 20, 24)
CARD = (29, 32, 38)
LINE = (44, 48, 57)
TEXT = (232, 233, 236)
DIM = (154, 160, 171)
WHITE = (255, 255, 255)
BLUE = (91, 140, 255)
GREEN = (69, 192, 138)
GOLD = (226, 185, 59)

URL = "giopas.github.io/Barline"

# Text the voice says differently from how the captions write it.
SPOKEN = {
    URL: "giopas dot github dot io slash Barline",
    ".wav": "wave",
    "BPM": "B P M",
}

SLIDES = [
    {
        "kicker": "MADE FOR OUR BAND",
        "color": BLUE,
        "title": "Barline",
        "sub": "Plan our songs together, then every phone and tablet follows them in sync on stage.",
        "media": ["01-editor.png", "08-live-phone-bass.png"],
        "bullets": [
            "Runs on our own Wi-Fi: no internet, no accounts, no app store",
            "Sections, bars, tempo changes, count-ins and cues for each player",
            "Every screen moves bar by bar together, each with its own click",
        ],
        "vo": "Hey everyone! This is Barline, a tool I built for our band. We plan our songs together, "
              "and then every phone and tablet follows them in sync on stage.",
    },
    {
        "kicker": "1 · SONG STRUCTURE & HINTS",
        "color": GREEN,
        "title": "Map Out Songs Together",
        "sub": "Verses, choruses, bridges, solos: everyone sees the exact shape of the song.",
        "media": ["planning.gif", "12-phone-editor.png"],
        "bullets": [
            "Bars and tempo per section: a half-time bridge gets its own BPM",
            "Hints for the whole band, or aimed at just one player",
            "A voice memo of up to 30 seconds on any hint, for that riff",
        ],
        "vo": "First, we map out each song section by section, with bar counts, tempo changes, "
              "voice memos, and reminders aimed at specific players.",
    },
    {
        "kicker": "2 · REAL-TIME BAND SYNC",
        "color": BLUE,
        "title": "Everyone Edits the Same Copy",
        "sub": "Change a bar count on the laptop and the singer's phone updates a moment later.",
        "media": ["sync.gif", "11-phone-who.png"],
        "bullets": [
            "No more \"which version is the latest?\" at rehearsal",
            "Say who's holding the phone, and your cues stand out",
            "Like a shared whiteboard in our rehearsal room",
        ],
        "vo": "Everyone edits the exact same copy, live. Change a bar count or add a hint on your phone, "
              "and everyone else's screen updates right away.",
    },
    {
        "kicker": "3 · SETLISTS IN SECONDS",
        "color": GOLD,
        "title": "Setlists & Count-Ins in One Go",
        "sub": "Drag songs into playing order, filter by tags, or paste a whole set.",
        "media": ["02-setlist.png", "15-quick-add.png", "19-count-ins.png"],
        "bullets": [
            "Drag to reorder, filter by tag, see the set's total time",
            "Paste a list (\"Seven Seas - 124 - 3:52\") or tap a tempo in",
            "Set the count-ins for one song or the whole set at once",
        ],
        "vo": "Building a setlist is quick. Drag songs into playing order, paste a whole list of titles "
              "and tempos at once, and set the count-ins for the whole set in one go.",
    },
    {
        "kicker": "4 · LIVE ON STAGE",
        "color": GREEN,
        "title": "One Tap, Every Screen Moves",
        "sub": "Anyone can press Start, usually the drummer, and every screen follows bar by bar.",
        "media": ["live.gif", "05-live-ready-tablet.png"],
        "bullets": [
            "Current section, beat, bar count and what's coming next",
            "Screens stay awake; a page-turner pedal starts the songs",
            "If the laptop drops out mid-song, every phone keeps playing",
        ],
        "vo": "When we play, our drummer taps Start, and every screen in the room moves through the song "
              "bar by bar. Even if the laptop drops out mid-song, your phone keeps playing.",
    },
    {
        "kicker": "5 · YOUR SCREEN, YOUR ROLE",
        "color": BLUE,
        "title": "Your Part, Front and Centre",
        "sub": "The drummer gets giant numbers; the rest of us get our own cues first.",
        "media": ["07-live-tablet-drums.png", "08-live-phone-bass.png", "09-live-count-in.png"],
        "bullets": [
            "Drummer's big view: tempo, bar (3/8) and bars to the next part",
            "Your phone puts the hints meant for you up front",
            "Count-ins flash yellow with the beat before each change",
        ],
        "vo": "Each of us sees what matters for our role: huge bar numbers and countdowns for the drummer, "
              "and our own cues up front on our phones.",
    },
    {
        "kicker": "6 · CLICK, JUMP & NUDGE",
        "color": GOLD,
        "title": "Your Own Click, Shared Beat",
        "sub": "The tempo is shared, but every player sets up their own in-ears.",
        "media": ["14-click-settings.png", "20-live-jump.png"],
        "bullets": [
            "7 sounds: wood, beep, tick, ride bell, cowbell, snap, side stick",
            "8ths, 16ths, triplets, spoken count-in, or one ear only",
            "Singer went to the chorus early? Jump lands on the next bar line",
        ],
        "vo": "Everyone sets up their own click: woodblock, cowbell, subdivisions, a spoken count-in, "
              "or one ear only for in-ears. And if the singer goes to the chorus early, "
              "we jump there on the next bar line.",
    },
    {
        "kicker": "7 · PAPER CHARTS",
        "color": GREEN,
        "title": "Charts & Floor Sheets to Print",
        "sub": "Prefer paper on the music stand or taped to the floor? One click makes a PDF.",
        "media": ["10-print-chart-bass.png", "16-paper-setlist-and-floor.png"],
        "bullets": [
            "A chart per player, with a box per bar to count along on",
            "Floor sheets in the biggest type that fits on one page",
            "Each PDF carries the song inside: import it straight back",
        ],
        "vo": "Prefer paper? One click makes a clean PDF chart for each player, "
              "or a giant-type floor sheet to tape down at our feet.",
    },
    {
        "kicker": "8 · BARLINE POCKET",
        "color": BLUE,
        "title": "Practise at Home, Offline",
        "sub": "Open " + URL + " on your phone: no server needed.",
        "media": ["22-pocket-phone.png", "21-import-merge.png"],
        "fallback": ["12-phone-editor.png"],
        "bullets": [
            "Works offline on your phone, click and voice memos included",
            "Back at rehearsal, merge your notes into the band's songs",
            "Or download practice click tracks (.wav) for the whole set",
        ],
        "vo": "At home, open Barline Pocket on your phone to practise with the click and add your own notes. "
              "At the next rehearsal we merge everyone's notes back in, and Barline asks before it replaces anything.",
    },
    {
        "kicker": "9 · NO WI-FI? NO PROBLEM",
        "color": GREEN,
        "title": "Plug In and Play Anywhere",
        "sub": "One laptop, or a Raspberry Pi in the gig bag, runs the whole show.",
        "media": ["13-launcher.png", "18-launcher-wifi.png", "04-connect.png"],
        "bullets": [
            "Apps for Mac, Windows and Linux, or a Raspberry Pi",
            "No Wi-Fi at the venue? It becomes the band's own network",
            "Two QR codes: one joins the Wi-Fi, one opens Barline",
        ],
        "vo": "And in a basement with no Wi-Fi, the laptop or a little Raspberry Pi becomes our own band network. "
              "Scan one code to join it, and another to open Barline.",
    },
    {
        "kicker": "10 · READY TO ROCK",
        "color": GOLD,
        "title": "Let's Try It at Rehearsal!",
        "sub": "Free and open source, built for how we actually play together.",
        "media": ["08-live-phone-bass.png", "04-connect.png"],
        "bullets": [
            "1. Open " + URL + " on your phone",
            "2. Add it to your Home Screen so it opens full-screen",
            "3. At rehearsal: scan the QR code, pick your name, play!",
        ],
        "vo": "Have a look right now at " + URL + ", and let's give it a spin at our next rehearsal!",
        "footer": "Barline {version} · free & open source (MIT) · inspired by song-map.com",
    },
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def barline_version() -> str:
    try:
        with open(os.path.join(ROOT, "server", "version.py"), encoding="utf-8") as f:
            m = re.search(r"[\"'](\d+\.\d+\.\d+)[\"']", f.read())
        return m.group(1) if m else ""
    except OSError:
        return ""


def ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


def read_wav_floats(path: str) -> list:
    with wave.open(path, "rb") as w:
        data = array.array("h", w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        data.byteswap()
    return [v / 32768.0 for v in data]


def write_wav(path: str, samples: list) -> None:
    pcm = array.array("h", (max(-32767, min(32767, int(v * 32767))) for v in samples))
    if sys.byteorder == "big":
        pcm.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Voice-over
# ---------------------------------------------------------------------------

# Nicer built-in macOS voices first; whichever is installed wins.
PREFERRED_SAY_VOICES = [
    "Zoe (Premium)", "Ava (Premium)", "Evan (Premium)", "Jamie (Premium)",
    "Zoe (Enhanced)", "Ava (Enhanced)", "Evan (Enhanced)", "Samantha (Enhanced)", "Daniel (Enhanced)",
    "Samantha", "Daniel", "Alex",
]


def say_voices() -> list:
    """[(name, locale)] of the voices `say` knows."""
    if not shutil.which("say"):
        return []
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    voices = []
    for line in out.splitlines():
        m = re.match(r"^(.+?)\s{2,}([a-z]{2}[_-][A-Za-z]{2,})", line)
        if m:
            voices.append((m.group(1).strip(), m.group(2)))
    return voices


def pick_say_voice(requested: str = None):
    names = [n for n, loc in say_voices()]
    if requested:
        if requested not in names:
            print(f"   ! `say` has no voice called {requested!r}; try --list-voices. Using the default.")
            return None
        return requested
    english = {n for n, loc in say_voices() if loc.lower().startswith("en")}
    for v in PREFERRED_SAY_VOICES:
        if v in english:
            return v
    return None


def spoken(text: str) -> str:
    for written, said in SPOKEN.items():
        text = text.replace(written, said)
    return text


def edge_tts_command():
    """How to run edge-tts: the command if it's on the PATH, otherwise as a
    module of this Python (`pip install --user` puts the command in a folder,
    e.g. ~/Library/Python/3.x/bin, that often isn't on the PATH)."""
    if shutil.which("edge-tts"):
        return ["edge-tts"]
    try:
        import importlib.util
        if importlib.util.find_spec("edge_tts"):
            return [sys.executable, "-m", "edge_tts"]
    except (ImportError, ValueError):
        pass
    return None


class Voice:
    """Turns a line of text into a 22050 Hz mono WAV with one engine."""

    def __init__(self, engine: str, voice: str = None, rate: int = 180):
        self.engine, self.voice, self.rate = engine, voice, rate
        self.label = engine

    @classmethod
    def choose(cls, tts: str, voice: str, rate: int) -> "Voice":
        if tts == "none":
            return cls("none")
        if tts == "edge":
            cmd = edge_tts_command()
            if cmd:
                v = cls("edge", voice or "en-US-AndrewNeural", rate)
                v.edge_cmd = cmd
                v.label = f"edge-tts ({v.voice})"
                return v
            print("   ! edge-tts isn't installed for this Python "
                  f"({sys.executable} -m pip install --user edge-tts); falling back.")
        if tts in ("say", "auto", "edge") and shutil.which("say"):
            v = cls("say", pick_say_voice(voice if tts == "say" else None), rate)
            v.label = f"macOS say ({v.voice or 'system voice'})"
            return v
        if tts in ("espeak", "auto", "edge", "say") and shutil.which("espeak-ng"):
            v = cls("espeak", voice or "en-us", rate)
            v.label = f"espeak-ng ({v.voice})"
            return v
        print("   ! No text-to-speech found: the video gets captions and music, no voice.")
        return cls("none")

    def render(self, text: str, out_wav: str, tmp: str) -> bool:
        if self.engine == "none":
            return False
        text = spoken(text)
        raw = os.path.join(tmp, "tts_raw")
        try:
            if self.engine == "say":
                raw += ".aiff"
                cmd = ["say", "-r", str(self.rate), "-o", raw]
                if self.voice:
                    cmd += ["-v", self.voice]
                run(cmd + [text])
            elif self.engine == "espeak":
                raw += ".wav"
                run(["espeak-ng", "-v", self.voice, "-s", str(int(self.rate * 0.92)), "-w", raw, text])
            elif self.engine == "edge":
                raw += ".mp3"
                pct = round((self.rate / 180.0 - 1) * 100)
                run(self.edge_cmd + ["--voice", self.voice, f"--rate={pct:+d}%", "--text", text,
                     "--write-media", raw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Clean, consistent level: trim silence at both ends, gentle compression, normalise.
            run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-af",
                 "silenceremove=start_periods=1:start_threshold=-50dB,"
                 "areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                 "highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=5:release=120,"
                 "loudnorm=I=-16:TP=-1.5:LRA=7",
                 "-ar", str(RATE), "-ac", "1", "-sample_fmt", "s16", out_wav])
            return True
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"   ! {self.label} failed ({e}); this slide gets no voice.")
            return False


# ---------------------------------------------------------------------------
# Timing: slide lengths snapped to the beat
# ---------------------------------------------------------------------------

def plan_timing(slides: list, voice_lens: list) -> list:
    """Per slide: start, dur, voice_at (seconds, absolute). Every slide starts on a beat."""
    plan, t = [], 0.0
    for i, (slide, vo) in enumerate(zip(slides, voice_lens)):
        lead = 2.0 if i == 0 else 0.6            # one bar of groove before the first word
        tail = 3.0 if i == len(slides) - 1 else 0.7
        dur = max(5.0, lead + vo + tail)
        dur = math.ceil(dur / BEAT - 1e-9) * BEAT
        plan.append({"start": t, "dur": dur, "voice_at": t + lead, "voice_len": vo})
        t += dur
    return plan


def estimate_speech(text: str) -> float:
    return max(2.5, len(text.split()) / 2.7)


# ---------------------------------------------------------------------------
# Soundtrack: Barline's click sounds + bass + pads, ducked under the voice
# ---------------------------------------------------------------------------

def load_kit() -> dict:
    """Barline's own percussion (server/click_track.py), as floats. Falls back
    to a plain synthesised tick if the module can't be imported."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "server"))
        import click_track  # noqa: E402
        kit = {}
        for name in ("wood", "rim", "bell", "cowbell", "snap"):
            hi, lo = click_track.sounds(name)
            kit[name] = ([v / 32768.0 for v in hi], [v / 32768.0 for v in lo])
        return kit
    except Exception as e:  # pragma: no cover - only without the repo around
        print(f"   ! Couldn't load server/click_track.py ({e}); using a plain tick.")
        n = int(RATE * 0.03)
        tick = [math.sin(2 * math.pi * 1500 * i / RATE) * math.exp(-9 * i / n) for i in range(n)]
        return {k: (tick, tick) for k in ("wood", "rim", "bell", "cowbell", "snap")}


NOTE = {"A2": 110.0, "C3": 130.81, "F2": 87.31, "G2": 98.0}
# Am - F - C - G, one bar each: (bass root, pad triad)
PROGRESSION = [
    (NOTE["A2"], (220.0, 261.63, 329.63)),
    (NOTE["F2"], (174.61, 220.0, 261.63)),
    (NOTE["C3"], (196.0, 261.63, 329.63)),
    (NOTE["G2"], (196.0, 246.94, 293.66)),
]


def _chord_bar(root: float, triad: tuple) -> list:
    """One bar (2 s) of bass + pad + soft kick, as floats."""
    n = int(4 * BEAT * RATE)
    out = [0.0] * n
    # Bass: beat 1, the "and" of 2, beat 3 (a little push), plucked and warm.
    for beat_pos, vel in ((0.0, 1.0), (1.5, 0.55), (2.0, 0.85)):
        s0 = int(beat_pos * BEAT * RATE)
        length = int(0.9 * BEAT * RATE * (2 if beat_pos == 2.0 else 1))
        for j in range(min(length, n - s0)):
            t = j / RATE
            env = min(1.0, t / 0.006) * math.exp(-3.5 * t) * vel
            w = 2 * math.pi * root * t
            out[s0 + j] += 0.30 * env * (math.sin(w) + 0.25 * math.sin(2 * w) + 0.08 * math.sin(3 * w))
    # Pad: the triad, slow swell, two slightly detuned sines per note.
    for j in range(n):
        t = j / RATE
        env = min(1.0, t / 0.35) * min(1.0, (n - j) / (0.25 * RATE))
        v = 0.0
        for f in triad:
            v += math.sin(2 * math.pi * f * t) + math.sin(2 * math.pi * f * 1.004 * t)
        out[j] += 0.012 * env * v
    # Soft kick on 1 and 3: a pitch-dropping sine.
    for beat in (0, 2):
        s0 = int(beat * BEAT * RATE)
        ph = 0.0
        for j in range(int(0.22 * RATE)):
            t = j / RATE
            f = 48 + 90 * math.exp(-t * 28)
            ph += 2 * math.pi * f / RATE
            out[s0 + j] += 0.42 * math.sin(ph) * math.exp(-t * 14)
    return out


def build_music(total: float, kit: dict) -> list:
    n = int(total * RATE)
    bars = [_chord_bar(r, tri) for r, tri in PROGRESSION]
    music = [0.0] * n
    bar_n = len(bars[0])
    for b in range(0, n // bar_n + 1):
        src, s0 = bars[b % 4], b * bar_n
        m = min(bar_n, n - s0)
        if m <= 0:
            break
        music[s0:s0 + m] = [a + c for a, c in zip(music[s0:s0 + m], src[:m])]

    def hit(sample: list, at: float, gain: float) -> None:
        s0 = int(at * RATE)
        for j in range(min(len(sample), n - s0)):
            music[s0 + j] += sample[j] * gain

    eighth = BEAT / 2
    for k in range(int(total / eighth)):
        at = k * eighth
        beat_in_bar = (k // 2) % 4
        bar = k // 8
        if k % 2 == 0:
            if beat_in_bar in (1, 3):
                hit(kit["rim"][0], at, 0.30)                  # side stick backbeat
            if beat_in_bar == 0 and bar % 4 == 0:
                hit(kit["wood"][0], at, 0.12)                 # wood block marks every 4 bars
        hit(kit["bell"][1], at, 0.07 if k % 2 == 0 else 0.045)  # ride bell 8ths, quiet
        if beat_in_bar == 3 and k % 2 == 1 and bar % 2 == 1:
            hit(kit["cowbell"][1], at, 0.06)                  # a little cowbell pickup

    # Fade in over a beat, out over the last 2.5 s.
    for j in range(min(n, int(BEAT * RATE))):
        music[j] *= j / (BEAT * RATE)
    fade = int(2.5 * RATE)
    for j in range(max(0, n - fade), n):
        music[j] *= (n - j) / fade
    return music


def mix_soundtrack(total: float, plan: list, vo_wavs: list, music_on: bool, kit: dict, out_wav: str) -> None:
    n = int(total * RATE)
    voice = [0.0] * n
    for p, wav in zip(plan, vo_wavs):
        if not wav:
            continue
        s = read_wav_floats(wav)
        s0 = int(p["voice_at"] * RATE)
        m = min(len(s), n - s0)
        voice[s0:s0 + m] = s[:m]

    if not music_on:
        write_wav(out_wav, voice)
        return

    music = build_music(total, kit)
    # Ducking: follow the voice's level in 10 ms blocks (fast attack, slow
    # release), so the music dips smoothly while someone talks instead of
    # pumping on every syllable.
    block = RATE // 100
    gains, env = [], 0.0
    for b0 in range(0, n, block):
        seg = voice[b0:b0 + block]
        rms = math.sqrt(sum(v * v for v in seg) / max(1, len(seg)))
        env = max(rms, env * 0.965)  # ~280 ms release
        duck = min(1.0, env / 0.04)
        gains.append(0.85 - 0.6 * duck)  # 0.85 alone, 0.25 under the voice
    out = [0.0] * n
    for i in range(n):
        b = i // block
        g0 = gains[b]
        g1 = gains[b + 1] if b + 1 < len(gains) else g0
        g = g0 + (g1 - g0) * ((i % block) / block)
        out[i] = voice[i] + music[i] * g
    peak = max(1e-9, max(abs(v) for v in out))
    if peak > 0.97:
        k = 0.97 / peak
        out = [v * k for v in out]
    write_wav(out_wav, out)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

FONT_FILES = {
    False: ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
            "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    True: ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
           "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}
_fonts: dict = {}


def font(size: int, bold: bool = False):
    key = (size, bold)
    if key not in _fonts:
        for path in FONT_FILES[bold]:
            if os.path.exists(path):
                _fonts[key] = ImageFont.truetype(path, size)
                break
        else:
            _fonts[key] = ImageFont.load_default()
    return _fonts[key]


def wrap(draw, text: str, f, max_w: int) -> list:
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def rounded_mask(size: tuple, radius: int) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def with_alpha(im: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return im
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return out


class Renderer:
    def __init__(self, width: int, captions: bool, version: str):
        self.W, self.H = width, width * 16 // 9
        self.S = width / 720.0
        self.captions = captions
        self.version = version
        self.icon = None
        icon_path = os.path.join(ICONS, "icon-256.png")
        if os.path.exists(icon_path):
            self.icon = Image.open(icon_path).convert("RGBA").resize((self.s(46), self.s(46)), Image.LANCZOS)
        self._cap_cache: dict = {}

    def s(self, v: float) -> int:
        return int(round(v * self.S))

    # -- static parts of a slide ------------------------------------------------

    def prepare(self, slide: dict, idx: int, total: int) -> dict:
        s, W, H = self.s, self.W, self.H
        base = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(base)
        color = slide["color"]

        # A soft glow of the slide's colour behind the title.
        glow = Image.new("L", (W, H), 0)
        ImageDraw.Draw(glow).ellipse([-s(200), -s(260), W + s(200), s(420)], fill=40)
        glow = glow.filter(ImageFilter.GaussianBlur(s(90)))
        base.paste(Image.new("RGB", (W, H), color), (0, 0), glow)

        # Header: icon, name, (beat dots drawn per frame)
        if self.icon:
            base.paste(self.icon, (s(28), s(34)), self.icon)
        d.text((s(86), s(33)), "Barline", fill=WHITE, font=font(s(27), True))
        d.text((s(87), s(64)), "Song & Setlist Planner", fill=DIM, font=font(s(15)))

        # Kicker pill
        y = s(112)
        fk = font(s(17), True)
        kw = int(d.textlength(slide["kicker"], font=fk)) + s(32)
        d.rounded_rectangle([s(28), y, s(28) + kw, y + s(36)], radius=s(18), fill=CARD, outline=color, width=max(2, s(2)))
        d.text((s(44), y + s(8)), slide["kicker"], fill=color, font=fk)
        y += s(52)

        ft = font(s(44) if len(slide["title"]) > 12 else s(64), True)
        lh = int(ft.size * 1.16)
        for line in wrap(d, slide["title"], ft, W - s(56)):
            d.text((s(28), y), line, fill=WHITE, font=ft)
            y += lh
        y += s(6)
        fs = font(s(22))
        for line in wrap(d, slide["sub"], fs, W - s(56)):
            d.text((s(28), y), line, fill=DIM, font=fs)
            y += s(30)
        vis_top = y + s(22)

        # Footer line (last slide)
        bottom_limit = H - s(26)
        if slide.get("footer"):
            ff = font(s(15))
            text = slide["footer"].format(version=self.version).replace("  ", " ")
            tw = d.textlength(text, font=ff)
            d.text(((W - tw) / 2, H - s(42)), text, fill=DIM, font=ff)
            bottom_limit = H - s(56)

        # Bullet cards, bottom-up, above the caption band.
        cap_top = H - s(178) if self.captions else bottom_limit
        cap_top = min(cap_top, bottom_limit)
        fb = font(s(21))
        cards = []
        for text in slide["bullets"]:
            lines = wrap(d, text, fb, W - s(56) - s(44))
            h = s(28) + len(lines) * s(28)
            card = Image.new("RGBA", (W - s(56), h), (0, 0, 0, 0))
            cd = ImageDraw.Draw(card)
            cd.rounded_rectangle([0, 0, card.width - 1, h - 1], radius=s(14), fill=CARD + (255,), outline=LINE, width=1)
            cd.rounded_rectangle([0, 0, s(6), h - 1], radius=s(3), fill=color)
            ty = s(14)
            for ln in lines:
                cd.text((s(26), ty), ln, fill=TEXT, font=fb)
                ty += s(28)
            cards.append(card)
        gap = s(12)
        total_h = sum(c.height for c in cards) + gap * (len(cards) - 1)
        by = cap_top - s(14) - total_h
        placed = []
        for c in cards:
            placed.append((c, by))
            by += c.height + gap
        vis_bottom = placed[0][1] - s(24) if placed else cap_top - s(24)

        media = self.load_media(slide, W - s(56), vis_bottom - vis_top)
        return {"base": base, "cards": placed, "media": media, "vis": (vis_top, vis_bottom),
                "color": color, "idx": idx, "total": total, "cap_y": cap_top}

    # -- screenshots, GIFs ------------------------------------------------------

    def frame_card(self, im: Image.Image, box_w: int, box_h: int, color) -> Image.Image:
        """A screenshot fitted into the box: a phone frame for tall shots,
        rounded corners and a soft shadow for everything else."""
        s = self.s
        im = im.convert("RGB")
        phone = im.height / im.width > 1.3
        pad = s(18)  # room for the shadow
        if phone:
            bezel = s(10)
            scale = min((box_w - 2 * pad - 2 * bezel) / im.width, (box_h - 2 * pad - 2 * bezel) / im.height)
            sw, sh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
            screen = im.resize((sw, sh), Image.LANCZOS)
            cw, ch = sw + 2 * bezel, sh + 2 * bezel
            body = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            ImageDraw.Draw(body).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=s(34), fill=(8, 9, 11, 255),
                                                   outline=(70, 74, 84, 255), width=max(1, s(2)))
            body.paste(screen, (bezel, bezel), rounded_mask((sw, sh), s(24)))
            radius = s(34)
        else:
            scale = min((box_w - 2 * pad) / im.width, (box_h - 2 * pad) / im.height)
            cw, ch = max(1, int(im.width * scale)), max(1, int(im.height * scale))
            body = im.resize((cw, ch), Image.LANCZOS).convert("RGBA")
            body.putalpha(rounded_mask((cw, ch), s(14)))
            ImageDraw.Draw(body).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=s(14), outline=LINE, width=1)
            radius = s(14)
        out = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), (0, 0, 0, 0))
        shadow = Image.new("L", out.size, 0)
        ImageDraw.Draw(shadow).rounded_rectangle([pad, pad + s(8), pad + cw, pad + ch + s(8)], radius=radius, fill=150)
        shadow = shadow.filter(ImageFilter.GaussianBlur(s(12)))
        out.paste(Image.new("RGBA", out.size, (0, 0, 0, 255)), (0, 0), shadow)
        out.alpha_composite(body, (pad, pad))
        return out

    def load_media(self, slide: dict, box_w: int, box_h: int) -> list:
        """[(kind, payload, weight)]: still -> card image; gif -> [(card, seconds)]."""
        names = [n for n in slide.get("media", []) if os.path.exists(os.path.join(SHOTS, n))]
        if not names:
            names = [n for n in slide.get("fallback", []) if os.path.exists(os.path.join(SHOTS, n))]
        items = []
        for name in names[:3]:
            path = os.path.join(SHOTS, name)
            im = Image.open(path)
            if getattr(im, "n_frames", 1) > 1:
                frames = []
                for k in range(im.n_frames):
                    im.seek(k)
                    secs = (im.info.get("duration") or 100) / 1000.0
                    frames.append((self.frame_card(im.convert("RGB"), box_w, box_h, slide["color"]), secs))
                items.append(("gif", frames, 2.0))
            elif im.height / im.width > 1.3:
                items.append(("still", self.frame_card(im, box_w, box_h, slide["color"]), 1.0))
            else:
                items.append(("zoom", self.zoom_source(im, box_w, box_h), 1.0))
        return items

    ZOOM = 1.32  # how far a desktop screenshot zooms in over its turn

    def zoom_source(self, im: Image.Image, box_w: int, box_h: int) -> dict:
        """A wide screenshot is small on a phone, so it slowly zooms in
        (Ken Burns) instead of sitting still: everything here is built once,
        each frame only crops and scales."""
        s = self.s
        im = im.convert("RGB")
        pad = s(18)
        scale = min((box_w - 2 * pad) / im.width, (box_h - 2 * pad) / im.height)
        cw, ch = max(1, int(im.width * scale)), max(1, int(im.height * scale))
        src = im.resize((int(cw * self.ZOOM * 1.5), int(ch * self.ZOOM * 1.5)), Image.LANCZOS)
        canvas = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), (0, 0, 0, 0))
        shadow = Image.new("L", canvas.size, 0)
        ImageDraw.Draw(shadow).rounded_rectangle([pad, pad + s(8), pad + cw, pad + ch + s(8)], radius=s(14), fill=150)
        canvas.paste(Image.new("RGBA", canvas.size, (0, 0, 0, 255)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(s(12))))
        edge = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(edge).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=s(14), outline=LINE, width=1)
        return {"src": src, "size": (cw, ch), "pad": pad, "canvas": canvas,
                "mask": rounded_mask((cw, ch), s(14)), "edge": edge, "cache": {}}

    def zoom_card(self, z: dict, amount: float) -> Image.Image:
        """The card at zoom 1 + (ZOOM-1)*amount, centred a little above the middle."""
        key = round(amount, 3)
        if key in z["cache"]:
            return z["cache"][key]
        cw, ch = z["size"]
        sw, sh = z["src"].size
        f = 1 + (self.ZOOM - 1) * amount
        w, h = sw / f, sh / f
        cx, cy = sw * 0.5, sh * 0.45
        x0 = min(max(0, cx - w / 2), sw - w)
        y0 = min(max(0, cy - h / 2), sh - h)
        body = z["src"].resize((cw, ch), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h)).convert("RGBA")
        body.putalpha(z["mask"])
        body.alpha_composite(z["edge"])
        card = z["canvas"].copy()
        card.alpha_composite(body, (z["pad"], z["pad"]))
        if len(z["cache"]) < 4:
            z["cache"][key] = card
        return card

    # -- per frame --------------------------------------------------------------

    def caption_image(self, text: str) -> Image.Image:
        if text in self._cap_cache:
            return self._cap_cache[text]
        s = self.s
        f = font(s(27), True)
        tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        lines = wrap(tmp, text, f, self.W - s(110))
        lh = s(36)
        w = int(max(tmp.textlength(ln, font=f) for ln in lines)) + s(40)
        h = len(lines) * lh + s(24)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=s(16), fill=(0, 0, 0, 175))
        y = s(12)
        for ln in lines:
            lw = d.textlength(ln, font=f)
            d.text(((w - lw) / 2, y), ln, fill=WHITE, font=f)
            y += lh
        self._cap_cache[text] = im
        return im

    def frame(self, prep: dict, lt: float, dur: float, gt: float, caption: tuple = None,
              progress: list = None) -> Image.Image:
        """Slide `prep` at local time `lt` (of `dur`), global time `gt`."""
        s, W = self.s, self.W
        img = prep["base"].copy()
        d = ImageDraw.Draw(img)
        color = prep["color"]

        # Story-style progress bar
        if progress:
            n = len(progress)
            gap = s(6)
            seg_w = (W - s(56) - gap * (n - 1)) / n
            for k, frac in enumerate(progress):
                x0 = s(28) + k * (seg_w + gap)
                d.rounded_rectangle([x0, s(14), x0 + seg_w, s(18)], radius=s(2), fill=(60, 64, 74))
                if frac > 0:
                    d.rounded_rectangle([x0, s(14), x0 + max(s(4), seg_w * frac), s(18)], radius=s(2), fill=WHITE)

        # Barline's four beat dots, in time with the music (beat 1 lit white).
        beat = int(gt / BEAT)
        phase = (gt / BEAT) - beat
        pulse = math.exp(-phase * 3.2)
        r = s(7)
        for k in range(4):
            cx = W - s(28) - r - (3 - k) * s(24)
            cy = s(56)
            on = (beat % 4) == k
            if on:
                c = WHITE if k == 0 else color
                rr = r + int(s(3) * pulse)
                fill = tuple(int(BG[j] + (c[j] - BG[j]) * (0.55 + 0.45 * pulse)) for j in range(3))
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=fill)
            else:
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=LINE)

        # Media: items share the slide; each slides in and crossfades to the next.
        media = prep["media"]
        if media:
            vt, vb = prep["vis"]
            total_w = sum(w for _, _, w in media)
            edges, acc = [], 0.0
            for _, _, w in media:
                edges.append(acc)
                acc += dur * w / total_w
            k = max(i for i, e in enumerate(edges) if lt >= e) if lt >= 0 else 0
            for idx in ([k - 1, k] if k > 0 else [k]):
                kind, payload, w = media[idx]
                it = lt - edges[idx]
                share = dur * w / total_w
                if idx == k:
                    a = ease_out(it / 0.4)
                    rise = int(s(26) * (1 - a))
                else:
                    a = 1.0 - ease_out((lt - edges[k]) / 0.4)
                    rise = 0
                    if a <= 0:
                        continue
                if kind == "gif":
                    frames = payload
                    loop = sum(sec for _, sec in frames)
                    speed = max(1.0, loop / max(0.5, share - 0.3))
                    speed = min(speed, max(1.0, min(sec for _, sec in frames) / 0.16))
                    tt = (it * speed) % loop if it > 0 else 0
                    card = frames[-1][0]
                    for c, sec in frames:
                        if tt < sec:
                            card = c
                            break
                        tt -= sec
                elif kind == "zoom":
                    x = max(0.0, min(1.0, it / max(0.5, share)))
                    card = self.zoom_card(payload, x * x * (3 - 2 * x))  # smoothstep
                else:
                    card = payload
                x = (W - card.width) // 2
                y = vt + (vb - vt - card.height) // 2 + rise
                img.paste(with_alpha(card, a), (x, y), with_alpha(card, a))

        # Bullet cards, staggered in.
        for i, (card, y) in enumerate(prep["cards"]):
            a = ease_out((lt - 0.35 - 0.22 * i) / 0.35)
            if a <= 0:
                continue
            c = with_alpha(card, a)
            img.paste(c, (s(28), y + int(s(18) * (1 - a))), c)

        # Caption
        if caption:
            text, alpha = caption
            cim = self.caption_image(text)
            c = with_alpha(cim, alpha)
            cy = prep["cap_y"] + (self.H - prep["cap_y"] - cim.height) // 2 - s(4)
            img.paste(c, ((W - cim.width) // 2, cy), c)
        return img


# ---------------------------------------------------------------------------
# Captions
# ---------------------------------------------------------------------------

def caption_chunks(text: str, max_words: int = 7) -> list:
    words, chunks, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        end = w[-1] in ".!?"
        soft = w[-1] in ",:;" and len(cur) >= 3
        if end or soft or len(cur) >= max_words:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        if chunks and len(cur) <= 2:
            chunks[-1] += " " + " ".join(cur)
        else:
            chunks.append(" ".join(cur))
    return chunks


def caption_track(text: str, start: float, length: float) -> list:
    """[(t0, t1, text)] spread over the speech by length, with pauses at punctuation."""
    chunks = caption_chunks(text)
    weights = [len(c) + (8 if c[-1] in ".!?" else 4 if c[-1] in ",:;" else 0) for c in chunks]
    total = sum(weights) or 1
    out, t = [], start
    for c, w in zip(chunks, weights):
        d = length * w / total
        out.append((t, t + d, c))
        t += d
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Make Barline's vertical pitch video (and stills).")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "Barline_Pitch.mp4"), help="output .mp4")
    ap.add_argument("--hd", action="store_true", help="1080x1920 instead of 720x1280")
    ap.add_argument("--tts", choices=("auto", "say", "espeak", "edge", "none"), default="auto",
                    help="voice engine (auto: macOS say, else espeak-ng)")
    ap.add_argument("--voice", help="voice name (say: see --list-voices; edge: e.g. en-GB-RyanNeural)")
    ap.add_argument("--rate", type=int, default=180, help="speaking rate, words per minute (default 180)")
    ap.add_argument("--list-voices", action="store_true", help="list the voices macOS `say` has, and stop")
    ap.add_argument("--no-music", action="store_true", help="voice only, no backing groove")
    ap.add_argument("--no-captions", action="store_true", help="no burned-in captions")
    ap.add_argument("--stills", action="store_true", help="also save one PNG per slide and a PDF deck")
    ap.add_argument("--stills-only", action="store_true", help="only the PNGs and the PDF, no video")
    ap.add_argument("--only", type=int, metavar="N", help="render just slide N (1-based), for a quick check")
    ap.add_argument("--crf", type=int, help="H.264 quality, lower is better/bigger (default 24, 22 with --hd)")
    args = ap.parse_args()

    if args.list_voices:
        voices = say_voices()
        if not voices:
            sys.exit("`say` isn't available here (it's macOS only).")
        for name, loc in voices:
            star = " *" if name in PREFERRED_SAY_VOICES else ""
            print(f"  {name:<28} {loc}{star}")
        print("\n* = picked automatically when installed (first one wins).")
        return

    slides = SLIDES
    if args.only:
        if not 1 <= args.only <= len(SLIDES):
            sys.exit(f"--only takes 1 to {len(SLIDES)}.")
        slides = [SLIDES[args.only - 1]]
    want_video = not args.stills_only
    if want_video and not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed to make the video. On a Mac: brew install ffmpeg "
                 "(Linux: sudo apt install ffmpeg). Or use --stills-only.")

    missing = sorted({n for sl in slides for n in sl.get("media", [])
                      if not os.path.exists(os.path.join(SHOTS, n))})
    if missing:
        print("   ! Not in screenshots/ (skipped): " + ", ".join(missing))

    width = 1080 if args.hd else 720
    renderer = Renderer(width, captions=not args.no_captions and want_video, version=barline_version())
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    t_start = time.time()

    if args.stills or args.stills_only:
        stills_dir = os.path.join(os.path.dirname(out_path), "stills")
        os.makedirs(stills_dir, exist_ok=True)
        still_r = Renderer(width, captions=False, version=renderer.version)
        pages = []
        for i, sl in enumerate(slides):
            prep = still_r.prepare(sl, i, len(slides))
            # Everything settled in, first screenshot showing.
            img = still_r.frame(prep, 1.5, 100.0, 0.0,
                                progress=[1.0 if k <= i else 0.0 for k in range(len(slides))])
            p = os.path.join(stills_dir, f"slide-{(args.only or i + 1):02d}.png")
            img.save(p)
            pages.append(img)
        pdf = os.path.join(os.path.dirname(out_path), "Barline_Pitch.pdf")
        pages[0].save(pdf, save_all=True, append_images=pages[1:], resolution=144)
        print(f"Stills: {stills_dir}/  ·  deck: {pdf}")
        if args.stills_only:
            return

    with tempfile.TemporaryDirectory(prefix="barline-pitch-") as tmp:
        voice = Voice.choose(args.tts, args.voice, args.rate)
        print(f"1/3 Voice-over with {voice.label}...")
        vo_wavs, vo_lens = [], []
        for i, sl in enumerate(slides):
            wav = os.path.join(tmp, f"vo_{i:02d}.wav")
            if voice.render(sl["vo"], wav, tmp):
                with wave.open(wav, "rb") as w:
                    vo_lens.append(w.getnframes() / float(w.getframerate()))
                vo_wavs.append(wav)
            else:
                vo_lens.append(estimate_speech(sl["vo"]))
                vo_wavs.append(None)
        plan = plan_timing(slides, vo_lens)
        total = plan[-1]["start"] + plan[-1]["dur"]

        print(f"2/3 Backing groove ({BPM} BPM, Barline's own click sounds) and mix, {total:.0f} s...")
        audio = os.path.join(tmp, "soundtrack.wav")
        mix_soundtrack(total, plan, vo_wavs, not args.no_music, load_kit(), audio)

        caps = []
        if renderer.captions:
            for sl, p in zip(slides, plan):
                caps += caption_track(sl["vo"], p["voice_at"], p["voice_len"])

        print(f"3/3 Rendering {renderer.W}x{renderer.H} at {FPS} fps and encoding...")
        preps = [renderer.prepare(sl, i, len(slides)) for i, sl in enumerate(slides)]
        crf = args.crf if args.crf is not None else (22 if args.hd else 24)
        enc = subprocess.Popen([
            "ffmpeg", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{renderer.W}x{renderer.H}", "-r", str(FPS), "-i", "-",
            "-i", audio,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-g", str(FPS * 2),
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart", "-shortest", out_path,
        ], stdin=subprocess.PIPE)

        n_frames = int(math.ceil(total * FPS))
        ci, last_pct = 0, -1
        for f in range(n_frames):
            gt = f / FPS
            si = max(i for i, p in enumerate(plan) if gt >= p["start"] - 1e-9)
            p = plan[si]
            lt = gt - p["start"]
            progress = [1.0 if k < si else (min(1.0, lt / p["dur"]) if k == si else 0.0) for k in range(len(plan))]

            cap = None
            while ci < len(caps) and caps[ci][1] <= gt:
                ci += 1
            if ci < len(caps) and caps[ci][0] <= gt:
                t0, t1, text = caps[ci]
                cap = (text, min(1.0, (gt - t0) / 0.12, (t1 - gt) / 0.08 + 0.3))

            img = renderer.frame(preps[si], lt, p["dur"], gt, cap, progress)
            if si > 0 and lt < XFADE:
                q = plan[si - 1]
                prev = renderer.frame(preps[si - 1], q["dur"], q["dur"], gt, None, progress)
                img = Image.blend(prev, img, ease_out(lt / XFADE))
            enc.stdin.write(img.tobytes())

            pct = int(100 * (f + 1) / n_frames)
            if pct % 10 == 0 and pct != last_pct:
                print(f"    {pct}%", flush=True)
                last_pct = pct
        enc.stdin.close()
        if enc.wait() != 0:
            sys.exit("ffmpeg failed to encode the video (see above).")

    mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"Done in {time.time() - t_start:.0f} s: {out_path}  ({mb:.1f} MB, {total:.0f} s)")
    if mb > 15.5:
        print("   ! Over ~16 MB: WhatsApp may squeeze it hard. Try --crf 27, or send it as a document.")


if __name__ == "__main__":
    main()
