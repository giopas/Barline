"use strict";

/*
 * Song files and merging (0.18).
 *
 * One place for what a Barline file holds and how two copies of a song come
 * back together. Used by the web app against the band's server and by
 * Pocket (the same app with no server), and run by the tests under node.
 * Pure functions: no DOM, no network.
 *
 * File formats
 *   { ssp_export: 1, song, audio }                 one song (and its voice memos)
 *   { ssp_export: 2, band?, songs, setlists, audio }  several songs: a setlist
 *                                                  with its songs, or everything
 *   a plain song .json (what's in data/songs/)
 * `audio` maps a clip name (12 hex + extension) to its bytes in base64.
 *
 * Merging
 *   The structure (sections, bars, BPM, count-ins, order) comes from one
 *   copy, chosen by whoever merges when the two differ. Hints come from
 *   both, matched by id: a hint only one copy has is kept; a hint both have
 *   but that differs keeps the newer version (`updated_at`). Nothing is
 *   deleted by a merge. A hint whose section isn't in the chosen structure
 *   moves to the section with the same name, or the one in the same place.
 */

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BarlineFiles = api;
})(typeof self !== "undefined" ? self : this, function () {
  const CLIP_RE = /^[0-9a-f]{12}\.(webm|ogg|m4a|mp4|mp3|wav|aac)$/;
  const SHAPE = ["label", "bars", "bpm", "count_in"];

  function clone(x) {
    return x === undefined ? undefined : JSON.parse(JSON.stringify(x));
  }

  function isSong(x) {
    return x && typeof x === "object" && Array.isArray(x.sections);
  }

  // -- reading a file -----------------------------------------------------

  // Whatever a file holds, as { songs, setlists, band, audio }. Throws
  // with a plain message when it isn't a Barline file.
  function normalize(payload) {
    const bad = new Error("that isn't a Barline song file (.ssp.json, .json or a song's PDF)");
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw bad;
    let songs = [];
    let setlists = [];
    let band = null;
    if (payload.ssp_export !== undefined && isSong(payload.song)) {
      songs = [payload.song];
    } else if (Array.isArray(payload.songs)) {
      songs = payload.songs.filter(isSong);
      setlists = (payload.setlists || []).filter((s) => s && typeof s === "object" && Array.isArray(s.songs));
      band = payload.band && typeof payload.band === "object" && Array.isArray(payload.band.players) ? payload.band : null;
      if (!songs.length && !setlists.length && !band) throw bad;
    } else if (isSong(payload)) {
      songs = [payload];
    } else {
      throw bad;
    }
    const audio = {};
    for (const [ref, b64] of Object.entries(payload.audio || {})) {
      if (CLIP_RE.test(ref) && typeof b64 === "string") audio[ref] = b64;
    }
    return { songs: clone(songs), setlists: clone(setlists), band: clone(band), audio };
  }

  function clipRefs(song) {
    const out = new Set();
    for (const s of song.sections || []) for (const h of s.hints || []) if (h.audio) out.add(h.audio);
    return out;
  }

  // -- writing a file -----------------------------------------------------

  // `clips` maps clip name -> base64 for every clip the songs use (missing
  // ones are left out; the hint keeps its text).
  function makeFile({ songs, setlists, band }, clips) {
    const audio = {};
    for (const song of songs) {
      for (const ref of clipRefs(song)) if (clips && clips[ref]) audio[ref] = clips[ref];
    }
    if (songs.length === 1 && !(setlists || []).length && !band) {
      return { ssp_export: 1, song: songs[0], audio };
    }
    const out = { ssp_export: 2, songs, setlists: setlists || [], audio };
    if (band) out.band = band;
    return out;
  }

  // -- who wrote it ---------------------------------------------------------

  // "Sam (Guitar)": the player as this band knows them now, or as the
  // hint remembers them when this band has no such player.
  function authorLabel(author, band) {
    if (!author) return "";
    const p = band && (band.players || []).find((x) => author.id && x.id === author.id);
    const name = (p && p.name) || author.name || "someone";
    const role = (p && p.role) || author.role;
    return role ? `${name} (${role})` : name;
  }

  // Same person? The same player id, or the same name and role (two
  // bands' copies of one player have different ids).
  function samePerson(a, b) {
    if (!a || !b) return false;
    if (a.id && b.id && a.id === b.id) return true;
    return !!a.name && (a.name || "").toLowerCase() === (b.name || "").toLowerCase() && (a.role || "") === (b.role || "");
  }

  // -- comparing ------------------------------------------------------------

  function ordered(song) {
    return (song.sections || []).slice().sort((a, b) => (a.order || 0) - (b.order || 0));
  }

  function shapeOf(section) {
    return JSON.stringify(SHAPE.map((k) => (k === "count_in" ? section.count_in || { bars: 0, style: "none" } : section[k] ?? null)));
  }

  // Same structure: the same sections in the same order with the same
  // label, bars, BPM and count-in, and the same song tempo.
  function structureSame(a, b) {
    const sa = ordered(a);
    const sb = ordered(b);
    if ((a.default_bpm || 0) !== (b.default_bpm || 0) || sa.length !== sb.length) return false;
    return sa.every((s, i) => shapeOf(s) === shapeOf(sb[i]));
  }

  function hintSame(a, b) {
    return (a.text || "") === (b.text || "") && (a.visibility || "all") === (b.visibility || "all") && (a.audio || null) === (b.audio || null);
  }

  // A short description of how two copies' structures differ, for the
  // person choosing which to keep.
  function structureDiff(local, incoming) {
    const out = [];
    if ((local.default_bpm || 0) !== (incoming.default_bpm || 0)) out.push(`tempo ${local.default_bpm} vs ${incoming.default_bpm} BPM`);
    const sa = ordered(local);
    const sb = ordered(incoming);
    const bars = (ss) => ss.reduce((n, s) => n + (s.bars || 0), 0);
    if (sa.length !== sb.length) out.push(`${sa.length} vs ${sb.length} sections`);
    else {
      const changed = sa.filter((s, i) => shapeOf(s) !== shapeOf(sb[i])).map((s, i) => s.label || `section ${i + 1}`);
      if (changed.length) out.push(`changed: ${changed.slice(0, 4).join(", ")}${changed.length > 4 ? "…" : ""}`);
    }
    if (bars(sa) !== bars(sb)) out.push(`${bars(sa)} vs ${bars(sb)} bars`);
    return out.join("; ");
  }

  // -- matching songs -------------------------------------------------------

  function norm(t) {
    return (t || "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  // Which song here an incoming song is a copy of: the same id, or failing
  // that the same title (only when exactly one song here has it).
  function matchSong(incoming, localSongs) {
    const byId = localSongs.find((s) => s.id === incoming.id);
    if (byId) return byId;
    const sameTitle = localSongs.filter((s) => norm(s.title) === norm(incoming.title));
    return sameTitle.length === 1 ? sameTitle[0] : null;
  }

  // -- merging one song -------------------------------------------------------

  // `structureFrom` is "local" or "incoming". Returns { song, report }: the
  // merged song (the local song's id, title and creation time; tags from
  // both) and what happened, for the preview and the toast.
  function mergeSong(local, incoming, structureFrom) {
    const base = structureFrom === "incoming" ? incoming : local;
    const other = structureFrom === "incoming" ? local : incoming;
    const song = clone(local);
    song.default_bpm = base.default_bpm;
    const tagSeen = new Set();
    song.tags = [];
    for (const t of [...(local.tags || []), ...(incoming.tags || [])]) {
      if (!tagSeen.has(t.toLowerCase())) {
        tagSeen.add(t.toLowerCase());
        song.tags.push(t);
      }
    }
    song.sections = clone(ordered(base)).map((s, i) => Object.assign(s, { order: i, hints: [] }));

    // where each hint goes: its own section if the structure has it, else
    // the section with the same label, else the one in the same place
    const byId = new Map(song.sections.map((s) => [s.id, s]));
    const byLabel = new Map();
    for (const s of song.sections) if (!byLabel.has(norm(s.label))) byLabel.set(norm(s.label), s);
    const home = (section, index) =>
      byId.get(section.id) || byLabel.get(norm(section.label)) || song.sections[Math.min(index, song.sections.length - 1)] || null;

    const report = {
      structure: structureSame(local, incoming) ? "same" : structureFrom,
      added: [], // hints only the file had: [{author}]
      updated: [], // the file's newer version replaced this copy's
      keptNewer: 0, // both changed it, this copy's was newer
      moved: 0, // a hint whose section isn't in the kept structure
      lost: 0, // nowhere to put it (the kept structure has no sections)
      kept: 0,
    };

    const placed = new Map(); // hint id -> { hint, section }
    const order = [];
    const take = (copy, fromIncoming) => {
      ordered(copy).forEach((section, index) => {
        for (const h of section.hints || []) {
          const prev = placed.get(h.id);
          if (!prev) {
            const target = home(section, index);
            if (!target) {
              report.lost += 1;
              continue;
            }
            if (!byId.has(section.id) || target.id !== section.id) report.moved += 1;
            placed.set(h.id, { hint: clone(h), section: target });
            order.push(h.id);
            if (fromIncoming) report.added.push({ author: h.author || null });
            else report.kept += 1;
            continue;
          }
          if (hintSame(prev.hint, h)) continue;
          const mine = prev.hint.updated_at || 0;
          const theirs = h.updated_at || 0;
          if (theirs > mine) {
            prev.hint = clone(h);
            report.updated.push({ author: h.author || null });
          } else {
            report.keptNewer += 1;
          }
        }
      });
    };
    take(local, false);
    take(incoming, true);
    for (const id of order) {
      const { hint, section } = placed.get(id);
      section.hints.push(hint);
    }
    song.updated_at = Math.max(local.updated_at || 0, incoming.updated_at || 0);
    return { song, report };
  }

  // Did a merge change anything at all?
  function reportEmpty(report) {
    return report.structure !== "incoming" && !report.added.length && !report.updated.length && !report.moved;
  }

  // "3 new hints (2 from Sam (Guitar), 1 from Ruby (Drums)) · 1 updated"
  function describe(report, band) {
    const who = (list) => {
      const counts = new Map();
      for (const x of list) {
        const k = x.author ? authorLabel(x.author, band) : "no name";
        counts.set(k, (counts.get(k) || 0) + 1);
      }
      return [...counts].map(([k, n]) => `${n} from ${k}`).join(", ");
    };
    const parts = [];
    if (report.added.length) parts.push(`${report.added.length} new hint${report.added.length === 1 ? "" : "s"} (${who(report.added)})`);
    if (report.updated.length) parts.push(`${report.updated.length} changed in the file (${who(report.updated)})`);
    if (report.keptNewer) parts.push(`${report.keptNewer} kept: yours is newer`);
    if (report.moved) parts.push(`${report.moved} moved to a matching section`);
    if (report.lost) parts.push(`${report.lost} with no section to go to`);
    return parts.join(" · ") || "no new hints";
  }

  // -- planning an import -----------------------------------------------------

  // What importing `file` (from normalize) into `local` ({songs, setlists,
  // band}) would do, song by song:
  //   { kind: "new", incoming }                    added as a new song
  //   { kind: "same", incoming, local }            nothing to bring in
  //   { kind: "merge", incoming, local, sameStructure, diff,
  //     preview: { local: {song, report}, incoming: {song, report} } }
  function plan(file, local) {
    // players: someone in the file this band already has under another id
    // (same name and role) is that player here; anyone else is added
    const players = [];
    if (file.band) {
      const map = {};
      for (const p of file.band.players) {
        const q = (local.band.players || []).find((x) => samePerson(x, p));
        if (q) map[p.id] = q.id;
        else players.push(p);
      }
      for (const song of file.songs) {
        for (const s of song.sections || []) {
          for (const h of s.hints || []) {
            if (map[h.visibility]) h.visibility = map[h.visibility];
            if (h.author && map[h.author.id]) h.author.id = map[h.author.id];
          }
        }
      }
    }
    const items = [];
    const usedLocal = new Set();
    for (const incoming of file.songs) {
      const match = matchSong(incoming, local.songs.filter((s) => !usedLocal.has(s.id)));
      if (!match) {
        items.push({ kind: "new", incoming });
        continue;
      }
      usedLocal.add(match.id);
      const same = structureSame(match, incoming);
      const preview = { local: mergeSong(match, incoming, "local") };
      if (!same) preview.incoming = mergeSong(match, incoming, "incoming");
      if (same && reportEmpty(preview.local.report)) {
        items.push({ kind: "same", incoming, local: match });
        continue;
      }
      items.push({ kind: "merge", incoming, local: match, sameStructure: same, diff: same ? "" : structureDiff(match, incoming), preview });
    }
    // setlists: one this side already has (same id or name) is kept as it is
    const setlists = file.setlists.map((sl) => {
      const mine = local.setlists.find((x) => x.id === sl.id) || local.setlists.find((x) => norm(x.name) === norm(sl.name));
      return { incoming: sl, local: mine || null };
    });
    return { items, setlists, players, bandName: file.band ? file.band.name : null };
  }

  return {
    CLIP_RE, normalize, makeFile, clipRefs, authorLabel, samePerson, structureSame, structureDiff,
    matchSong, mergeSong, reportEmpty, describe, plan,
  };
});
