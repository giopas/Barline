#!/usr/bin/env python3
"""
Single Song Planner -- the one server.

A small, plain, stdlib-only Python app (same spirit as QLC+ Swiss Knife):
holds the in-memory data model (backed by the one-JSON-per-song storage in
storage.py), serves the single-page web app, and exposes a small JSON REST
API for it. Headless-capable -- no GUI dependency, so this runs the same way
on a laptop or a display-less Raspberry Pi.

v0.1 scope (see claude/WORKPLAN.md): one client at a time, no WebSocket
sync yet (that's v0.3), no audio (v0.6). This version proves the data model,
storage layout, and editing/switching UX.

Local-network only, by design -- see PROJECT_CHARTER.md section 4. There is
no authentication beyond "on the same Wi-Fi and knows the URL": anyone on
that network can read and edit everything.

Can also be driven programmatically (see build_server() below) -- that's
what launcher/gui.py does to start/stop the server from a desktop control
panel instead of a terminal.

Usage:
    python3 app.py [--port 8420] [--data <path>] [--static <path>]

    --data and --static default to paths.default_data_dir() /
    paths.default_static_dir(), which resolve relative to this repo when
    running from source, or to the per-OS app-support folder / the bundled
    web app when packaged (see server/paths.py).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import models
import paths
from models import ValidationError
from storage import Storage

DEFAULT_PORT = 8420


# ---------------------------------------------------------------------------
# LAN address discovery (adapted from QLC+ Swiss Knife's
# core/stage_monitor.py local_addresses() -- see WORKPLAN.md's "Reuse"
# section; reimplemented here against the stdlib socket module rather than
# copied, since SSP has no QLC+ process to borrow a live connection from).
# ---------------------------------------------------------------------------

def local_addresses() -> list:
    """Best-effort list of this machine's LAN IPv4 addresses, for printing
    a reachable URL on startup. Falls back to the UDP-connect trick if
    gethostbyname_ex doesn't turn up anything useful."""
    addrs = set()
    try:
        hostname = socket.gethostname()
        _, _, ips = socket.gethostbyname_ex(hostname)
        for ip in ips:
            if not ip.startswith("127."):
                addrs.add(ip)
    except socket.error:
        pass
    if not addrs:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                addrs.add(s.getsockname()[0])
            finally:
                s.close()
        except OSError:
            pass
    return sorted(addrs)


# ---------------------------------------------------------------------------
# In-memory store -- the one source of truth while the server runs.
# Every song/setlist is loaded at startup and kept here; disk writes happen
# on edit and are the only time storage.py is touched again until shutdown.
# ---------------------------------------------------------------------------

