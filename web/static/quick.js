"use strict";

/*
 * Fast entry (0.10): turning "Song A - 128 - 3:45" into a song, and tap
 * tempo. Pure functions, no DOM: loads as a plain <script> in the page and
 * as a module under Node for the tests (tests/test_quick.py).
 *
 * A quick song is just a title and a tempo: one section ("Song") long
 * enough for the length given (4:00 when there's none). Enough for the
 * click; the structure can be planned later, or never.
 */

(function (root) {
  const MIN_BPM = 20;
  const MAX_BPM = 400;
  const DEFAULT_LENGTH_S = 240;

  // "3:45" -> 225 seconds; null when there's no length
  function parseLength(text) {
    const m = /^(\d{1,2}):([0-5]\d)$/.exec(String(text || "").trim());
    return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null;
  }

  // bars (4/4) that fill `seconds` at `bpm`, at least one
  function barsForLength(seconds, bpm) {
    return Math.max(1, Math.round((seconds * bpm) / 60 / 4));
  }

  /*
   * One line of a pasted list. Understands, among others:
   *   Song A - 128            Song A, 128, 3:45        3. Song A (128 bpm)
   *   Song A<TAB>128<TAB>3:45 (pasted from a spreadsheet)
   * Returns {title, bpm|null, seconds|null} or null for a blank/comment line.
   */
  function parseLine(line) {
    let text = String(line || "").replace(/\s+$/, "");
    if (!text.trim() || /^\s*(#|\/\/)/.test(text)) return null;
    text = text.replace(/^\s*\d{1,3}\s*[.)]\s+/, ""); // "3. " / "3) "
    let seconds = null;
    text = text.replace(/(^|[\s,;|\t(\-–—])(\d{1,2}:[0-5]\d)(?=$|[\s,;|\t)])/, (all, pre, len) => {
      seconds = parseLength(len);
      return pre;
    });
    let bpm = null;
    // a number of 20..400, optionally followed by "bpm", the last one on the line
    const re = /(^|[\s,;|\t(\-–—])(\d{2,3})(\s*bpm)?(?=$|[\s,;|\t)])/gi;
    let m;
    let hit = null;
    while ((m = re.exec(text))) {
      const v = parseInt(m[2], 10);
      if (v >= MIN_BPM && v <= MAX_BPM) hit = { index: m.index + m[1].length, length: m[2].length + (m[3] || "").length, v };
    }
    // a number is only a tempo if a title comes before it ("99 Problems")
    if (hit) {
      const before = text.slice(0, hit.index);
      if (before.replace(/[\s,;|\t()\-–—:]/g, "")) {
        bpm = hit.v;
        text = text.slice(0, hit.index) + text.slice(hit.index + hit.length);
      }
    }
    const title = text
      .replace(/\(\s*\)/g, " ")
      .replace(/[\t|;]+/g, " ")
      .replace(/^[\s,\-–—:]+|[\s,\-–—:(]+$/g, "")
      .replace(/\s{2,}/g, " ")
      .trim();
    if (!title) return null;
    return { title: title.slice(0, 120), bpm, seconds };
  }

  function parseList(text) {
    return String(text || "").split(/\r?\n/).map(parseLine).filter(Boolean);
  }

  // The song a quick entry becomes (what POST /api/songs takes).
  function quickSong(entry, newId) {
    const bpm = entry.bpm || 120;
    const seconds = entry.seconds || DEFAULT_LENGTH_S;
    return {
      title: entry.title,
      default_bpm: bpm,
      sections: [{ id: newId(), label: "Song", order: 0, bars: barsForLength(seconds, bpm), bpm: null,
        count_in: { bars: 0, style: "none" }, hints: [] }],
    };
  }

  /*
   * Tap tempo: the average of the last few gaps between taps. A pause of
   * more than two seconds starts over. `now` is injectable for tests.
   */
  class TapTempo {
    constructor(maxTaps) {
      this.maxTaps = maxTaps || 8;
      this.taps = [];
    }

    tap(now) {
      const t = now === undefined ? Date.now() : now;
      const last = this.taps[this.taps.length - 1];
      if (last !== undefined && t - last > 2000) this.taps = [];
      this.taps.push(t);
      if (this.taps.length > this.maxTaps) this.taps.shift();
      return this.bpm();
    }

    bpm() {
      if (this.taps.length < 2) return null;
      const span = this.taps[this.taps.length - 1] - this.taps[0];
      const v = Math.round((60000 * (this.taps.length - 1)) / span);
      return Math.max(MIN_BPM, Math.min(MAX_BPM, v));
    }
  }

  const api = { parseLength, barsForLength, parseLine, parseList, quickSong, TapTempo, DEFAULT_LENGTH_S };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SSPQuick = api;
})(typeof window !== "undefined" ? window : globalThis);
