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
  const S = window.Barline;
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
    big: S.prefs.get("bigView", null), // null: not chosen yet -> on for drummers
    wakeLock: null,
  };

  // -- data ---------------------------------------------------------------
  // In solo mode songs come from this device's copy (S.bundle, kept fresh
  // while the server is reachable), so it keeps working without one.

  async function getSong(id) {
    if (live.solo) {
      const s = S.bundleSong(id);
      if (!s) throw new Error("not on this device");
      return s;
    }
    return S.api("GET", `/songs/${id}`);
  }

  async function getSetlist(id) {
    if (live.solo) {
      const s = S.bundleSetlist(id);
      if (!s) throw new Error("not on this device");
      return s;
    }
    return S.api("GET", `/setlists/${id}`);
  }

  async function loadCued() {
    const t = live.transport;
    try {
      live.song = t.song_id ? await getSong(t.song_id) : null;
    } catch (err) {
      live.song = null;
    }
    try {
      live.setlist = t.setlist_id ? await getSetlist(t.setlist_id) : null;
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

  // -- solo: this device runs its own transport ------------------------------
  // Same shape and rules as server/transport.py (cue, start with a lead
  // time, stop, next/prev, end of song cues the next one in the setlist),
  // but on this device's clock only. Used when the drummer practises alone,
  // or automatically when the server drops off mid-song.

  const JUMP_LEAD_MS = 450; // server/transport.py JUMP_LEAD_MS

  const solo = {
    run: 0,
    timer: null,
    state: { state: "stopped", song_id: null, setlist_id: null, start_section_id: null, started_at: null, timeline: null, driver: null, run: 0 },
    publish(extra) {
      applyTransport({ ...this.state, ...(extra || {}) });
    },
    stopLocked() {
      clearTimeout(this.timer);
      this.timer = null;
      Object.assign(this.state, { state: "stopped", started_at: null, timeline: null, driver: null });
    },
    songsOf(setlistId) {
      const sl = S.bundleSetlist(setlistId);
      return sl ? sl.songs.filter((id) => S.bundleSong(id)) : [];
    },
    cue(songId, setlistId) {
      this.stopLocked();
      Object.assign(this.state, { song_id: songId || null, setlist_id: setlistId || null, start_section_id: null });
      this.publish();
    },
    start(body) {
      const songId = body.song_id || this.state.song_id;
      const song = songId && S.bundleSong(songId);
      if (!song) throw new Error("that song isn't on this device");
      const tl = Timing.build(song, body.start_section_id);
      if (!tl.bars.length) throw new Error("this song has no bars to play yet");
      this.stopLocked();
      this.run += 1;
      this.state = {
        state: "running", song_id: songId, setlist_id: body.setlist_id !== undefined ? body.setlist_id : this.state.setlist_id,
        start_section_id: body.start_section_id || null, started_at: Sync.serverNow() + 1500, timeline: tl,
        driver: { client_id: Sync.clientId, name: "you" }, run: "solo-" + this.run, rev: 0, moved: null,
      };
      this.arm();
      this.publish();
    },
    // finish at the end of the timeline (also used to adopt a server run)
    arm() {
      clearTimeout(this.timer);
      const t = this.state;
      const left = t.started_at + t.timeline.total_ms - Sync.serverNow();
      const run = t.run;
      this.timer = setTimeout(() => this.finish(run), Math.max(0, left) + 50);
    },
    finish(run) {
      if (this.state.run !== run) return;
      const { song_id: songId, setlist_id: setlistId } = this.state;
      this.stopLocked();
      const ids = setlistId ? this.songsOf(setlistId) : [];
      const i = ids.indexOf(songId);
      if (i >= 0 && i + 1 < ids.length) this.state.song_id = ids[i + 1];
      this.state.start_section_id = null;
      this.publish({ finished: true });
    },
    // same rules as Transport.jump / .nudge in server/transport.py
    jump(body) {
      const t = this.state;
      if (t.state !== "running") throw new Error("nothing is playing");
      const song = S.bundleSong(t.song_id) || live.song;
      const now = Sync.serverNow();
      if (now < t.started_at + JUMP_LEAD_MS) {
        return this.start({ song_id: t.song_id, setlist_id: t.setlist_id, start_section_id: body.section_id });
      }
      const tl = Timing.build(song, body.section_id, false, false);
      if (!tl.bars.length) throw new Error("that section has no bars");
      const land = t.started_at + Timing.nextBoundary(t.timeline, now - t.started_at + JUMP_LEAD_MS);
      Object.assign(t, {
        timeline: tl, started_at: land, start_section_id: body.section_id, rev: (t.rev || 0) + 1,
        moved: { kind: "jump", by: "you", client_id: Sync.clientId, label: tl.bars[0].label, ms: null },
      });
      this.arm();
      this.publish();
    },
    nudge(body) {
      const t = this.state;
      if (t.state !== "running") throw new Error("nothing is playing");
      const ms = Math.max(-10000, Math.min(10000, Number(body.ms) || 0));
      t.started_at -= ms;
      t.rev = (t.rev || 0) + 1;
      t.moved = { kind: "nudge", by: "you", client_id: Sync.clientId, label: null, ms };
      this.arm();
      this.publish();
    },
    step(dir) {
      const ids = this.songsOf(this.state.setlist_id);
      if (!ids.length) return;
      const i = ids.indexOf(this.state.song_id);
      this.cue(ids[Math.max(0, Math.min(ids.length - 1, i + dir))], this.state.setlist_id);
    },
    command(body) {
      if (body.action === "cue") return this.cue(body.song_id, body.setlist_id);
      if (body.action === "start") return this.start(body);
      if (body.action === "stop") {
        this.stopLocked();
        return this.publish();
      }
      if (body.action === "next" || body.action === "prev") return this.step(body.action === "next" ? 1 : -1);
      if (body.action === "jump") return this.jump(body);
      if (body.action === "nudge") return this.nudge(body);
      return null;
    },
  };

  // Pocket (0.18): no server, so the live view always plays on this device,
  // and the app's own transport calls (Go live) land here.
  if (window.BarlinePocket) {
    live.solo = true;
    live.soloWhy = "pocket";
    document.body.classList.add("is-solo");
  }

  // Every transport button goes through here: to the server, or to this
  // device's own transport in solo mode.
  async function command(body) {
    if (live.solo) return solo.command(body);
    return S.api("POST", "/transport", body);
  }

  // Switch solo on (taking over whatever is cued or running right now, so a
  // song in progress plays on) or off (back to the band's shared run).
  async function setSolo(on, why) {
    if (on === live.solo) return;
    live.solo = on;
    live.soloWhy = on ? why || "chosen" : null;
    document.body.classList.toggle("is-solo", on);
    if (on) {
      const t = live.transport;
      solo.stopLocked();
      solo.state = { ...solo.state, song_id: t.song_id || null, setlist_id: t.setlist_id || null, start_section_id: t.start_section_id || null };
      if (t.state === "running" && t.timeline) {
        Object.assign(solo.state, { state: "running", started_at: t.started_at, timeline: t.timeline, driver: t.driver, run: t.run, rev: t.rev || 0 });
        solo.arm();
      }
      live.lostClock = false;
      renderSolo();
      renderControls();
      return;
    }
    solo.stopLocked();
    renderSolo();
    try {
      await applyTransport(await S.api("GET", "/transport"));
      live.lastHeard = performance.now();
    } catch (err) {
      S.toast("The server is still out of reach.", "warn");
      live.solo = true;
      live.soloWhy = "lost";
      document.body.classList.add("is-solo");
      renderSolo();
    }
  }

  function renderSolo() {
    const b = $("live-solo");
    b.textContent = live.solo ? "Solo: this device only" : "With the band";
    b.classList.toggle("active", live.solo);
    b.title = live.solo
      ? "Start/stop here only affects this device. Tap to rejoin the band."
      : "Tap to play on your own (practice, or no server): Start/Stop only affect this device.";
    const note = $("live-solo-note");
    if (live.solo && live.soloWhy === "lost") {
      note.textContent = Sync.connected
        ? "The server is back. You'll rejoin the band when this song stops."
        : "Server out of reach: playing on, on this device only.";
      note.classList.remove("hidden");
    } else {
      note.classList.add("hidden");
    }
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
    if (h.author) li.appendChild(S.el("span", "hint-by", window.BarlineFiles.authorLabel(h.author, S.state.band)));
    if (h.audio) {
      const b = S.el("button", "btn-icon hint-play-live", "▶");
      b.title = "Play the voice memo";
      b.addEventListener("click", (ev) => {
        ev.stopPropagation();
        metronome.playClip(S.clipUrl(h.audio));
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
    $("live-view").classList.toggle("nothing-cued", !song);
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
      const jb = S.el("button", "btn-small chart-jump", "\u2935 Jump here");
      jb.title = "Carry on from this section, from the next bar line";
      jb.addEventListener("click", (ev) => {
        ev.stopPropagation();
        jumpTo(s.id);
      });
      top.appendChild(jb);
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
      const sl = await getSetlist(it.id);
      const first = sl.songs.find((id) => S.state.songs.some((s) => s.id === id));
      if (first) command({ action: "cue", song_id: first, setlist_id: sl.id });
    });
    mk("Songs", S.state.songs.map((x) => ({ label: x.title, id: x.id })), (it) =>
      command({ action: "cue", song_id: it.id }));
    return wrap;
  }

  function chooseStart(sectionId) {
    if (live.transport.state === "running") return armJump(sectionId);
    const first = sections()[0];
    live.startSection = first && first.id === sectionId ? null : sectionId;
    renderChart();
    renderIdle();
  }

  // -- 0.16: jump to a section while playing, nudge the click ----------------
  // Tapping a section of the chart while the band plays arms it (a "Jump
  // here" button shows on that row for a few seconds) -- two taps, so a
  // stray touch on stage never moves anybody. The Jump button opens the
  // same choice as a sheet, which also works on phones and in big view.

  function armJump(sectionId) {
    live.armed = live.armed === sectionId ? null : sectionId;
    clearTimeout(live.armTimer);
    if (live.armed) live.armTimer = setTimeout(() => armJump(null), 4000);
    if (!sectionId) live.armed = null;
    for (const row of document.querySelectorAll("#live-chart .chart-row")) {
      row.classList.toggle("jump-armed", row.dataset.sectionId === live.armed);
    }
  }

  async function jumpTo(sectionId) {
    armJump(null);
    closeJump();
    try {
      await command({ action: "jump", section_id: sectionId });
    } catch (err) {
      S.toast("Couldn't jump: " + err.message, "error");
    }
  }

  // the current bar's beat and bar length, for "1 beat"/"1 bar" nudges
  function currentBar() {
    const t = live.transport;
    if (!t.timeline || !t.timeline.bars.length) return null;
    const idx = Timing.barAt(t.timeline, Sync.serverNow() - t.started_at);
    return t.timeline.bars[Math.max(0, Math.min(t.timeline.bars.length - 1, idx))];
  }

  async function nudge(kind) {
    if (live.transport.state !== "running") return;
    const bar = currentBar();
    if (!bar) return;
    const sign = String(kind).startsWith("-") ? -1 : 1;
    const k = String(kind).replace(/^-/, "");
    const ms = k === "beat" ? bar.beat_ms : k === "bar" ? bar.beat_ms * bar.beats : Number(k);
    try {
      await command({ action: "nudge", ms: sign * ms });
    } catch (err) {
      S.toast("Couldn't move the click: " + err.message, "error");
    }
  }

  function renderJump() {
    const box = $("live-jump-list");
    box.innerHTML = "";
    const song = live.song;
    if (!song) return;
    const cur = currentBar();
    let bar = 1;
    sections().forEach((s, i) => {
      const b = S.el("button", "jump-to", s.label);
      b.style.borderLeftColor = S.sectionColor(i);
      b.appendChild(S.el("small", "", `bar ${bar} · ${s.bars} bar${s.bars === 1 ? "" : "s"}`));
      if (cur && cur.section_id === s.id) b.classList.add("now");
      b.addEventListener("click", () => jumpTo(s.id));
      box.appendChild(b);
      bar += s.bars;
    });
  }

  function openJump() {
    renderJump();
    $("live-jump").classList.remove("hidden");
  }

  function closeJump() {
    $("live-jump").classList.add("hidden");
  }

  $("live-jump-btn").addEventListener("click", () => {
    if ($("live-jump").classList.contains("hidden")) openJump();
    else closeJump();
  });
  $("live-jump-close").addEventListener("click", closeJump);
  for (const b of document.querySelectorAll("#live-nudge [data-nudge]")) {
    b.addEventListener("click", () => nudge(b.dataset.nudge));
  }

  // someone (maybe us) jumped or nudged: same run, new clock or timeline
  function moved() {
    const t = live.transport;
    live.lastBar = -2;
    live.lastBeat = -1;
    live.lastSection = null;
    renderChart();
    if (!$("live-jump").classList.contains("hidden")) renderJump();
    clickOn();
    const m = t.moved;
    if (!m) return;
    const who = m.client_id === Sync.clientId ? "" : `${m.by || "Someone"}: `;
    if (m.kind === "jump") S.toast(`${who}jump to ${m.label}`);
    else if (m.kind === "nudge") S.toast(`${who}click ${m.ms > 0 ? "ahead" : "back"} ${Math.round(Math.abs(m.ms))} ms`);
  }

  // -- drummer ("big") view ------------------------------------------------------
  // Tempo, where you are in the section and what's coming, readable from
  // the drum stool. On by default when this device belongs to a drummer.

  function bigOn() {
    if (live.big !== null) return live.big;
    const p = S.playerById(S.state.me);
    return !!(p && p.role === "Drums");
  }

  function renderBig() {
    const on = bigOn();
    $("live-view").classList.toggle("big", on);
    $("live-big").classList.toggle("active", on);
  }

  $("live-big").addEventListener("click", () => {
    live.big = !bigOn();
    S.prefs.set("bigView", live.big);
    renderBig();
  });

  function setStats(bpm, bar, barKey, next, nextKey, soon) {
    $("st-bpm").textContent = bpm;
    $("st-bar").textContent = bar;
    $("st-bar-k").textContent = barKey;
    $("st-next").textContent = next;
    $("st-next-k").textContent = nextKey;
    $("now-stats").classList.toggle("soon", !!soon);
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
    const head = S.el("div", "hints-now-head");
    head.appendChild(S.el("h3", "", count ? `Hints: ${section.label}`
      : othersHidden ? `${section.label}: nothing for you (${othersHidden} for others)` : `${section.label}: no hints`));
    const add = S.el("button", "btn-small", "+ Hint");
    add.title = `Add a hint to ${section.label}`;
    add.addEventListener("click", () => openQuickHint(section));
    head.appendChild(add);
    now.appendChild(head);
    now.appendChild(hintList(section, true));
    // a hint being typed survives the panel moving on to the next section
    if (live.quickForm) now.appendChild(live.quickForm);
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

  // Jot a hint from the stage view: it's saved to the song for everyone,
  // on the section it was opened for (even if the band has moved on).
  function openQuickHint(section) {
    if (live.quickForm) live.quickForm.remove();
    const form = S.el("form", "quick-hint");
    const input = S.el("input");
    input.placeholder = `Hint for ${section.label}`;
    input.maxLength = 200;
    const who = S.el("select");
    const all = S.el("option", "", "For the whole band");
    all.value = "all";
    who.appendChild(all);
    for (const p of S.state.band.players) {
      const o = S.el("option", "", `For ${p.name}`);
      o.value = p.id;
      who.appendChild(o);
    }
    const save = S.el("button", "btn-small", "Add");
    save.type = "submit";
    const cancel = S.el("button", "btn-small", "Cancel");
    cancel.type = "button";
    const close = () => {
      form.remove();
      live.quickForm = null;
    };
    cancel.addEventListener("click", close);
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const text = input.value.trim();
      if (!text || !live.song) return;
      try {
        const song = await S.api("GET", `/songs/${live.song.id}`);
        const target = song.sections.find((x) => x.id === section.id);
        if (!target) throw new Error("that section is gone");
        const a = new Uint8Array(6);
        crypto.getRandomValues(a);
        const id = Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
        target.hints.push({ id, text, audio: null, visibility: who.value });
        await S.api("PUT", `/songs/${song.id}`, song);
        live.song = song;
        close();
        renderChart();
        renderHintsPanel(true);
        S.toast(`Hint added to ${section.label}`);
      } catch (err) {
        S.toast("Couldn't add the hint: " + err.message, "error");
      }
    });
    form.append(input, who, save, cancel);
    live.quickForm = form;
    renderHintsPanel(true, live.transport.state === "running" ? section : null);
    input.focus();
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
      setStats("–", "–", "bar", "–", "next");
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
    if (start) {
      const left = Timing.build(song, start.id).total_ms;
      setStats(String(start.bpm || song.default_bpm), String(start.bars), `bars of ${start.label}`,
        Timing.fmtDuration(left), live.startSection ? "to the end" : "song length");
    } else setStats("–", "–", "bar", "–", "next");
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
    {
      const nb = j < tl.bars.length ? tl.bars[j] : null;
      const away = nb ? j - idx : tl.bars.length - idx;
      const tempo = nb && nb.bpm !== bar.bpm ? ` · ${Math.round(nb.bpm)} BPM` : "";
      setStats(String(Math.round(bar.bpm)), `${bar.bar_in_section}/${bar.section_bars}`, bar.count_in ? "count-in" : `bar of ${bar.label}`,
        String(away), nb ? `bar${away === 1 ? "" : "s"} to ${nb.label}${nb.count_in ? " (count-in)" : ""}${tempo}` : `bar${away === 1 ? "" : "s"} left`,
        away <= 2);
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
    live.lastHeard = performance.now();
    clickOn();
    if (!live.raf) live.raf = requestAnimationFrame(frame);
    if (!live.watchdog) live.watchdog = setInterval(watchdog, 1000);
  }

  // Start (or restart) this device's click for the current run. Only while
  // the page is on screen and the server is still in touch: a click that
  // can't hear "stop" must not keep going.
  function clickOn() {
    const t = live.transport;
    if (t.state !== "running" || document.hidden || live.lostClock) return;
    if (metronome.unlocked && metronome.enabled) metronome.run(t.timeline, Sync.toLocal(t.started_at), S.soundForBar);
  }

  // The server announces every bar. If nothing has come through for a
  // couple of bars (Wi-Fi gone, phone asleep), silence the click and say
  // so, rather than click on after the band has stopped.
  function watchdog() {
    if (live.solo) return;
    const t = live.transport;
    if (t.state !== "running" || !t.timeline) return;
    const bar = t.timeline.bars[0];
    const limit = Math.max(5000, bar ? bar.beat_ms * bar.beats * 2.5 : 5000);
    const quiet = performance.now() - (live.lastHeard || 0);
    if (quiet > limit && !live.lostClock && !live.solo) {
      if (S.prefs.get("keepPlaying", true) && !document.hidden) {
        // the drummer keeps going: this device carries on alone to the
        // end of the song (and on through the setlist) until the server is back
        setSolo(true, "lost");
        return;
      }
      live.lostClock = true;
      metronome.stop();
      $("live-driver").textContent = "Lost touch with the server: click paused";
      $("live-driver").classList.add("warn");
    }
  }

  function heard() {
    live.lastHeard = performance.now();
    if (live.lostClock) {
      live.lostClock = false;
      $("live-driver").classList.remove("warn");
      renderControls();
      clickOn();
    }
  }

  function stopRunning() {
    metronome.stop();
    if (live.watchdog) clearInterval(live.watchdog);
    live.watchdog = null;
    live.lostClock = false;
    $("live-driver").classList.remove("warn");
    if (live.raf) cancelAnimationFrame(live.raf);
    live.raf = null;
    $("now-label").style.color = "";
  }

  // -- controls ---------------------------------------------------------------

  function renderControls() {
    const running = live.transport.state === "running";
    $("live-start").classList.toggle("hidden", running);
    $("live-stop").classList.toggle("hidden", !running);
    $("live-jump-btn").classList.toggle("hidden", !running);
    $("live-start").disabled = !live.song;
    const d = live.transport.driver;
    $("live-driver").textContent = running && d ? `Started by ${d.client_id === Sync.clientId ? "you" : d.name}` : "";
    $("live-prev").title = live.solo ? "Previous song (this device only)" : "Previous song";
    renderSolo();
    renderClick();
  }

  function renderClick() {
    const b = $("click-toggle");
    if (!metronome.unlocked) b.textContent = "🔈 Click: tap to enable";
    else b.textContent = metronome.enabled ? "🔊 Click on" : "🔇 Click off";
    b.classList.toggle("active", metronome.unlocked && metronome.enabled);
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
    if (t.state === "running" && metronome.enabled) clickOn();
    if (!metronome.enabled) metronome.stop();
    setTimeout(renderClick, 50);
  });

  $("live-volume").addEventListener("input", (ev) => {
    S.saveClick({ volume: parseFloat(ev.target.value) });
  });

  $("live-click-settings").addEventListener("click", () => S.openClickSettings());

  async function start() {
    if (!live.song) return;
    if (!metronome.unlocked && metronome.enabled) metronome.unlock(); // this tap is our one chance on iOS
    try {
      await command({
        action: "start", song_id: live.song.id, setlist_id: live.setlist ? live.setlist.id : null,
        start_section_id: live.startSection,
      });
    } catch (err) {
      S.toast("Couldn't start: " + err.message, "error");
    }
  }

  async function stop() {
    try {
      await command({ action: "stop" });
    } catch (err) {
      S.toast("Couldn't stop: " + err.message, "error");
    }
  }

  $("live-start").addEventListener("click", start);
  $("live-stop").addEventListener("click", stop);
  $("live-prev").addEventListener("click", () => command({ action: "prev" }));
  $("live-next").addEventListener("click", () => command({ action: "next" }));
  $("live-solo").addEventListener("click", () => setSolo(!live.solo, "chosen"));
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
    } else if (live.transport.state === "running" && ["[", "]", ",", "."].includes(ev.key)) {
      nudge({ "[": "-beat", "]": "beat", ",": "-20", ".": "20" }[ev.key]);
    } else if ((ev.key === "ArrowRight" || ev.key === "PageDown") && live.setlist && live.transport.state !== "running") {
      command({ action: "next" });
    } else if ((ev.key === "ArrowLeft" || ev.key === "PageUp") && live.setlist && live.transport.state !== "running") {
      command({ action: "prev" });
    }
  });

  // Keep the screen on in the live view. The proper way (Wake Lock) only
  // works on https/localhost; on the band's plain-http Wi-Fi an iPad or
  // Android tablet would dim and lock. The fallback is the long-standing
  // trick of a tiny, muted, looping video, which browsers treat as "someone
  // is watching". It needs a tap to start, so every Start/click tap retries.
  async function keepAwake(on) {
    if (on && !S.prefs.get("keepAwake", true)) on = false;
    try {
      if (on && !live.wakeLock && navigator.wakeLock && window.isSecureContext) {
        live.wakeLock = await navigator.wakeLock.request("screen");
        live.wakeLock.addEventListener("release", () => (live.wakeLock = null));
      }
      if (!on && live.wakeLock) {
        await live.wakeLock.release();
        live.wakeLock = null;
      }
    } catch (err) {
      live.wakeLock = null;
    }
    const v = awakeVideo();
    if (on && !live.wakeLock) v.play().catch(() => {}); // refused until a tap: tried again on the next one
    else v.pause();
  }

  function awakeVideo() {
    if (!live.awakeVideo) {
      const v = document.createElement("video");
      v.src = "keepawake.mp4";
      v.muted = true;
      v.loop = true;
      v.playsInline = true;
      v.setAttribute("playsinline", "");
      v.setAttribute("muted", "");
      v.setAttribute("aria-hidden", "true");
      v.className = "keep-awake";
      document.body.appendChild(v);
      live.awakeVideo = v;
    }
    return live.awakeVideo;
  }

  // any tap in the live view is a chance to (re)start the keep-awake video
  $("live-view").addEventListener("pointerup", () => {
    if (live.visibleNow) keepAwake(true);
  });

  // -- the outside world ----------------------------------------------------------

  async function applyTransport(t) {
    // went solo because the server dropped: rejoin when the song is over
    if (live.solo && live.soloWhy === "lost" && Sync.connected && t && t.state !== "running") {
      live.solo = false;
      document.body.classList.remove("is-solo");
      try {
        t = await S.api("GET", "/transport");
      } catch (err) {
        live.solo = true;
        document.body.classList.add("is-solo");
      }
    }
    const prevSong = live.transport.song_id;
    const prevRun = live.transport.run;
    const prevRev = live.transport.rev || 0;
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
      } else if ((live.transport.rev || 0) !== prevRev) {
        moved();
      }
    } else {
      closeJump();
      armJump(null);
      stopRunning();
      if (wasRunning) renderChart();
      renderIdle();
    }
    renderControls();
  }

  Sync.on("transport", (t) => {
    if (!live.solo) applyTransport(t);
  });
  // the server came back after we went solo on our own: rejoin once idle
  Sync.on("status", (ok) => {
    if (!live.solo || live.soloWhy !== "lost") return;
    renderSolo();
    if (ok && live.transport.state !== "running") setSolo(false);
  });
  // Positions are worked out locally from the shared clock; the server's
  // per-bar message is the heartbeat that says "the run is still on".
  Sync.on("position", () => heard());
  Sync.on("transport", () => heard());

  // Screen off, app switched, tab hidden: stop the click straight away
  // (Android keeps sound playing in the background but drops the
  // connection, so it would never hear "stop"). Back on screen: re-sync
  // the clock, ask the server where the band is, and pick up from there.
  document.addEventListener("visibilitychange", async () => {
    if (document.hidden) {
      metronome.stop();
      return;
    }
    if (!live.visibleNow) return;
    if (live.solo) {
      clickOn();
      return;
    }
    await Sync.syncClock(4);
    try {
      const t = await S.api("GET", "/transport");
      live.lastHeard = performance.now();
      live.lostClock = false;
      if (t.run === live.transport.run && t.state === live.transport.state && (t.rev || 0) === (live.transport.rev || 0)) {
        clickOn(); // same run still going: just bring the click back
        renderControls();
      } else {
        await applyTransport(t);
      }
    } catch (err) {
      /* the stream's own reconnect will catch us up */
    }
  });

  window.SSPLive = {
    async visible(v) {
      live.visibleNow = v;
      renderBig();
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
    song: () => live.song,
    soloState: () => ({ ...solo.state }),
    soloCommand(body) {
      solo.command(body);
      return { ...solo.state };
    },
    keepAwake: (on) => keepAwake(on && live.visibleNow),
    awake: () => !!live.wakeLock || !!(live.awakeVideo && !live.awakeVideo.paused),
    // click settings changed on this device: a running click picks them up
    clickChanged() {
      renderClick();
      if (live.transport.state === "running" && metronome.enabled) clickOn();
    },
    async refresh() {
      if (!live.visibleNow) return;
      renderBig();
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
