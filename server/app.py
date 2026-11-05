#!/usr/bin/env python3
"""
SSP -- Song and Setlist Planner -- the one server.

A small, plain, stdlib-only Python app (same spirit as QLC+ Swiss Knife):
holds the in-memory data model (backed by the one-JSON-per-song storage in
storage.py), serves the single-page web app, exposes a small JSON REST API,
pushes every change to every connected device (events.py), and runs the
band's shared clock for live playback (transport.py). Headless-capable --
no GUI dependency, so this runs the same way on a laptop or a display-less
Raspberry Pi.

Local-network only, by design -- see PROJECT_CHARTER.md section 4. There is
no authentication beyond "on the same Wi-Fi and knows the URL": anyone on
that network can read and edit everything. The server makes no outbound
connections and sends no telemetry; it reads and writes only its data
folder.

Can also be driven programmatically (see build_server() / stop_server()
below) -- that's what launcher/gui.py does.

Usage:
    python3 app.py [--port 8420] [--data <path>] [--static <path>] [--demo]

    --demo serves a fresh copy of the fictional demo band (demo/) from a
    temporary folder, so trying things out never touches real songs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import click_track
import events
import export
import models
import paths
import qr
import timeline
import transport
from models import ValidationError
from storage import Storage
from version import VERSION

DEFAULT_PORT = 8420
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_IMPORT_BYTES = 40 * 1024 * 1024


# ---------------------------------------------------------------------------
# LAN address discovery (adapted from QLC+ Swiss Knife's
# core/stage_monitor.py local_addresses()).
# ---------------------------------------------------------------------------

def local_addresses() -> list:
    """Best-effort list of this machine's LAN IPv4 addresses, for printing
    a reachable URL on startup. The UDP "connect" never sends a packet --
    it only asks the OS which interface it would route through."""
    addrs = set()
    try:
        hostname = socket.gethostname()
        _, _, ips = socket.gethostbyname_ex(hostname)
        for ip in ips:
            if not ip.startswith("127."):
                addrs.add(ip)
    except socket.error:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            if not ip.startswith("127."):
                addrs.add(ip)
        finally:
            s.close()
    except OSError:
        pass
    return sorted(addrs)


# ---------------------------------------------------------------------------
# In-memory store -- the one source of truth while the server runs.
# Every change is saved to disk and broadcast to every connected device.
# ---------------------------------------------------------------------------

class Store:
    def __init__(self, storage: Storage, hub: events.Hub):
        self.storage = storage
        self.hub = hub
        self.lock = threading.RLock()
        self.band = storage.load_band()
        self.songs = storage.load_all_songs()
        self.setlists = storage.load_all_setlists()

    # -- band -------------------------------------------------------------
    def get_band(self) -> dict:
        with self.lock:
            return self.band

    def put_band(self, payload: dict, origin=None) -> dict:
        with self.lock:
            band = models.clean_band(payload, self.band)
            gone = {p["id"] for p in self.band.get("players", [])} - {p["id"] for p in band["players"]}
            self.band = band
            self.storage.save_band(band)
            # hints aimed at a player who left the band go back to everyone
            touched = []
            if gone:
                for song in self.songs.values():
                    hit = False
                    for s in song.get("sections", []):
                        for h in s.get("hints", []):
                            if h.get("visibility") in gone:
                                h["visibility"] = "all"
                                hit = True
                    if hit:
                        self.storage.save_song(song)
                        touched.append(song)
        self.hub.publish("band", band, origin)
        for song in touched:
            self.hub.publish("song", song, origin)
        return band

    # -- songs --------------------------------------------------------------
    def song_summary(self, s: dict) -> dict:
        return {
            "id": s["id"],
            "title": s["title"],
            "default_bpm": s["default_bpm"],
            "section_count": len(s.get("sections", [])),
            "total_bars": models.song_total_bars(s),
            "duration_ms": timeline.duration_ms(s),
        }

    def list_songs(self) -> list:
        with self.lock:
            return [self.song_summary(s) for s in sorted(self.songs.values(), key=lambda s: s["title"].lower())]

    def get_song(self, song_id: str) -> dict:
        with self.lock:
            song = self.songs.get(song_id)
            if song is None:
                raise KeyError(song_id)
            return song

    def _add_song(self, song: dict, origin=None) -> dict:
        with self.lock:
            models.validate_song(song)
            self.songs[song["id"]] = song
            self.storage.save_song(song)
        self.hub.publish("song", song, origin)
        return song

    def create_song(self, payload: dict, origin=None) -> dict:
        song = models.new_song(
            title=str(payload.get("title", "Untitled Song"))[:120],
            default_bpm=payload.get("default_bpm", 120),
        )
        if isinstance(payload.get("sections"), list):
            song["sections"] = payload["sections"]
        return self._add_song(song, origin)

    def import_song(self, payload: dict, origin=None) -> dict:
        with self.lock:
            song = export.unbundle(payload, self.storage, set(self.songs))
        return self._add_song(song, origin)

    def put_song(self, song_id: str, payload: dict, origin=None) -> dict:
        with self.lock:
            if song_id not in self.songs:
                raise KeyError(song_id)
            existing = self.songs[song_id]
            song = {
                "id": song_id,
                "title": str(payload.get("title", existing["title"]))[:120],
                "default_bpm": payload.get("default_bpm", existing["default_bpm"]),
                "sections": payload.get("sections", existing.get("sections", [])),
                "created_at": existing.get("created_at", models.now()),
                "updated_at": models.now(),
            }
            models.validate_song(song)
            dropped = models.audio_refs(existing) - models.audio_refs(song)
            self.songs[song_id] = song
            self.storage.save_song(song)
            self._collect_audio(dropped)
        self.hub.publish("song", song, origin)
        return song

    def delete_song(self, song_id: str, origin=None) -> None:
        touched = []
        with self.lock:
            if song_id not in self.songs:
                raise KeyError(song_id)
            dropped = models.audio_refs(self.songs[song_id])
            del self.songs[song_id]
            self.storage.delete_song(song_id)
            self._collect_audio(dropped)
            # a song can vanish out from under a setlist -- drop stale
            # references rather than let the setlist 404 on playback.
            for setlist in self.setlists.values():
                if song_id in setlist["songs"]:
                    setlist["songs"] = [s for s in setlist["songs"] if s != song_id]
                    self.storage.save_setlist(setlist)
                    touched.append(setlist)
        self.hub.publish("song_deleted", {"id": song_id}, origin)
        for setlist in touched:
            self.hub.publish("setlist", setlist, origin)

    def _collect_audio(self, refs: set) -> None:
        """Delete clips no song points at any more (a duplicated section
        shares its clip with the original, so count across all songs)."""
        if not refs:
            return
        still_used = set()
        for s in self.songs.values():
            still_used |= models.audio_refs(s)
        for ref in refs - still_used:
            self.storage.delete_audio(ref)

    # -- setlists ---------------------------------------------------------
    def list_setlists(self) -> list:
        with self.lock:
            out = []
            for sl in sorted(self.setlists.values(), key=lambda sl: sl["name"].lower()):
                present = [self.songs[s] for s in sl["songs"] if s in self.songs]
                out.append({
                    "id": sl["id"], "name": sl["name"], "song_count": len(sl["songs"]),
                    "duration_ms": sum(timeline.duration_ms(s) for s in present),
                })
            return out

    def get_setlist(self, setlist_id: str) -> dict:
        with self.lock:
            setlist = self.setlists.get(setlist_id)
            if setlist is None:
                raise KeyError(setlist_id)
            return setlist

    def create_setlist(self, payload: dict, origin=None) -> dict:
        with self.lock:
            setlist = models.new_setlist(name=str(payload.get("name", "New Setlist"))[:120])
            setlist["songs"] = payload.get("songs", [])
            models.validate_setlist(setlist)
            self.setlists[setlist["id"]] = setlist
            self.storage.save_setlist(setlist)
        self.hub.publish("setlist", setlist, origin)
        return setlist

    def put_setlist(self, setlist_id: str, payload: dict, origin=None) -> dict:
        with self.lock:
            if setlist_id not in self.setlists:
                raise KeyError(setlist_id)
            existing = self.setlists[setlist_id]
            setlist = {
                "id": setlist_id,
                "name": str(payload.get("name", existing["name"]))[:120],
                "songs": payload.get("songs", existing["songs"]),
            }
            models.validate_setlist(setlist)
            self.setlists[setlist_id] = setlist
            self.storage.save_setlist(setlist)
        self.hub.publish("setlist", setlist, origin)
        return setlist

    def delete_setlist(self, setlist_id: str, origin=None) -> None:
        with self.lock:
            if setlist_id not in self.setlists:
                raise KeyError(setlist_id)
            del self.setlists[setlist_id]
            self.storage.delete_setlist(setlist_id)
        self.hub.publish("setlist_deleted", {"id": setlist_id}, origin)


# ---------------------------------------------------------------------------
# HTTP handler -- JSON REST API under /api/, printable charts under
# /export/, static files otherwise. Locked-down static serving adapted from
# Swiss Knife's stage_monitor.py pattern.
# ---------------------------------------------------------------------------

_SAFE_FILENAME = re.compile(r"[^\w .,()+-]", re.UNICODE)


def _filename(text: str, suffix: str) -> str:
    base = _SAFE_FILENAME.sub("", str(text or "")).strip(" .")[:80] or "song"
    return base + suffix


class Handler(BaseHTTPRequestHandler):
    server_version = f"SSP/{VERSION}"
    store: Store = None  # set by build_server() before the server starts
    hub: events.Hub = None
    transport: transport.Transport = None
    static_root: str = None
    port: int = DEFAULT_PORT
    log_hook = None  # optional callable(str); set by the launcher GUI

    # -- helpers ------------------------------------------------------------
    def _origin(self):
        value = self.headers.get("X-SSP-Client", "")
        return value[:40] if value else None

    def _send(self, status: int, body: bytes, content_type: str, extra: dict = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload) -> None:
        if status == 204:
            self.send_response(204)
            self._security_headers()
            self.end_headers()
            return
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _download(self, body: bytes, content_type: str, filename: str) -> None:
        self._send(200, body, content_type, {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        })

    def _security_headers(self) -> None:
        # Same spirit as Swiss Knife's stage_monitor handler: this page has
        # no reason to load anything but itself.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")

    def _read_body(self, limit: int) -> bytes:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > limit:
            raise ValidationError(f"that's too big (over {limit // (1024 * 1024)} MB)")
        return self.rfile.read(length) if length else b""

    def _read_json_body(self, limit: int = MAX_JSON_BYTES) -> dict:
        raw = self._read_body(limit)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValidationError(f"invalid JSON body: {exc}") from exc
        if not isinstance(data, dict):
            raise ValidationError("expected a JSON object")
        return data

    def log_message(self, fmt, *args) -> None:  # noqa: A003 - stdlib signature
        line = f"[ssp] {self.address_string()} - {fmt % args}"
        if Handler.log_hook is not None:
            Handler.log_hook(line)
        else:
            sys.stderr.write(line + "\n")

    # -- routing --------------------------------------------------------
    def do_GET(self):  # noqa: N802 - stdlib naming
        if self.path.startswith("https://"):
            self._send_json(400, {"error": "this server is plain HTTP, not HTTPS"})
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._route_api("GET", parsed)
        elif parsed.path.startswith("/export/"):
            self._route_export(parsed)
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
        query = parse_qs(parsed.query)
        q = lambda k, d=None: (query.get(k) or [d])[0]  # noqa: E731
        origin = self._origin()
        store, tr = self.store, self.transport
        route = parts[1:]
        try:
            # -- live sync ---------------------------------------------------
            if route == ["events"] and method == "GET":
                return self._stream_events(q("client", ""), q("player"), q("device", ""))
            if route == ["time"] and method == "GET":
                return self._send_json(200, {"now": transport.now_ms()})
            if route == ["state"] and method == "GET":
                return self._send_json(200, {
                    "version": VERSION, "band": store.get_band(), "songs": store.list_songs(),
                    "setlists": store.list_setlists(), "transport": tr.snapshot(),
                    "presence": self.hub.presence(), "now": transport.now_ms(),
                })
            if route == ["presence"] and method == "POST":
                body = self._read_json_body()
                self.hub.set_player(str(body.get("client", ""))[:40], body.get("player_id"))
                return self._send_json(200, {"ok": True})
            if route == ["connect"] and method == "GET":
                return self._send_json(200, {
                    "port": self.port,
                    "addresses": [f"http://{ip}:{self.port}/" for ip in local_addresses()],
                })
            if route == ["qr.svg"] and method == "GET":
                text = q("text", "")
                if not text.startswith("http://") or len(text.encode("utf-8")) > qr.MAX_BYTES:
                    raise ValidationError("a QR code here is for an http:// address of up to 106 characters")
                return self._send(200, qr.svg(text).encode("utf-8"), "image/svg+xml")

            # -- transport ---------------------------------------------------
            if route == ["transport"] and method == "GET":
                return self._send_json(200, tr.snapshot())
            if route == ["transport"] and method == "POST":
                body = self._read_json_body()
                action = body.get("action")
                if action == "cue":
                    return self._send_json(200, tr.cue(body.get("song_id"), body.get("setlist_id"), origin))
                if action == "start":
                    lead = body.get("lead_ms", transport.LEAD_MS)
                    if not isinstance(lead, (int, float)):
                        raise ValidationError("lead_ms must be a number")
                    return self._send_json(200, tr.start(body.get("song_id"), body.get("setlist_id"),
                                                         body.get("start_section_id"), origin, lead))
                if action == "stop":
                    return self._send_json(200, tr.stop(origin))
                if action in ("next", "prev"):
                    return self._send_json(200, tr.step(1 if action == "next" else -1, origin))
                raise ValidationError("action is cue, start, stop, next or prev")

            # -- band ------------------------------------------------------
            if route == ["band"] and method == "GET":
                return self._send_json(200, store.get_band())
            if route == ["band"] and method == "PUT":
                return self._send_json(200, store.put_band(self._read_json_body(), origin))

            # -- songs -----------------------------------------------------
            if route == ["songs"] and method == "GET":
                return self._send_json(200, store.list_songs())
            if route == ["songs"] and method == "POST":
                return self._send_json(201, store.create_song(self._read_json_body(), origin))
            if route == ["songs", "import"] and method == "POST":
                return self._send_json(201, store.import_song(self._read_json_body(MAX_IMPORT_BYTES), origin))
            if len(route) == 2 and route[0] == "songs":
                if method == "GET":
                    return self._send_json(200, store.get_song(route[1]))
                if method == "PUT":
                    return self._send_json(200, store.put_song(route[1], self._read_json_body(), origin))
                if method == "DELETE":
                    store.delete_song(route[1], origin)
                    tr.song_deleted(route[1])
                    return self._send_json(204, None)
            if len(route) == 3 and route[0] == "songs" and method == "GET":
                song = store.get_song(route[1])
                if route[2] == "click.wav":
                    try:
                        wav = click_track.song_wav(song, q("sound"), q("count_in", "1") != "0")
                    except ValueError as exc:
                        raise ValidationError(str(exc)) from exc
                    sound = click_track.check_sound(q("sound"))
                    return self._download(wav, "audio/wav", _filename(f"{song['title']} click {sound}", ".wav"))
                if route[2] == "export":
                    body = json.dumps(export.bundle(song, store.storage), ensure_ascii=False, indent=1)
                    return self._download(body.encode("utf-8"), "application/json",
                                          _filename(song["title"], ".ssp.json"))
                if route[2] == "timeline":
                    return self._send_json(200, timeline.build(song, q("from")))

            # -- hint clips ------------------------------------------------
            if route == ["audio"] and method == "POST":
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/x-m4a": "m4a",
                       "audio/m4a": "m4a", "audio/aac": "aac", "audio/mpeg": "mp3", "audio/mp3": "mp3",
                       "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
                       "video/mp4": "m4a", "video/webm": "webm"}.get(ctype)
                if not ext:
                    raise ValidationError("that doesn't look like an audio file (webm, ogg, m4a, mp3, wav, aac)")
                data = self._read_body(models.MAX_AUDIO_BYTES)
                if not data:
                    raise ValidationError("the recording is empty")
                return self._send_json(201, {"ref": store.storage.save_audio(data, ext)})
            if len(route) == 2 and route[0] == "audio" and method == "GET":
                try:
                    path = store.storage.audio_path(route[1])
                except ValueError as exc:
                    raise KeyError(route[1]) from exc
                if not os.path.isfile(path):
                    raise KeyError(route[1])
                with open(path, "rb") as f:
                    data = f.read()
                return self._send(200, data, models.AUDIO_EXTS[route[1].rsplit(".", 1)[1]])

            # -- setlists ----------------------------------------------------
            if route == ["setlists"] and method == "GET":
                return self._send_json(200, store.list_setlists())
            if route == ["setlists"] and method == "POST":
                return self._send_json(201, store.create_setlist(self._read_json_body(), origin))
            if len(route) == 2 and route[0] == "setlists":
                if method == "GET":
                    return self._send_json(200, store.get_setlist(route[1]))
                if method == "PUT":
                    return self._send_json(200, store.put_setlist(route[1], self._read_json_body(), origin))
                if method == "DELETE":
                    store.delete_setlist(route[1], origin)
                    return self._send_json(204, None)

            self._send_json(404, {"error": f"no such route: {method} {parsed.path}"})
        except KeyError as exc:
            self._send_json(404, {"error": f"not found: {exc}"})
        except (ValidationError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001 - last-resort JSON error, never a stack trace to the client
            self._send_json(500, {"error": f"internal error: {exc}"})

    # -- live event stream ------------------------------------------------
    def _stream_events(self, client_id: str, player_id, device: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self._security_headers()
        self.end_headers()
        client = self.hub.subscribe(client_id[:40], player_id, device)

        def write(chunk: bytes) -> None:
            self.wfile.write(chunk)
            self.wfile.flush()

        try:
            self.hub.stream(client, write)
        except OSError:
            pass  # the device went away; hub.stream already unsubscribed it
        self.close_connection = True

    # -- printable charts -------------------------------------------------
    def _route_export(self, parsed) -> None:
        parts = [p for p in parsed.path.split("/") if p]
        player = (parse_qs(parsed.query).get("player") or [None])[0]
        store = self.store
        try:
            band = store.get_band()
            if len(parts) == 3 and parts[1] == "song":
                page = export.song_html(store.get_song(parts[2]), band, player)
            elif len(parts) == 3 and parts[1] == "setlist":
                page = export.setlist_html(store.get_setlist(parts[2]), store.songs, band, player)
            else:
                raise KeyError(parsed.path)
        except KeyError:
            return self._send_json(404, {"error": "not found"})
        self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")

    # -- static file serving -----------------------------------------------
    def _serve_static(self, url_path: str) -> None:
        if url_path == "/":
            url_path = "/index.html"
        safe_rel = os.path.normpath(url_path).lstrip("/\\")
        root = os.path.normpath(self.static_root)
        full_path = os.path.normpath(os.path.join(root, safe_rel))
        if not (full_path == root or full_path.startswith(root + os.sep)):
            self._send_json(403, {"error": "forbidden"})
            return
        if os.path.isdir(full_path) or not os.path.isfile(full_path):
            self._send_json(404, {"error": "not found"})
            return
        with open(full_path, "rb") as f:
            body = f.read()
        self._send(200, body, self._guess_content_type(full_path))

    @staticmethod
    def _guess_content_type(path: str) -> str:
        for ext, ctype in ((".html", "text/html; charset=utf-8"), (".css", "text/css; charset=utf-8"),
                           (".js", "application/javascript; charset=utf-8"),
                           (".json", "application/json; charset=utf-8"), (".svg", "image/svg+xml"),
                           (".png", "image/png"), (".ico", "image/x-icon"),
                           (".webmanifest", "application/manifest+json")):
            if path.endswith(ext):
                return ctype
        return "application/octet-stream"


class SSPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def build_server(data_dir: str, static_root: str, port: int) -> tuple:
    """Build (but don't run) the server: loads/creates the data dir, loads
    everything into memory, and constructs the HTTP server. Returns
    (httpd, store) so a caller -- the CLI's main() below, or the Tkinter
    launcher running this in a background thread -- can start it and later
    call stop_server(httpd) to stop it cleanly.

    Raises OSError (e.g. port already in use) to the caller rather than
    printing and exiting, so a GUI can show it."""
    data_dir = os.path.abspath(data_dir)
    static_root = os.path.abspath(static_root)

    storage = Storage(data_dir)
    storage.ensure_dirs()
    hub = events.Hub()
    store = Store(storage, hub)
    tr = transport.Transport(store, hub)

    httpd = SSPServer(("0.0.0.0", port), Handler)
    Handler.store = store
    Handler.hub = hub
    Handler.transport = tr
    Handler.static_root = static_root
    Handler.port = httpd.server_address[1]
    httpd.ssp_hub = hub
    httpd.ssp_transport = tr
    return httpd, store


def stop_server(httpd) -> None:
    """Stop a running server: end the live run, close every device's event
    stream (so nothing holds the port open), then stop serving."""
    tr = getattr(httpd, "ssp_transport", None)
    hub = getattr(httpd, "ssp_hub", None)
    if tr is not None:
        tr.shutdown()
    if hub is not None:
        hub.close()
    httpd.shutdown()
    httpd.server_close()


def prepare_demo(target: str = None) -> str:
    """A fresh copy of the demo band's data, ready to serve. Always a copy,
    so playing with the demo never changes the files in the repo."""
    target = target or tempfile.mkdtemp(prefix="ssp-demo-")
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(paths.demo_data_dir(), target)
    return target


def startup_banner(httpd, store: Store, data_dir: str, static_root: str) -> str:
    port = httpd.server_address[1]
    lines = [
        f"SSP -- Song and Setlist Planner -- v{VERSION}",
        f"  data dir:   {os.path.abspath(data_dir)}",
        f"  static dir: {os.path.abspath(static_root)}",
        f"  songs loaded: {len(store.songs)}  setlists loaded: {len(store.setlists)}",
        "  open on each phone/tablet (same Wi-Fi):",
    ]
    for ip in local_addresses():
        lines.append(f"    http://{ip}:{port}/")
    lines.append(f"    http://localhost:{port}/   (this computer)")
    lines.append("  (local network only -- this server is never meant to be reachable over the internet)")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="SSP - Song and Setlist Planner server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--data", default=None)
    parser.add_argument("--static", default=paths.default_static_dir())
    parser.add_argument("--demo", action="store_true",
                        help="serve a fresh, throwaway copy of the fictional demo band")
    args = parser.parse_args()

    data = prepare_demo() if args.demo else (args.data or paths.default_data_dir())
    httpd, store = build_server(data, args.static, args.port)
    print(startup_banner(httpd, store, data, args.static))
    if args.demo:
        print("  DEMO MODE: changes go to a temporary copy and are thrown away.")
    print("  Ctrl+C to stop.")

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nShutting down.")
        stop_server(httpd)


if __name__ == "__main__":
    main()
