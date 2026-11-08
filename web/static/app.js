"use strict";

/*
 * SSP - Song and Setlist Planner -- the one web app.
 *
 * Drafting (this file) and the live, on-stage view (live.js) are the same
 * app against the same server, not separate ones (PROJECT_CHARTER.md
 * section 10). Every edit is saved to the server a moment after you stop
 * typing and pushed from there to every other connected device (sync.js).
 *
 * Concurrency is deliberately simple: last write wins, per song. When
 * another device changes the song you have open, this page takes their
 * version -- unless you're mid-edit yourself, in which case your save,
 * a fraction of a second later, wins and goes out to everyone.
 *
 * No build step: plain <script>s, vanilla JS.
 */

const Timing = window.SSPTiming;
const Sync = window.SSPSync;
const api = (...args) => Sync.api(...args);

// ---------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------

function debounce(fn, delay) {
  let timer = null;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, delay);
  };
  wrapped.pending = () => timer !== null;
  return wrapped;
}

const prefs = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem("ssp." + key);
      return v === null ? fallback : JSON.parse(v);
    } catch (err) {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem("ssp." + key, JSON.stringify(value));
    } catch (err) {
      /* private mode etc. -- a per-device convenience only */
    }
  },
};

function toast(text, kind) {
  const box = document.getElementById("toasts");
  // the same message again (another device saving as it types): keep one
  for (const old of box.children) if (old.textContent === text && !old.classList.contains("toast-out")) old.remove();
  const t = document.createElement("div");
  t.className = "toast" + (kind ? " toast-" + kind : "");
  t.textContent = text;
  box.appendChild(t);
  setTimeout(() => t.classList.add("toast-out"), 3200);
  setTimeout(() => t.remove(), 3800);
}

function newId() {
  const a = new Uint8Array(6);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// ---------------------------------------------------------------------
// Section colours -- one per section by its position in the song, the
// same in the overview strip, the bar grid, the card border, the live
// view and the printed chart (server/export.py has the same list).
// ---------------------------------------------------------------------

const SECTION_PALETTE = ["#5b8cff", "#45c08a", "#e2b93b", "#e2574c", "#b073f0", "#39c2c9", "#f08a3c", "#6fcf97"];

function sectionColor(index) {
  return SECTION_PALETTE[index % SECTION_PALETTE.length];
}

function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const ROLES = ["Drums", "Bass", "Guitar", "Vocals", "Keys", "Other"];

// ---------------------------------------------------------------------
// App state
// ---------------------------------------------------------------------

const state = {
  band: { name: "", players: [] },
  songs: [],
  setlists: [],
  currentSong: null,
  currentSetlist: null,
  view: "empty",
  transport: { state: "stopped" },
  presence: [],
  me: prefs.get("player", null), // this device's player id, or null = whole band
  previewing: false,
};

const metronome = new window.SSPAudio.Metronome();
// this device's click (0.10: one saved object; older versions saved sound/volume alone)
metronome.configure(prefs.get("clickopts", { sound: prefs.get("sound", "wood"), volume: prefs.get("volume", 0.8) }));
metronome.enabled = prefs.get("click", true);

function saveClick(changes) {
  const opts = metronome.configure(changes);
  prefs.set("clickopts", opts);
  return opts;
}

// The same choices as a query string, for the .wav / .zip downloads.
function clickQuery() {
  const o = metronome.opts;
  return new URLSearchParams({
    sound: o.sound, subdivision: o.subdivision, voice: o.voice ? "1" : "0", mode: o.mode,
    accent: o.accent, beat: o.beat, sub: o.sub, channel: o.channel,
  }).toString();
}

const els = {
  sidebar: document.getElementById("sidebar"),
  scrim: document.getElementById("scrim"),
  songList: document.getElementById("song-list"),
  setlistList: document.getElementById("setlist-list"),
  emptyState: document.getElementById("empty-state"),
  songView: document.getElementById("song-view"),
  setlistView: document.getElementById("setlist-view"),
  bandView: document.getElementById("band-view"),
  liveView: document.getElementById("live-view"),
  songTitle: document.getElementById("song-title"),
  songBpm: document.getElementById("song-bpm"),
  songShape: document.getElementById("song-shape"),
  songSummary: document.getElementById("song-summary"),
  sectionsList: document.getElementById("sections-list"),
  setlistName: document.getElementById("setlist-name"),
  setlistSongs: document.getElementById("setlist-songs"),
  setlistAvailable: document.getElementById("setlist-available"),
  setlistSummary: document.getElementById("setlist-summary"),
  bandName: document.getElementById("band-name"),
  playerList: document.getElementById("player-list"),
};

function playerById(id) {
  return state.band.players.find((p) => p.id === id) || null;
}

function playerName(id) {
  const p = playerById(id);
  return p ? p.name : null;
}

function nameForClient(clientId) {
  const c = state.presence.find((x) => x.client_id === clientId);
  return (c && playerName(c.player_id)) || "Another device";
}

// ---------------------------------------------------------------------
// Re-render without losing the cursor: every editable input carries a
// data-focus-key; after a redraw we put focus (and the caret) back.
// ---------------------------------------------------------------------

function preserveFocus(fn) {
  const a = document.activeElement;
  const key = a && a.dataset ? a.dataset.focusKey : null;
  let sel = null;
  if (key && typeof a.selectionStart === "number") {
    try {
      sel = [a.selectionStart, a.selectionEnd];
    } catch (err) {
      sel = null;
    }
  }
  fn();
  if (!key) return;
  const b = document.querySelector(`[data-focus-key="${CSS.escape(key)}"]`);
  if (b) {
    b.focus({ preventScroll: true });
    if (sel) {
      try {
        b.setSelectionRange(sel[0], sel[1]);
      } catch (err) {
        /* number inputs */
      }
    }
  }
}

// ---------------------------------------------------------------------
// Routing: #/song/<id>, #/setlist/<id>, #/band, #/live[?player=<id>]
// ---------------------------------------------------------------------

function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [path, query] = h.split("?");
  const parts = path.split("/").filter(Boolean);
  return { parts, params: new URLSearchParams(query || "") };
}

async function route() {
  const { parts, params } = parseHash();
  closeSidebar();
  if (params.get("player") !== null) {
    const pid = params.get("player");
    setMe(pid && playerById(pid) ? pid : null);
  }
  stopPreview();
  try {
    if (parts[0] === "song" && parts[1]) return await openSong(parts[1]);
    if (parts[0] === "setlist" && parts[1]) return await openSetlist(parts[1]);
    if (parts[0] === "band") return openBand();
    if (parts[0] === "live") return openLive();
  } catch (err) {
    toast("That song or setlist isn't here any more.", "warn");
  }
  showView("empty");
}

function openLive() {
  showView("live");
}

function showView(view) {
  state.view = view;
  els.emptyState.classList.toggle("hidden", view !== "empty");
  els.songView.classList.toggle("hidden", view !== "song");
  els.setlistView.classList.toggle("hidden", view !== "setlist");
  els.bandView.classList.toggle("hidden", view !== "band");
  els.liveView.classList.toggle("hidden", view !== "live");
  document.body.classList.toggle("is-live", view === "live");
  if (view !== "song") state.currentSong = null;
  if (view !== "setlist") state.currentSetlist = null;
  document.getElementById("nav-band").classList.toggle("active", view === "band");
  renderSidebar();
  if (window.SSPLive) window.SSPLive.visible(view === "live");
}

// ---------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------

