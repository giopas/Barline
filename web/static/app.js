"use strict";

/*
 * Single Song Planner -- v0.1 single-page app.
 *
 * One client at a time in this version (no WebSocket sync yet -- that's
 * v0.3). Drafting controls and the eventual live/player view are meant to
 * be the same app, not separate ones (see PROJECT_CHARTER.md section 10),
 * so this file is written to grow into that rather than be thrown away.
 *
 * No build step: this is loaded directly as a <script>, vanilla JS.
 */

const API = "/api";

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(API + path, opts);
  setConnectionStatus(true);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `${method} ${path} failed (${res.status})`);
  }
  return data;
}

function setConnectionStatus(ok) {
  const dot = document.getElementById("connection-status");
  const label = document.getElementById("connection-label");
  dot.className = "status-dot " + (ok ? "status-ok" : "status-bad");
  label.textContent = ok ? "connected" : "disconnected";
}

// debounce helper -- edits accumulate locally and only hit the server
// (and therefore disk) a short while after the user stops typing.
function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// ---------------------------------------------------------------------
// Section color coding -- one color per section, by its position in the
// song (left-to-right order), reused consistently between the song-shape
// overview strip, the detailed bar/beat grid, and a small swatch on each
// section card, so all three views read as the same picture of the song.
// ---------------------------------------------------------------------

const SECTION_PALETTE = [
  "#5b8cff", // blue
  "#45c08a", // green
  "#e2b93b", // amber
  "#e2574c", // red
  "#b073f0", // purple
  "#39c2c9", // teal
  "#f08a3c", // orange
  "#6fcf97", // mint
];

function sectionColor(index) {
  return SECTION_PALETTE[index % SECTION_PALETTE.length];
}

function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// ---------------------------------------------------------------------
// App state
// ---------------------------------------------------------------------

const state = {
  songs: [],       // sidebar summaries
  setlists: [],    // sidebar summaries
  currentSong: null,     // full song object, or null
  currentSetlist: null,  // full setlist object, or null
};

const els = {
  songList: document.getElementById("song-list"),
  setlistList: document.getElementById("setlist-list"),
  emptyState: document.getElementById("empty-state"),
  songView: document.getElementById("song-view"),
  setlistView: document.getElementById("setlist-view"),
  songTitle: document.getElementById("song-title"),
  songBpm: document.getElementById("song-bpm"),
  songShape: document.getElementById("song-shape"),
  sectionsList: document.getElementById("sections-list"),
  setlistName: document.getElementById("setlist-name"),
  setlistSongs: document.getElementById("setlist-songs"),
  setlistAvailable: document.getElementById("setlist-available"),
};

// ---------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------

async function refreshSidebar() {
  const [songs, setlists] = await Promise.all([api("GET", "/songs"), api("GET", "/setlists")]);
  state.songs = songs;
  state.setlists = setlists;
  renderSidebar();
}

function renderSidebar() {
  els.songList.innerHTML = "";
  for (const song of state.songs) {
    const li = document.createElement("li");
    li.textContent = song.title || "(untitled)";
    const count = document.createElement("span");
    count.className = "item-count";
    count.textContent = `${song.total_bars}b`;
    li.appendChild(count);
    if (state.currentSong && state.currentSong.id === song.id) li.classList.add("active");
    li.addEventListener("click", () => selectSong(song.id));
    els.songList.appendChild(li);
  }

  els.setlistList.innerHTML = "";
  for (const setlist of state.setlists) {
    const li = document.createElement("li");
    li.textContent = setlist.name;
    const count = document.createElement("span");
    count.className = "item-count";
    count.textContent = `${setlist.song_count}`;
    li.appendChild(count);
    if (state.currentSetlist && state.currentSetlist.id === setlist.id) li.classList.add("active");
    li.addEventListener("click", () => selectSetlist(setlist.id));
    els.setlistList.appendChild(li);
  }
}

// ---------------------------------------------------------------------
// View switching
// ---------------------------------------------------------------------

function showEmpty() {
  state.currentSong = null;
  state.currentSetlist = null;
  els.emptyState.classList.remove("hidden");
  els.songView.classList.add("hidden");
  els.setlistView.classList.add("hidden");
  renderSidebar();
}

function showSongView() {
  state.currentSetlist = null;
  els.emptyState.classList.add("hidden");
  els.songView.classList.remove("hidden");
  els.setlistView.classList.add("hidden");
}

function showSetlistView() {
  state.currentSong = null;
  els.emptyState.classList.add("hidden");
  els.songView.classList.add("hidden");
  els.setlistView.classList.remove("hidden");
}