class Store:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.lock = threading.RLock()
        self.band = storage.load_band()
        self.songs = storage.load_all_songs()
        self.setlists = storage.load_all_setlists()

    # -- band -------------------------------------------------------------
    def get_band(self) -> dict:
        with self.lock:
            return self.band

    def put_band(self, payload: dict) -> dict:
        with self.lock:
            self.band = {
                "id": "band",
                "name": payload.get("name", self.band.get("name", "My Band")),
                "players": payload.get("players", self.band.get("players", [])),
            }
            self.storage.save_band(self.band)
            return self.band

    # -- songs --------------------------------------------------------------
    def list_songs(self) -> list:
        with self.lock:
            return [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "default_bpm": s["default_bpm"],
                    "section_count": len(s.get("sections", [])),
                    "total_bars": models.song_total_bars(s),
                }
                for s in sorted(self.songs.values(), key=lambda s: s["title"].lower())
            ]

    def get_song(self, song_id: str) -> dict:
        with self.lock:
            song = self.songs.get(song_id)
            if song is None:
                raise KeyError(song_id)
            return song

    def create_song(self, payload: dict) -> dict:
        with self.lock:
            song = models.new_song(
                title=payload.get("title", "Untitled Song"),
                default_bpm=payload.get("default_bpm", 120),
            )
            models.validate_song(song)
            self.songs[song["id"]] = song
            self.storage.save_song(song)
            return song

    def put_song(self, song_id: str, payload: dict) -> dict:
        with self.lock:
            if song_id not in self.songs:
                raise KeyError(song_id)
            existing = self.songs[song_id]
            song = {
                "id": song_id,
                "title": payload.get("title", existing["title"]),
                "default_bpm": payload.get("default_bpm", existing["default_bpm"]),
                "sections": payload.get("sections", existing.get("sections", [])),
                "created_at": existing.get("created_at", models.now()),
                "updated_at": models.now(),
            }
            models.validate_song(song)
            self.songs[song_id] = song
            self.storage.save_song(song)
            return song

    def delete_song(self, song_id: str) -> None:
        with self.lock:
            if song_id not in self.songs:
                raise KeyError(song_id)
            del self.songs[song_id]
            self.storage.delete_song(song_id)
            # a song can vanish out from under a setlist (a band deletes a
            # tune they dropped) -- drop stale references rather than let
            # the setlist 404 on playback.
            for setlist in self.setlists.values():
                if song_id in setlist["songs"]:
                    setlist["songs"] = [s for s in setlist["songs"] if s != song_id]
                    self.storage.save_setlist(setlist)

    # -- setlists ---------------------------------------------------------
    def list_setlists(self) -> list:
        with self.lock:
            return [
                {"id": sl["id"], "name": sl["name"], "song_count": len(sl["songs"])}
                for sl in sorted(self.setlists.values(), key=lambda sl: sl["name"].lower())
            ]

    def get_setlist(self, setlist_id: str) -> dict:
        with self.lock:
            setlist = self.setlists.get(setlist_id)
            if setlist is None:
                raise KeyError(setlist_id)
            return setlist

    def create_setlist(self, payload: dict) -> dict:
        with self.lock:
            setlist = models.new_setlist(name=payload.get("name", "New Setlist"))
            setlist["songs"] = payload.get("songs", [])
            models.validate_setlist(setlist)
            self.setlists[setlist["id"]] = setlist
            self.storage.save_setlist(setlist)
            return setlist

    def put_setlist(self, setlist_id: str, payload: dict) -> dict:
        with self.lock:
            if setlist_id not in self.setlists:
                raise KeyError(setlist_id)
            existing = self.setlists[setlist_id]
            setlist = {
                "id": setlist_id,
                "name": payload.get("name", existing["name"]),
                "songs": payload.get("songs", existing["songs"]),
            }
            models.validate_setlist(setlist)
            self.setlists[setlist_id] = setlist
            self.storage.save_setlist(setlist)
            return setlist

    def delete_setlist(self, setlist_id: str) -> None:
        with self.lock:
            if setlist_id not in self.setlists:
                raise KeyError(setlist_id)
            del self.setlists[setlist_id]
            self.storage.delete_setlist(setlist_id)


