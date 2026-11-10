"use strict";

/*
 * Barline Pocket (0.18): the same web app with no server.
 *
 * Pocket is published as a static site (GitHub Pages, https) and added to
 * a phone's or tablet's home screen. It keeps the band's songs in this
 * browser's own storage (IndexedDB) and works offline (sw.js). Files are
 * how it talks to the band: import the band's file, practise and add
 * notes, export a file and import it back on the band's Barline, where
 * it's merged (files.js).
 *
 * How: this file answers the app's /api/ calls itself, in the page, with
 * the same shapes as server/app.py, so app.js and live.js run unchanged.
 * The live view always plays solo (this device's own transport). There is
 * no sync, no QR, no paper charts, no click-track downloads.
 *
 * Only loaded in the Pocket build (tools/build_pocket.py), never by the
 * band's server.
 */

(function (root) {
  const DB_NAME = "barline-pocket";
  const ROLES = ["Drums", "Bass", "Guitar", "Vocals", "Keys", "Other"];
  const STYLES = ["sticks", "click", "verbal", "none"];
  const AUDIO_EXTS = { webm: "audio/webm", ogg: "audio/ogg", m4a: "audio/mp4", mp4: "audio/mp4", mp3: "audio/mpeg", wav: "audio/wav", aac: "audio/aac" };
  const ID_RE = /^[A-Za-z0-9_-]{1,40}$/;

  const mem = { band: { id: "band", name: "My Band", players: [] }, songs: {}, setlists: {}, clips: {}, urls: {}, demo: false };
  let db = null;

  // -- storage ---------------------------------------------------------------

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore("kv");
        req.result.createObjectStore("audio");
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function tx(store, mode, fn) {
    return new Promise((resolve, reject) => {
      const t = db.transaction(store, mode);
      const out = fn(t.objectStore(store));
      t.oncomplete = () => resolve(out && out.result !== undefined ? out.result : undefined);
      t.onerror = () => reject(t.error);
      t.onabort = () => reject(t.error || new Error("storage full?"));
    });
  }

  function allOf(store) {
    return new Promise((resolve, reject) => {
      const out = {};
      const req = db.transaction(store, "readonly").objectStore(store).openCursor();
      req.onsuccess = () => {
        const c = req.result;
        if (!c) return resolve(out);
        out[c.key] = c.value;
        c.continue();
      };
      req.onerror = () => reject(req.error);
    });
  }

  const put = (key, value) => tx("kv", "readwrite", (s) => s.put(value, key));
  const del = (key) => tx("kv", "readwrite", (s) => s.delete(key));

  const ready = (async () => {
    try {
      db = await openDb();
      const kv = await allOf("kv");
      for (const [k, v] of Object.entries(kv)) {
        if (k === "band") mem.band = v;
        else if (k === "demo") mem.demo = !!v;
        else if (k.startsWith("song:")) mem.songs[v.id] = v;
        else if (k.startsWith("setlist:")) mem.setlists[v.id] = v;
      }
      mem.clips = await allOf("audio");
    } catch (err) {
      console.warn("Pocket storage unavailable:", err);
    }
    // ask the browser not to clear this storage when space runs low
    try {
      if (navigator.storage && navigator.storage.persist) navigator.storage.persist();
    } catch (err) {
      /* best effort */
    }
  })();

  // -- the model (same rules as server/models) -----------------------------------

  function newId() {
    const a = new Uint8Array(6);
    crypto.getRandomValues(a);
    return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  const now = () => Date.now() / 1000;
  const clone = (x) => JSON.parse(JSON.stringify(x));

  class Invalid extends Error {}

  function cleanTags(tags) {
    if (!Array.isArray(tags)) return [];
    const out = [];
    const seen = new Set();
    for (let t of tags) {
      if (typeof t !== "string") continue;
      t = t.split(/\s+/).join(" ").slice(0, 30).trim();
      if (t && !seen.has(t.toLowerCase())) {
        seen.add(t.toLowerCase());
        out.push(t);
      }
      if (out.length >= 12) break;
    }
    return out;
  }

  function validateSong(song) {
    if (!String(song.title || "").trim()) throw new Invalid("song title cannot be empty");
    const bpm = song.default_bpm;
    if (!Number.isInteger(bpm) || bpm < 20 || bpm > 400) throw new Invalid(`default_bpm ${bpm} out of range 20-400`);
    for (const s of song.sections || []) {
      if (!Number.isInteger(s.bars) || s.bars < 1 || s.bars > 999) throw new Invalid(`section ${s.label || s.id}: bars must be 1 to 999`);
      if (s.bpm !== null && s.bpm !== undefined && (s.bpm < 20 || s.bpm > 400)) throw new Invalid(`section ${s.label || s.id}: BPM out of range 20-400`);
      const ci = s.count_in || {};
      if (!STYLES.includes(ci.style || "none")) throw new Invalid("invalid count-in style");
      if (!Number.isInteger(ci.bars || 0) || (ci.bars || 0) < 0 || ci.bars > 8) throw new Invalid("count-in is 0 to 8 bars");
      s.hints = s.hints || [];
    }
  }

  function cleanAuthor(raw) {
    if (!raw || typeof raw !== "object") return null;
    const id = raw.id ? String(raw.id).slice(0, 40) : null;
    const name = String(raw.name || "").split(/\s+/).join(" ").slice(0, 60);
    if (!id && !name) return null;
    return { id, name: name || "Player", role: ROLES.includes(raw.role) ? raw.role : null };
  }

  function me() {
    const pid = root.SSPSync && root.SSPSync.playerId;
    const p = mem.band.players.find((x) => x.id === pid);
    return p ? { id: p.id, name: p.name, role: p.role } : null;
  }

  // models.stamp_changes: who changed which hint, and when
  function stamp(existing, song) {
    const when = now();
    const author = me();
    const oldS = {};
    const oldH = {};
    for (const s of (existing && existing.sections) || []) {
      oldS[s.id] = s;
      for (const h of s.hints || []) oldH[h.id] = h;
    }
    for (const s of song.sections || []) {
      const o = oldS[s.id];
      const changed = !o || ["label", "order", "bars", "bpm", "count_in"].some((k) => JSON.stringify(o[k] ?? null) !== JSON.stringify(s[k] ?? null));
      s.updated_at = changed ? when : o.updated_at;
      if (s.updated_at == null) delete s.updated_at;
      for (const h of s.hints || []) {
        const oh = oldH[h.id];
        const hChanged = !oh || ["text", "visibility", "audio"].some((k) => (oh[k] ?? null) !== (h[k] ?? null));
        if (hChanged) {
          h.updated_at = when;
          h.author = author || cleanAuthor(h.author);
        } else {
          h.updated_at = oh.updated_at;
          h.author = cleanAuthor(oh.author);
        }
        if (h.updated_at == null) delete h.updated_at;
        if (!h.author) delete h.author;
      }
    }
  }

  function tidyStamps(song) {
    for (const s of song.sections || []) {
      if (typeof s.updated_at !== "number") delete s.updated_at;
      for (const h of s.hints || []) {
        const a = cleanAuthor(h.author);
        if (a) h.author = a;
        else delete h.author;
        if (typeof h.updated_at !== "number") delete h.updated_at;
      }
    }
  }

  function clipRefs(song) {
    const out = new Set();
    for (const s of song.sections || []) for (const h of s.hints || []) if (h.audio) out.add(h.audio);
    return out;
  }

  function summary(s) {
    const T = root.SSPTiming;
    return {
      id: s.id, title: s.title, default_bpm: s.default_bpm, tags: cleanTags(s.tags),
      section_count: (s.sections || []).length, total_bars: T.songTotalBars(s), duration_ms: T.durationMs(s),
    };
  }

  function listSongs() {
    return Object.values(mem.songs).sort((a, b) => a.title.toLowerCase().localeCompare(b.title.toLowerCase())).map(summary);
  }

  function listSetlists() {
    return Object.values(mem.setlists)
      .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()))
      .map((sl) => ({
        id: sl.id, name: sl.name, song_count: sl.songs.length, songs: sl.songs.slice(),
        duration_ms: sl.songs.filter((id) => mem.songs[id]).reduce((n, id) => n + root.SSPTiming.durationMs(mem.songs[id]), 0),
      }));
  }

  function cleanBand(payload) {
    const name = String(payload.name ?? mem.band.name ?? "My Band").trim().slice(0, 80);
    if (!name) throw new Invalid("the band needs a name");
    const players = [];
    const seen = new Set();
    for (const p of payload.players ?? mem.band.players) {
      let pid = String(p.id || newId()).slice(0, 40);
      if (seen.has(pid) || pid === "all") pid = newId();
      seen.add(pid);
      players.push({ id: pid, name: String(p.name || "").trim().slice(0, 60) || "Player", role: ROLES.includes(p.role) ? p.role : "Other" });
    }
    return { id: "band", name, players };
  }

  async function saveClip(blob, ext) {
    const ref = `${newId()}.${ext}`;
    await tx("audio", "readwrite", (s) => s.put(blob, ref));
    mem.clips[ref] = blob;
    return ref;
  }

  async function collectClips(refs) {
    if (!refs.size) return;
    const used = new Set();
    for (const s of Object.values(mem.songs)) clipRefs(s).forEach((r) => used.add(r));
    for (const ref of refs) {
      if (used.has(ref)) continue;
      delete mem.clips[ref];
      if (mem.urls[ref]) URL.revokeObjectURL(mem.urls[ref]);
      delete mem.urls[ref];
      await tx("audio", "readwrite", (s) => s.delete(ref));
    }
  }

  function b64ToBlob(b64, ref) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: AUDIO_EXTS[ref.split(".").pop()] || "application/octet-stream" });
  }

  // models.apply_count_ins
  function countInChoice(raw, what) {
    if (raw === null || raw === undefined) return null;
    const bars = raw.bars ?? 1;
    const style = raw.style ?? "click";
    if (!STYLES.includes(style)) throw new Invalid(`${what}: the style is sticks, click, verbal or none`);
    if (!Number.isInteger(bars) || bars < 0 || bars > 8) throw new Invalid(`${what}: a count-in is 0 to 8 bars`);
    return style === "none" || bars === 0 ? { bars: 0, style: "none" } : { bars, style };
  }

  function applyCountIns(song, startRaw, changesRaw, tempoOnly, keep) {
    const start = countInChoice(startRaw, "start of the song");
    const changes = countInChoice(changesRaw, "section changes");
    let changed = 0;
    let prev = null;
    root.SSPTiming.sortedSections(song).forEach((s, i) => {
      const bpm = s.bpm || song.default_bpm;
      let want = i === 0 ? start : changes;
      if (i > 0 && tempoOnly && bpm === prev) want = null;
      prev = bpm;
      if (!want) return;
      const cur = s.count_in || { bars: 0, style: "none" };
      const has = (cur.style || "none") !== "none" && (cur.bars || 0) > 0;
      if (keep && has) return;
      if (!has && want.bars === 0) {
        s.count_in = { bars: 0, style: "none" };
        return;
      }
      if (cur.bars !== want.bars || cur.style !== want.style) {
        s.count_in = { ...want };
        changed += 1;
      }
    });
    return changed;
  }

  // -- the "server" ---------------------------------------------------------------

  function publish(type, data) {
    const S = root.SSPSync;
    if (S) S.emit(type, { type, data, origin: S.clientId });
  }

  async function saveSong(song) {
    mem.songs[song.id] = song;
    await put("song:" + song.id, song);
    publish("song", song);
    return song;
  }

  function live() {
    if (!root.SSPLive) throw new Invalid("the live view isn't ready yet");
    return root.SSPLive;
  }

  async function handle(method, path, query, body) {
    await ready;
    const r = path.split("/").filter(Boolean); // ["songs", "<id>"]
    const json = () => (body ? JSON.parse(body.text) : {});

    if (r[0] === "time") return { now: performance.now() };
    if (r[0] === "presence") return { ok: true };
    if (r[0] === "state") {
      return {
        version: root.BARLINE_VERSION || "", band: mem.band, songs: listSongs(), setlists: listSetlists(),
        transport: root.SSPLive ? root.SSPLive.soloState() : { state: "stopped" }, presence: [], now: performance.now(),
        // the demo band loaded with "Try the demo band": the banner offers a way out
        demo: { on: mem.demo, can_return: mem.demo }, pocket: true,
      };
    }
    if (r[0] === "bundle") {
      return {
        version: root.BARLINE_VERSION || "", band: mem.band,
        songs: listSongs().map((s) => mem.songs[s.id]), setlists: listSetlists().map((s) => mem.setlists[s.id]),
      };
    }
    if (r[0] === "transport") {
      if (method === "GET") return live().soloState();
      return live().soloCommand(json());
    }
    if (r[0] === "band") {
      if (method === "GET") return mem.band;
      const band = cleanBand(json());
      const gone = new Set(mem.band.players.map((p) => p.id).filter((id) => !band.players.some((p) => p.id === id)));
      mem.band = band;
      await put("band", band);
      publish("band", band);
      if (gone.size) {
        for (const song of Object.values(mem.songs)) {
          let hit = false;
          for (const s of song.sections) for (const h of s.hints || []) if (gone.has(h.visibility)) (h.visibility = "all"), (hit = true);
          if (hit) await saveSong(song);
        }
      }
      return band;
    }
    if (r[0] === "count-ins") {
      const p = json();
      const scope = p.scope || {};
      let ids;
      if (scope.song_id) ids = [scope.song_id];
      else if (scope.setlist_id) ids = (mem.setlists[scope.setlist_id] || { songs: [] }).songs;
      else if (scope.all === true) ids = Object.keys(mem.songs);
      else throw new Invalid("scope is {song_id}, {setlist_id} or {all: true}");
      if (p.start == null && p.changes == null) throw new Invalid("nothing to change: choose the start, the section changes, or both");
      const changed = [];
      let sections = 0;
      for (const id of new Set(ids)) {
        if (!mem.songs[id]) continue;
        const song = clone(mem.songs[id]);
        const n = applyCountIns(song, p.start, p.changes, !!p.tempo_only, !!p.keep_existing);
        if (!n) continue;
        stamp(mem.songs[id], song);
        song.updated_at = now();
        await saveSong(song);
        changed.push(song);
        sections += n;
      }
      return { songs: changed, sections, checked: new Set(ids).size };
    }
    if (r[0] === "audio") {
      if (method === "POST") {
        const ext = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/m4a": "m4a", "audio/aac": "aac", "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "video/mp4": "m4a", "video/webm": "webm" }[(body.type || "").split(";")[0].trim().toLowerCase()];
        if (!ext) throw new Invalid("that doesn't look like an audio file (webm, ogg, m4a, mp3, wav, aac)");
        if (!body.blob.size) throw new Invalid("the recording is empty");
        if (body.blob.size > 3 * 1024 * 1024) throw new Invalid("that's too big (over 3 MB)");
        return { ref: await saveClip(body.blob, ext) };
      }
      if (mem.clips[r[1]]) return { blob: mem.clips[r[1]] };
      throw new KeyError(r[1]);
    }
    if (r[0] === "import") throw new Invalid("Pocket can't read a PDF: import the song's .ssp.json file instead");
    if (r[0] === "songs") {
      if (r.length === 1 && method === "GET") return listSongs();
      if (r.length === 1 && method === "POST") {
        const p = json();
        const song = {
          id: newId(), title: String(p.title || "Untitled Song").slice(0, 120), default_bpm: p.default_bpm ?? 120,
          tags: cleanTags(p.tags), sections: Array.isArray(p.sections) ? p.sections : [], created_at: now(), updated_at: now(),
        };
        validateSong(song);
        stamp(null, song);
        return saveSong(song);
      }
      if (r[1] === "import" && method === "POST") {
        // export.unbundle: keeps the song's id when it's free, new clip names
        const payload = JSON.parse(body.text);
        let song = payload.ssp_export !== undefined ? payload.song : payload;
        if (!song || !Array.isArray(song.sections)) throw new Invalid("that isn't a Barline song file");
        song = clone(song);
        if (!song.id || mem.songs[song.id] || !ID_RE.test(String(song.id))) song.id = newId();
        song.title = song.title || "Imported song";
        song.default_bpm = song.default_bpm ?? 120;
        song.tags = cleanTags(song.tags);
        const renamed = {};
        for (const [ref, b64] of Object.entries((payload.ssp_export !== undefined && payload.audio) || {})) {
          if (!/^[0-9a-f]{12}\.(webm|ogg|m4a|mp4|mp3|wav|aac)$/.test(ref)) continue;
          try {
            renamed[ref] = await saveClip(b64ToBlob(b64, ref), ref.split(".").pop());
          } catch (err) {
            /* a broken clip: the hint keeps its text */
          }
        }
        for (const s of song.sections) for (const h of s.hints || []) if (h.audio) h.audio = renamed[h.audio] || null;
        song.updated_at = now();
        song.created_at = song.created_at || now();
        validateSong(song);
        tidyStamps(song);
        return saveSong(song);
      }
      const existing = mem.songs[r[1]];
      if (!existing) throw new KeyError(r[1]);
      if (method === "GET") return existing;
      if (method === "PUT") {
        const p = json();
        const song = {
          id: existing.id, title: String(p.title ?? existing.title).slice(0, 120), default_bpm: p.default_bpm ?? existing.default_bpm,
          tags: cleanTags(p.tags ?? existing.tags), sections: clone(p.sections ?? existing.sections),
          created_at: existing.created_at || now(), updated_at: now(),
        };
        validateSong(song);
        if (query.get("merge") === "1") tidyStamps(song);
        else stamp(existing, song);
        const dropped = new Set([...clipRefs(existing)].filter((x) => !clipRefs(song).has(x)));
        await saveSong(song);
        await collectClips(dropped);
        return song;
      }
      if (method === "DELETE") {
        const dropped = clipRefs(existing);
        delete mem.songs[existing.id];
        await del("song:" + existing.id);
        await collectClips(dropped);
        for (const sl of Object.values(mem.setlists)) {
          if (sl.songs.includes(existing.id)) {
            sl.songs = sl.songs.filter((x) => x !== existing.id);
            await put("setlist:" + sl.id, sl);
            publish("setlist", sl);
          }
        }
        publish("song_deleted", { id: existing.id });
        return null;
      }
    }
    if (r[0] === "setlists") {
      if (r.length === 1 && method === "GET") return listSetlists();
      if (r.length === 1 && method === "POST") {
        const p = json();
        const id = typeof p.id === "string" && ID_RE.test(p.id) && !mem.setlists[p.id] ? p.id : newId();
        const sl = { id, name: String(p.name || "New Setlist").slice(0, 120), songs: Array.isArray(p.songs) ? p.songs.filter((x) => typeof x === "string") : [] };
        if (!sl.name.trim()) throw new Invalid("setlist name cannot be empty");
        mem.setlists[id] = sl;
        await put("setlist:" + id, sl);
        publish("setlist", sl);
        return sl;
      }
      const existing = mem.setlists[r[1]];
      if (!existing) throw new KeyError(r[1]);
      if (method === "GET") return existing;
      if (method === "PUT") {
        const p = json();
        const sl = { id: existing.id, name: String(p.name ?? existing.name).slice(0, 120), songs: p.songs ?? existing.songs };
        if (!sl.name.trim()) throw new Invalid("setlist name cannot be empty");
        if (!Array.isArray(sl.songs) || !sl.songs.every((x) => typeof x === "string")) throw new Invalid("setlist songs must be a list of song ids");
        mem.setlists[sl.id] = sl;
        await put("setlist:" + sl.id, sl);
        publish("setlist", sl);
        return sl;
      }
      if (method === "DELETE") {
        delete mem.setlists[existing.id];
        await del("setlist:" + existing.id);
        publish("setlist_deleted", { id: existing.id });
        return null;
      }
    }
    throw new KeyError(`no such route: ${method} /api/${path}`);
  }

  class KeyError extends Error {}

  // Every fetch of /api/... is answered here instead of going out.
  const realFetch = root.fetch.bind(root);
  root.fetch = async function (input, init) {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    const at = url.pathname.indexOf("/api/");
    if (url.origin !== location.origin || at < 0) return realFetch(input, init);
    const path = url.pathname.slice(at + 5);
    const method = ((init && init.method) || "GET").toUpperCase();
    let body = null;
    if (init && init.body !== undefined && init.body !== null) {
      const blob = init.body instanceof Blob ? init.body : new Blob([init.body]);
      const headers = new Headers((init && init.headers) || {});
      body = { blob, type: headers.get("Content-Type") || blob.type, text: await blob.text() };
    }
    const reply = (status, data) =>
      new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    try {
      const out = await handle(method, path, url.searchParams, body);
      if (out && out.blob instanceof Blob) return new Response(out.blob, { status: 200, headers: { "Content-Type": out.blob.type } });
      if (out === null || out === undefined) return reply(204, null);
      return reply(method === "POST" && /^(songs|setlists)(\/import)?$/.test(path) ? 201 : 200, out);
    } catch (err) {
      if (err instanceof KeyError) return reply(404, { error: `not found: ${err.message}` });
      if (err instanceof Invalid || err instanceof SyntaxError) return reply(400, { error: err.message });
      console.error(err);
      return reply(500, { error: `internal error: ${err.message}` });
    }
  };

  root.BarlinePocket = {
    ready,
    song: (id) => mem.songs[id] || null,
    setlist: (id) => mem.setlists[id] || null,
    clipUrl(ref) {
      if (!mem.clips[ref]) return "";
      if (!mem.urls[ref]) mem.urls[ref] = URL.createObjectURL(mem.clips[ref]);
      return mem.urls[ref];
    },
    empty: () => !Object.keys(mem.songs).length,
    isDemo: () => mem.demo,
    async setDemo(on) {
      mem.demo = !!on;
      await put("demo", mem.demo);
    },
    // empty this device: every song, setlist, player and voice memo
    async reset() {
      await ready;
      await tx("kv", "readwrite", (s) => s.clear());
      await tx("audio", "readwrite", (s) => s.clear());
      Object.values(mem.urls).forEach((u) => URL.revokeObjectURL(u));
      Object.assign(mem, { band: { id: "band", name: "My Band", players: [] }, songs: {}, setlists: {}, clips: {}, urls: {}, demo: false });
    },
  };
})(window);