async function refreshLists() {
  const [songs, setlists] = await Promise.all([api("GET", "/songs"), api("GET", "/setlists")]);
  state.songs = songs;
  state.setlists = setlists;
  renderSidebar();
  if (state.view === "setlist") preserveFocus(renderSetlistSongs);
  if (window.SSPLive) window.SSPLive.refresh();
}
const refreshListsSoon = debounce(() => refreshLists().catch(() => {}), 150);

function renderSidebar() {
  els.songList.innerHTML = "";
  for (const song of state.songs) {
    const li = el("li");
    li.appendChild(el("span", "item-name", song.title || "(untitled)"));
    li.appendChild(el("span", "item-count", `${song.default_bpm} · ${Timing.fmtDuration(song.duration_ms)}`));
    if (state.currentSong && state.currentSong.id === song.id) li.classList.add("active");
    li.addEventListener("click", () => go(`#/song/${song.id}`));
    els.songList.appendChild(li);
  }
  els.setlistList.innerHTML = "";
  for (const setlist of state.setlists) {
    const li = el("li");
    li.appendChild(el("span", "item-name", setlist.name));
    li.appendChild(el("span", "item-count", `${setlist.song_count} · ${Timing.fmtDuration(setlist.duration_ms)}`));
    if (state.currentSetlist && state.currentSetlist.id === setlist.id) li.classList.add("active");
    li.addEventListener("click", () => go(`#/setlist/${setlist.id}`));
    els.setlistList.appendChild(li);
  }
  renderWho();
}

function openSidebar() {
  els.sidebar.classList.add("open");
  els.scrim.classList.add("open");
}

function closeSidebar() {
  els.sidebar.classList.remove("open");
  els.scrim.classList.remove("open");
}

document.getElementById("menu-btn").addEventListener("click", openSidebar);
els.scrim.addEventListener("click", closeSidebar);
document.getElementById("nav-band").addEventListener("click", () => go("#/band"));
document.getElementById("nav-live").addEventListener("click", () => go("#/live"));

// ---------------------------------------------------------------------
// Who's on this device
// ---------------------------------------------------------------------

function setMe(playerId) {
  state.me = playerId || null;
  prefs.set("player", state.me);
  prefs.set("asked", true);
  Sync.setPlayer(state.me);
  renderWho();
  if (state.view === "song") preserveFocus(renderSections);
  if (window.SSPLive) window.SSPLive.refresh();
}

function whoLabel() {
  const p = playerById(state.me);
  return p ? `${p.name} · ${p.role}` : "Whole band";
}

function renderWho() {
  for (const id of ["who-btn", "live-who"]) {
    const b = document.getElementById(id);
    if (b) b.textContent = (id === "who-btn" ? "You: " : "") + whoLabel();
  }
}

function openWho() {
  const box = document.getElementById("who-options");
  box.innerHTML = "";
  const all = el("button", "who-option" + (state.me ? "" : " active"));
  all.appendChild(el("strong", "", "Whole band"));
  all.appendChild(el("span", "", "No one in particular, every hint looks the same"));
  all.addEventListener("click", () => {
    setMe(null);
    closeModal("who-modal");
  });
  box.appendChild(all);
  for (const p of state.band.players) {
    const b = el("button", "who-option" + (state.me === p.id ? " active" : ""));
    b.appendChild(el("strong", "", p.name));
    b.appendChild(el("span", "", p.role));
    b.addEventListener("click", () => {
      setMe(p.id);
      closeModal("who-modal");
    });
    box.appendChild(b);
  }
  openModal("who-modal");
}

document.getElementById("who-btn").addEventListener("click", openWho);
document.getElementById("live-who").addEventListener("click", openWho);

// ---------------------------------------------------------------------
// Modals
// ---------------------------------------------------------------------

function openModal(id) {
  document.getElementById(id).classList.remove("hidden");
}

function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
}

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") for (const m of document.querySelectorAll(".modal")) m.classList.add("hidden");
});

for (const m of document.querySelectorAll(".modal")) {
  m.addEventListener("click", (ev) => {
    if (ev.target === m || ev.target.hasAttribute("data-close")) m.classList.add("hidden");
  });
}

// -- connect a device -----------------------------------------------------

async function openConnect() {
  let info = { addresses: [] };
  try {
    info = await api("GET", "/connect");
  } catch (err) {
    /* fall back to this page's own address */
  }
  const here = location.origin + "/";
  const onLocal = /^(localhost|127\.|\[::1\])/.test(location.hostname);
  const options = onLocal ? info.addresses : [here, ...info.addresses.filter((a) => a !== here)];
  if (!options.length) options.push(here);
  const select = document.getElementById("connect-address");
  select.innerHTML = "";
  for (const a of options) {
    const o = el("option", "", a);
    o.value = a;
    select.appendChild(o);
  }
  const draw = () => {
    const base = select.value;
    document.getElementById("connect-url").textContent = base;
    document.getElementById("connect-qr").src = "/api/qr.svg?text=" + encodeURIComponent(base);
    const box = document.getElementById("connect-players");
    box.innerHTML = "";
    for (const p of state.band.players) {
      const url = `${base}#/live?player=${p.id}`;
      const b = el("button", "chip", `${p.name} · ${p.role}`);
      b.title = url;
      b.addEventListener("click", () => {
        document.getElementById("connect-qr").src = "/api/qr.svg?text=" + encodeURIComponent(url);
        document.getElementById("connect-url").textContent = url;
      });
      box.appendChild(b);
    }
    if (!state.band.players.length) box.appendChild(el("p", "modal-note", "Add players on the Band page to get one code per player."));
  };
  select.onchange = draw;
  draw();
  const wifi = info.wifi;
  document.getElementById("connect-wifi").classList.toggle("hidden", !wifi);
  if (wifi) {
    const b = document.getElementById("connect-wifi-btn");
    b.textContent = `Wi-Fi: ${wifi.ssid}${wifi.password ? ` · password ${wifi.password}` : ""}`;
    b.onclick = () => {
      document.getElementById("connect-qr").src = "/api/qr.svg?text=" + encodeURIComponent(wifi.qr);
      document.getElementById("connect-url").textContent = `Scan to join "${wifi.ssid}", then scan the address code.`;
    };
  }
  openModal("connect-modal");
}

document.getElementById("connect-btn").addEventListener("click", openConnect);

// ---------------------------------------------------------------------
// Song editing
// ---------------------------------------------------------------------

let songEdits = 0; // bumps on every local edit; lets a remote update know we're mid-edit

async function openSong(id) {
  const song = await api("GET", `/songs/${id}`);
  state.currentSong = song;
  showView("song");
  renderSongView();
  renderSidebar();
}

function renderSongView() {
  const song = state.currentSong;
  if (document.activeElement !== els.songTitle) els.songTitle.value = song.title;
  if (document.activeElement !== els.songBpm) els.songBpm.value = song.default_bpm;
  renderSongShape();
  renderSections();
}

function songIsDirty() {
  return saveSong.pending() || savingSong;
}

let savingSong = false;
const saveSong = debounce(async () => {
  if (!state.currentSong) return;
  const song = state.currentSong;
  const editsAtSend = songEdits;
  savingSong = true;
  try {
    // Deliberately does NOT replace state.currentSong with the server's
    // response: every input handler in renderSections() closes over the
    // section objects that were on state.currentSong when it rendered, and
    // swapping in a new object graph here would orphan them (the v0.1
    // "section names not saved" bug). Remote updates do re-render, which
    // rebuilds every handler against the new objects -- see onRemoteSong.
    await api("PUT", `/songs/${song.id}`, song);
    refreshListsSoon();
  } catch (err) {
    toast("Couldn't save: " + err.message, "error");
  } finally {
    savingSong = false;
    if (songEdits !== editsAtSend && !saveSong.pending()) saveSong();
  }
}, 400);