// ---------------------------------------------------------------------
// Song editing -- switching songs is instant (server keeps everything
// in memory; this is just a GET against that in-memory copy).
// ---------------------------------------------------------------------

async function selectSong(id) {
  const song = await api("GET", `/songs/${id}`);
  state.currentSong = song;
  showSongView();
  renderSongView();
  renderSidebar();
}

function renderSongView() {
  const song = state.currentSong;
  els.songTitle.value = song.title;
  els.songBpm.value = song.default_bpm;
  renderSongShape();
  renderSections();
}

const saveSong = debounce(async () => {
  if (!state.currentSong) return;
  const song = state.currentSong;
  try {
    // Deliberately does NOT replace state.currentSong with the server's
    // response. Every input handler in renderSections() closes over the
    // specific section objects that were on state.currentSong at render
    // time; swapping in a new object graph here would silently orphan
    // those closures -- further typing would keep mutating the old,
    // now-unreachable objects while saveSong() kept re-sending whatever
    // state.currentSong still pointed at, so edits would appear in the
    // input boxes but never actually reach the server. (This was the
    // "section names not updated" bug -- the UI only re-renders from
    // state.currentSong after an explicit action like switching songs,
    // so there's no need for the PUT response to feed back into it.)
    await api("PUT", `/songs/${song.id}`, song);
    await refreshSidebar();
  } catch (err) {
    alert("Couldn't save: " + err.message);
  }
}, 400);

els.songTitle.addEventListener("input", () => {
  state.currentSong.title = els.songTitle.value;
  renderSidebarSongTitleOnly();
  saveSong();
});

els.songBpm.addEventListener("input", () => {
  const v = parseInt(els.songBpm.value, 10);
  if (!Number.isNaN(v)) {
    state.currentSong.default_bpm = v;
    renderSongShape();
    renderSections();
    saveSong();
  }
});

function renderSidebarSongTitleOnly() {
  // avoid a full sidebar re-render (and losing focus) on every keystroke
  const entry = state.songs.find((s) => s.id === state.currentSong.id);
  if (entry) entry.title = state.currentSong.title;
  renderSidebar();
  els.songTitle.focus();
}

document.getElementById("new-song-btn").addEventListener("click", async () => {
  const song = await api("POST", "/songs", { title: "Untitled Song", default_bpm: 120 });
  await refreshSidebar();
  selectSong(song.id);
});

document.getElementById("delete-song-btn").addEventListener("click", async () => {
  if (!state.currentSong) return;
  if (!confirm(`Delete "${state.currentSong.title}"? This can't be undone.`)) return;
  await api("DELETE", `/songs/${state.currentSong.id}`);
  await refreshSidebar();
  showEmpty();
});

// -- sections -----------------------------------------------------------

function newId() {
  return "tmp-" + Math.random().toString(36).slice(2, 10);
}

function newSectionLocal(order) {
  return {
    id: newId(),
    label: "Section",
    order,
    bars: 4,
    bpm: null,
    count_in: { bars: 0, style: "none" },
    hints: [],
  };
}

// Clones a section (bars, BPM override, count-in, and every hint, each
// hint getting its own fresh id) and inserts the copy immediately after
// the original -- for repeating a section verbatim (another Chorus,
// another Verse) without retyping it.
function duplicateSection(song, section) {
  const clone = {
    id: newId(),
    label: section.label,
    order: section.order + 0.5, // placed right after the original once reindexed below
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
  const order = song.sections.length;
  song.sections.push(newSectionLocal(order));
  renderSongShape();
  renderSections();
  saveSong();
});

function sectionStartBar(song, sectionId) {
  let bar = 1;
  for (const s of [...song.sections].sort((a, b) => a.order - b.order)) {
    if (s.id === sectionId) return bar;
    bar += s.bars;
  }
  return bar;
}

function songTotalBars(song) {
  return song.sections.reduce((sum, s) => sum + s.bars, 0);
}

function effectiveBpm(song, section) {
  return section.bpm || song.default_bpm;
}

function renderSongShape() {
  const song = state.currentSong;
  els.songShape.innerHTML = "";
  const sorted = [...song.sections].sort((a, b) => a.order - b.order);
  sorted.forEach((section, index) => {
    const color = sectionColor(index);
    const block = document.createElement("div");
    block.className = "song-shape-block";
    block.style.flexGrow = String(section.bars);
    block.style.flexBasis = "0";
    block.style.background = hexToRgba(color, 0.28);
    block.style.borderColor = hexToRgba(color, 0.7);
    block.title = `${section.label} -- ${section.bars} bars @ ${effectiveBpm(song, section)} BPM`;
    block.textContent = section.bars >= 2 ? section.label : "";
    els.songShape.appendChild(block);
  });
  if (song.sections.length === 0) {
    const empty = document.createElement("div");
    empty.className = "song-shape-block";
    empty.style.flexGrow = "1";
    empty.textContent = "no sections yet";
    els.songShape.appendChild(empty);
  }
}

