"""
Live transport: the "play" button for the whole band.

Any connected device can start or stop a run. The server then owns the
clock: it fixes the exact moment bar 1 starts (a short lead time in the
future, so every tablet can schedule its first click before it happens),
snapshots the song's tempo map (server/timeline.py), and broadcasts both.
From there every browser works out the current bar on its own from the
shared clock -- that's what keeps the playhead smooth and each device's
metronome in time -- while this module's own thread announces each bar
change (for a device that just joined) and stops the run at the end of the
song.

Nobody clicks "next" in real time: position always comes from the tempo
map and the clock. Editing the song mid-run doesn't move the playhead; the
run plays the snapshot it started with.

State, as broadcast (`transport` event):

    {state: "stopped"|"running", song_id, setlist_id, start_section_id,
     started_at (server clock, ms), timeline, driver {client_id, name},
     run (counter, bumps on every start)}
"""

from __future__ import annotations

import threading
import time

import timeline as tl

LEAD_MS = 1500  # time between pressing Start and the first count-in beat


def now_ms() -> float:
    return time.time() * 1000.0


class Transport:
    def __init__(self, store, hub):
        self.store = store
        self.hub = hub
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.run_counter = 0
        self.state = {
            "state": "stopped",
            "song_id": None,
            "setlist_id": None,
            "start_section_id": None,
            "started_at": None,
            "timeline": None,
            "driver": None,
            "run": 0,
        }
        self._thread = None

    # -- public ---------------------------------------------------------
    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.state)

    def cue(self, song_id, setlist_id=None, origin=None) -> dict:
        """Put a song (optionally within a setlist) on every live screen,
        without starting it. Stops a run that's going."""
        with self.lock:
            if song_id is not None:
                self.store.get_song(song_id)  # KeyError -> 404
            if setlist_id is not None:
                self.store.get_setlist(setlist_id)
            self._stop_locked()
            self.state.update(song_id=song_id, setlist_id=setlist_id, start_section_id=None)
            snap = dict(self.state)
        self.hub.publish("transport", snap, origin)
        return snap

    def start(self, song_id=None, setlist_id=None, start_section_id=None, origin=None, lead_ms=LEAD_MS) -> dict:
        with self.lock:
            song_id = song_id or self.state["song_id"]
            if song_id is None:
                raise KeyError("no song cued")
            song = self.store.get_song(song_id)
            if setlist_id is None and song_id == self.state["song_id"]:
                setlist_id = self.state["setlist_id"]
            timeline = tl.build(song, start_section_id)
            if not timeline["bars"]:
                raise ValueError("this song has no bars to play yet")
            self.run_counter += 1
            self.state = {
                "state": "running",
                "song_id": song_id,
                "setlist_id": setlist_id,
                "start_section_id": start_section_id,
                "started_at": now_ms() + max(200, min(int(lead_ms), 10000)),
                "timeline": timeline,
                "driver": {"client_id": origin, "name": self.hub.player_name(self.store.get_band(), origin)},
                "run": self.run_counter,
            }
            snap = dict(self.state)
            self.wake.set()
            self._thread = threading.Thread(target=self._run, args=(self.run_counter,), daemon=True)
            self._thread.start()
        self.hub.publish("transport", snap, origin)
        return snap

    def stop(self, origin=None) -> dict:
        with self.lock:
            self._stop_locked()
            snap = dict(self.state)
        self.hub.publish("transport", snap, origin)
        return snap

    def step(self, direction: int, origin=None) -> dict:
        """Cue the previous/next song in the cued setlist."""
        with self.lock:
            setlist_id = self.state["setlist_id"]
            if not setlist_id:
                raise ValueError("no setlist cued")
            songs = [s for s in self.store.get_setlist(setlist_id)["songs"] if s in self.store.songs]
            if not songs:
                raise ValueError("this setlist has no songs")
            cur = self.state["song_id"]
            i = songs.index(cur) if cur in songs else -1
            j = max(0, min(len(songs) - 1, i + direction))
            target = songs[j]
        return self.cue(target, setlist_id, origin)

    def song_deleted(self, song_id) -> None:
        with self.lock:
            hit = self.state["song_id"] == song_id
        if hit:
            self.cue(None, None)

    def shutdown(self) -> None:
        with self.lock:
            self._stop_locked()

    # -- internals ------------------------------------------------------
    def _stop_locked(self) -> None:
        self.state.update(state="stopped", started_at=None, timeline=None, driver=None)
        self.wake.set()

    def _run(self, run: int) -> None:
        """Announce each bar as it starts; finish the run at the end."""
        last = None
        while True:
            with self.lock:
                if self.state["run"] != run or self.state["state"] != "running":
                    return
                started = self.state["started_at"]
                timeline = self.state["timeline"]
                song_id = self.state["song_id"]
                setlist_id = self.state["setlist_id"]
            elapsed = now_ms() - started
            idx = tl.bar_at(timeline, elapsed)
            if idx >= len(timeline["bars"]):
                self._finish(run, song_id, setlist_id)
                return
            if idx != last and idx >= 0:
                bar = timeline["bars"][idx]
                self.hub.publish("position", {
                    "run": run, "bar_index": idx, "section_id": bar["section_id"],
                    "song_bar": bar["song_bar"], "count_in": bar["count_in"],
                })
                last = idx
            # sleep until the next bar boundary (or until woken by stop/start)
            nxt = timeline["bars"][idx + 1]["start_ms"] if 0 <= idx + 1 < len(timeline["bars"]) else (
                timeline["total_ms"] if idx >= 0 else timeline["bars"][0]["start_ms"])
            wait_s = max(0.005, (nxt - elapsed) / 1000.0)
            self.wake.clear()
            self.wake.wait(min(wait_s, 1.0))

    def _finish(self, run: int, song_id, setlist_id) -> None:
        """End of the song: stop, and in a setlist cue the next song so the
        band is one tap from starting it."""
        with self.lock:
            if self.state["run"] != run:
                return
            self._stop_locked()
            if setlist_id and setlist_id in self.store.setlists:
                songs = [s for s in self.store.setlists[setlist_id]["songs"] if s in self.store.songs]
                if song_id in songs and songs.index(song_id) + 1 < len(songs):
                    self.state["song_id"] = songs[songs.index(song_id) + 1]
            self.state["start_section_id"] = None
            snap = dict(self.state)
        self.hub.publish("transport", dict(snap, finished=True))