function edited() {
  songEdits++;
  renderSummary();
  saveSong();
}

els.songTitle.addEventListener("input", () => {
  state.currentSong.title = els.songTitle.value;
  const entry = state.songs.find((s) => s.id === state.currentSong.id);
  if (entry) entry.title = state.currentSong.title;
  renderSidebar();
  edited();
});

els.songBpm.addEventListener("input", () => {
  const v = parseInt(els.songBpm.value, 10);
  if (!Number.isNaN(v) && v >= 20 && v <= 400) {
    state.currentSong.default_bpm = v;
    renderSongShape();
    preserveFocus(renderSections);
    edited();
  }
});

document.getElementById("new-song-btn").addEventListener("click", () => openQuick());
document.getElementById("empty-quick-btn").addEventListener("click", () => openQuick());

// -- tap tempo in the editor ----------------------------------------------------

const songTap = new window.SSPQuick.TapTempo();
document.getElementById("song-tap").addEventListener("pointerdown", (ev) => {
  ev.preventDefault();
  const bpm = songTap.tap(performance.now());
  ev.currentTarget.textContent = bpm ? `Tap · ${bpm}` : "Tap…";
  if (bpm && state.currentSong) {
    els.songBpm.value = bpm;
    state.currentSong.default_bpm = bpm;
    renderSongShape();
    preserveFocus(renderSections);
    edited();
  }
});

// -- quick add: one song, or a pasted list -------------------------------------

const Quick = window.SSPQuick;
const quickTap = new Quick.TapTempo();

function openQuick(tab) {
  for (const id of ["q-title", "q-bpm", "q-length"]) document.getElementById(id).value = "";
  document.getElementById("q-added").textContent = "";
  document.getElementById("q-tap").textContent = "Tap";
  document.getElementById("q-setlist-name").value = `Set ${new Date().toLocaleDateString()}`;
  showQuickTab(tab || "quick-one");
  openModal("quick-modal");
  setTimeout(() => document.getElementById(tab === "quick-list" ? "q-paste" : "q-title").focus(), 50);
}

function showQuickTab(id) {
  for (const t of document.querySelectorAll("#quick-modal .tab")) t.classList.toggle("active", t.dataset.tab === id);
  for (const p of document.querySelectorAll("#quick-modal .quick-pane")) p.classList.toggle("hidden", p.id !== id);
}

for (const t of document.querySelectorAll("#quick-modal .tab")) t.addEventListener("click", () => showQuickTab(t.dataset.tab));

document.getElementById("q-tap").addEventListener("pointerdown", (ev) => {
  ev.preventDefault();
  const bpm = quickTap.tap(performance.now());
  ev.currentTarget.textContent = bpm ? `Tap · ${bpm}` : "Tap…";
  if (bpm) document.getElementById("q-bpm").value = bpm;
});

async function addQuickSong(plan) {
  const title = document.getElementById("q-title").value.trim();
  if (!title) return document.getElementById("q-title").focus();
  const bpm = parseInt(document.getElementById("q-bpm").value, 10);
  const lengthText = document.getElementById("q-length").value.trim();
  const seconds = Quick.parseLength(lengthText);
  if (lengthText && seconds === null) return toast("Length is minutes:seconds, like 3:45.", "warn");
  if (document.getElementById("q-bpm").value && !(bpm >= 20 && bpm <= 400)) return toast("BPM is 20 to 400.", "warn");
  try {
    const song = await api("POST", "/songs", Quick.quickSong({ title, bpm: bpm || null, seconds }, newId));
    await refreshLists();
    if (plan) {
      closeModal("quick-modal");
      go(`#/song/${song.id}`);
      return;
    }
    document.getElementById("q-added").textContent = `Added "${song.title}" (${song.default_bpm} BPM). Next one?`;
    for (const id of ["q-title", "q-bpm", "q-length"]) document.getElementById(id).value = "";
    document.getElementById("q-tap").textContent = "Tap";
    document.getElementById("q-title").focus();
  } catch (err) {
    toast("Couldn't add it: " + err.message, "error");
  }
}

document.getElementById("quick-one").addEventListener("submit", (ev) => {
  ev.preventDefault();
  addQuickSong(false);
});
document.getElementById("q-add-plan").addEventListener("click", () => addQuickSong(true));

function quickEntries() {
  const byTitle = new Map(state.songs.map((s) => [s.title.trim().toLowerCase(), s]));
  return Quick.parseList(document.getElementById("q-paste").value).map((e) => ({ ...e, existing: byTitle.get(e.title.toLowerCase()) || null }));
}

function renderQuickPreview() {
  const rows = quickEntries();
  const table = document.getElementById("q-preview");
  table.innerHTML = "";
  if (rows.length) {
    const head = el("tr");
    for (const h of ["", "Title", "BPM", "Length", ""]) head.appendChild(el("th", "", h));
    table.appendChild(head);
  }
  rows.forEach((r, i) => {
    const tr = el("tr", r.existing ? "existing" : r.bpm ? "" : "warn");
    tr.appendChild(el("td", "", String(i + 1)));
    tr.appendChild(el("td", "", r.title));
    tr.appendChild(el("td", "", r.existing ? String(r.existing.default_bpm) : r.bpm ? String(r.bpm) : "120?"));
    tr.appendChild(el("td", "", r.existing ? "" : r.seconds ? Timing.fmtDuration(r.seconds * 1000) : "4:00"));
    tr.appendChild(el("td", "", r.existing ? "already here" : r.bpm ? "new" : "new, no tempo found"));
    table.appendChild(tr);
  });
  const fresh = rows.filter((r) => !r.existing).length;
  const btn = document.getElementById("q-list-add");
  btn.disabled = !rows.length;
  const mk = document.getElementById("q-make-setlist").checked;
  btn.textContent = !rows.length ? "Add songs"
    : fresh ? `Add ${fresh} song${fresh === 1 ? "" : "s"}${mk ? " and the setlist" : ""}` : mk ? "Make the setlist" : "Nothing new to add";
  if (!fresh && !mk) btn.disabled = true;
}

document.getElementById("q-paste").addEventListener("input", renderQuickPreview);
document.getElementById("q-make-setlist").addEventListener("change", renderQuickPreview);

document.getElementById("q-list-add").addEventListener("click", async () => {
  const rows = quickEntries();
  const ids = [];
  try {
    for (const r of rows) {
      if (r.existing) ids.push(r.existing.id);
      else ids.push((await api("POST", "/songs", Quick.quickSong(r, newId))).id);
    }
    let setlist = null;
    if (document.getElementById("q-make-setlist").checked) {
      const name = document.getElementById("q-setlist-name").value.trim() || "New Setlist";
      setlist = await api("POST", "/setlists", { name, songs: ids });
    }
    await refreshLists();
    document.getElementById("q-paste").value = "";
    renderQuickPreview();
    closeModal("quick-modal");
    toast(`Added ${rows.filter((r) => !r.existing).length} songs${setlist ? ` and "${setlist.name}"` : ""}`);
    if (setlist) go(`#/setlist/${setlist.id}`);
  } catch (err) {
    toast("Stopped part-way: " + err.message, "error");
    refreshLists().catch(() => {});
  }
});

