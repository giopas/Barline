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

  // firstCountIn === false: a jump mid-run (0.16) lands straight on bar 1
  // of the section -- no count-in, no lead-in (see server/timeline.py)
  function build(song, startSectionId, leadIn, firstCountIn) {
    if (leadIn === undefined) leadIn = true;
    if (firstCountIn === undefined) firstCountIn = true;
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
      if (idx === startIndex && !firstCountIn) {
        ciBars = 0;
      } else if (idx === startIndex && ciBars === 0 && leadIn) {
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

  // the first bar line at or after earliestMs: where a jump can land
  function nextBoundary(timeline, earliestMs) {
    for (const bar of timeline.bars) if (bar.start_ms >= earliestMs) return bar.start_ms;
    return Math.max(timeline.total_ms, earliestMs);
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

  // -- click options (0.10), mirrored from server/timeline.py -------------
  const SUBDIVISIONS = { none: [], 8: [1 / 2], 16: [1 / 4, 1 / 2, 3 / 4], triplet: [1 / 3, 2 / 3] };
  const CLICK_DEFAULTS = { subdivision: "none", voice: false, mode: "always" };

  function clickOptions(raw) {
    raw = raw || {};
    const out = { ...CLICK_DEFAULTS };
    if (Object.prototype.hasOwnProperty.call(SUBDIVISIONS, raw.subdivision)) out.subdivision = String(raw.subdivision);
    out.voice = [true, 1, "1", "true", "on"].includes(raw.voice);
    if (raw.mode === "always" || raw.mode === "countin") out.mode = raw.mode;
    return out;
  }

  function clickEvents(timeline, options) {
    const o = clickOptions(options);
    const subs = SUBDIVISIONS[o.subdivision];
    const bars = timeline.bars;
    const out = [];
    for (let i = 0; i < bars.length; i++) {
      const bar = bars[i];
      const ci = !!bar.count_in;
      if (!ci && o.mode === "countin") continue;
      const lastCi = ci && !(i + 1 < bars.length && bars[i + 1].count_in && bars[i + 1].section_id === bar.section_id);
      for (let b = 0; b < bar.beats; b++) {
        const t = bar.start_ms + b * bar.beat_ms;
        if (ci && o.voice) {
          if (lastCi) out.push({ t, kind: "voice", n: b + 1, bar: i });
          else if (b % 2 === 0) out.push({ t, kind: "voice", n: b / 2 + 1, bar: i });
          continue;
        }
        out.push({ t, kind: b === 0 ? "accent" : "beat", n: b + 1, bar: i });
        if (!ci) for (const f of subs) out.push({ t: t + f * bar.beat_ms, kind: "sub", n: b + 1, bar: i });
      }
    }
    return out;
  }

  function durationMs(song) {
    return build(song).total_ms;
  }

  function fmtDuration(ms) {
    const s = Math.round(ms / 1000);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  const api = { BEATS_PER_BAR, SUBDIVISIONS, build, nextBoundary, clickOptions, clickEvents, barAt, sectionStartBar, songTotalBars, durationMs, fmtDuration, sortedSections };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SSPTiming = api;
})(typeof window !== "undefined" ? window : globalThis);
