"use strict";

/*
 * Tempo map, mirrored line for line from server/timeline.py so a song's
 * shape, length and playhead read the same in the browser as on the
 * server (tests/test_timing_parity.py checks the two agree on the demo
 * songs). Pure functions, no DOM: loads as a plain <script> in the page
 * and as a module under Node for the tests.
 */

(function (root) {
  const BEATS_PER_BAR = 4;
  const LEAD_IN_BARS = 1;

  function sortedSections(song) {
    return [...(song.sections || [])].sort((a, b) => (a.order || 0) - (b.order || 0));
  }

  function build(song, startSectionId, leadIn) {
    if (leadIn === undefined) leadIn = true;
    const sections = sortedSections(song);
    const defaultBpm = song.default_bpm || 120;
    let startIndex = 0;
    if (startSectionId) {
      const i = sections.findIndex((s) => s.id === startSectionId);
      if (i >= 0) startIndex = i;
    }
    const bars = [];
    let t = 0;
    let songBar = 1;
    for (const s of sections.slice(0, startIndex)) songBar += s.bars | 0;

    for (let idx = startIndex; idx < sections.length; idx++) {
      const s = sections[idx];
      const bpm = s.bpm || defaultBpm;
      const beatMs = 60000 / bpm;
      const barMs = beatMs * BEATS_PER_BAR;
      const ci = s.count_in || {};
      let ciBars = ci.bars | 0;
      let ciStyle = ci.style || "none";
      if (ciStyle === "none") ciBars = 0;
      if (idx === startIndex && ciBars === 0 && leadIn) {
        ciBars = LEAD_IN_BARS;
        ciStyle = "lead-in";
      }
      for (let n = 0; n < ciBars; n++) {
        bars.push({
          section_id: s.id, label: s.label || "", section_index: idx, count_in: true,
          count_in_style: ciStyle, bar_in_section: n + 1, section_bars: ciBars, bpm,
          beats: BEATS_PER_BAR, beat_ms: beatMs, start_ms: t, song_bar: null,
        });
        t += barMs;
      }
      for (let n = 0; n < (s.bars | 0); n++) {
        bars.push({
          section_id: s.id, label: s.label || "", section_index: idx, count_in: false,
          count_in_style: null, bar_in_section: n + 1, section_bars: s.bars | 0, bpm,
          beats: BEATS_PER_BAR, beat_ms: beatMs, start_ms: t, song_bar: songBar,
        });
        t += barMs;
        songBar += 1;
      }
    }
    return { bars, total_ms: t, song_bars: sections.reduce((n, s) => n + (s.bars | 0), 0) };
  }

  function barAt(timeline, elapsedMs) {
    const bars = timeline.bars;
    if (elapsedMs < 0) return -1;
    if (elapsedMs >= timeline.total_ms) return bars.length;
    let lo = 0;
    let hi = bars.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (bars[mid].start_ms <= elapsedMs) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }

  function sectionStartBar(song, sectionId) {
    let bar = 1;
    for (const s of sortedSections(song)) {
      if (s.id === sectionId) return bar;
      bar += s.bars;
    }
    return bar;
  }

  function songTotalBars(song) {
    return (song.sections || []).reduce((sum, s) => sum + (s.bars | 0), 0);
  }

  function durationMs(song) {
    return build(song).total_ms;
  }

  function fmtDuration(ms) {
    const s = Math.round(ms / 1000);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  const api = { BEATS_PER_BAR, build, barAt, sectionStartBar, songTotalBars, durationMs, fmtDuration, sortedSections };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SSPTiming = api;
})(typeof window !== "undefined" ? window : globalThis);