document.getElementById("delete-song-btn").addEventListener("click", async () => {
  if (!state.currentSong) return;
  if (!confirm(`Delete "${state.currentSong.title}"? This can't be undone.`)) return;
  await api("DELETE", `/songs/${state.currentSong.id}`);
  state.currentSong = null;
  await refreshLists();
  go("#/");
});

document.getElementById("song-live-btn").addEventListener("click", async () => {
  if (!state.currentSong) return;
  await api("POST", "/transport", { action: "cue", song_id: state.currentSong.id });
  go("#/live");
});

document.getElementById("song-wav-btn").addEventListener("click", () => {
  if (!state.currentSong) return;
  location.href = `/api/songs/${state.currentSong.id}/click.wav?${clickQuery()}`;
});

document.getElementById("song-click-settings").addEventListener("click", () => openClickSettings());

// -- click settings + click check (per device) -------------------------------

const CK_FIELDS = ["sound", "subdivision", "channel", "mode", "voice", "volume", "accent", "beat", "sub", "latency"];

function renderClickSettings() {
  const o = metronome.opts;
  for (const f of CK_FIELDS) {
    const input = document.getElementById("ck-" + f);
    const key = f === "latency" ? "latencyMs" : f;
    if (input.type === "checkbox") input.checked = !!o[key];
    else input.value = o[key];
  }
  document.getElementById("ck-keep").checked = prefs.get("keepPlaying", true);
  document.getElementById("ck-awake").checked = prefs.get("keepAwake", true);
  document.getElementById("ck-latency-val").textContent = `${o.latencyMs > 0 ? "+" : ""}${o.latencyMs} ms`;
  renderDiagnostics();
}

function renderDiagnostics() {
  const d = metronome.diagnostics();
  const box = document.getElementById("ck-diag");
  box.innerHTML = "";
  const row = (k, v, bad) => {
    box.appendChild(el("dt", "", k));
    box.appendChild(el("dd", bad ? "bad" : "", v));
  };
  row("Sound engine", d.engine, d.engine !== "running");
  if (d.sampleRate) row("Sample rate", `${d.sampleRate} Hz`);
  if (d.outputLatencyMs !== null) row("Output delay", `${d.outputLatencyMs} ms (already allowed for)`);
  if (d.channels) row("Output", d.channels >= 2 ? "stereo" : "mono: left/right ear not possible here", d.channels < 2);
  if (metronome.opts.voice) row("Spoken count-in", d.voiceLoaded ? "ready" : "loading…", !d.voiceLoaded);
  const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  if ("ontouchend" in document) {
    row("Home-screen app", standalone ? "yes" : "no: Share → Add to Home Screen for full screen", !standalone);
  }
  if (window.SSPLive && state.view === "live") row("Screen stays on", window.SSPLive.awake() ? "yes" : "not yet: tap Start (or set Auto-Lock to Never)");
  if (/iPhone|iPad|Macintosh/.test(navigator.userAgent) && "ontouchend" in document) {
    row("Silent switch", d.silentModeSafe ? "ignored (click plays anyway)" : "may mute the click: check the switch", !d.silentModeSafe);
  }
}

function openClickSettings() {
  const song = state.currentSong || (window.SSPLive && window.SSPLive.song());
  document.getElementById("ck-test-bpm").textContent = song ? song.default_bpm : 120;
  renderClickSettings();
  openModal("click-modal");
}

for (const f of CK_FIELDS) {
  const input = document.getElementById("ck-" + f);
  input.addEventListener(input.tagName === "SELECT" || input.type === "checkbox" ? "change" : "input", () => {
    const key = f === "latency" ? "latencyMs" : f;
    const v = input.type === "checkbox" ? input.checked : input.type === "range" ? parseFloat(input.value) : input.value;
    saveClick({ [key]: v });
    if (key === "voice" && v && metronome.unlocked) metronome.loadVoice();
    renderClickSettings();
    if (window.SSPLive) window.SSPLive.clickChanged();
  });
}

document.getElementById("ck-keep").addEventListener("change", (ev) => prefs.set("keepPlaying", ev.target.checked));
document.getElementById("ck-awake").addEventListener("change", (ev) => {
  prefs.set("keepAwake", ev.target.checked);
  if (window.SSPLive) window.SSPLive.keepAwake(ev.target.checked);
});

document.getElementById("ck-reset").addEventListener("click", () => {
  saveClick({ ...window.SSPAudio.DEFAULTS });
  renderClickSettings();
  if (window.SSPLive) window.SSPLive.clickChanged();
});

// A count-in and two bars, right here: the check for "do I hear it, in
// the right ear, through my splitter?" -- no server run needed.
document.getElementById("ck-test").addEventListener("click", () => {
  const song = state.currentSong || (window.SSPLive && window.SSPLive.song());
  const bpm = song ? song.default_bpm : 120;
  const tl = Timing.build({ default_bpm: bpm, sections: [{ id: "test", label: "Test", order: 0, bars: 2, count_in: { bars: 1, style: "click" } }] });
  startPreview(tl);
  renderDiagnostics();
  setTimeout(renderDiagnostics, 300);
  setTimeout(renderDiagnostics, tl.total_ms + 700);
});

document.getElementById("song-export-btn").addEventListener("click", () => {
  if (!state.currentSong) return;
  location.href = `/api/songs/${state.currentSong.id}/export`;
});

// Paper charts: a PDF made by the server (server/paper.py). Size, colour
// and (for a set) what to print are remembered on this device.
const PRINT_DEFAULTS = { size: "fit", ink: "color", parts: "all" };
let printTarget = null;

function printOptions() {
  return Object.assign({}, PRINT_DEFAULTS, prefs.get("print", {}));
}

function renderPrintChoices() {
  if (!printTarget) return;
  const { kind, id } = printTarget;
  const opts = printOptions();
  document.querySelectorAll("#print-modal .seg").forEach((seg) => {
    for (const b of seg.querySelectorAll("button")) b.classList.toggle("active", b.dataset.v === opts[seg.dataset.opt]);
  });
  document.getElementById("print-parts").classList.toggle("hidden", kind !== "setlist");
  const listOnly = kind === "setlist" && opts.parts === "list";
  const box = document.getElementById("print-options");
  box.innerHTML = "";
  const href = (player, download) => {
    const q = new URLSearchParams({ size: opts.size, ink: opts.ink });
    if (kind === "setlist") q.set("parts", opts.parts);
    if (player) q.set("player", player);
    if (download) q.set("download", "1");
    return `/export/${kind}/${id}?${q}`;
  };
  const add = (label, sub, player) => {
    const row = el("div", "who-option print-row");
    const open = el("a", "print-open");
    open.href = href(player);
    open.target = "_blank";
    open.rel = "noopener";
    open.appendChild(el("strong", "", label));
    open.appendChild(el("span", "", sub));
    open.addEventListener("click", () => closeModal("print-modal"));
    const save = el("a", "print-save", "\u2913");
    save.href = href(player, true);
    save.title = "Download the PDF";
    save.setAttribute("aria-label", `Download the PDF for ${label}`);
    row.appendChild(open);
    row.appendChild(save);
    box.appendChild(row);
  };
  if (listOnly) {
    add("Set list", "The running order on one page, in big type");
    return;
  }
  add("Whole band", "Every hint, with who it's for");
  for (const p of state.band.players) add(p.name, `${p.role}: band-wide hints plus ${p.name}'s own`, p.id);
}

