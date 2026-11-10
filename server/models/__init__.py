"""
Data model for Barline - Song and Setlist Planner.

Deliberately plain: every entity is a dict that round-trips straight to/from
JSON (see server/storage.py). These helpers exist to keep "what a fresh
Song/Section/Hint/etc. looks like" and "what counts as valid" in one place,
not to introduce an ORM. See WORKPLAN.md's "Data model & storage
layout" for the authoritative shape.

Timing model: a Section stores only its own `bars` (and an optional `bpm`
override) -- never an absolute start bar/time. Position in the song is
always computed by summing everything before it (see `section_start_bar`
and `song_total_bars` below).
"""

from __future__ import annotations

import re
import time
import uuid

VALID_COUNT_IN_STYLES = ("sticks", "click", "verbal", "none")
VALID_ROLES = ("Drums", "Bass", "Guitar", "Vocals", "Keys", "Other")
MIN_BPM = 20
MAX_BPM = 400

# A recorded hint clip: data/audio/<12 hex>.<ext> -- nothing else is ever
# served or deleted from that folder (see storage.py).
AUDIO_EXTS = {
    "webm": "audio/webm", "ogg": "audio/ogg", "m4a": "audio/mp4", "mp4": "audio/mp4",
    "mp3": "audio/mpeg", "wav": "audio/wav", "aac": "audio/aac",
}
AUDIO_REF = re.compile(r"^[0-9a-f]{12}\.(" + "|".join(AUDIO_EXTS) + r")$")
MAX_AUDIO_BYTES = 3 * 1024 * 1024  # ~3 MB: a short voice memo, not a song


def audio_refs(song: dict) -> set:
    """Every clip a song's hints point at."""
    return {h["audio"] for s in song.get("sections", []) for h in s.get("hints", []) if h.get("audio")}


ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def new_id() -> str:
    """Short, URL- and filename-safe unique id."""
    return uuid.uuid4().hex[:12]


def now() -> float:
    return time.time()


class ValidationError(ValueError):
    """Raised when a payload from the API/storage doesn't shape up."""


# ---------------------------------------------------------------------------
# Band / Player
# ---------------------------------------------------------------------------

def new_band(name: str = "My Band") -> dict:
    return {"id": "band", "name": name, "players": []}


def new_player(name: str, role: str = "Other") -> dict:
    if role not in VALID_ROLES:
        role = "Other"
    return {"id": new_id(), "name": name, "role": role}


def clean_band(payload: dict, existing: dict) -> dict:
    """A band from an API payload: name, and players with a name, a known
    role and an id each (a missing id gets a fresh one). Raises
    ValidationError in plain words."""
    name = str(payload.get("name", existing.get("name", "My Band")) or "").strip()[:80]
    if not name:
        raise ValidationError("the band needs a name")
    players_in = payload.get("players", existing.get("players", []))
    if not isinstance(players_in, list):
        raise ValidationError("players must be a list")
    players, seen = [], set()
    for p in players_in:
        if not isinstance(p, dict):
            raise ValidationError("each player must be an object")
        pid = str(p.get("id") or new_id())[:40]
        if pid in seen or pid == "all":
            pid = new_id()
        seen.add(pid)
        role = p.get("role") if p.get("role") in VALID_ROLES else "Other"
        players.append({"id": pid, "name": str(p.get("name", "")).strip()[:60] or "Player", "role": role})
    return {"id": "band", "name": name, "players": players}


# ---------------------------------------------------------------------------
# Hint
# ---------------------------------------------------------------------------

def new_hint(text: str = "", visibility: str = "all", audio=None) -> dict:
    return {
        "id": new_id(),
        "text": text,
        "audio": audio,  # clip_ref string, or null -- recording lands in v0.6
        "visibility": visibility,  # "all" | player_id
    }


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

def new_section(label: str = "Section", order: int = 0, bars: int = 4) -> dict:
    return {
        "id": new_id(),
        "label": label,
        "order": order,
        "bars": bars,
        "bpm": None,  # overrides the song's default_bpm when set
        "count_in": {"bars": 0, "style": "none"},
        "hints": [],
    }


def validate_section(section: dict) -> None:
    bars = section.get("bars")
    if not isinstance(bars, int) or bars < 1:
        raise ValidationError(f"section {section.get('id')!r}: bars must be a positive integer")
    bpm = section.get("bpm")
    if bpm is not None and not (MIN_BPM <= bpm <= MAX_BPM):
        raise ValidationError(
            f"section {section.get('id')!r}: bpm override {bpm} out of range {MIN_BPM}-{MAX_BPM}"
        )
    count_in = section.get("count_in") or {}
    style = count_in.get("style", "none")
    if style not in VALID_COUNT_IN_STYLES:
        raise ValidationError(f"section {section.get('id')!r}: invalid count_in style {style!r}")
    ci_bars = count_in.get("bars", 0)
    if not isinstance(ci_bars, int) or not (0 <= ci_bars <= 8):
        raise ValidationError(f"section {section.get('id')!r}: count-in is 0 to 8 bars")
    if bars > 999:
        raise ValidationError(f"section {section.get('id')!r}: at most 999 bars in one section")
    for hint in section.get("hints", []):
        audio = hint.get("audio")
        if audio is not None and not (isinstance(audio, str) and AUDIO_REF.match(audio)):
            raise ValidationError(f"hint {hint.get('id')!r}: bad audio clip reference")


