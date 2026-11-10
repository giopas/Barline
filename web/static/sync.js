"use strict";

/*
 * Talking to the one server (v0.3): REST calls for edits, one Server-Sent
 * Events stream for everything the server pushes back (other devices'
 * edits, who's connected, the live transport), and a shared clock.
 *
 * Clock: every device asks the server for its time a few times, keeps the
 * fastest round trip, and from then on knows "server time" to within a few
 * milliseconds. Live playback is scheduled in server time, so every tablet
 * lands on the same beat.
 */

(function (root) {
  function randomId() {
    const a = new Uint8Array(6);
    (root.crypto || root.msCrypto).getRandomValues(a);
    return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  const clientId = randomId(); // one per open page, never stored

  const Sync = {
    clientId,
    offsetMs: 0, // serverTime = performance.now() + offsetMs
    connected: false,
    listeners: {},
    source: null,
    playerId: null,

    on(type, fn) {
      (this.listeners[type] = this.listeners[type] || []).push(fn);
    },

    emit(type, msg) {
      for (const fn of this.listeners[type] || []) {
        try {
          fn(msg.data, msg);
        } catch (err) {
          console.error(err);
        }
      }
    },

    async api(method, path, body, raw) {
      const opts = { method, headers: { "X-SSP-Client": clientId } };
      if (raw) {
        opts.body = raw.body;
        opts.headers["Content-Type"] = raw.type;
      } else if (body !== undefined) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
      const res = await fetch("/api" + path, opts);
      if (res.status === 204) return null;
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `${method} ${path} failed (${res.status})`);
      return data;
    },

    serverNow() {
      return performance.now() + this.offsetMs;
    },

    // server ms -> this device's performance.now() ms
    toLocal(serverMs) {
      return serverMs - this.offsetMs;
    },

    async syncClock(samples) {
      let best = null;
      for (let i = 0; i < (samples || 6); i++) {
        const t0 = performance.now();
        let res;
        try {
          res = await fetch("/api/time", { cache: "no-store" }).then((r) => r.json());
        } catch (err) {
          return;
        }
        const t1 = performance.now();
        const rtt = t1 - t0;
        if (!best || rtt < best.rtt) best = { rtt, offset: res.now - (t0 + rtt / 2) };
      }
      if (best) {
        this.offsetMs = best.offset;
        this.rttMs = best.rtt;
      }
    },

    connect() {
      // Pocket (0.18) has no server: nothing to stream from, nobody to sync with
      if (root.BarlinePocket) return;
      if (this.source) this.source.close();
      const device = /iPad|Tablet/i.test(navigator.userAgent) ? "tablet" : /Mobi|iPhone|Android/i.test(navigator.userAgent) ? "phone" : "computer";
      const q = new URLSearchParams({ client: clientId, device });
      if (this.playerId) q.set("player", this.playerId);
      const src = new EventSource("/api/events?" + q.toString());
      this.source = src;
      src.onopen = () => {
        const was = this.connected;
        this.connected = true;
        this.emit("status", { data: true });
        if (!was) this.emit("reconnect", { data: null });
      };
      src.onerror = () => {
        if (this.connected) {
          this.connected = false;
          this.emit("status", { data: false });
        }
      };
      src.onmessage = (ev) => {
        let msg;
        try {
          msg = JSON.parse(ev.data);
        } catch (err) {
          return;
        }
        this.emit(msg.type, msg);
      };
      // keep the clock honest over a long rehearsal
      if (!this.clockTimer) this.clockTimer = setInterval(() => this.syncClock(4), 30000);
    },

    async setPlayer(playerId) {
      this.playerId = playerId || null;
      try {
        await this.api("POST", "/presence", { client: clientId, player_id: this.playerId });
      } catch (err) {
        /* shown by the status dot */
      }
    },
  };

  root.SSPSync = Sync;
})(window);
