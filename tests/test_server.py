"""Server tests: REST API, live sync stream, transport, clips, export/import.

    python3 -m unittest discover -s tests

Standard library only. Each test class runs a real server on a free port
against a throwaway copy of the demo band (demo/), so nothing here touches
real data.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave
import zipfile
from unittest import mock
import array
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

import app  # noqa: E402
import click_track  # noqa: E402
import models  # noqa: E402
import qr  # noqa: E402
import timeline  # noqa: E402


class Server:
    def __init__(self):
        app.Handler.log_hook = lambda line: None  # keep test output readable
        self.tmp = tempfile.mkdtemp(prefix="ssp-test-")
        self.data = app.prepare_demo(os.path.join(self.tmp, "data"))
        self.httpd, self.store = app.build_server(self.data, os.path.join(ROOT, "web", "static"), 0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        app.stop_server(self.httpd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None, raw=None, ctype=None, client="test"):
        data = None
        headers = {"X-SSP-Client": client}
        if raw is not None:
            data, headers["Content-Type"] = raw, ctype
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                payload = r.read()
                return r.status, payload, r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def json(self, method, path, body=None, **kw):
        status, payload, _ = self.call(method, path, body, **kw)
        return status, (json.loads(payload) if payload else None)


class Listener:
    """A fake device holding the live event stream open."""

    def __init__(self, base, client="listener", player=None):
        q = f"/api/events?client={client}" + (f"&player={player}" if player else "")
        self.resp = urllib.request.urlopen(base + q, timeout=10)
        self.messages: "queue.Queue" = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.resp:
                line = line.decode().strip()
                if line.startswith("data: "):
                    self.messages.put(json.loads(line[6:]))
        except Exception:  # noqa: BLE001 - stream closed
            pass

    def wait_for(self, kind, timeout=5, cond=lambda m: True):
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = self.messages.get(timeout=end - time.time())
            except queue.Empty:
                break
            if m["type"] == kind and cond(m):
                return m
        raise AssertionError(f"no {kind!r} message within {timeout}s")

    def close(self):
        self.resp.close()


def demo_song(server, title):
    return next(s for s in server.store.songs.values() if s["title"] == title)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Server()

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    def test_state_and_demo_loaded(self):
        status, st = self.s.json("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(st["band"]["name"], "The Paper Lanterns")
        self.assertGreaterEqual(len(st["songs"]), 6)
        self.assertEqual(len(st["setlists"]), 2)
        self.assertIn("duration_ms", st["songs"][0])

    def test_song_crud_and_validation(self):
        status, song = self.s.json("POST", "/api/songs", {"title": "Test Tune", "default_bpm": 100})
        self.assertEqual(status, 201)
        song["sections"] = [{"id": "aaa", "label": "A", "order": 0, "bars": 4, "bpm": None,
                             "count_in": {"bars": 1, "style": "click"}, "hints": []}]
        self.assertEqual(self.s.json("PUT", f"/api/songs/{song['id']}", song)[0], 200)
        bad = dict(song, default_bpm=999)
        self.assertEqual(self.s.json("PUT", f"/api/songs/{song['id']}", bad)[0], 400)
        bad = dict(song, sections=[dict(song["sections"][0], count_in={"bars": 20, "style": "click"})])
        self.assertEqual(self.s.json("PUT", f"/api/songs/{song['id']}", bad)[0], 400)
        self.assertEqual(self.s.json("GET", "/api/songs/nope")[0], 404)
        self.assertEqual(self.s.call("DELETE", f"/api/songs/{song['id']}")[0], 204)

    def test_static_is_locked_down(self):
        status, body, headers = self.s.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.s.call("GET", "/../server/app.py")[0] in (403, 404), True)
        self.assertEqual(self.s.call("GET", "/%2e%2e/server/app.py")[0] in (403, 404), True)

    def test_click_track(self):
        song = demo_song(self.s, "Harbour Lights")
        status, body, headers = self.s.call("GET", f"/api/songs/{song['id']}/click.wav?sound=tick")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        with wave.open(io.BytesIO(body)) as w:
            seconds = w.getnframes() / w.getframerate()
        self.assertAlmostEqual(seconds, timeline.duration_ms(song) / 1000, delta=0.01)
        self.assertEqual(self.s.call("GET", f"/api/songs/{song['id']}/click.wav?sound=cowbell")[0], 400)

    def test_click_track_with_device_options(self):
        """0.10: the .wav follows the device's click choices."""
        song = demo_song(self.s, "Harbour Lights")
        base = f"/api/songs/{song['id']}/click.wav?sound=wood"
        _, plain, _ = self.s.call("GET", base)
        status, body, _ = self.s.call("GET", base + "&subdivision=16&voice=1&channel=left&sub=0.5")
        self.assertEqual(status, 200)
        with wave.open(io.BytesIO(body)) as w:
            self.assertEqual(w.getnchannels(), 2)
            frames = w.readframes(w.getnframes())
        pcm = array.array("h", frames)
        if sys.byteorder == "big":
            pcm.byteswap()
        self.assertGreater(max(abs(x) for x in pcm[0::2]), 1000)  # left: the click
        self.assertEqual(max(abs(x) for x in pcm[1::2]), 0)         # right: silent
        # subdivisions add sound between the beats
        with wave.open(io.BytesIO(plain)) as w:
            mono = array.array("h", w.readframes(w.getnframes()))
        self.assertGreater(sum(1 for x in pcm[0::2] if x), sum(1 for x in mono if x))
        # count-in only: silent after the count-in
        _, only, _ = self.s.call("GET", base + "&mode=countin")
        with wave.open(io.BytesIO(only)) as w:
            rate = w.getframerate()
            mono = array.array("h", w.readframes(w.getnframes()))
        first_bar_ms = timeline.build(song)["bars"][1]["start_ms"]
        self.assertEqual(max(abs(x) for x in mono[int((first_bar_ms + 50) * rate / 1000):]), 0)

    def test_setlist_practice_pack(self):
        sl = next(iter(self.s.store.setlists.values()))
        status, body, headers = self.s.call("GET", f"/api/setlists/{sl['id']}/clicks.zip?sound=beep&subdivision=8")
        self.assertEqual(status, 200)
        self.assertIn(".zip", headers["Content-Disposition"])
        names = zipfile.ZipFile(io.BytesIO(body)).namelist()
        playable = [x for x in sl["songs"] if x in self.s.store.songs and self.s.store.songs[x]["sections"]]
        self.assertEqual(len(names), len(playable))
        self.assertTrue(names[0].startswith("01 ") and names[0].endswith(".wav"))
        self.assertEqual(self.s.call("GET", "/api/setlists/nope/clicks.zip")[0], 404)

    def test_bundle_for_solo_mode(self):
        status, b = self.s.json("GET", "/api/bundle")
        self.assertEqual(status, 200)
        self.assertEqual(len(b["songs"]), len(self.s.store.songs))
        self.assertIn("sections", b["songs"][0])
        self.assertEqual(len(b["setlists"]), len(self.s.store.setlists))

    def test_static_extras_for_tablets(self):
        status, body, headers = self.s.call("GET", "/manifest.webmanifest")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["display"], "standalone")
        self.assertEqual(self.s.call("GET", "/apple-touch-icon.png")[2]["Content-Type"], "image/png")
        for word in ("one", "two", "three", "four"):
            self.assertEqual(self.s.call("GET", f"/voice/{word}.wav")[0], 200)
        # Safari needs byte ranges to play the keep-awake video
        req = urllib.request.Request(self.s.base + "/keepawake.mp4", headers={"Range": "bytes=0-9"})
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status, 206)
            self.assertEqual(len(r.read()), 10)
            self.assertTrue(r.headers["Content-Range"].startswith("bytes 0-9/"))

    def test_wifi_qr_and_terminal_qr(self):
        self.assertEqual(qr.wifi_text("SSP;Band", "pa:ss"), "WIFI:T:WPA;S:SSP\\;Band;P:pa\\:ss;;")
        status, body, _ = self.s.call("GET", "/api/qr.svg?text=" + urllib.request.quote(qr.wifi_text("SSP-Band", "secret123")))
        self.assertEqual(status, 200)
        app.Handler.wifi_ssid, app.Handler.wifi_password = "SSP-Band", "secret123"
        try:
            _, info = self.s.json("GET", "/api/connect")
            self.assertEqual(info["wifi"]["ssid"], "SSP-Band")
        finally:
            app.Handler.wifi_ssid = app.Handler.wifi_password = None
        self.assertIn("\u2588", qr.terminal("http://ssp.local/"))

    def test_click_samples_match_swiss_knife_formulas(self):
        # first-beat beep starts at zero and is a 25 ms decaying sine
        hi, lo = click_track.sounds("beep")
        self.assertEqual(len(hi), click_track.RATE * 25 // 1000)
        self.assertEqual(hi[0], 0)
        self.assertGreater(max(hi), max(lo))
        # tick noise is deterministic
        self.assertEqual(list(click_track.sounds("tick")[0][:10]), list(click_track.sounds("tick")[0][:10]))

    def test_qr_svg_and_connect(self):
        status, body, headers = self.s.call("GET", "/api/qr.svg?text=" + urllib.request.quote("http://192.168.1.5:8420/"))
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"<svg"))
        self.assertEqual(self.s.call("GET", "/api/qr.svg?text=javascript:alert(1)")[0], 400)
        status, info = self.s.json("GET", "/api/connect")
        self.assertEqual(status, 200)
        self.assertIn("addresses", info)

    def test_qr_decodes(self):
        try:
            import cv2  # noqa: F401 - optional, dev machines only
            import numpy as np
        except ImportError:
            self.skipTest("opencv not installed")
        text = "http://192.168.100.200:8420/#/live?player=abcdef123456"
        m = qr.encode(text)
        scale, quiet = 8, 4
        n = len(m) + 2 * quiet
        img = np.full((n * scale, n * scale), 255, dtype=np.uint8)
        for y, row in enumerate(m):
            for x, v in enumerate(row):
                if v:
                    img[(y + quiet) * scale:(y + quiet + 1) * scale, (x + quiet) * scale:(x + quiet + 1) * scale] = 0
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        self.assertEqual(decoded, text)

    def test_export_page_escapes_and_filters(self):
        song = demo_song(self.s, "Harbour Lights")
        band = self.s.store.get_band()
        sam = next(p for p in band["players"] if p["name"] == "Sam")
        status, body, _ = self.s.call("GET", f"/export/song/{song['id']}")
        page = body.decode()
        self.assertEqual(status, 200)
        self.assertIn("Brushes", page)  # Ruby's hint, on the whole-band chart
        status, body, _ = self.s.call("GET", f"/export/song/{song['id']}?player={sam['id']}")
        page = body.decode()
        self.assertIn("Root notes only", page)
        self.assertNotIn("Brushes", page)  # not Sam's
        # titles are escaped
        _, s2 = self.s.json("POST", "/api/songs", {"title": "<script>x</script>"})
        _, body, _ = self.s.call("GET", f"/export/song/{s2['id']}")
        self.assertNotIn(b"<script>x", body)
        sl = next(iter(self.s.store.setlists.values()))
        self.assertEqual(self.s.call("GET", f"/export/setlist/{sl['id']}")[0], 200)

    def test_audio_upload_serve_and_cleanup(self):
        status, res = self.s.json("POST", "/api/audio", raw=b"RIFFfakewav", ctype="audio/wav")
        self.assertEqual(status, 201)
        ref = res["ref"]
        self.assertTrue(models.AUDIO_REF.match(ref))
        status, body, headers = self.s.call("GET", f"/api/audio/{ref}")
        self.assertEqual((status, body, headers["Content-Type"]), (200, b"RIFFfakewav", "audio/wav"))
        self.assertEqual(self.s.call("GET", "/api/audio/..%2Fband.json")[0], 404)
        self.assertEqual(self.s.json("POST", "/api/audio", raw=b"x", ctype="text/html")[0], 400)
        # attach to two hints (a duplicated section shares a clip), drop one, then both
        _, song = self.s.json("POST", "/api/songs", {"title": "Clip test"})
        sec = lambda sid: {"id": sid, "label": sid, "order": 0, "bars": 2, "bpm": None,  # noqa: E731
                           "count_in": {"bars": 0, "style": "none"},
                           "hints": [{"id": sid + "h", "text": "x", "audio": ref, "visibility": "all"}]}
        song["sections"] = [sec("a"), sec("b")]
        self.s.json("PUT", f"/api/songs/{song['id']}", song)
        path = self.s.store.storage.audio_path(ref)
        song["sections"] = [sec("a")]
        self.s.json("PUT", f"/api/songs/{song['id']}", song)
        self.assertTrue(os.path.exists(path), "still used by the other hint")
        self.s.call("DELETE", f"/api/songs/{song['id']}")
        self.assertFalse(os.path.exists(path), "no longer used anywhere")

    def test_export_import_round_trip_with_clip(self):
        song = demo_song(self.s, "Harbour Lights")
        status, body, headers = self.s.call("GET", f"/api/songs/{song['id']}/export")
        self.assertEqual(status, 200)
        bundle = json.loads(body)
        self.assertEqual(len(bundle["audio"]), 1)
        status, imported = self.s.json("POST", "/api/songs/import", bundle)
        self.assertEqual(status, 201)
        self.assertNotEqual(imported["id"], song["id"])  # never overwrites
        clip = next(h["audio"] for s in imported["sections"] for h in s["hints"] if h["audio"])
        orig = next(h["audio"] for s in song["sections"] for h in s["hints"] if h["audio"])
        self.assertNotEqual(clip, orig)
        self.assertEqual(self.s.call("GET", f"/api/audio/{clip}")[1], base64.b64decode(bundle["audio"][orig]))
        self.assertEqual(self.s.json("POST", "/api/songs/import", {"hello": 1})[0], 400)

    def test_removing_player_resets_their_hints(self):
        _, band = self.s.json("GET", "/api/band")
        jonas = next(p for p in band["players"] if p["name"] == "Jonas")
        band2 = dict(band, players=[p for p in band["players"] if p["id"] != jonas["id"]])
        self.assertEqual(self.s.json("PUT", "/api/band", band2)[0], 200)
        for song in self.s.store.songs.values():
            for sec in song["sections"]:
                for h in sec["hints"]:
                    self.assertNotEqual(h["visibility"], jonas["id"])
        self.s.json("PUT", "/api/band", band)  # put him back for other tests


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.s = Server()

    def tearDown(self):
        self.s.close()

    def test_edit_is_broadcast_with_origin(self):
        lst = Listener(self.s.base)
        lst.wait_for("presence")
        song = demo_song(self.s, "Slow Tide")
        song = json.loads(json.dumps(song))
        song["title"] = "Slow Tide (new arrangement)"
        self.s.json("PUT", f"/api/songs/{song['id']}", song, client="laptop")
        m = lst.wait_for("song", cond=lambda m: m["data"]["id"] == song["id"])
        self.assertEqual(m["data"]["title"], "Slow Tide (new arrangement)")
        self.assertEqual(m["origin"], "laptop")
        lst.close()

    def test_presence_tracks_players(self):
        band = self.s.store.get_band()
        ruby = next(p for p in band["players"] if p["name"] == "Ruby")
        a = Listener(self.s.base, "tabA", ruby["id"])
        m = a.wait_for("presence", cond=lambda m: any(c["client_id"] == "tabA" for c in m["data"]))
        self.assertEqual(next(c for c in m["data"] if c["client_id"] == "tabA")["player_id"], ruby["id"])
        self.assertEqual(self.s.store.hub.player_name(band, "tabA"), "Ruby")
        a.close()

    def test_transport_run_positions_and_finish(self):
        lst = Listener(self.s.base)
        lst.wait_for("presence")
        _, song = self.s.json("POST", "/api/songs", {"title": "Short", "default_bpm": 400, "sections": [
            {"id": "x1", "label": "A", "order": 0, "bars": 1, "bpm": None, "count_in": {"bars": 0, "style": "none"}, "hints": []},
            {"id": "x2", "label": "B", "order": 1, "bars": 1, "bpm": None, "count_in": {"bars": 0, "style": "none"}, "hints": []},
        ]})
        sl = self.s.json("POST", "/api/setlists", {"name": "S", "songs": [song["id"], demo_song(self.s, "Slow Tide")["id"]]})[1]
        self.s.json("POST", "/api/transport", {"action": "cue", "song_id": song["id"], "setlist_id": sl["id"]})
        status, snap = self.s.json("POST", "/api/transport", {"action": "start"}, client="drummer")
        self.assertEqual(status, 200)
        self.assertEqual(snap["state"], "running")
        self.assertEqual(snap["setlist_id"], sl["id"])
        # lead-in bar + 2 bars at 400 BPM = 1.8 s, plus 1.5 s lead time
        self.assertEqual(len(snap["timeline"]["bars"]), 3)
        self.assertTrue(snap["timeline"]["bars"][0]["count_in"])
        self.assertGreater(snap["started_at"], time.time() * 1000)
        seen = set()
        end = time.time() + 6
        while time.time() < end:
            m = lst.messages.get(timeout=6)
            if m["type"] == "position":
                seen.add(m["data"]["bar_index"])
            if m["type"] == "transport" and m["data"].get("finished"):
                self.assertEqual(m["data"]["state"], "stopped")
                # the next song in the setlist is cued, ready to go
                self.assertEqual(m["data"]["song_id"], demo_song(self.s, "Slow Tide")["id"])
                break
        else:
            self.fail("run never finished")
        self.assertEqual(seen, {0, 1, 2})
        lst.close()

    def test_transport_stop_next_prev(self):
        sl = next(s for s in self.s.store.setlists.values() if s["name"] == "Friday at the Harbour Bar")
        self.s.json("POST", "/api/transport", {"action": "cue", "song_id": sl["songs"][0], "setlist_id": sl["id"]})
        self.assertEqual(self.s.json("POST", "/api/transport", {"action": "next"})[1]["song_id"], sl["songs"][1])
        self.assertEqual(self.s.json("POST", "/api/transport", {"action": "prev"})[1]["song_id"], sl["songs"][0])
        self.assertEqual(self.s.json("POST", "/api/transport", {"action": "prev"})[1]["song_id"], sl["songs"][0])
        self.s.json("POST", "/api/transport", {"action": "start", "start_section_id": None})
        st = self.s.json("POST", "/api/transport", {"action": "stop"})[1]
        self.assertEqual(st["state"], "stopped")
        self.assertEqual(st["song_id"], sl["songs"][0])
        self.assertEqual(self.s.json("POST", "/api/transport", {"action": "dance"})[0], 400)

    def test_deleting_cued_song_uncues(self):
        song = demo_song(self.s, "Paper Boats")
        self.s.json("POST", "/api/transport", {"action": "cue", "song_id": song["id"]})
        self.s.call("DELETE", f"/api/songs/{song['id']}")
        self.assertIsNone(self.s.json("GET", "/api/transport")[1]["song_id"])

    def test_stop_server_closes_streams(self):
        lst = Listener(self.s.base)
        lst.wait_for("presence")
        port = self.s.httpd.server_address[1]
        app.stop_server(self.s.httpd)
        self.s.close = lambda: shutil.rmtree(self.s.tmp, ignore_errors=True)
        import socket
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1)