function renderSections() {
  const song = state.currentSong;
  const template = document.getElementById("section-card-template");
  els.sectionsList.innerHTML = "";
  const sorted = [...song.sections].sort((a, b) => a.order - b.order);

  sorted.forEach((section, index) => {
    const color = sectionColor(index);
    const node = template.content.cloneNode(true);
    const card = node.querySelector(".section-card");
    card.dataset.sectionId = section.id;
    card.style.borderLeft = `4px solid ${color}`;

    const labelInput = node.querySelector(".section-label");
    labelInput.value = section.label;
    labelInput.addEventListener("input", () => {
      section.label = labelInput.value;
      renderSongShape();
      saveSong();
    });

    const barsInput = node.querySelector(".section-bars");
    barsInput.value = section.bars;
    barsInput.addEventListener("input", () => {
      const v = parseInt(barsInput.value, 10);
      if (v >= 1) {
        section.bars = v;
        renderSongShape();
        // Use card.querySelector, not node.querySelector: by the time this
        // handler fires, node (the cloned <template> fragment) has already
        // been appended to the document and is now empty -- its children,
        // card included, were moved into the live DOM, not copied. card
        // itself is one of those moved children, so it's still valid.
        renderBarGrid(card.querySelector(".section-bar-grid"), section, song, color);
        saveSong();
      }
    });

    const bpmInput = node.querySelector(".section-bpm");
    bpmInput.value = section.bpm || "";
    bpmInput.addEventListener("input", () => {
      const v = parseInt(bpmInput.value, 10);
      section.bpm = Number.isNaN(v) ? null : v;
      renderSongShape();
      saveSong();
    });

    const countBars = node.querySelector(".count-in-bars");
    countBars.value = section.count_in.bars;
    countBars.addEventListener("input", () => {
      const v = parseInt(countBars.value, 10);
      section.count_in.bars = Number.isNaN(v) ? 0 : v;
      saveSong();
    });

    const countStyle = node.querySelector(".count-in-style");
    countStyle.value = section.count_in.style;
    countStyle.addEventListener("change", () => {
      section.count_in.style = countStyle.value;
      saveSong();
    });

    node.querySelector(".move-up").disabled = index === 0;
    node.querySelector(".move-up").addEventListener("click", () => {
      if (index === 0) return;
      const prev = sorted[index - 1];
      [section.order, prev.order] = [prev.order, section.order];
      renderSongShape();
      renderSections();
      saveSong();
    });

    node.querySelector(".move-down").disabled = index === sorted.length - 1;
    node.querySelector(".move-down").addEventListener("click", () => {
      if (index === sorted.length - 1) return;
      const next = sorted[index + 1];
      [section.order, next.order] = [next.order, section.order];
      renderSongShape();
      renderSections();
      saveSong();
    });

    node.querySelector(".remove-section").addEventListener("click", () => {
      song.sections = song.sections.filter((s) => s.id !== section.id);
      // keep order contiguous
      song.sections.sort((a, b) => a.order - b.order).forEach((s, i) => (s.order = i));
      renderSongShape();
      renderSections();
      saveSong();
    });

    node.querySelector(".duplicate-section").addEventListener("click", () => {
      duplicateSection(song, section);
      renderSongShape();
      renderSections();
      saveSong();
    });

    renderBarGrid(node.querySelector(".section-bar-grid"), section, song, color);
    renderHints(node.querySelector(".hint-list"), section);

    node.querySelector(".add-hint").addEventListener("click", () => {
      section.hints.push({ id: newId(), text: "", audio: null, visibility: "all" });
      renderHints(card.querySelector(".hint-list"), section); // see comment on the bars handler above
      saveSong();
    });

    els.sectionsList.appendChild(node);
  });
}

// -- bar/beat visualization ------------------------------------------
// One small square per bar; each square is a 2x2 dot grid for its beats
// (4/4 assumed for v0.1 -- see wishlist for other time signatures).

function renderBarGrid(container, section, song, color) {
  container.innerHTML = "";
  const startBar = sectionStartBar(song, section.id);
  for (let i = 0; i < section.bars; i++) {
    const square = document.createElement("div");
    square.className = "bar-square";
    square.style.background = hexToRgba(color, 0.22);
    square.style.borderColor = hexToRgba(color, 0.55);
    square.title = `bar ${startBar + i}`;
    for (let beat = 0; beat < 4; beat++) {
      const dot = document.createElement("div");
      dot.className = "beat-dot";
      dot.style.background = color;
      square.appendChild(dot);
    }
    container.appendChild(square);
  }
}

