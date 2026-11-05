"""
Data model for Single Song Planner.

Deliberately plain: every entity is a dict that round-trips straight to/from
JSON (see server/storage.py). These helpers exist to keep "what a fresh
Song/Section/Hint/etc. looks like" and "what counts as valid" in one place,
not to introduce an ORM. See claude/WORKPLAN.md's "Data model & storage
layout" for the authoritative shape.

Timing model: a Section stores only its own `bars` (and an optional `bpm`
override) -- never an absolute start bar/time. Position in the song is
always computed by summing everything before it (see `section_start_bar`
and `song_total_bars` below).
"""

from __future__ import annotations

import time
import uuid

VALID_COUNT_IN_STYLES = ("sticks", "click", "verbal", "none")
VALID_ROLES = ("Drums", "Bass", "Guitar", "Vocals", "Keys", "Other")
MIN_BPM = 20
MAX_BPM = 400


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


# ---------------------------------------------------------------------------
# Song
# ---------------------------------------------------------------------------

def new_song(title: str = "Untitled Song", default_bpm: int = 120) -> dict:
    sid = new_id()
    return {
        "id": sid,
        "title": title,
        "default_bpm": default_bpm,
        "sections": [],
        "created_at": now(),
        "updated_at": now(),
    }


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