# ---------------------------------------------------------------------------
# HTTP handler -- small JSON REST API under /api/, static files otherwise.
# Locked-down static serving adapted from Swiss Knife's stage_monitor.py
# pattern: no directory listing, only serves files inside the static root.
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "SSP/0.1"
    store: Store = None  # set by build_server() before the server starts
    static_root: str = None
    log_hook = None  # optional callable(str); set by the launcher GUI to
    # capture request logging into its own log pane instead of stderr.

    # -- helpers ------------------------------------------------------------
    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self) -> None:
        # Same spirit as Swiss Knife's stage_monitor handler: this page has
        # no reason to load anything but itself.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"invalid JSON body: {exc}") from exc

    def log_message(self, fmt, *args) -> None:  # noqa: A003 - stdlib signature
        line = f"[ssp] {self.address_string()} - {fmt % args}"
        if Handler.log_hook is not None:
            Handler.log_hook(line)
        else:
            sys.stderr.write(line + "\n")

    # -- routing --------------------------------------------------------
    def do_GET(self):  # noqa: N802 - stdlib naming
        if self.path.startswith("https://"):
            # A tablet occasionally mistypes/forces https on a plain-HTTP
            # LAN server -- same pitfall Swiss Knife's Stage Monitor guards
            # against. Fail clearly instead of a confusing connection reset.
            self._send_json(400, {"error": "this server is plain HTTP, not HTTPS"})
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._route_api("GET", parsed)
        else:
            self._serve_static(parsed.path)

    def do_POST(self):  # noqa: N802
        self._route_api("POST", urlparse(self.path))

    def do_PUT(self):  # noqa: N802
        self._route_api("PUT", urlparse(self.path))

    def do_DELETE(self):  # noqa: N802
        self._route_api("DELETE", urlparse(self.path))

    def _route_api(self, method: str, parsed) -> None:
        parts = [p for p in parsed.path.split("/") if p]  # ["api", "songs", "<id>"]
        try:
            if parts[1:] == ["band"] and method == "GET":
                return self._send_json(200, self.store.get_band())
            if parts[1:] == ["band"] and method == "PUT":
                return self._send_json(200, self.store.put_band(self._read_json_body()))

            if parts[1:] == ["songs"] and method == "GET":
                return self._send_json(200, self.store.list_songs())
            if parts[1:] == ["songs"] and method == "POST":
                return self._send_json(201, self.store.create_song(self._read_json_body()))
            if len(parts) == 3 and parts[1] == "songs" and method == "GET":
                return self._send_json(200, self.store.get_song(parts[2]))
            if len(parts) == 3 and parts[1] == "songs" and method == "PUT":
                return self._send_json(200, self.store.put_song(parts[2], self._read_json_body()))
            if len(parts) == 3 and parts[1] == "songs" and method == "DELETE":
                self.store.delete_song(parts[2])
                return self._send_json(204, {})

            if parts[1:] == ["setlists"] and method == "GET":
                return self._send_json(200, self.store.list_setlists())
            if parts[1:] == ["setlists"] and method == "POST":
                return self._send_json(201, self.store.create_setlist(self._read_json_body()))
            if len(parts) == 3 and parts[1] == "setlists" and method == "GET":
                return self._send_json(200, self.store.get_setlist(parts[2]))
            if len(parts) == 3 and parts[1] == "setlists" and method == "PUT":
                return self._send_json(200, self.store.put_setlist(parts[2], self._read_json_body()))
            if len(parts) == 3 and parts[1] == "setlists" and method == "DELETE":
                self.store.delete_setlist(parts[2])
                return self._send_json(204, {})

            self._send_json(404, {"error": f"no such route: {method} {parsed.path}"})
        except KeyError as exc:
            self._send_json(404, {"error": f"not found: {exc}"})
        except ValidationError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - last-resort JSON error, never a stack trace to the client
            self._send_json(500, {"error": f"internal error: {exc}"})

    # -- static file serving -----------------------------------------------
    def _serve_static(self, url_path: str) -> None:
        if url_path == "/":
            url_path = "/index.html"
        # Collapse the path and refuse anything that would escape static_root
        # (no "..", no absolute paths, no directory listing).
        safe_rel = os.path.normpath(url_path).lstrip("/\\")
        full_path = os.path.normpath(os.path.join(self.static_root, safe_rel))
        if not full_path.startswith(os.path.normpath(self.static_root)):
            self._send_json(403, {"error": "forbidden"})
            return
        if os.path.isdir(full_path) or not os.path.isfile(full_path):
            self._send_json(404, {"error": "not found"})
            return
        content_type = self._guess_content_type(full_path)
        with open(full_path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _guess_content_type(path: str) -> str:
        if path.endswith(".html"):
            return "text/html; charset=utf-8"
        if path.endswith(".css"):
            return "text/css; charset=utf-8"
        if path.endswith(".js"):
            return "application/javascript; charset=utf-8"
        if path.endswith(".json"):
            return "application/json; charset=utf-8"
        if path.endswith(".svg"):
            return "image/svg+xml"
        if path.endswith(".png"):
            return "image/png"
        return "application/octet-stream"


def build_server(data_dir: str, static_root: str, port: int) -> tuple:
    """Build (but don't run) the server: loads/creates the data dir,
    loads everything into memory, and constructs the ThreadingHTTPServer.
    Returns (httpd, store) so a caller -- the CLI's main() below, or the
    Tkinter launcher running this in a background thread -- can start it,
    inspect it, and call httpd.shutdown() to stop it cleanly.

    Raises OSError (e.g. port already in use) or ValidationError-adjacent
    storage errors to the caller rather than printing and exiting, so a GUI
    can show them instead of a startup only visible in a terminal."""
    data_dir = os.path.abspath(data_dir)
    static_root = os.path.abspath(static_root)

    storage = Storage(data_dir)
    storage.ensure_dirs()
    store = Store(storage)

    Handler.store = store
    Handler.static_root = static_root

    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    return httpd, store


def startup_banner(httpd, store: Store, data_dir: str, static_root: str) -> str:
    port = httpd.server_address[1]
    lines = [
        "Single Song Planner -- v0.1",
        f"  data dir:   {os.path.abspath(data_dir)}",
        f"  static dir: {os.path.abspath(static_root)}",
        f"  songs loaded: {len(store.songs)}  setlists loaded: {len(store.setlists)}",
        "  reachable at:",
        f"    http://localhost:{port}/",
    ]
    for ip in local_addresses():
        lines.append(f"    http://{ip}:{port}/")
    lines.append("  (local network only -- this server is never meant to be reachable over the internet)")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Single Song Planner server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--data", default=paths.default_data_dir())
    parser.add_argument("--static", default=paths.default_static_dir())
    args = parser.parse_args()

    httpd, store = build_server(args.data, args.static, args.port)
    print(startup_banner(httpd, store, args.data, args.static))
    print("  Ctrl+C to stop.")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
