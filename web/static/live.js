"use strict";

/*
 * The live, on-stage view (v0.4 player emphasis, v0.5 transport).
 *
 * Every device in live view shows the song the band has cued. When anyone
 * presses Start, the server fixes the moment bar 1 begins and sends the
 * tempo map; from then on this page works out the bar and beat itself,
 * every animation frame, from the shared clock -- so all screens move
 * together without a message per beat -- and its own metronome clicks in
 * time. Stop, or the end of the song, stops every device at once.
 *
 * Hints aimed at this device's player stand out; other players' hints
 * stay one tap away ("Show everyone's hints").
 */

(function () {
  const S = window.SSP;
  const Sync = window.SSPSync;
  const Timing = window.SSPTiming;
  const $ = (id) => document.getElementById(id);
  const metronome = S.metronome;

  const live = {
    visibleNow: false,
    transport: { state: "stopped" },
    song: null,
    setlist: null,
    startSection: null, // chosen start point while stopped
    raf: null,
    lastBar: -2,
    lastBeat: -1,
    lastSection: null,
    showAll: S.prefs.get("showAllHints", false),
    wakeLock: null,
  };

  // -- data ---------------------------------------------------------------

  async function loadCued() {
    const t = live.transport;
    try {
      live.song = t.song_id ? await S.api("GET", `/songs/${t.song_id}`) : null;
    } catch (err) {
      live.song = null;
    }
    try {
      live.setlist = t.setlist_id ? await S.api("GET", `/setlists/${t.setlist_id}`) : null;
    } catch (err) {
      live.setlist = null;
    }
    if (live.song && live.startSection && !live.song.sections.some((s) => s.id === live.startSection)) live.startSection = null;
  }

  function sections() {
    return live.song ? Timing.sortedSections(live.song) : [];
  }

  function hintsFor(section) {
    const me = S.state.me;
    const out = { mine: [], all: [], others: [] };
    for (const h of section.hints || []) {
      if (!(h.text || "").trim() && !h.audio) continue;
      if (h.visibility === "all" || !S.playerById(h.visibility)) out.all.push(h);
      else if (h.visibility === me) out.mine.push(h);
      else out.others.push(h);
    }
    return out;
  }

  // -- static parts (redrawn when the song or setlist changes) --------------

  function renderHeader() {
    const song = live.song;
    $("live-song-title").textContent = song ? song.title : "No song cued";
    $("live-song-meta").textContent = song
      ? `${song.default_bpm} BPM · ${Timing.songTotalBars(song)} bars · ${Timing.fmtDuration(Timing.durationMs(song))}`
      : "";
    const nav = $("live-setlist-nav");
    if (live.setlist) {
      const ids = live.setlist.songs.filter((id) => S.state.songs.some((s) => s.id === id));
      const i = song ? ids.indexOf(song.id) : -1;
      $("live-setlist-pos").textContent = `${live.setlist.name} · ${i + 1}/${ids.length}`;
      $("live-prev").disabled = i <= 0;
      $("live-next").disabled = i < 0 || i >= ids.length - 1;
      nav.classList.remove("hidden");
    } else {
      nav.classList.add("hidden");
    }
  }

  function renderShape() {
    const box = $("live-shape");
    box.innerHTML = "";
    const secs = sections();
    secs.forEach((s, i) => {
      const b = S.el("div", "song-shape-block", s.bars >= 2 ? s.label : "");
      const c = S.sectionColor(i);
      b.style.flexGrow = String(s.bars);
      b.style.flexBasis = "0";
      b.style.background = S.hexToRgba(c, 0.3);
      b.style.borderColor = S.hexToRgba(c, 0.75);
      b.dataset.sectionId = s.id;
      b.addEventListener("click", () => chooseStart(s.id));
      box.appendChild(b);
    });
    const head = S.el("div", "playhead");
    head.id = "live-playhead";
    box.appendChild(head);
  }

  function hintItem(h, kind) {
    const li = S.el("li", `live-hint hint-${kind}`);
    if (kind !== "all") {
      const who = S.playerById(h.visibility);
      li.appendChild(S.el("span", "hint-who", kind === "mine" ? "For you" : who ? who.name : ""));
    }
    li.appendChild(S.el("span", "hint-body", h.text || "(voice memo)"));
    if (h.audio) {
      const b = S.el("button", "btn-icon hint-play-live", "▶");
      b.title = "Play the voice memo";
      b.addEventListener("click", (ev) => {
        ev.stopPropagation();
        metronome.playClip(`/api/audio/${h.audio}`);
      });
      li.appendChild(b);
    }
    return li;
  }

  function hintList(section, compact) {
    const ul = S.el("ul", "live-hint-list");
    const h = hintsFor(section);
    h.mine.forEach((x) => ul.appendChild(hintItem(x, "mine")));
    h.all.forEach((x) => ul.appendChild(hintItem(x, "all")));
    if (live.showAll || !S.state.me) h.others.forEach((x) => ul.appendChild(hintItem(x, "other")));
    else if (h.others.length && !compact) {
      const more = S.el("li", "live-hint hint-more", `+${h.others.length} for other players`);
      more.addEventListener("click", (ev) => {
        ev.stopPropagation();
        setShowAll(true);
      });
      ul.appendChild(more);
    }
    return ul;
  }

  function setShowAll(v) {
    live.showAll = v;
    S.prefs.set("showAllHints", v);
    renderChart();
    renderHintsPanel(true);
  }

  function renderChart() {
    const box = $("live-chart");
    box.innerHTML = "";
    const song = live.song;
    if (!song) {
      box.appendChild(renderPicker());
      return;
    }
    const head = S.el("div", "chart-head");
    head.appendChild(S.el("h3", "", "The song"));
    if (S.state.me) {
      const t = S.el("button", "chip", live.showAll ? "Only my hints" : "Show everyone's hints");
      t.addEventListener("click", () => setShowAll(!live.showAll));
      head.appendChild(t);
    }
    box.appendChild(head);
    let bar = 1;
    sections().forEach((s, i) => {
      const row = S.el("div", "chart-row");
      row.dataset.sectionId = s.id;
      row.style.borderLeftColor = S.sectionColor(i);
      if (live.transport.state !== "running" && (live.startSection || sections()[0].id) === s.id) row.classList.add("start-here");
      const top = S.el("div", "chart-row-top");
      top.appendChild(S.el("span", "chart-label", s.label));
      const bpm = s.bpm || song.default_bpm;
      const ci = s.count_in && s.count_in.style !== "none" && s.count_in.bars ? ` · count-in ${s.count_in.bars} (${s.count_in.style})` : "";
      top.appendChild(S.el("span", "chart-meta", `bar ${bar} · ${s.bars} bar${s.bars === 1 ? "" : "s"} · ${bpm} BPM${s.bpm ? " (change)" : ""}${ci}`));
      top.appendChild(S.el("span", "chart-start-tag", "start here"));
      row.appendChild(top);
      row.appendChild(hintList(s));
      row.addEventListener("click", () => chooseStart(s.id));
      box.appendChild(row);
      bar += s.bars;
    });
  }

  function renderPicker() {
    const wrap = S.el("div", "live-picker");
    wrap.appendChild(S.el("p", "", "Nothing cued yet. Pick a setlist or a song: it goes up on every live screen in the room."));
    const mk = (title, items, onPick) => {
      if (!items.length) return;
      wrap.appendChild(S.el("h3", "", title));
      const ul = S.el("ul", "picker-list");
      for (const it of items) {
        const li = S.el("li", "", it.label);
        li.addEventListener("click", () => onPick(it));
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
    };
    mk("Setlists", S.state.setlists.map((x) => ({ label: x.name, id: x.id })), async (it) => {
      const sl = await S.api("GET", `/setlists/${it.id}`);
      const first = sl.songs.find((id) => S.state.songs.some((s) => s.id === id));
      if (first) S.api("POST", "/transport", { action: "cue", song_id: first, setlist_id: sl.id });
    });
    mk("Songs", S.state.songs.map((x) => ({ label: x.title, id: x.id })), (it) =>
      S.api("POST", "/transport", { action: "cue", song_id: it.id }));
    return wrap;
  }

  function chooseStart(sectionId) {
    if (live.transport.state === "running") return;
    const first = sections()[0];
    live.startSection = first && first.id === sectionId ? null : sectionId;
    renderChart();
    renderIdle();
  }

  // -- the "now" panel ----------------------------------------------------------

  function setBeats(beat, accentCountIn) {
    const dots = $("now-beats").children;
    for (let i = 0; i < dots.length; i++) {
      dots[i].classList.toggle("on", i === beat);
      dots[i].classList.toggle("past", beat >= 0 && i < beat);
      dots[i].classList.toggle("accent", i === 0);
    }
    $("now-beats").classList.toggle("count-in", !!accentCountIn);
  }

  function renderHintsPanel(force, section, nextSection) {
    const box = $("live-hints");
    if (!section) {
      const secs = sections();
      section = secs.find((s) => s.id === live.startSection) || secs[0];
      nextSection = null;
    }
    const key = (section ? section.id : "") + "|" + (nextSection ? nextSection.id : "") + "|" + live.showAll + "|" + S.state.me;
    if (!force && box.dataset.key === key) return;
    box.dataset.key = key;
    box.innerHTML = "";
    if (!section) return;
    const now = S.el("div", "hints-now");
    const h = hintsFor(section);
    const count = h.mine.length + h.all.length + (live.showAll || !S.state.me ? h.others.length : 0);
    const othersHidden = S.state.me && !live.showAll ? h.others.length : 0;
    now.appendChild(S.el("h3", "", count ? `Hints: ${section.label}`
      : othersHidden ? `${section.label}: nothing for you (${othersHidden} for others)` : `${section.label}: no hints`));
    now.appendChild(hintList(section, true));
    box.appendChild(now);
    if (nextSection) {
      const nx = S.el("div", "hints-next");
      const hn = hintsFor(nextSection);
      if (hn.mine.length + hn.all.length) {
        nx.appendChild(S.el("h3", "", `Coming up: ${nextSection.label}`));
        const ul = S.el("ul", "live-hint-list");
        hn.mine.forEach((x) => ul.appendChild(hintItem(x, "mine")));
        hn.all.forEach((x) => ul.appendChild(hintItem(x, "all")));
        nx.appendChild(ul);
        box.appendChild(nx);
      }
    }
  }

  function renderNowBars(section, index, barInSection, countIn) {
    let box = $("now-bars");
    if (!box) {
      box = S.el("div", "now-bars");
      box.id = "now-bars";
      document.querySelector(".now-main").appendChild(box);
    }
    if (!section) {
      box.innerHTML = "";
      return;
    }
    const color = S.sectionColor(index);
    const key = section.id + ":" + section.bars;
    if (box.dataset.key !== key) {
      box.dataset.key = key;
      box.innerHTML = "";
      for (let i = 0; i < section.bars; i++) {
        const sq = S.el("div", "bar-square");
        sq.style.background = S.hexToRgba(color, 0.25);
        sq.style.borderColor = S.hexToRgba(color, 0.6);
        for (let b = 0; b < 4; b++) {
          const d = S.el("div", "beat-dot");
          d.style.background = color;
          sq.appendChild(d);
        }
        box.appendChild(sq);
      }
    }
    const squares = box.children;
    for (let i = 0; i < squares.length; i++) {
      const n = i + 1;
      squares[i].classList.toggle("past", !countIn && n < barInSection);
      squares[i].classList.toggle("current", !countIn && n === barInSection);
      squares[i].classList.toggle("upcoming", countIn || n > barInSection);
    }
  }

  function renderIdle() {
    const song = live.song;
    const panel = $("live-now");
    panel.classList.remove("running", "count-in-now");
    const finished = live.transport.finished;
    if (!song) {
      $("now-kicker").textContent = "Live view";
      $("now-label").textContent = "Nothing cued";
      $("now-sub").textContent = "";
      $("now-next").textContent = "";
      setBeats(-1);
      renderNowBars(null);
      $("live-hints").innerHTML = "";
      return;
    }
    const secs = sections();
    const start = secs.find((s) => s.id === live.startSection) || secs[0];
    $("now-kicker").textContent = finished ? "Finished · ready for the next one" : "Ready";
    $("now-label").textContent = start ? start.label : "(no sections yet)";
    $("now-sub").textContent = start
      ? `${live.startSection ? "starting from bar " + Timing.sectionStartBar(song, start.id) : "from the top"} · ${start.bpm || song.default_bpm} BPM`
      : "Add sections in the editor first.";
    $("now-next").textContent = "Press Start, or tap a section to start there.";
    setBeats(-1);
    renderNowBars(start, start ? secs.indexOf(start) : 0, 0, true);
    renderHintsPanel(true);
    setPlayhead(start ? (Timing.sectionStartBar(song, start.id) - 1) / Math.max(1, Timing.songTotalBars(song)) : 0);
    markChart(null);
  }

  function setPlayhead(frac) {
    const p = $("live-playhead");
    if (p) p.style.left = `${Math.max(0, Math.min(1, frac)) * 100}%`;
  }

  function markChart(sectionId) {
    for (const row of document.querySelectorAll("#live-chart .chart-row")) {
      const on = row.dataset.sectionId === sectionId;
      row.classList.toggle("now", on);
      if (on) row.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    for (const b of document.querySelectorAll("#live-shape .song-shape-block")) b.classList.toggle("now", b.dataset.sectionId === sectionId);
  }

  // -- running ------------------------------------------------------------------

  function frame() {
    live.raf = null;
    const t = live.transport;
    if (t.state !== "running" || !t.timeline) return;
    const elapsed = Sync.serverNow() - t.started_at;
    const tl = t.timeline;
    const idx = Timing.barAt(tl, elapsed);
    const panel = $("live-now");
    if (idx >= tl.bars.length) {
      setBeats(-1);
      return; // the server's "finished" message follows
    }
    if (idx < 0) {
      // Start pressed, first beat not here yet
      const secs = Math.ceil(-elapsed / 1000);
      $("now-kicker").textContent = "Get ready";
      $("now-sub").textContent = `starting in ${secs}…`;
      setBeats(-1);
    } else {
      const bar = tl.bars[idx];
      const beat = Math.min(bar.beats - 1, Math.floor((elapsed - bar.start_ms) / bar.beat_ms));
      if (idx !== live.lastBar) onBar(idx, bar);
      if (beat !== live.lastBeat) {
        live.lastBeat = beat;
        setBeats(beat, bar.count_in);
        if (bar.count_in) $("now-sub").textContent = `${bar.count_in_style === "lead-in" ? "count-in" : bar.count_in_style + " count-in"} · ${beat + 1}`;
      }
      // smooth playhead across the song's bars
      if (bar.song_bar) {
        const frac = (bar.song_bar - 1 + (elapsed - bar.start_ms) / (bar.beat_ms * bar.beats)) / Math.max(1, tl.song_bars);
        setPlayhead(frac);
      }
      panel.classList.toggle("count-in-now", bar.count_in);
    }
    live.raf = requestAnimationFrame(frame);
  }

  function onBar(idx, bar) {
    live.lastBar = idx;
    const tl = live.transport.timeline;
    const secs = sections();
    const section = secs.find((s) => s.id === bar.section_id) || { id: bar.section_id, label: bar.label, bars: bar.section_bars, hints: [] };
    const sIndex = bar.section_index;
    $("now-label").textContent = bar.label;
    $("now-label").style.color = S.sectionColor(sIndex);
    if (bar.count_in) {
      $("now-kicker").textContent = bar.section_bars > 1 ? `Count-in, bar ${bar.bar_in_section} of ${bar.section_bars}, into` : "Count-in into";
    } else {
      $("now-kicker").textContent = "Now";
      $("now-sub").textContent = `bar ${bar.bar_in_section} of ${bar.section_bars} · ${Math.round(bar.bpm)} BPM · song bar ${bar.song_bar}/${tl.song_bars}`;
    }
    // what's next, and how far away
    let j = idx + 1;
    while (j < tl.bars.length && tl.bars[j].section_id === bar.section_id && tl.bars[j].count_in === bar.count_in) j++;
    let nextSection = null;
    if (j < tl.bars.length) {
      const nb = tl.bars[j];
      const away = j - idx;
      nextSection = secs.find((s) => s.id === nb.section_id) || null;
      const tempo = nb.bpm !== bar.bpm ? ` · tempo ${Math.round(nb.bpm)}` : "";
      $("now-next").textContent = nb.section_id === bar.section_id && !nb.count_in
        ? `${nb.label} starts in ${away} bar${away === 1 ? "" : "s"}`
        : `Next: ${nb.label}${nb.count_in ? " (count-in)" : ""} in ${away} bar${away === 1 ? "" : "s"}${tempo}`;
      $("now-next").classList.toggle("soon", away <= 2);
    } else {
      const left = tl.bars.length - idx;
      $("now-next").textContent = `Last ${left === 1 ? "bar" : left + " bars"}`;
      $("now-next").classList.add("soon");
    }
    renderNowBars(section, sIndex, bar.bar_in_section, bar.count_in);
    if (live.lastSection !== bar.section_id) {
      live.lastSection = bar.section_id;
      markChart(bar.section_id);
    }
    renderHintsPanel(false, section, nextSection);
  }

  function startRunning() {
    const t = live.transport;
    live.lastBar = -2;
    live.lastBeat = -1;
    live.lastSection = null;
    $("live-now").classList.add("running");
    $("now-label").textContent = (t.timeline.bars[0] || {}).label || "";
    if (metronome.unlocked && metronome.enabled) metronome.run(t.timeline, Sync.toLocal(t.started_at), S.soundForBar);
    if (!live.raf) live.raf = requestAnimationFrame(frame);
  }

  function stopRunning() {
    metronome.stop();
    if (live.raf) cancelAnimationFrame(live.raf);
    live.raf = null;
    $("now-label").style.color = "";
  }

  // -- controls ---------------------------------------------------------------

  function renderControls() {
    const running = live.transport.state === "running";
    $("live-start").classList.toggle("hidden", running);
    $("live-stop").classList.toggle("hidden", !running);
    $("live-start").disabled = !live.song;
    const d = live.transport.driver;
    $("live-driver").textContent = running && d ? `Started by ${d.client_id === Sync.clientId ? "you" : d.name}` : "";
    renderClick();
  }

  function renderClick() {
    const b = $("click-toggle");
    if (!metronome.unlocked) b.textContent = "🔈 Click: tap to enable";
    else b.textContent = metronome.enabled ? "🔊 Click on" : "🔇 Click off";
    b.classList.toggle("active", metronome.unlocked && metronome.enabled);
    $("live-sound").value = metronome.sound;
    $("live-volume").value = metronome.volume;
  }

  $("click-toggle").addEventListener("click", () => {
    if (!metronome.unlocked) {
      metronome.unlock();
      metronome.enabled = true;
    } else {
      metronome.enabled = !metronome.enabled;
    }
    S.prefs.set("click", metronome.enabled);
    const t = live.transport;
    if (t.state === "running" && metronome.enabled) metronome.run(t.timeline, Sync.toLocal(t.started_at), S.soundForBar);
    if (!metronome.enabled) metronome.stop();
    setTimeout(renderClick, 50);
  });

  $("live-sound").addEventListener("change", (ev) => {
    metronome.sound = ev.target.value;
    S.prefs.set("sound", metronome.sound);
    const t = live.transport;
    if (t.state === "running" && metronome.enabled) metronome.run(t.timeline, Sync.toLocal(t.started_at), S.soundForBar);
  });

  $("live-volume").addEventListener("input", (ev) => {
    metronome.setVolume(parseFloat(ev.target.value));
    S.prefs.set("volume", metronome.volume);
  });

  async function start() {
    if (!live.song) return;
    if (!metronome.unlocked && metronome.enabled) metronome.unlock(); // this tap is our one chance on iOS
    try {
      await S.api("POST", "/transport", {
        action: "start", song_id: live.song.id, setlist_id: live.setlist ? live.setlist.id : null,
        start_section_id: live.startSection,
      });
    } catch (err) {
      S.toast("Couldn't start: " + err.message, "error");
    }
  }

  async function stop() {
    try {
      await S.api("POST", "/transport", { action: "stop" });
    } catch (err) {
      S.toast("Couldn't stop: " + err.message, "error");
    }
  }

  $("live-start").addEventListener("click", start);
  $("live-stop").addEventListener("click", stop);
  $("live-prev").addEventListener("click", () => S.api("POST", "/transport", { action: "prev" }));
  $("live-next").addEventListener("click", () => S.api("POST", "/transport", { action: "next" }));
  $("live-exit").addEventListener("click", () => {
    S.go(live.song ? `#/song/${live.song.id}` : "#/");
  });

  // Space starts/stops; arrows or page keys change song -- which is also
  // what most Bluetooth page-turner pedals send.
  document.addEventListener("keydown", (ev) => {
    if (!live.visibleNow || /INPUT|SELECT|TEXTAREA/.test(ev.target.tagName)) return;
    if (ev.key === " ") {
      ev.preventDefault();
      if (live.transport.state === "running") stop();
      else start();
    } else if ((ev.key === "ArrowRight" || ev.key === "PageDown") && live.setlist && live.transport.state !== "running") {
      S.api("POST", "/transport", { action: "next" });
    } else if ((ev.key === "ArrowLeft" || ev.key === "PageUp") && live.setlist && live.transport.state !== "running") {
      S.api("POST", "/transport", { action: "prev" });
    }
  });

  async function keepAwake(on) {
    try {
      if (on && !live.wakeLock && navigator.wakeLock) live.wakeLock = await navigator.wakeLock.request("screen");
      if (!on && live.wakeLock) {
        await live.wakeLock.release();
        live.wakeLock = null;
      }
    } catch (err) {
      live.wakeLock = null; // only on https/localhost; on plain LAN http the device's own setting rules
    }
  }

  // -- the outside world ----------------------------------------------------------

  async function applyTransport(t) {
    const prevSong = live.transport.song_id;
    const prevRun = live.transport.run;
    const wasRunning = live.transport.state === "running";
    live.transport = t || { state: "stopped" };
    if (live.transport.song_id !== prevSong || !live.song) {
      live.startSection = null;
      await loadCued();
    } else if (live.transport.setlist_id && (!live.setlist || live.setlist.id !== live.transport.setlist_id)) {
      await loadCued();
    } else if (!live.transport.setlist_id) {
      live.setlist = null;
    }
    if (!live.visibleNow) return;
    if (live.transport.song_id !== prevSong) {
      renderHeader();
      renderShape();
      renderChart();
    }
    if (live.transport.state === "running") {
      if (!wasRunning || live.transport.run !== prevRun) {
        renderChart();
        startRunning();
      }
    } else {
      stopRunning();
      if (wasRunning) renderChart();
      renderIdle();
    }
    renderControls();
  }

  Sync.on("transport", (t) => applyTransport(t));
  Sync.on("position", () => {
    /* positions are worked out locally from the shared clock; the server's
       per-bar message is for devices without a clock fix yet. */
  });

  window.SSPLive = {
    async visible(v) {
      live.visibleNow = v;
      keepAwake(v);
      if (!v) {
        stopRunning();
        return;
      }
      if (!live.song && live.transport.song_id) await loadCued();
      renderHeader();
      renderShape();
      renderChart();
      if (live.transport.state === "running") startRunning();
      else renderIdle();
      renderControls();
    },
    transport: applyTransport,
    async refresh() {
      if (!live.visibleNow) return;
      if (live.setlist) {
        try {
          live.setlist = await S.api("GET", `/setlists/${live.setlist.id}`);
        } catch (err) {
          live.setlist = null;
        }
      }
      renderHeader();
      renderChart();
      if (live.transport.state !== "running") renderIdle();
      else {
        live.lastBar = -2;
        renderHintsPanel(true);
      }
      renderControls();
    },
    songChanged(song) {
      if (!live.song || live.song.id !== song.id) return;
      live.song = song;
      if (!live.visibleNow) return;
      renderHeader();
      renderShape();
      renderChart();
      if (live.transport.state !== "running") renderIdle();
      else {
        live.lastBar = -2;
        live.lastSection = null;
      }
    },
  };
})();
