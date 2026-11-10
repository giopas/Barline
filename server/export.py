"""
Export (v0.7): a portable song file (`.ssp.json`) -- the song plus any
recorded hint clips, base64-encoded, in one file you can email or put on a
USB stick and import on another band's Barline. The plain `data/songs/<id>.json`
is still portable on its own; this is the version that keeps the clips.

Paper charts are server/paper.py (0.13: real PDFs; they replaced v0.7's
printable HTML pages). A song's PDF carries this same bundle inside it, so
`payload_from_bytes` reads either file.
"""

from __future__ import annotations

import base64
import binascii
import copy
import json
import os

import models
import paper

EXPORT_FORMAT = 1


# ---------------------------------------------------------------------------
# Portable song file
# ---------------------------------------------------------------------------

def bundle(song: dict, storage) -> dict:
    clips = {}
    for ref in sorted(models.audio_refs(song)):
        try:
            clips[ref] = base64.b64encode(storage.read_audio(ref)).decode("ascii")
        except (OSError, ValueError):
            pass  # a clip that went missing: export the song without it
    return {"ssp_export": EXPORT_FORMAT, "song": song, "audio": clips}


def unbundle(payload: dict, storage, taken_ids) -> dict:
    """A song ready to add to the store from an exported file (or a plain
    song .json). Gets a fresh id when its own is already used here, and
    fresh clip names, so importing never overwrites anything."""
    if not isinstance(payload, dict):
        raise models.ValidationError("that isn't a Barline song file")
    song = payload.get("song") if "ssp_export" in payload else payload
    if not isinstance(song, dict) or "sections" not in song:
        raise models.ValidationError("that isn't a Barline song file")
    song = copy.deepcopy(song)
    if not song.get("id") or song["id"] in taken_ids or not models.ID_RE.match(str(song["id"])):
        song["id"] = models.new_id()
    song.setdefault("title", "Imported song")
    song.setdefault("default_bpm", 120)
    clips = payload.get("audio", {}) if "ssp_export" in payload else {}
    renamed = {}
    for ref, b64 in (clips or {}).items():
        if not models.AUDIO_REF.match(str(ref)):
            continue
        try:
            data = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError, TypeError):
            continue
        if len(data) > models.MAX_AUDIO_BYTES:
            continue
        renamed[ref] = storage.save_audio(data, os.path.splitext(ref)[1][1:])
    for s in song.get("sections", []):
        for h in s.get("hints", []):
            if h.get("audio"):
                h["audio"] = renamed.get(h["audio"])
    song["updated_at"] = models.now()
    song.setdefault("created_at", models.now())
    models.validate_song(song)
    return song


def payload_from_bytes(data: bytes) -> dict:
    """What an imported file holds, ready for `unbundle`: an `.ssp.json`, a
    plain song `.json`, or a song chart PDF made by Barline 0.13 or later."""
    if data[:5] == b"%PDF-":
        payload = paper.read_embedded(data)
        if payload is None:
            raise models.ValidationError(
                "this PDF has no song inside it -- only a song's paper chart from Barline 0.13 "
                "or later carries one (a set's PDF doesn't)")
        return payload
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise models.ValidationError("that isn't a Barline song file (.ssp.json, .json or a song's PDF)") from None
    if not isinstance(payload, dict):
        raise models.ValidationError("that isn't a Barline song file")
    return payload