function openPrint(kind, id) {
  printTarget = { kind, id };
  document.getElementById("print-title").textContent = kind === "setlist" ? "Print the set" : "Paper chart";
  document.getElementById("print-note").textContent =
    kind === "setlist"
      ? "Opens a PDF in a new tab: the running order, then one chart per song. Print it from there, or save it."
      : "Opens a PDF in a new tab: print it from there, or save it. The PDF carries the song, so \u21e1 Import reads it back.";
  renderPrintChoices();
  openModal("print-modal");
}

document.querySelectorAll("#print-modal .seg button").forEach((b) => {
  b.addEventListener("click", () => {
    const key = b.closest(".seg").dataset.opt;
    prefs.set("print", Object.assign(printOptions(), { [key]: b.dataset.v }));
    renderPrintChoices();
  });
});

document.getElementById("song-print-btn").addEventListener("click", () => {
  if (state.currentSong) openPrint("song", state.currentSong.id);
});

// -- import ---------------------------------------------------------------

document.getElementById("import-song-btn").addEventListener("click", () => document.getElementById("import-file").click());
document.getElementById("import-file").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  ev.target.value = "";
  if (!file) return;
  try {
    // a song file, or a song's paper chart (its PDF carries the song)
    const pdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
    const song = await api("POST", "/songs/import", undefined, {
      body: file,
      type: pdf ? "application/pdf" : "application/json",
    });
    toast(`Imported "${song.title}"`);
    await refreshLists();
    go(`#/song/${song.id}`);
  } catch (err) {
    toast("Couldn't import that file: " + err.message, "error");
  }
});

// -- preview the click ------------------------------------------------------

function soundForBar(bar) {
  if (bar.count_in && bar.count_in_style === "sticks") return metronome.sound === "tick" ? "wood" : "tick";
  return metronome.sound;
}

function stopPreview() {
  if (!state.previewing) return;
  state.previewing = false;
  metronome.stop();
  clearTimeout(state.previewTimer);
  document.getElementById("song-preview-btn").textContent = "♫ Preview click";
  for (const b of document.querySelectorAll(".preview-section.playing")) b.classList.remove("playing");
}

function startPreview(timeline, button) {
  stopPreview();
  if (!metronome.unlock()) {
    toast("This browser can't play sound.", "warn");
    return;
  }
  const wasEnabled = metronome.enabled;
  metronome.enabled = true;
  state.previewing = true;
  metronome.run(timeline, performance.now() + 250, soundForBar);
  state.previewTimer = setTimeout(() => {
    metronome.enabled = wasEnabled;
    stopPreview();
  }, timeline.total_ms + 600);
  if (button) button.classList.add("playing");
}

document.getElementById("song-preview-btn").addEventListener("click", (ev) => {
  if (state.previewing) return stopPreview();
  const tl = Timing.build(state.currentSong);
  if (!tl.bars.length) return toast("Add a section with some bars first.", "warn");
  startPreview(tl);
  ev.currentTarget.textContent = "■ Stop preview";
});

// -- sections -------------------------------------------------------------

function newSectionLocal(order) {
  return { id: newId(), label: "Section", order, bars: 4, bpm: null, count_in: { bars: 0, style: "none" }, hints: [] };
}

// Clones a section (bars, BPM override, count-in, every hint with a fresh
// id) and inserts the copy straight after the original.
function duplicateSection(song, section) {
  const clone = {
    id: newId(),
    label: section.label,
    order: section.order + 0.5,
    bars: section.bars,
    bpm: section.bpm,
    count_in: { ...section.count_in },
    hints: section.hints.map((h) => ({ ...h, id: newId() })),
  };
  song.sections.push(clone);
  song.sections.sort((a, b) => a.order - b.order).forEach((s, i) => (s.order = i));
}

document.getElementById("add-section-btn").addEventListener("click", () => {
  const song = state.currentSong;
  song.sections.push(newSectionLocal(song.sections.length));
  renderSongShape();
  renderSections();
  edited();
  const cards = els.sectionsList.querySelectorAll(".section-label");
  if (cards.length) {
    cards[cards.length - 1].focus();
    cards[cards.length - 1].select();
  }
});

function effectiveBpm(song, section) {
  return section.bpm || song.default_bpm;
}

function renderSummary() {
  const song = state.currentSong;
  if (!song) return;
  const bars = Timing.songTotalBars(song);
  const n = song.sections.length;
  els.songSummary.textContent = n
    ? `${n} section${n === 1 ? "" : "s"} · ${bars} bars · about ${Timing.fmtDuration(Timing.durationMs(song))} with count-ins`
    : "No sections yet: add the first one below.";
}

