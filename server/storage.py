"""
Plain-JSON, one-file-per-song storage (see WORKPLAN.md's "Storage"
decision).

This module only talks to disk. The in-memory `Store` in app.py is the one
that's actually read from during normal operation -- every song is loaded
into memory at startup and kept there, so switching songs or rebuilding a
setlist in the app is instant, never a disk read per switch. This module is
called on load (startup) and on save (after an edit, or on shutdown).

Layout:

    data/
      band.json              # band identity + players
      songs/<song-id>.json   # one song per file -- portable on its own
      setlists/<id>.json     # name + ordered [song_id, ...] -- a thin
                              # reference list, not a copy of the songs
      audio/<clip>.<ext>     # recorded hint clips, referenced by hints
                              # (v0.6). To move one song with its clips to
                              # another setup, use the song's "Export"
                              # button instead: that bundles both into one
                              # .ssp.json file.
"""

from __future__ import annotations

import json
import os
import tempfile

import models
from models import new_band


class Storage:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.band_path = os.path.join(data_dir, "band.json")
        self.songs_dir = os.path.join(data_dir, "songs")
        self.setlists_dir = os.path.join(data_dir, "setlists")
        self.audio_dir = os.path.join(data_dir, "audio")

    def ensure_dirs(self) -> None:
        os.makedirs(self.songs_dir, exist_ok=True)
        os.makedirs(self.setlists_dir, exist_ok=True)
        os.makedirs(self.audio_dir, exist_ok=True)

    # -- atomic write -------------------------------------------------
    @staticmethod
    def _write_json(path: str, payload: dict) -> None:
        """Write via a temp file + atomic rename so a crash mid-write (or a
        tablet losing Wi-Fi at the wrong moment) never leaves a half-written
        song file behind."""
        directory = os.path.dirname(path) or "."
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    @staticmethod
    def _read_json(path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # -- band -----------------------------------------------------------
    def load_band(self) -> dict:
        if os.path.exists(self.band_path):
            return self._read_json(self.band_path)
        band = new_band()
        self.save_band(band)
        return band

    def save_band(self, band: dict) -> None:
        self._write_json(self.band_path, band)

    # -- songs ------------------------------------------------------------
    def _song_path(self, song_id: str) -> str:
        return os.path.join(self.songs_dir, f"{song_id}.json")

    def load_all_songs(self) -> dict:
        songs = {}
        if not os.path.isdir(self.songs_dir):
            return songs
        for name in os.listdir(self.songs_dir):
            if not name.endswith(".json") or name.startswith("."):
                continue
            try:
                song = self._read_json(os.path.join(self.songs_dir, name))
                songs[song["id"]] = song
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                print(f"[storage] skipping unreadable song file {name}: {exc}")
        return songs

    def save_song(self, song: dict) -> None:
        self._write_json(self._song_path(song["id"]), song)

    def delete_song(self, song_id: str) -> None:
        path = self._song_path(song_id)
        if os.path.exists(path):
            os.remove(path)

    # -- setlists --------------------------------------------------------
    def _setlist_path(self, setlist_id: str) -> str:
        return os.path.join(self.setlists_dir, f"{setlist_id}.json")

    def load_all_setlists(self) -> dict:
        setlists = {}
        if not os.path.isdir(self.setlists_dir):
            return setlists
        for name in os.listdir(self.setlists_dir):
            if not name.endswith(".json") or name.startswith("."):
                continue
            try:
                setlist = self._read_json(os.path.join(self.setlists_dir, name))
                setlists[setlist["id"]] = setlist
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                print(f"[storage] skipping unreadable setlist file {name}: {exc}")
        return setlists

    def save_setlist(self, setlist: dict) -> None:
        self._write_json(self._setlist_path(setlist["id"]), setlist)

    def delete_setlist(self, setlist_id: str) -> None:
        path = self._setlist_path(setlist_id)
        if os.path.exists(path):
            os.remove(path)

    # -- recorded hint clips ------------------------------------------------
    def audio_path(self, ref: str) -> str:
        """Path of a clip, or ValueError -- only well-formed refs, inside
        data/audio/, are ever touched (no path tricks)."""
        if not isinstance(ref, str) or not models.AUDIO_REF.match(ref):
            raise ValueError("bad clip reference")
        return os.path.join(self.audio_dir, ref)

    def save_audio(self, data: bytes, ext: str) -> str:
        if ext not in models.AUDIO_EXTS:
            raise ValueError("unsupported audio type")
        ref = f"{models.new_id()}.{ext}"
        path = self.audio_path(ref)
        fd, tmp_path = tempfile.mkstemp(dir=self.audio_dir, prefix=".tmp-")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)
        return ref

    def read_audio(self, ref: str) -> bytes:
        with open(self.audio_path(ref), "rb") as f:
            return f.read()

    def delete_audio(self, ref: str) -> None:
        try:
            path = self.audio_path(ref)
        except ValueError:
            return
        if os.path.exists(path):
            os.remove(path)