class DemoSwitchTests(unittest.TestCase):
    def test_switch_to_demo_and_back_leaves_band_untouched(self):
        app.Handler.log_hook = lambda line: None
        tmp = tempfile.mkdtemp(prefix="ssp-test-")
        try:
            home = os.path.join(tmp, "band")
            httpd, store = app.build_server(home, os.path.join(ROOT, "web", "static"), 0)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            s = Server.__new__(Server)
            s.base = f"http://127.0.0.1:{httpd.server_address[1]}"
            s.json("POST", "/api/songs", {"title": "Our Song"})
            lst = Listener(s.base)
            lst.wait_for("presence")
            status, st = s.json("POST", "/api/demo", {"on": True})
            self.assertEqual((status, st), (200, {"on": True, "can_return": True}))
            self.assertEqual(lst.wait_for("reload")["data"]["on"], True)
            titles = {x["title"] for x in s.json("GET", "/api/songs")[1]}
            self.assertIn("Harbour Lights", titles)
            self.assertNotIn("Our Song", titles)
            demo_tmp = store._demo_tmp
            # edits in the demo go to the throwaway copy
            s.json("POST", "/api/songs", {"title": "Demo scribble"})
            self.assertEqual(s.json("POST", "/api/demo", {"on": False})[1], {"on": False, "can_return": False})
            titles = {x["title"] for x in s.json("GET", "/api/songs")[1]}
            self.assertEqual(titles, {"Our Song"})
            self.assertFalse(os.path.exists(demo_tmp), "demo copy cleaned up")
            self.assertEqual(len(os.listdir(os.path.join(home, "songs"))), 1)
            lst.close()
            app.stop_server(httpd)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_demo_only_server_cannot_go_back(self):
        s = Server()  # started on the demo alone, like `--demo`
        try:
            s.store.demo = True
            s.store.home_dir = None
            self.assertEqual(s.json("GET", "/api/state")[1]["demo"], {"on": True, "can_return": False})
            self.assertEqual(s.json("POST", "/api/demo", {"on": False})[0], 400)
        finally:
            s.close()


