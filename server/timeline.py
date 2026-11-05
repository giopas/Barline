"""
Tempo map: turns a song's ordered sections into a list of bars with exact
start times. Everything time-based in SSP reads from this one function --
the live transport (server/transport.py), the offline click track
(server/click_track.py), and, mirrored line for line in
web/static/timing.js, every browser's playhead and metronome.

Rules (see WORKPLAN.md's "Timing model"):

  * a section only stores its own `bars` and optional `bpm`; where it sits
    in the song is always computed here, never stored;
  * a count-in is extra bars played *before* its section, at that section's
    tempo -- it doesn't eat into the section's own bars;
  * a run always starts with a count-in so the band can come in together:
    if the first section played has none, one bar of click is added
    ("lead-in");
  * 4 beats per bar for now (see the wishlist for other time signatures);
  * same input, same output: no clock, no randomness.
"""

from __future__ import annotations

BEATS_PER_BAR = 4
LEAD_IN_BARS = 1


def _sorted_sections(song: dict) -> list:
    return sorted(song.get("sections", []), key=lambda s: s.get("order", 0))


def build(song: dict, start_section_id: str = None, lead_in: bool = True) -> dict:
    """The song's bars from `start_section_id` (or the top) to the end.

    Returns {"bars": [...], "total_ms": float, "song_bars": int}. Each bar:

        section_id, label, section_index (position in the song, for colour),
        count_in (bool), count_in_style, bar_in_section (1-based),
        section_bars, bpm, beats, beat_ms, start_ms, song_bar (1-based bar
        number in the whole song, None for count-in bars)
    """
    sections = _sorted_sections(song)
    default_bpm = song.get("default_bpm") or 120
    start_index = 0
    if start_section_id:
        for i, s in enumerate(sections):
            if s.get("id") == start_section_id:
                start_index = i
                break

    bars = []
    t = 0.0
    song_bar = 1
    for s in sections[:start_index]:
        song_bar += int(s.get("bars", 0))

    for idx in range(start_index, len(sections)):
        s = sections[idx]
        bpm = s.get("bpm") or default_bpm
        beat_ms = 60000.0 / bpm
        bar_ms = beat_ms * BEATS_PER_BAR
        count_in = s.get("count_in") or {}
        ci_bars = int(count_in.get("bars") or 0)
        ci_style = count_in.get("style") or "none"
        if ci_style == "none":
            ci_bars = 0
        if idx == start_index and ci_bars == 0 and lead_in:
            ci_bars, ci_style = LEAD_IN_BARS, "lead-in"
        for n in range(ci_bars):
            bars.append({
                "section_id": s.get("id"),
                "label": s.get("label", ""),
                "section_index": idx,
                "count_in": True,
                "count_in_style": ci_style,
                "bar_in_section": n + 1,
                "section_bars": ci_bars,
                "bpm": bpm,
                "beats": BEATS_PER_BAR,
                "beat_ms": beat_ms,
                "start_ms": t,
                "song_bar": None,
            })
            t += bar_ms
        for n in range(int(s.get("bars", 0))):
            bars.append({
                "section_id": s.get("id"),
                "label": s.get("label", ""),
                "section_index": idx,
                "count_in": False,
                "count_in_style": None,
                "bar_in_section": n + 1,
                "section_bars": int(s.get("bars", 0)),
                "bpm": bpm,
                "beats": BEATS_PER_BAR,
                "beat_ms": beat_ms,
                "start_ms": t,
                "song_bar": song_bar,
            })
            t += bar_ms
            song_bar += 1
    return {"bars": bars, "total_ms": t, "song_bars": sum(int(s.get("bars", 0)) for s in sections)}


def bar_at(timeline: dict, elapsed_ms: float) -> int:
    """Index of the bar playing `elapsed_ms` after the run started; -1 before
    the first bar, len(bars) once the song is over. Binary search, since a
    long song has a few hundred bars and this runs every animation frame on
    the client (same algorithm in timing.js)."""
    bars = timeline["bars"]
    if elapsed_ms < 0:
        return -1
    if elapsed_ms >= timeline["total_ms"]:
        return len(bars)
    lo, hi = 0, len(bars) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if bars[mid]["start_ms"] <= elapsed_ms:
            lo = mid
        else:
            hi = mid - 1
    return lo


def duration_ms(song: dict) -> float:
    """How long the song plays from the top, count-ins included."""
    return build(song)["total_ms"]
