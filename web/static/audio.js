"use strict";

/*
 * The metronome every device plays for itself (v0.2, driven live in v0.5).
 *
 * Sounds: the same three as server/click_track.py (and QLC+ Swiss Knife's
 * click track) -- beep, wood, tick -- built from the very same formulas at
 * the same 22050 Hz, so the practice .wav and the stage click sound alike.
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
  const SOUNDS = ["beep", "wood", "tick"];
  const LOOKAHEAD_MS = 160;
  const TICK_MS = 25;

  function clickSamples(freq, amp) {
    const n = Math.floor((RATE * 25) / 1000);
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) out[i] = amp * Math.sin((2 * Math.PI * freq * i) / RATE) * Math.exp((-6.0 * i) / n);
    return out;
  }

  function woodSamples(accent) {
    const [f, amp] = accent ? [1500, 0.95] : [900, 0.65];
    const n = Math.floor((RATE * 30) / 1000);
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      out[i] = amp * (0.75 * Math.sin((2 * Math.PI * f * i) / RATE) + 0.25 * Math.sin((2 * Math.PI * f * 2.43 * i) / RATE)) *
        Math.exp((-9.0 * i) / n);
    }
    return out;
  }

  function tickSamples(accent) {
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

  function samplesFor(sound, accent) {
    if (sound === "wood") return woodSamples(accent);
    if (sound === "tick") return tickSamples(accent);
    return accent ? clickSamples(1600, 0.9) : clickSamples(1000, 0.6);
  }

  class Metronome {
    constructor() {
      this.ctx = null;
      this.gain = null;
      this.buffers = {};
      this.enabled = true;
      this.sound = "wood";
      this.volume = 0.8;
      this.latencyMs = 0; // per-device nudge, e.g. for Bluetooth speakers
      this.timer = null;
      this.job = null;
      this.onbeat = null;
    }

    get unlocked() {
      return !!this.ctx && this.ctx.state === "running";
    }

    unlock() {
      const AC = root.AudioContext || root.webkitAudioContext;
      if (!AC) return false;
      if (!this.ctx) {
        this.ctx = new AC();
        this.gain = this.ctx.createGain();
        this.gain.gain.value = this.volume;
        this.gain.connect(this.ctx.destination);
        for (const s of SOUNDS) {
          for (const accent of [true, false]) {
            const data = samplesFor(s, accent);
            const buf = this.ctx.createBuffer(1, data.length, RATE);
            buf.getChannelData(0).set(data);
            this.buffers[`${s}:${accent ? 1 : 0}`] = buf;
          }
        }
      }
      if (this.ctx.state !== "running") this.ctx.resume();
      // a silent buffer, so iOS really opens the audio path on this tap
      const src = this.ctx.createBufferSource();
      src.buffer = this.ctx.createBuffer(1, 1, RATE);
      src.connect(this.ctx.destination);
      src.start();
      return true;
    }

    setVolume(v) {
      this.volume = v;
      if (this.gain) this.gain.gain.value = v;
    }

    // performance.now() milliseconds -> AudioContext seconds
    audioTimeFor(perfMs) {
      const ctx = this.ctx;
      if (ctx.getOutputTimestamp) {
        const ts = ctx.getOutputTimestamp();
        if (ts && ts.performanceTime) return ts.contextTime + (perfMs - ts.performanceTime) / 1000;
      }
      return ctx.currentTime + (perfMs - performance.now()) / 1000 - (ctx.outputLatency || 0);
    }

    play(sound, accent, perfMs) {
      if (!this.unlocked || !this.enabled) return;
      const buf = this.buffers[`${sound}:${accent ? 1 : 0}`];
      if (!buf) return;
      const src = this.ctx.createBufferSource();
      src.buffer = buf;
      src.connect(this.gain);
      const when = Math.max(this.ctx.currentTime, this.audioTimeFor(perfMs + this.latencyMs));
      src.start(when);
    }

    /*
     * Run a timeline. `startPerfMs` is when its first bar starts, on this
     * device's performance.now() clock (already corrected for the server's
     * clock by the caller). `soundFor(bar)` picks the sound per bar, so a
     * "sticks" count-in can sound different from the song.
     */
    run(timeline, startPerfMs, soundFor) {
      this.stop();
      const beats = [];
      for (const bar of timeline.bars) {
        for (let b = 0; b < bar.beats; b++) beats.push({ t: bar.start_ms + b * bar.beat_ms, accent: b === 0, bar, beat: b });
      }
      this.job = { beats, next: 0, startPerfMs, soundFor };
      const tick = () => {
        const job = this.job;
        if (!job) return;
        const horizon = performance.now() + LOOKAHEAD_MS;
        while (job.next < job.beats.length && job.startPerfMs + job.beats[job.next].t <= horizon) {
          const bt = job.beats[job.next];
          const at = job.startPerfMs + bt.t;
          if (at >= performance.now() - 30) {
            const sound = job.soundFor ? job.soundFor(bt.bar) : this.sound;
            if (sound) this.play(sound, bt.accent, at);
          }
          job.next++;
        }
        if (job.next >= job.beats.length) this.job = null;
      };
      tick();
      this.timer = setInterval(tick, TICK_MS);
    }

    stop() {
      this.job = null;
      if (this.timer) clearInterval(this.timer);
      this.timer = null;
    }

    playClip(url) {
      const a = new Audio(url);
      a.play().catch(() => {});
      return a;
    }
  }

  root.SSPAudio = { Metronome, SOUNDS, RATE, samplesFor };
})(window);