class StorageCompatTests(unittest.TestCase):
    def test_v01_song_without_new_fields_still_loads(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "songs"))
            old = {"id": "c2fa753af214", "title": "Test", "default_bpm": 120, "sections": [
                {"id": "tmp-abc", "label": "Section", "order": 0, "bars": 4, "bpm": None,
                 "count_in": {"bars": 0, "style": "none"},
                 "hints": [{"id": "tmp-h", "text": "hi", "audio": None, "visibility": "all"}]}]}
            with open(os.path.join(tmp, "songs", "c2fa753af214.json"), "w") as f:
                json.dump(old, f)
            httpd, store = app.build_server(tmp, os.path.join(ROOT, "web", "static"), 0)
            self.assertIn("c2fa753af214", store.songs)
            models.validate_song(store.songs["c2fa753af214"])
            self.assertTrue(os.path.isdir(os.path.join(tmp, "audio")))
            httpd.server_close()
        finally:
            shutil.rmtree(tmp)


IFCONFIG = """lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
	inet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
	inet 192.168.1.23 netmask 0xffffff00 broadcast 192.168.1.255
bridge100: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
	inet 192.168.2.1 netmask 0xffffff00 broadcast 192.168.2.255
en5: flags=8863<UP> mtu 1500
	inet 169.254.10.2 netmask 0xffff0000
"""
IPADDR = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536
    inet 127.0.0.1/8 scope host lo
