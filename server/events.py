"""
Live sync: every connected browser holds one long-lived HTTP response open
(Server-Sent Events, `GET /api/events`) and the server pushes every change
down all of them at once.

Why SSE and not a WebSocket: the traffic Barline needs is one-way -- the
server tells everyone "this song changed" or "the band is on bar 17".
Edits still go up as ordinary REST calls. SSE does exactly that with the
standard library alone (a WebSocket server would mean hand-writing the
RFC 6455 framing), and every browser reconnects an SSE stream on its own
after a Wi-Fi blip, which is the behaviour a tablet on a mic stand wants.

Each message is one JSON object: {"type", "data", "origin", "seq"}.
`origin` is the client id that caused the change, so the browser that made
an edit can skip re-rendering its own echo.
"""

from __future__ import annotations

import itertools
import json
import queue
import threading
import time

KEEPALIVE_S = 15
_CLOSE = object()


class Client:
    def __init__(self, client_id: str, player_id: str = None, device: str = ""):
        self.client_id = client_id or "anon"
        self.player_id = player_id or None
        self.device = device[:40]
        self.connected_at = time.time()
        self.queue: "queue.Queue" = queue.Queue(maxsize=500)

    def info(self) -> dict:
        return {
            "client_id": self.client_id,
            "player_id": self.player_id,
            "device": self.device,
            "connected_at": self.connected_at,
        }


class Hub:
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = []
        self.seq = itertools.count(1)
        self.closed = False
        self.players = {}  # client_id -> player_id, remembered across reconnects

    # -- connections --------------------------------------------------------
    def subscribe(self, client_id: str, player_id: str = None, device: str = "") -> Client:
        with self.lock:
            if player_id is None:
                player_id = self.players.get(client_id)
            else:
                self.players[client_id] = player_id
        client = Client(client_id, player_id, device)
        with self.lock:
            self.clients.append(client)
        self.publish("presence", self.presence())
        return client

    def unsubscribe(self, client: Client) -> None:
        with self.lock:
            if client in self.clients:
                self.clients.remove(client)
        if not self.closed:
            self.publish("presence", self.presence())

    def set_player(self, client_id: str, player_id: str = None) -> None:
        with self.lock:
            self.players[client_id] = player_id or None
            if len(self.players) > 500:
                self.players.pop(next(iter(self.players)))
            for c in self.clients:
                if c.client_id == client_id:
                    c.player_id = player_id or None
        self.publish("presence", self.presence())

    def presence(self) -> list:
        with self.lock:
            return [c.info() for c in self.clients]

    def player_name(self, band: dict, client_id: str) -> str:
        """Who's behind a client id, in words, for "Started by Ruby"."""
        with self.lock:
            pid = next((c.player_id for c in self.clients if c.client_id == client_id), None)
        for p in band.get("players", []):
            if p.get("id") == pid:
                return p.get("name") or "someone"
        return "someone"

    # -- broadcasting -----------------------------------------------------
    def publish(self, kind: str, data, origin: str = None) -> None:
        message = {"type": kind, "data": data, "origin": origin, "seq": next(self.seq)}
        payload = json.dumps(message, ensure_ascii=False)
        with self.lock:
            targets = list(self.clients)
        for c in targets:
            try:
                c.queue.put_nowait(payload)
            except queue.Full:
                # a device that stopped reading (asleep, gone) -- drop it
                # rather than let it hold memory; it reconnects when it wakes.
                self.unsubscribe(c)

    def close(self) -> None:
        """Ends every open stream (server shutting down)."""
        self.closed = True
        with self.lock:
            targets = list(self.clients)
            self.clients = []
        for c in targets:
            try:
                c.queue.put_nowait(_CLOSE)
            except queue.Full:
                pass

    # -- the stream itself (called from the HTTP handler's thread) ---------
    def stream(self, client: Client, write) -> None:
        """Feed `client`'s queue into `write(bytes)` until the connection
        drops or the hub closes. `write` raises OSError on a dead socket."""
        write(b"retry: 2000\n\n")
        try:
            while not self.closed:
                try:
                    item = client.queue.get(timeout=KEEPALIVE_S)
                except queue.Empty:
                    write(b": keepalive\n\n")
                    continue
                if item is _CLOSE:
                    break
                write(b"data: " + item.encode("utf-8") + b"\n\n")
        finally:
            self.unsubscribe(client)