# ---------------------------------------------------------------------------
# Song
# ---------------------------------------------------------------------------

def new_song(title: str = "Untitled Song", default_bpm: int = 120) -> dict:
    sid = new_id()
    return {
        "id": sid,
        "title": title,
        "default_bpm": default_bpm,
        "tags": [],
        "sections": [],
        "created_at": now(),
        "updated_at": now(),
    }


MAX_TAGS = 12
MAX_TAG_LEN = 30


def clean_tags(tags) -> list:
    """A song's tags, tidied: trimmed strings, no blanks, no repeats
    (ignoring case; the first spelling wins), at most MAX_TAGS. Anything
    that isn't a list of strings becomes no tags rather than an error, so
    an old or hand-edited song file still loads."""
    if not isinstance(tags, list):
        return []
    out, seen = [], set()
    for t in tags:
        if not isinstance(t, str):
            continue
        t = " ".join(t.split())[:MAX_TAG_LEN].strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
        if len(out) >= MAX_TAGS:
            break
    return out


def validate_song(song: dict) -> None:
    if not song.get("title", "").strip():
        raise ValidationError("song title cannot be empty")
    bpm = song.get("default_bpm")
    if not isinstance(bpm, int) or not (MIN_BPM <= bpm <= MAX_BPM):
        raise ValidationError(f"default_bpm {bpm} out of range {MIN_BPM}-{MAX_BPM}")
    for section in song.get("sections", []):
        validate_section(section)


def section_bpm(song: dict, section: dict) -> int:
    """Effective BPM for a section: its own override, else the song default."""
    return section.get("bpm") or song["default_bpm"]


def section_start_bar(song: dict, section_id: str) -> int:
    """1-indexed bar at which `section_id` begins, computed from the ordered
    list of sections before it. Never stored -- see module docstring."""
    bar = 1
    for s in sorted(song.get("sections", []), key=lambda s: s["order"]):
        if s["id"] == section_id:
            return bar
        bar += s["bars"]
    raise ValidationError(f"section {section_id!r} not found in song {song.get('id')!r}")


def song_total_bars(song: dict) -> int:
    return sum(s["bars"] for s in song.get("sections", []))


def _count_in_choice(raw, what: str):
    """One side of a bulk count-in change: None (leave as is) or
    {"bars": 0..8, "style": ...}. Zero bars or style "none" means "no
    count-in"; a style with no bars gets one bar, bars with no style click."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValidationError(f"{what}: give bars and a style, or leave it out")
    bars, style = raw.get("bars", 1), raw.get("style", "click")
    if style not in VALID_COUNT_IN_STYLES:
        raise ValidationError(f"{what}: the style is sticks, click, verbal or none")
    if not isinstance(bars, int) or isinstance(bars, bool) or not (0 <= bars <= 8):
        raise ValidationError(f"{what}: a count-in is 0 to 8 bars")
    if style == "none" or bars == 0:
        return {"bars": 0, "style": "none"}
    return {"bars": bars, "style": style}


def apply_count_ins(song: dict, start=None, changes=None, tempo_only: bool = False,
                    keep_existing: bool = False) -> int:
    """Set count-ins across a song in one go (0.16), in place.

      * `start`: the first section's count-in (the start of the song);
      * `changes`: every later section's -- or, with `tempo_only`, only
        the sections whose tempo differs from the one before;
      * each is None (leave alone) or {"bars", "style"} (see
        _count_in_choice; bars 0 / style "none" removes it);
      * `keep_existing`: only fill in sections that have no count-in yet.

    Returns how many sections changed."""
    start = _count_in_choice(start, "start of the song")
    changes = _count_in_choice(changes, "section changes")
    changed = 0
    ordered = sorted(song.get("sections", []), key=lambda s: s.get("order", 0))
    prev_bpm = None
    for i, s in enumerate(ordered):
        bpm = s.get("bpm") or song.get("default_bpm")
        want = start if i == 0 else changes
        if i > 0 and tempo_only and bpm == prev_bpm:
            want = None
        prev_bpm = bpm
        if want is None:
            continue
        cur = s.get("count_in") or {"bars": 0, "style": "none"}
        has = cur.get("style", "none") != "none" and (cur.get("bars") or 0) > 0
        if keep_existing and has:
            continue
        if not has and want["bars"] == 0:
            if cur != {"bars": 0, "style": "none"}:
                s["count_in"] = {"bars": 0, "style": "none"}
            continue
        if cur.get("bars") != want["bars"] or cur.get("style") != want["style"]:
            s["count_in"] = dict(want)
            changed += 1
    return changed


# ---------------------------------------------------------------------------
# Setlist
# ---------------------------------------------------------------------------

def new_setlist(name: str = "New Setlist") -> dict:
    return {"id": new_id(), "name": name, "songs": []}


def validate_setlist(setlist: dict) -> None:
    if not setlist.get("name", "").strip():
        raise ValidationError("setlist name cannot be empty")
    if not isinstance(setlist.get("songs"), list):
        raise ValidationError("setlist songs must be a list of song ids")
    if not all(isinstance(s, str) for s in setlist["songs"]):
        raise ValidationError("setlist songs must be a list of song ids")