function renderSongShape() {
  const song = state.currentSong;
  els.songShape.innerHTML = "";
  const sorted = Timing.sortedSections(song);
  sorted.forEach((section, index) => {
    const color = sectionColor(index);
    const block = el("div", "song-shape-block");
    block.style.flexGrow = String(section.bars);
    block.style.flexBasis = "0";
    block.style.background = hexToRgba(color, 0.28);
    block.style.borderColor = hexToRgba(color, 0.7);
    block.title = `${section.label} -- ${section.bars} bars @ ${effectiveBpm(song, section)} BPM`;
    block.textContent = section.bars >= 2 ? section.label : "";
    block.addEventListener("click", () => {
      const card = els.sectionsList.querySelector(`[data-section-id="${section.id}"]`);
      if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    els.songShape.appendChild(block);
  });
  if (!sorted.length) {
    const empty = el("div", "song-shape-block", "no sections yet");
    empty.style.flexGrow = "1";
    els.songShape.appendChild(empty);
  }
  renderSummary();
}

function renderSections() {
  const song = state.currentSong;
  if (!song) return;
  const template = document.getElementById("section-card-template");
  els.sectionsList.innerHTML = "";
  const sorted = Timing.sortedSections(song);

  sorted.forEach((section, index) => {
    const color = sectionColor(index);
    const node = template.content.cloneNode(true);
    const card = node.querySelector(".section-card");
    card.dataset.sectionId = section.id;
    card.style.borderLeft = `4px solid ${color}`;
    card.querySelector(".section-start").textContent = `bar ${Timing.sectionStartBar(song, section.id)}`;

    const labelInput = node.querySelector(".section-label");
    labelInput.value = section.label;
    labelInput.dataset.focusKey = `${section.id}:label`;
    labelInput.addEventListener("input", () => {
      section.label = labelInput.value;
      renderSongShape();
      edited();
    });

    const barsInput = node.querySelector(".section-bars");
    barsInput.value = section.bars;
    barsInput.dataset.focusKey = `${section.id}:bars`;
    barsInput.addEventListener("input", () => {
      const v = parseInt(barsInput.value, 10);
      if (v >= 1 && v <= 999) {
        section.bars = v;
        renderSongShape();
        // card, not node: by now node (the <template> clone) has been
        // appended and is empty -- its children were moved into the page.
        renderBarGrid(card.querySelector(".section-bar-grid"), section, song, color);
        for (const c of els.sectionsList.querySelectorAll(".section-card")) {
          c.querySelector(".section-start").textContent = `bar ${Timing.sectionStartBar(song, c.dataset.sectionId)}`;
        }
        edited();
      }
    });

    const bpmInput = node.querySelector(".section-bpm");
    bpmInput.value = section.bpm || "";
    bpmInput.placeholder = `(${song.default_bpm})`;
    bpmInput.dataset.focusKey = `${section.id}:bpm`;
    bpmInput.addEventListener("input", () => {
      const v = parseInt(bpmInput.value, 10);
      if (bpmInput.value === "") section.bpm = null;
      else if (v >= 20 && v <= 400) section.bpm = v;
      else return;
      renderSongShape();
      edited();
    });

    const countBars = node.querySelector(".count-in-bars");
    countBars.value = section.count_in.bars;
    countBars.dataset.focusKey = `${section.id}:cibars`;
    countBars.addEventListener("input", () => {
      const v = parseInt(countBars.value, 10);
      section.count_in.bars = Number.isNaN(v) ? 0 : Math.max(0, Math.min(8, v));
      if (section.count_in.bars > 0 && section.count_in.style === "none") {
        section.count_in.style = "click";
        countStyle.value = "click";
      }
      edited();
    });

    const countStyle = node.querySelector(".count-in-style");
    countStyle.value = section.count_in.style;
    countStyle.dataset.focusKey = `${section.id}:cistyle`;
    countStyle.addEventListener("change", () => {
      section.count_in.style = countStyle.value;
      if (countStyle.value !== "none" && !section.count_in.bars) {
        section.count_in.bars = 1;
        countBars.value = 1;
      }
      edited();
    });

    const move = (delta) => {
      const other = sorted[index + delta];
      if (!other) return;
      [section.order, other.order] = [other.order, section.order];
      renderSongShape();
      renderSections();
      edited();
    };
    node.querySelector(".move-up").disabled = index === 0;
    node.querySelector(".move-up").addEventListener("click", () => move(-1));
    node.querySelector(".move-down").disabled = index === sorted.length - 1;
    node.querySelector(".move-down").addEventListener("click", () => move(1));

    node.querySelector(".remove-section").addEventListener("click", () => {
      song.sections = song.sections.filter((s) => s.id !== section.id);
      song.sections.sort((a, b) => a.order - b.order).forEach((s, i) => (s.order = i));
      renderSongShape();
      renderSections();
      edited();
    });

    node.querySelector(".duplicate-section").addEventListener("click", () => {
      duplicateSection(song, section);
      renderSongShape();
      renderSections();
      edited();
    });

    const previewBtn = node.querySelector(".preview-section");
    previewBtn.addEventListener("click", () => {
      if (state.previewing) return stopPreview();
      const full = Timing.build(song, section.id);
      const keep = full.bars.filter((b) => b.section_id === section.id);
      const ci = keep.filter((b) => b.count_in).length;
      const bars = keep.slice(0, ci + Math.min(2, section.bars));
      const last = bars[bars.length - 1];
      startPreview({ bars, total_ms: last.start_ms + last.beat_ms * last.beats }, previewBtn);
    });

    renderBarGrid(node.querySelector(".section-bar-grid"), section, song, color);
    renderHints(node.querySelector(".hint-list"), section);

    node.querySelector(".add-hint").addEventListener("click", () => {
      const hint = { id: newId(), text: "", audio: null, visibility: "all" };
      section.hints.push(hint);
      renderHints(card.querySelector(".hint-list"), section);
      edited();
      const input = card.querySelector(`[data-focus-key="${hint.id}:text"]`);
      if (input) input.focus();
    });

    els.sectionsList.appendChild(node);
  });
}

// -- bar/beat visualization ------------------------------------------
// One small square per bar; each square is a 2x2 dot grid for its beats.

function renderBarGrid(container, section, song, color) {
  container.innerHTML = "";
  const startBar = Timing.sectionStartBar(song, section.id);
  if (section.count_in.style !== "none" && section.count_in.bars > 0) {
    for (let i = 0; i < section.count_in.bars; i++) {
      const sq = el("div", "bar-square count-in");
      sq.title = `count-in (${section.count_in.style})`;
      for (let b = 0; b < 4; b++) sq.appendChild(el("div", "beat-dot"));
      container.appendChild(sq);
    }
    container.appendChild(el("span", "count-in-gap"));
  }
  for (let i = 0; i < section.bars; i++) {
    const square = el("div", "bar-square");
    square.style.background = hexToRgba(color, 0.22);
    square.style.borderColor = hexToRgba(color, 0.55);
    square.title = `bar ${startBar + i}`;
    for (let beat = 0; beat < 4; beat++) {
      const dot = el("div", "beat-dot");
      dot.style.background = color;
      square.appendChild(dot);
    }
    container.appendChild(square);
  }
}

// -- hints -------------------------------------------------------------

const canRecord = () => !!(window.isSecureContext && navigator.mediaDevices && window.MediaRecorder);

function renderHints(container, section) {
  const template = document.getElementById("hint-row-template");
  container.innerHTML = "";
  if (!section.hints.length) {
    container.appendChild(el("li", "hint-empty",
      "No hints yet. Add a note for this section: for the whole band, or aimed at one player."));
  }

  for (const hint of section.hints) {
    const node = template.content.cloneNode(true);
    const row = node.querySelector(".hint-row");
    if (hint.visibility !== "all" && hint.visibility === state.me) row.classList.add("mine");
    const textInput = node.querySelector(".hint-text");
    textInput.value = hint.text;
    textInput.dataset.focusKey = `${hint.id}:text`;
    textInput.addEventListener("input", () => {
      hint.text = textInput.value;
      edited();
    });

    const visSelect = node.querySelector(".hint-visibility");
    visSelect.dataset.focusKey = `${hint.id}:vis`;
    for (const p of state.band.players) {
      const opt = el("option", "", `For ${p.name} (${p.role})`);
      opt.value = p.id;
      visSelect.appendChild(opt);
    }
    visSelect.value = playerById(hint.visibility) ? hint.visibility : "all";
    visSelect.addEventListener("change", () => {
      hint.visibility = visSelect.value;
      row.classList.toggle("mine", hint.visibility !== "all" && hint.visibility === state.me);
      edited();
    });

    const playBtn = node.querySelector(".hint-play");
    const recBtn = node.querySelector(".hint-record");
    const fileInput = node.querySelector(".hint-file");
    const drawClip = () => {
      playBtn.classList.toggle("hidden", !hint.audio);
      recBtn.title = hint.audio ? "Remove the voice memo" : canRecord() ? "Record a short voice memo" : "Attach a voice memo (record one, or pick a file)";
      recBtn.innerHTML = hint.audio ? "&#10005;&#9834;" : "&#127908;";
      recBtn.classList.toggle("has-clip", !!hint.audio);
    };
    drawClip();
    playBtn.addEventListener("click", () => metronome.playClip(`/api/audio/${hint.audio}`));

    const attach = async (blob) => {
      try {
        const type = (blob.type || "audio/webm").split(";")[0];
        const res = await api("POST", "/audio", undefined, { body: blob, type });
        hint.audio = res.ref;
        drawClip();
        edited();
        toast("Voice memo saved");
      } catch (err) {
        toast("Couldn't save the memo: " + err.message, "error");
      }
    };

    recBtn.addEventListener("click", async () => {
      if (hint.audio) {
        hint.audio = null;
        drawClip();
        edited();
        return;
      }
      if (!canRecord()) {
        fileInput.click();
        return;
      }
      if (recBtn._recorder) {
        recBtn._recorder.stop();
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const rec = new MediaRecorder(stream);
        const chunks = [];
        rec.ondataavailable = (e) => chunks.push(e.data);
        rec.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          recBtn._recorder = null;
          recBtn.classList.remove("recording");
          clearTimeout(recBtn._limit);
          attach(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
        };
        rec.start();
        recBtn._recorder = rec;
        recBtn.classList.add("recording");
        recBtn.innerHTML = "&#9632;";
        recBtn.title = "Stop recording";
        recBtn._limit = setTimeout(() => rec.state === "recording" && rec.stop(), 30000);
      } catch (err) {
        fileInput.click(); // no microphone permission -- offer a file instead
      }
    });

    fileInput.addEventListener("change", () => {
      const f = fileInput.files[0];
      fileInput.value = "";
      if (f) attach(f);
    });

    node.querySelector(".remove-hint").addEventListener("click", () => {
      section.hints = section.hints.filter((h) => h.id !== hint.id);
      renderHints(container, section);
      edited();
    });

    container.appendChild(node);
  }
}

// ---------------------------------------------------------------------
// Setlist builder
// ---------------------------------------------------------------------

async function openSetlist(id) {
  const setlist = await api("GET", `/setlists/${id}`);
  state.currentSetlist = setlist;
  showView("setlist");
  if (document.activeElement !== els.setlistName) els.setlistName.value = setlist.name;
  renderSetlistSongs();
  renderSidebar();
}

function renderSetlistSongs() {
  const setlist = state.currentSetlist;
  if (!setlist) return;
  const songsById = Object.fromEntries(state.songs.map((s) => [s.id, s]));
  let total = 0;
  els.setlistSongs.innerHTML = "";
  setlist.songs.forEach((songId, index) => {
    const song = songsById[songId];
    if (song) total += song.duration_ms;
    const li = el("li");
    li.appendChild(el("span", "song-order", String(index + 1)));
    const title = el("span", "setlist-song-title", song ? song.title : "(deleted song)");
    if (song) title.addEventListener("click", () => go(`#/song/${song.id}`));
    li.appendChild(title);
    if (song) li.appendChild(el("span", "item-count", `${song.default_bpm} BPM · ${Timing.fmtDuration(song.duration_ms)}`));
    const mk = (label, tip, fn, disabled) => {
      const b = el("button", "btn-icon", label);
      b.title = tip;
      b.disabled = !!disabled;
      b.addEventListener("click", fn);
      li.appendChild(b);
    };
    const swap = (d) => {
      const j = index + d;
      [setlist.songs[index], setlist.songs[j]] = [setlist.songs[j], setlist.songs[index]];
      renderSetlistSongs();
      saveSetlist();
    };
    mk("↑", "Move up", () => swap(-1), index === 0);
    mk("↓", "Move down", () => swap(1), index === setlist.songs.length - 1);
    mk("−", "Remove from setlist", () => {
      setlist.songs.splice(index, 1);
      renderSetlistSongs();
      saveSetlist();
    });
    li.lastChild.classList.add("danger");
    els.setlistSongs.appendChild(li);
  });
  els.setlistSummary.textContent = setlist.songs.length
    ? `${setlist.songs.length} songs · about ${Timing.fmtDuration(total)} of music`
    : "Empty: add songs from the right.";

  els.setlistAvailable.innerHTML = "";
  for (const song of state.songs) {
    if (setlist.songs.includes(song.id)) continue;
    const li = el("li");
    li.appendChild(el("span", "setlist-song-title", song.title));
    li.appendChild(el("span", "item-count", `${song.default_bpm} BPM · ${Timing.fmtDuration(song.duration_ms)}`));
    const addBtn = el("button", "btn-icon", "+");
    addBtn.title = "Add to setlist";
    addBtn.addEventListener("click", () => {
      setlist.songs.push(song.id);
      renderSetlistSongs();
      saveSetlist();
    });
    li.appendChild(addBtn);
    els.setlistAvailable.appendChild(li);
  }
}

const saveSetlist = debounce(async () => {
  if (!state.currentSetlist) return;
  try {
    // same reasoning as saveSong(): don't swap in the PUT response
    await api("PUT", `/setlists/${state.currentSetlist.id}`, state.currentSetlist);
    refreshListsSoon();
  } catch (err) {
    toast("Couldn't save: " + err.message, "error");
  }
}, 400);

els.setlistName.addEventListener("input", () => {
  state.currentSetlist.name = els.setlistName.value;
  const entry = state.setlists.find((s) => s.id === state.currentSetlist.id);
  if (entry) entry.name = els.setlistName.value;
  renderSidebar();
  saveSetlist();
});

document.getElementById("new-setlist-btn").addEventListener("click", async () => {
  const setlist = await api("POST", "/setlists", { name: "New Setlist", songs: [] });
  await refreshLists();
  go(`#/setlist/${setlist.id}`);
});

document.getElementById("delete-setlist-btn").addEventListener("click", async () => {
  if (!state.currentSetlist) return;
  if (!confirm(`Delete "${state.currentSetlist.name}"? The songs stay; only the list goes.`)) return;
  await api("DELETE", `/setlists/${state.currentSetlist.id}`);
  state.currentSetlist = null;
  await refreshLists();
  go("#/");
});

document.getElementById("setlist-live-btn").addEventListener("click", async () => {
  const sl = state.currentSetlist;
  if (!sl) return;
  const first = sl.songs.find((id) => state.songs.some((s) => s.id === id));
  if (!first) return toast("Add a song to the setlist first.", "warn");
  await api("POST", "/transport", { action: "cue", song_id: first, setlist_id: sl.id });
  go("#/live");
});

document.getElementById("setlist-zip-btn").addEventListener("click", () => {
  if (state.currentSetlist) location.href = `/api/setlists/${state.currentSetlist.id}/clicks.zip?${clickQuery()}`;
});

document.getElementById("setlist-print-btn").addEventListener("click", () => {
  if (state.currentSetlist) openPrint("setlist", state.currentSetlist.id);
});

// ---------------------------------------------------------------------
// Band & players
// ---------------------------------------------------------------------

function openBand() {
  showView("band");
  renderBand();
}

function renderBand() {
  if (document.activeElement !== els.bandName) els.bandName.value = state.band.name;
  els.playerList.innerHTML = "";
  for (const p of state.band.players) {
    const li = el("li", "player-row" + (p.id === state.me ? " mine" : ""));
    const name = el("input", "player-name");
    name.value = p.name;
    name.placeholder = "Name";
    name.dataset.focusKey = `${p.id}:name`;
    name.addEventListener("input", () => {
      p.name = name.value;
      saveBand();
    });
    const role = el("select", "player-role");
    role.dataset.focusKey = `${p.id}:role`;
    for (const r of ROLES) {
      const o = el("option", "", r);
      o.value = r;
      role.appendChild(o);
    }
    role.value = p.role;
    role.addEventListener("change", () => {
      p.role = role.value;
      saveBand();
    });
    const del = el("button", "btn-icon danger", "×");
    del.title = "Remove player (their hints go back to the whole band)";
    del.addEventListener("click", () => {
      if (!confirm(`Remove ${p.name || "this player"}? Hints aimed at them will show for the whole band.`)) return;
      state.band.players = state.band.players.filter((x) => x.id !== p.id);
      if (state.me === p.id) setMe(null);
      renderBand();
      saveBand();
    });
    li.append(name, role, del);
    els.playerList.appendChild(li);
  }
}

const saveBand = debounce(async () => {
  try {
    await api("PUT", "/band", state.band);
  } catch (err) {
    toast("Couldn't save: " + err.message, "error");
  }
}, 400);

els.bandName.addEventListener("input", () => {
  state.band.name = els.bandName.value;
  saveBand();
});

document.getElementById("add-player-btn").addEventListener("click", () => {
  const p = { id: newId(), name: "", role: "Other" };
  state.band.players.push(p);
  renderBand();
  saveBand();
  const input = document.querySelector(`[data-focus-key="${p.id}:name"]`);
  if (input) input.focus();
});

// ---------------------------------------------------------------------
// What other devices do arrives here
// ---------------------------------------------------------------------

function mine(msg) {
  return msg && msg.origin === Sync.clientId;
}

Sync.on("song", (song, msg) => {
  refreshListsSoon();
  if (mine(msg)) return;
  if (state.currentSong && state.currentSong.id === song.id) {
    if (songIsDirty()) return; // we're mid-edit: our save follows and wins (last write wins)
    state.currentSong = song;
    preserveFocus(renderSongView);
    toast(`${nameForClient(msg.origin)} changed this song`);
  }
  if (window.SSPLive) window.SSPLive.songChanged(song);
});

Sync.on("song_deleted", (data, msg) => {
  refreshListsSoon();
  if (state.currentSong && state.currentSong.id === data.id && !mine(msg)) {
    state.currentSong = null;
    toast("This song was deleted on another device.", "warn");
    go("#/");
  }
});

Sync.on("setlist", (setlist, msg) => {
  refreshListsSoon();
  if (mine(msg)) return;
  if (state.currentSetlist && state.currentSetlist.id === setlist.id && !saveSetlist.pending()) {
    state.currentSetlist = setlist;
    preserveFocus(() => {
      if (document.activeElement !== els.setlistName) els.setlistName.value = setlist.name;
      renderSetlistSongs();
    });
  }
});

Sync.on("setlist_deleted", (data, msg) => {
  refreshListsSoon();
  if (state.currentSetlist && state.currentSetlist.id === data.id && !mine(msg)) {
    state.currentSetlist = null;
    toast("This setlist was deleted on another device.", "warn");
    go("#/");
  }
});

Sync.on("band", (band, msg) => {
  if (mine(msg) && state.view === "band") return;
  if (saveBand.pending()) return;
  state.band = band;
  if (state.me && !playerById(state.me)) setMe(null);
  renderWho();
  if (state.view === "band") preserveFocus(renderBand);
  if (state.view === "song") preserveFocus(renderSections);
  if (window.SSPLive) window.SSPLive.refresh();
});

Sync.on("presence", (list) => {
  state.presence = list;
  renderPresence();
});

function renderPresence() {
  const n = state.presence.length;
  const names = state.presence.map((c) => playerName(c.player_id)).filter(Boolean);
  const label = n ? `${n} device${n === 1 ? "" : "s"}` : "";
  const tip = names.length ? names.join(", ") : "";
  for (const id of ["presence-label", "live-presence"]) {
    const e = document.getElementById(id);
    e.textContent = label;
    e.title = tip;
  }
}

Sync.on("status", (ok) => {
  const dot = document.getElementById("connection-status");
  dot.className = "status-dot " + (ok ? "status-ok" : "status-bad");
  dot.title = ok ? "Connected to the server" : "Lost the server: retrying";
  document.getElementById("connection-label").textContent = ok ? "connected" : "reconnecting…";
  document.body.classList.toggle("offline", !ok);
});

// ---------------------------------------------------------------------
// Demo band: the whole server (so every device) switches to a throwaway
// copy of the fictional demo band, and back. Every device reloads.
// ---------------------------------------------------------------------

function renderDemo() {
  const on = !!(state.demo && state.demo.on);
  document.body.classList.toggle("is-demo", on);
  document.getElementById("demo-banner").classList.toggle("hidden", !on);
  document.getElementById("demo-off-btn").classList.toggle("hidden", !(on && state.demo.can_return));
  document.getElementById("demo-on-btn").textContent = on ? "Fresh copy of the demo" : "Try the demo band";
}

async function switchDemo(on) {
  const msg = on
    ? "Switch to the demo band?\n\nEvery connected device switches with you. Your own songs are kept safe and come back with \"Back to my band\"."
    : "Back to your band's own songs? Everything changed in the demo is thrown away, on every connected device.";
  if (!confirm(msg)) return;
  try {
    await api("POST", "/demo", { on });
  } catch (err) {
    toast("Couldn't switch: " + err.message, "error");
  }
}

document.getElementById("demo-on-btn").addEventListener("click", () => switchDemo(true));
document.getElementById("demo-off-btn").addEventListener("click", () => switchDemo(false));

// Someone switched bands: start this page fresh on the new one (stays in
// live view if that's where we were). A half-typed edit is dropped -- it
// belonged to the other band anyway.
Sync.on("reload", () => {
  const keepLive = state.view === "live";
  history.replaceState(null, "", location.pathname + (keepLive ? "#/live" : "#/"));
  location.reload();
});

// after a Wi-Fi blip, catch up on anything missed while away
Sync.on("reconnect", () => {
  loadState(true);
  refreshBundleSoon();
});

// ---------------------------------------------------------------------
// This device's own copy of every song and setlist, refreshed whenever
// something changes while the server is reachable -- what solo mode (and
// a server dropping off mid-gig) plays from.
// ---------------------------------------------------------------------

const bundle = { songs: {}, setlists: {}, at: null };

async function refreshBundle() {
  try {
    const b = await api("GET", "/bundle");
    bundle.songs = Object.fromEntries(b.songs.map((x) => [x.id, x]));
    bundle.setlists = Object.fromEntries(b.setlists.map((x) => [x.id, x]));
    bundle.at = Date.now();
  } catch (err) {
    /* keep the last good copy */
  }
}
const refreshBundleSoon = debounce(refreshBundle, 800);
for (const type of ["song", "song_deleted", "setlist", "setlist_deleted"]) Sync.on(type, () => refreshBundleSoon());

// ---------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------

async function loadState(again) {
  const s = await api("GET", "/state");
  state.band = s.band;
  state.songs = s.songs;
  state.setlists = s.setlists;
  state.presence = s.presence;
  state.transport = s.transport;
  state.demo = s.demo || { on: false, can_return: false };
  renderDemo();
  document.getElementById("version-label").textContent = s.version ? "v" + s.version : "";
  if (state.me && !playerById(state.me)) state.me = null;
  renderSidebar();
  renderPresence();
  if (again) {
    if (state.currentSong && !songIsDirty()) {
      try {
        state.currentSong = await api("GET", `/songs/${state.currentSong.id}`);
        preserveFocus(renderSongView);
      } catch (err) {
        go("#/");
      }
    }
    if (window.SSPLive) window.SSPLive.transport(s.transport);
  }
  return s;
}

async function boot() {
  try {
    await loadState(false);
  } catch (err) {
    console.error(err);
  }
  const linked = parseHash().params.get("player");
  if (linked !== null) state.me = linked && playerById(linked) ? linked : null;
  Sync.playerId = state.me;
  await Sync.syncClock(6);
  Sync.connect();
  if (window.SSPLive) window.SSPLive.transport(state.transport);
  await route();
  refreshBundle();
  const linkedPlayer = parseHash().params.get("player") !== null;
  if (!linkedPlayer && !prefs.get("asked", false) && state.band.players.length) openWho();
}

window.addEventListener("hashchange", route);

window.SSP = {
  state, els, api, prefs, toast, el, go, metronome, sectionColor, hexToRgba, playerById, playerName,
  nameForClient, soundForBar, openWho, renderPresence, openClickSettings, saveClick, openModal, closeModal,
  bundleSong: (id) => bundle.songs[id] || null,
  bundleSetlist: (id) => bundle.setlists[id] || null,
  refreshBundle,
};

window.addEventListener("load", boot);