// -- hints -------------------------------------------------------------

function renderHints(container, section) {
  const template = document.getElementById("hint-row-template");
  container.innerHTML = "";
  const players = state.currentBand ? state.currentBand.players : [];

  for (const hint of section.hints) {
    const node = template.content.cloneNode(true);
    const textInput = node.querySelector(".hint-text");
    textInput.value = hint.text;
    textInput.addEventListener("input", () => {
      hint.text = textInput.value;
      saveSong();
    });

    const visSelect = node.querySelector(".hint-visibility");
    for (const p of players) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      visSelect.appendChild(opt);
    }
    visSelect.value = hint.visibility;
    visSelect.addEventListener("change", () => {
      hint.visibility = visSelect.value;
      saveSong();
    });

    node.querySelector(".remove-hint").addEventListener("click", () => {
      section.hints = section.hints.filter((h) => h.id !== hint.id);
      renderHints(container, section);
      saveSong();
    });

    container.appendChild(node);
  }
}

// ---------------------------------------------------------------------
// Setlist builder
// ---------------------------------------------------------------------

async function selectSetlist(id) {
  const setlist = await api("GET", `/setlists/${id}`);
  state.currentSetlist = setlist;
  showSetlistView();
  renderSetlistView();
  renderSidebar();
}

function renderSetlistView() {
  const setlist = state.currentSetlist;
  els.setlistName.value = setlist.name;
  renderSetlistSongs();
}

function renderSetlistSongs() {
  const setlist = state.currentSetlist;
  const songsById = Object.fromEntries(state.songs.map((s) => [s.id, s]));

  els.setlistSongs.innerHTML = "";
  setlist.songs.forEach((songId, index) => {
    const song = songsById[songId];
    const li = document.createElement("li");
    const order = document.createElement("span");
    order.className = "song-order";
    order.textContent = String(index + 1);
    li.appendChild(order);
    const title = document.createElement("span");
    title.textContent = song ? song.title : "(deleted song)";
    title.style.flex = "1";
    li.appendChild(title);

    const removeBtn = document.createElement("button");
    removeBtn.className = "btn-icon danger";
    removeBtn.textContent = "−";
    removeBtn.title = "Remove from setlist";
    removeBtn.addEventListener("click", () => {
      setlist.songs.splice(index, 1);
      renderSetlistSongs();
      saveSetlist();
    });
    li.appendChild(removeBtn);
    els.setlistSongs.appendChild(li);
  });

  els.setlistAvailable.innerHTML = "";
  for (const song of state.songs) {
    if (setlist.songs.includes(song.id)) continue;
    const li = document.createElement("li");
    const title = document.createElement("span");
    title.textContent = song.title;
    title.style.flex = "1";
    li.appendChild(title);
    const addBtn = document.createElement("button");
    addBtn.className = "btn-icon";
    addBtn.textContent = "+";
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
  const setlist = state.currentSetlist;
  try {
    // See the comment in saveSong() -- same reasoning, same fix: don't
    // replace state.currentSetlist with the PUT response.
    await api("PUT", `/setlists/${setlist.id}`, setlist);
    await refreshSidebar();
  } catch (err) {
    alert("Couldn't save: " + err.message);
  }
}, 400);

els.setlistName.addEventListener("input", () => {
  state.currentSetlist.name = els.setlistName.value;
  const entry = state.setlists.find((s) => s.id === state.currentSetlist.id);
  if (entry) entry.name = els.setlistName.value;
  renderSidebar();
  els.setlistName.focus();
  saveSetlist();
});

document.getElementById("new-setlist-btn").addEventListener("click", async () => {
  const setlist = await api("POST", "/setlists", { name: "New Setlist", songs: [] });
  await refreshSidebar();
  selectSetlist(setlist.id);
});

document.getElementById("delete-setlist-btn").addEventListener("click", async () => {
  if (!state.currentSetlist) return;
  if (!confirm(`Delete "${state.currentSetlist.name}"? This can't be undone.`)) return;
  await api("DELETE", `/setlists/${state.currentSetlist.id}`);
  await refreshSidebar();
  showEmpty();
});

// ---------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------

async function boot() {
  try {
    state.currentBand = await api("GET", "/band");
    await refreshSidebar();
  } catch (err) {
    setConnectionStatus(false);
    console.error(err);
  }
}

boot();
