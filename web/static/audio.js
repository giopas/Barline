"use strict";

/*
 * The metronome every device plays for itself (v0.2, driven live in v0.5).
 *
 * Sounds: the same as server/click_track.py -- beep, wood, tick (from
 * QLC+ Swiss Knife's click track) and, since 0.16, ride bell, cowbell,
 * finger snap and side stick -- built from the very same formulas, so the
 * practice .wav and the stage click sound alike.
 *
 * Timing: clicks are never fired from a JS timer (timers jitter by tens of
 * milliseconds). A short look-ahead loop instead hands each beat to the Web
 * Audio clock a little before it's due, at an exact time. Audio never
 * travels over the network -- only the shared start time and tempo map do.
 *
 * Browsers only allow sound after a tap, so unlock() must run from a click.
 */

(function (root) {
  const RATE = 22050;
  const SOUNDS = ["beep", "wood", "tick", "bell", "cowbell", "snap", "rim"];
  const LOOKAHEAD_MS = 160;
  const TICK_MS = 25;

  function clickSamples(freq, amp, RATE) {
    const n = Math.floor((RATE * 25) / 1000);
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) out[i] = amp * Math.sin((2 * Math.PI * freq * i) / RATE) * Math.exp((-6.0 * i) / n);
    return out;
  }

  function woodSamples(accent, RATE) {
    const [f, amp] = accent ? [1500, 0.95] : [900, 0.65];
    const n = Math.floor((RATE * 30) / 1000);
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      out[i] = amp * (0.75 * Math.sin((2 * Math.PI * f * i) / RATE) + 0.25 * Math.sin((2 * Math.PI * f * 2.43 * i) / RATE)) *
        Math.exp((-9.0 * i) / n);
    }
    return out;
  }

  function tickSamples(accent, RATE) {
    const n = Math.floor((RATE * (accent ? 40 : 12)) / 1000);
    const amp = accent ? 0.9 : 0.5;
    const out = new Float32Array(n);
    let seed = 12345;
    for (let i = 0; i < n; i++) {
      seed = (Math.imul(seed, 1103515245) + 12345) & 0x7fffffff; // same 31-bit LCG as the Python
      const noise = seed / 0x3fffffff - 1.0;
      const body = accent ? 0.6 * Math.sin((2 * Math.PI * 220 * i) / RATE) : 0;
      out[i] = (amp * (0.7 * noise + body)) / 1.3 * Math.exp((-7.0 * i) / n);
    }
    return out;
  }

  // -- 0.16: drum-kit sounds (mirrors click_track.py line for line) ---------

  function noise(n, seed) {
    const out = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      seed = (Math.imul(seed, 1103515245) + 12345) & 0x7fffffff;
      out[i] = seed / 0x3fffffff - 1.0;
    }
    return out;
  }

  function resonate(x, freq, r, RATE) {
    const c = 2.0 * r * Math.cos((2 * Math.PI * freq) / RATE);
    const r2 = r * r;
    let y1 = 0;
    let y2 = 0;
    const out = new Float64Array(x.length);
    for (let i = 0; i < x.length; i++) {
      const y = x[i] + c * y1 - r2 * y2;
      out[i] = y;
      y2 = y1;
      y1 = y;
    }
    return out;
  }

  function finish(x, amp, RATE) {
    let peak = 0;
    for (const v of x) peak = Math.max(peak, Math.abs(v));
    peak = peak || 1;
    const n = x.length;
    const fade = Math.floor((RATE * 3) / 1000);
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const f = i >= n - fade ? Math.min(1, (n - 1 - i) / fade) : 1;
      out[i] = (amp * x[i] / peak) * f;
    }
    return out;
  }

  function bellSamples(accent, RATE) {
    const [f, amp, ms] = accent ? [760, 0.9, 240] : [640, 0.7, 200];
    const n = Math.floor((RATE * ms) / 1000);
    const partials = [[1.0, 1.0, 5.0], [1.47, 0.7, 6.5], [2.09, 0.55, 8.0], [2.56, 0.4, 9.5], [3.42, 0.3, 12.0]];
    const nz = noise(n, 777);
    const x = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const t = i / RATE;
      let v = 0;
      for (const [k, a, d] of partials) v += a * Math.sin(2 * Math.PI * f * k * t) * Math.exp((-d * i) / n);
      x[i] = v + 0.8 * nz[i] * Math.exp(-i / (RATE * 0.002));
    }
    return finish(x, amp, RATE);
  }

  function cowbellSamples(accent, RATE) {
    const [k, amp] = accent ? [1.12, 0.9] : [1.0, 0.7];
    const n = Math.floor((RATE * 150) / 1000);
    const x = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const t = i / RATE;
      let v = 0;
      for (const f of [540 * k, 800 * k]) {
        const w = 2 * Math.PI * f * t;
        v += Math.sin(w) + 0.33 * Math.sin(3 * w) + 0.2 * Math.sin(5 * w);
      }
      x[i] = v * (0.65 * Math.exp(-i / (RATE * 0.008)) + 0.35 * Math.exp(-i / (RATE * 0.045)));
    }
    return finish(x, amp, RATE);
  }

  function snapSamples(accent, RATE) {
    const [f, amp] = accent ? [2600, 0.9] : [2100, 0.7];
    const n = Math.floor((RATE * 60) / 1000);
    const band = resonate(noise(n, 4242), f, 0.93, RATE);
    const x = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const env = Math.min(1, i / (RATE * 0.0005)) * Math.exp(-i / (RATE * 0.009));
      x[i] = band[i] * env;
    }
    return finish(x, amp, RATE);
  }

  function rimSamples(accent, RATE) {
    const [f, amp] = accent ? [1750, 0.9] : [1450, 0.7];
    const n = Math.floor((RATE * 50) / 1000);
    const body = resonate(noise(n, 999), 420, 0.96, RATE);
    let peak = 0;
    for (const v of body) peak = Math.max(peak, Math.abs(v));
    peak = peak || 1;
    const x = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const t = i / RATE;
      const tone = Math.sin(2 * Math.PI * f * t) * Math.exp(-i / (RATE * 0.006));
      x[i] = 0.65 * tone + (0.35 * body[i]) / peak * Math.exp(-i / (RATE * 0.01));
    }
    return finish(x, amp, RATE);
  }

  // `rate` defaults to the click track's 22050 Hz; the live metronome
  // builds them at the device's own rate (same formulas, so same sound).
  function samplesFor(sound, accent, rate) {
    const r = rate || RATE;
    if (sound === "wood") return woodSamples(accent, r);
    if (sound === "tick") return tickSamples(accent, r);
    if (sound === "bell") return bellSamples(accent, r);
    if (sound === "cowbell") return cowbellSamples(accent, r);
    if (sound === "snap") return snapSamples(accent, r);
    if (sound === "rim") return rimSamples(accent, r);
    return accent ? clickSamples(1600, 0.9, r) : clickSamples(1000, 0.6, r);
  }

  // Per-device click choices (0.10). Levels are 0..1 on top of the volume.
  const DEFAULTS = {
    sound: "wood", volume: 0.8, accent: 1, beat: 0.8, sub: 0.45,
    subdivision: "none", voice: false, mode: "always", channel: "both", latencyMs: 0,
  };
  const VOICE = ["one", "two", "three", "four"];

  class Metronome {
    constructor() {
      this.ctx = null;
      this.gain = null;
      this.buffers = {};
      this.voice = {};
      this.enabled = true;
      this.opts = { ...DEFAULTS };
      this.timer = null;
      this.job = null;
      this.onbeat = null;
    }

    // old names, still used around the app
    get sound() { return this.opts.sound; }
    set sound(v) { this.opts.sound = SOUNDS.includes(v) ? v : DEFAULTS.sound; }
    get volume() { return this.opts.volume; }
    get latencyMs() { return this.opts.latencyMs; }
    set latencyMs(v) { this.opts.latencyMs = Number(v) || 0; }

    // Change any of the options; unknown keys and bad values are ignored.
    configure(changes) {
      for (const [k, v] of Object.entries(changes || {})) {
        if (!(k in DEFAULTS)) continue;
        if (k === "sound") this.sound = v;
        else if (k === "channel") this.opts.channel = ["left", "right"].includes(v) ? v : "both";
        else if (k === "subdivision") this.opts.subdivision = ["8", "16", "triplet"].includes(String(v)) ? String(v) : "none";
        else if (k === "mode") this.opts.mode = v === "countin" ? "countin" : "always";
        else if (k === "voice") this.opts.voice = !!v;
        else if (k === "latencyMs") this.opts.latencyMs = Math.max(-300, Math.min(300, Number(v) || 0));
        else this.opts[k] = Math.max(0, Math.min(1, Number(v)));
      }
      if (this.gain) this.gain.gain.value = this.opts.volume;
      this.route();
      return { ...this.opts };
    }

    // Sound has been allowed (a tap created the audio engine). Safari
    // starts the engine a moment *after* the tap, so this deliberately
    // doesn't wait for "running": clicks get scheduled straight away and
    // the engine catches up -- waiting here was why an iPad stayed silent.
    get unlocked() {
      return !!this.ctx && this.ctx.state !== "closed";
    }

    unlock() {
      const AC = root.AudioContext || root.webkitAudioContext;
      if (!AC) return false;
      // iPhone/iPad: by default Web Audio is muted by silent mode. Asking
      // for "playback" makes the click behave like music instead (Safari 16.4+).
      try {
        if (navigator.audioSession) navigator.audioSession.type = "playback";
      } catch (err) {
        /* older Safari: silent mode mutes the click */
      }
      if (!this.ctx) {
        this.ctx = new AC();
        const rate = this.ctx.sampleRate;
        this.gain = this.ctx.createGain();
        this.gain.gain.value = this.opts.volume;
        this.route();
        for (const s of SOUNDS) {
          for (const accent of [true, false]) {
            const data = samplesFor(s, accent, rate);
            const buf = this.ctx.createBuffer(1, data.length, rate);
            buf.getChannelData(0).set(data);
            this.buffers[`${s}:${accent ? 1 : 0}`] = buf;
          }
        }
        this.loadVoice();
        // iOS can "interrupt" the engine (a call, Siri, another app);
        // pick it up again as soon as we're allowed
        document.addEventListener("visibilitychange", () => {
          if (!document.hidden) this.wake();
        });
      }
      this.wake();
      // a silent buffer, so iOS really opens the audio path on this tap
      const src = this.ctx.createBufferSource();
      src.buffer = this.ctx.createBuffer(1, 1, this.ctx.sampleRate);
      src.connect(this.ctx.destination);
      src.start();
      return true;
    }

    // The spoken count-in: four short recordings served with the app.
    loadVoice() {
      for (let i = 0; i < VOICE.length; i++) {
        if (this.voice[i + 1]) continue;
        fetch(`voice/${VOICE[i]}.wav`)
          .then((r) => r.arrayBuffer())
          .then((data) => new Promise((ok, fail) => this.ctx.decodeAudioData(data, ok, fail)))
          .then((buf) => (this.voice[i + 1] = buf))
          .catch(() => {});
      }
    }

    // Both ears, or only the left or right one -- with a Y-splitter into
    // in-ears, a click in one ear can sit next to the band mix in the other.
    route() {
      if (!this.ctx || !this.gain) return;
      try {
        this.gain.disconnect();
      } catch (err) {
        /* not connected yet */
      }
      const ch = this.opts.channel;
      const dest = this.ctx.destination;
      if (ch === "both" || dest.maxChannelCount < 2) {
        this.gain.connect(dest);
        return;
      }
      if (!this.merger) {
        this.merger = this.ctx.createChannelMerger(2);
        this.merger.connect(dest);
      }
      this.gain.connect(this.merger, 0, ch === "left" ? 0 : 1);
    }

    wake() {
      if (this.ctx && this.ctx.state !== "running" && this.ctx.state !== "closed") {
        this.ctx.resume().catch(() => {});
      }
    }

    setVolume(v) {
      this.configure({ volume: v });
    }

    // performance.now() milliseconds -> AudioContext seconds
    audioTimeFor(perfMs) {
      const ctx = this.ctx;
      const now = performance.now();
      if (ctx.getOutputTimestamp) {
        const ts = ctx.getOutputTimestamp();
        // only trust it when it's plausible -- some Safari versions report
        // zeros or a stale stamp while the engine is still starting
        if (ts && ts.performanceTime > 0 && Math.abs(now - ts.performanceTime) < 500 &&
            Math.abs(ctx.currentTime - ts.contextTime) < 0.5) {
          return ts.contextTime + (perfMs - ts.performanceTime) / 1000;
        }
      }
      return ctx.currentTime + (perfMs - now) / 1000 - (ctx.outputLatency || 0);
    }

    // One sound at `perfMs`. kind: accent | beat | sub | voice (n = 1..4).
    play(sound, kind, perfMs, n) {
      if (!this.unlocked || !this.enabled) return;
      if (kind === true || kind === false) kind = kind ? "accent" : "beat"; // old play(sound, accent, t)
      if (this.ctx.state !== "running") this.wake();
      let buf;
      let level;
      if (kind === "voice" && this.voice[n]) {
        buf = this.voice[n];
        level = 1;
      } else {
        const accent = kind === "accent" || (kind === "voice" && n === 1);
        buf = this.buffers[`${sound}:${accent ? 1 : 0}`];
        level = kind === "sub" ? this.opts.sub : accent ? this.opts.accent : this.opts.beat;
      }
      if (!buf || level <= 0) return;
      const src = this.ctx.createBufferSource();
      src.buffer = buf;
      let out = this.gain;
      if (level < 1) {
        const g = this.ctx.createGain();
        g.gain.value = level;
        g.connect(this.gain);
        out = g;
      }
      src.connect(out);
      const when = Math.max(this.ctx.currentTime, this.audioTimeFor(perfMs + this.opts.latencyMs));
      src.start(when);
    }

    /*
     * Run a timeline. `startPerfMs` is when its first bar starts, on this
     * device's performance.now() clock (already corrected for the server's
     * clock by the caller). `soundFor(bar)` picks the sound per bar, so a
     * "sticks" count-in can sound different from the song. What actually
     * sounds (subdivisions, spoken count-in, count-in only) comes from the
     * shared rules in timing.js, so it matches the downloadable .wav.
     */
    run(timeline, startPerfMs, soundFor) {
      this.stop();
      const T = root.SSPTiming;
      const events = T.clickEvents(timeline, this.opts);
      this.job = { events, bars: timeline.bars, next: 0, startPerfMs, soundFor };
      const tick = () => {
        const job = this.job;
        if (!job) return;
        const horizon = performance.now() + LOOKAHEAD_MS;
        while (job.next < job.events.length && job.startPerfMs + job.events[job.next].t <= horizon) {
          const ev = job.events[job.next];
          const at = job.startPerfMs + ev.t;
          if (at >= performance.now() - 30) {
            // a beat the song's pattern gave a sound of its own keeps it
            const sound = ev.sound || (job.soundFor ? job.soundFor(job.bars[ev.bar]) : this.opts.sound);
            if (sound) this.play(sound, ev.kind, at, ev.n);
          }
          job.next++;
        }
        if (job.next >= job.events.length) this.job = null;
      };
      tick();
      this.timer = setInterval(tick, TICK_MS);
    }

    stop() {
      this.job = null;
      if (this.timer) clearInterval(this.timer);
      this.timer = null;
    }

    // What the click check shows: is the engine really making sound?
    diagnostics() {
      const c = this.ctx;
      return {
        engine: c ? c.state : "not started (tap to enable)",
        sampleRate: c ? c.sampleRate : null,
        outputLatencyMs: c && c.outputLatency ? Math.round(c.outputLatency * 1000) : null,
        baseLatencyMs: c && c.baseLatency ? Math.round(c.baseLatency * 1000) : null,
        channels: c ? c.destination.maxChannelCount : null,
        voiceLoaded: Object.keys(this.voice).length === VOICE.length,
        silentModeSafe: !!(navigator.audioSession && navigator.audioSession.type === "playback"),
      };
    }

    playClip(url) {
      const a = new Audio(url);
      a.play().catch(() => {});
      return a;
    }
  }

  root.SSPAudio = { Metronome, SOUNDS, RATE, DEFAULTS, samplesFor };
})(window);