3: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
    inet 10.42.0.1/24 brd 10.42.0.255 scope global noprefixroute wlan0
"""
IPCONFIG = """Wireless LAN adapter Local Area Connection* 2:
   IPv4 Address. . . . . . . . . . . : 192.168.137.1
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
Ethernet adapter Ethernet:
   IPv4 Address. . . . . . . . . . . : 10.0.0.5(Preferred)
   Default Gateway . . . . . . . . . : 10.0.0.1
"""


class AddressTests(unittest.TestCase):
    """The URL/QR addresses come from ifconfig / ip / ipconfig (ported from
    Swiss Knife), never from a DNS lookup of this computer's own name: that
    lookup hung every macOS release build (and could freeze the Connect
    screen at a venue with no internet)."""

    def test_addresses_from_each_system(self):
        self.assertEqual(app.parse_addresses(IFCONFIG, "Darwin"), ["192.168.1.23", "192.168.2.1"])
        self.assertEqual(app.parse_addresses(IPADDR, "Linux"), ["10.42.0.1"])
        self.assertEqual(app.parse_addresses(IPCONFIG, "Windows"), ["192.168.137.1", "10.0.0.5"])

    def test_hotspot_address_comes_first(self):
        class Result:
            stdout = IFCONFIG
        with mock.patch.object(app.platform, "system", lambda: "Darwin"), \
                mock.patch.object(app.subprocess, "run", lambda *a, **k: Result()):
            self.assertEqual(app.local_addresses(), ["192.168.2.1", "192.168.1.23"])

    def test_no_dns_lookup_of_this_computers_name(self):
        def boom(*_a, **_k):
            raise AssertionError("local_addresses() must not resolve the hostname")
        with mock.patch.object(app.socket, "gethostbyname_ex", boom), \
                mock.patch.object(app.socket, "gethostbyname", boom), \
                mock.patch.object(app.socket, "getaddrinfo", boom):
            started = time.monotonic()
            app.local_addresses()
            self.assertLess(time.monotonic() - started, 5)

    def test_falls_back_when_the_tool_is_missing(self):
        def missing(*_a, **_k):
            raise FileNotFoundError("ip")
        with mock.patch.object(app.subprocess, "run", missing):
            self.assertIsInstance(app.local_addresses(), list)


if __name__ == "__main__":
    unittest.main()
