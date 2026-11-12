"""Barline Pocket (0.18) in a real browser, and a round trip back to the band.

Builds Pocket (tools/build_pocket.py) into a temp folder, serves it as the
static site it is, and drives it with Playwright: load the demo band, say
who's holding the device, add a note and change a section, keep working
offline, export everything, then import that file on the band's server,
where the song is merged (choosing the file's structure).

Needs Playwright with Chromium. Skipped otherwise.

    python3 -m unittest tests.test_pocket
"""

from __future__ import annotations

import copy
import functools
import http.server
import json
import os
import re
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_server import ROOT, Server, demo_song  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_pocket  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class PocketRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pocket-test-")
        out = os.path.join(cls.tmp.name, "barline")  # served from a sub-folder, like GitHub Pages
        build_pocket.build(out)
        cls.static = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=cls.tmp.name))
        threading.Thread(target=cls.static.serve_forever, daemon=True).start()
        cls.pocket_url = f"http://127.0.0.1:{cls.static.server_address[1]}/barline/"
        cls.s = Server()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.s.close()
        cls.static.shutdown()
        cls.static.server_close()
        cls.tmp.cleanup()

    def page(self, context):
        pg = context.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "net::ERR_INTERNET_DISCONNECTED" not in m.text else None)
        self.addCleanup(lambda: self.assertEqual(errors, [], "browser errors"))
        return pg

    def test_practise_on_pocket_then_merge_back_into_the_band(self):
        ctx = self.browser.new_context(accept_downloads=True)
        self.addCleanup(ctx.close)
        pg = self.page(ctx)
        pg.goto(self.pocket_url)
        pg.wait_for_selector("#pocket-demo-btn", state="visible")
        self.assertEqual(pg.text_content("#connection-label"), "Pocket: on this device")
        self.assertFalse(pg.is_visible("#connect-btn"))

        # the demo band, as a first file: everything new, players come along
        pg.click("#pocket-demo-btn")
        pg.wait_for_selector("#import-modal:not(.hidden)")
        self.assertIn("Sam (Bass)", pg.text_content("#import-extra"))
        pg.click("#import-apply")
        # ... and then it asks who's holding the device
        pg.wait_for_selector("#who-modal:not(.hidden)")
        pg.locator("#who-options .who-option", has=pg.locator("strong", has_text=re.compile("^Sam$"))).click()
        pg.wait_for_function("document.getElementById('who-btn').textContent === 'You: Sam · Bass'", timeout=3000)

        song = demo_song(self.s, "Lantern Parade")  # same demo band on the server, same ids
        pg.goto(self.pocket_url + f"#/song/{song['id']}")
        pg.wait_for_selector(".section-card")
        # a note at home, and the first section two bars longer
        card = pg.locator(".section-card").nth(1)
        card.locator(".add-hint").click()
        pg.keyboard.type("Pocket note: slide into the verse")
        card.locator(".hint-author:not(.hidden)").last.wait_for()  # this card, not a CSS position: the count-in block comes first
        self.assertEqual(card.locator(".hint-author:not(.hidden)").last.text_content(), "from Sam (Bass)")
        # ... with a voice memo (a file, as a phone without a microphone gives)
        clip = os.path.join(ROOT, "demo", "audio", sorted(os.listdir(os.path.join(ROOT, "demo", "audio")))[0])
        card.locator(".hint-file").last.set_input_files(clip)
        card.locator(".hint-play:not(.hidden)").first.wait_for()
        bars = pg.locator(".section-bars").first
        bars.fill(str(song["sections"][0]["bars"] + 2))
        pg.wait_for_timeout(900)  # the save is debounced

        # offline: the service worker has every file, the songs are in IndexedDB
        pg.evaluate("navigator.serviceWorker.ready")
        pg.reload()
        pg.wait_for_function("navigator.serviceWorker.controller !== null")
        ctx.set_offline(True)
        pg.reload()
        pg.wait_for_selector(".section-card")
        self.assertIn("Pocket note", pg.evaluate("[...document.querySelectorAll('.hint-text')].map(i => i.value).join('|')"))

        # live on Pocket is always this device's own run
        pg.click("#song-live-btn")
        pg.wait_for_function(f"document.getElementById('live-song-title').textContent === {song['title']!r}")
        self.assertTrue(pg.evaluate("document.body.classList.contains('is-solo')"))
        pg.click("#live-start")
        pg.wait_for_selector("#live-stop:not(.hidden)")
        pg.click("#live-stop")
        pg.click("#live-exit")
        ctx.set_offline(False)

        # everything, as one file
        pg.click("#nav-band")
        with pg.expect_download() as dl:
            pg.click("#export-all-btn")
        path = os.path.join(self.tmp.name, "everything.ssp.json")
        dl.value.save_as(path)
        with open(path, encoding="utf-8") as f:
            exported = json.load(f)
        self.assertEqual(exported["ssp_export"], 2)
        self.assertEqual(len(exported["songs"]), len(self.s.store.songs))

        # meanwhile at rehearsal, Ruby added a note on the band's server
        ruby = next(p for p in self.s.store.band["players"] if p["name"] == "Ruby")
        self.s.json("POST", "/api/presence", {"client": "rubys-tablet", "player_id": ruby["id"]})
        server_song = copy.deepcopy(self.s.store.songs[song["id"]])
        server_song["sections"][2]["hints"].append({"id": "rubynote01", "text": "Ruby: fill before the chorus", "audio": None, "visibility": "all"})
        self.assertEqual(self.s.json("PUT", f"/api/songs/{song['id']}", server_song, client="rubys-tablet")[0], 200)

        # back with the band: import the Pocket file on the server
        band = self.browser.new_context()
        band.add_init_script("localStorage.setItem('ssp.asked','true')")
        self.addCleanup(band.close)
        bp = self.page(band)
        bp.goto(self.s.base + "/")
        bp.wait_for_selector("#song-list li")
        bp.set_input_files("#import-file", path)
        bp.wait_for_selector("#import-modal:not(.hidden)")
        item = bp.locator(".import-merge", has_text=song["title"])
        self.assertIn("1 new hint (1 from Sam (Bass))", item.text_content())
        self.assertTrue(bp.is_disabled("#import-apply"))  # the structures differ: no silent default
        item.locator("button", has_text="Keep the file's").click()
        self.assertFalse(bp.is_disabled("#import-apply"))
        bp.click("#import-apply")
        bp.wait_for_selector("#import-modal.hidden", state="attached")

        merged = self.s.store.songs[song["id"]]
        self.assertEqual(merged["sections"][0]["bars"], song["sections"][0]["bars"] + 2)  # the file's structure
        texts = {h["text"]: h for s in merged["sections"] for h in s["hints"]}
        self.assertEqual(texts["Pocket note: slide into the verse"]["author"]["name"], "Sam")
        ref = texts["Pocket note: slide into the verse"]["audio"]
        self.assertTrue(ref and os.path.isfile(self.s.store.storage.audio_path(ref)))  # the memo came across
        self.assertEqual(texts["Ruby: fill before the chorus"]["author"]["name"], "Ruby")  # nothing lost
        self.assertEqual(len(self.s.store.songs), len(exported["songs"]))  # merged, not doubled
        # and the editor shows who wrote it
        bp.goto(self.s.base + f"/#/song/{song['id']}")
        bp.wait_for_selector(".section-card")
        self.assertIn("Sam (Bass)", bp.evaluate("[...document.querySelectorAll('.hint-author')].map(e => e.textContent).join('|')"))


    def test_leave_the_demo_and_use_offline(self):
        ctx = self.browser.new_context()
        self.addCleanup(ctx.close)
        pg = self.page(ctx)
        pg.goto(self.pocket_url)
        pg.wait_for_selector("#pocket-demo-btn", state="visible")
        # the three start buttons sit on one line
        tops = pg.evaluate("['empty-quick-btn','pocket-import-btn','pocket-demo-btn'].map(i => document.getElementById(i).getBoundingClientRect().top)")
        self.assertEqual(len(set(tops)), 1, tops)

        # Use offline: this browser's steps open, and it says whether it's ready
        pg.click("#pocket-offline-btn")
        pg.wait_for_selector("#offline-modal:not(.hidden)")
        self.assertTrue(pg.evaluate("document.querySelector('#offline-guides details[data-browser=chrome]').open"))
        pg.wait_for_function("document.getElementById('offline-status').classList.contains('ok')")
        self.assertIn("Ready to work with no internet", pg.text_content("#offline-status"))
        pg.click("#offline-modal [data-close]")

        pg.click("#pocket-demo-btn")
        pg.wait_for_selector("#import-modal:not(.hidden)")
        pg.click("#import-apply")
        pg.wait_for_selector("#who-modal:not(.hidden)")
        pg.click("#who-modal [data-close]")
        pg.wait_for_selector("#demo-banner:not(.hidden)")
        self.assertEqual(pg.text_content("#demo-off-btn"), "Leave the demo")
        pg.reload()  # the demo is remembered
        pg.wait_for_selector("#demo-banner:not(.hidden)")
        pg.wait_for_selector("#who-modal:not(.hidden)")  # nobody chosen yet: it asks again
        pg.click("#who-modal [data-close]")

        # importing a band file while in the demo offers to leave it first
        song = demo_song(self.s, "Slow Tide")
        path = os.path.join(self.tmp.name, "one-song.ssp.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ssp_export": 1, "song": dict(song, id="ownsong001", title="Our own song"), "audio": {}}, f)
        pg.once("dialog", lambda d: d.accept())
        pg.set_input_files("#import-file", path)
        pg.wait_for_function("document.querySelectorAll('#song-list li').length === 1")
        self.assertTrue(pg.is_hidden("#demo-banner"))
        self.assertIn("Our own song", pg.text_content("#song-list"))

        # back into the demo, then out with the banner's button
        pg.click("#nav-band")
        pg.once("dialog", lambda d: d.accept())
        pg.click("#pocket-wipe-btn")
        pg.wait_for_selector("#pocket-demo-btn", state="visible")
        pg.click("#pocket-demo-btn")
        pg.wait_for_selector("#import-modal:not(.hidden)")
        pg.click("#import-apply")
        pg.wait_for_selector("#who-modal:not(.hidden)")
        pg.locator("#who-options .who-option strong", has_text="Ruby").click()
        pg.wait_for_selector("#demo-banner:not(.hidden)")
        pg.once("dialog", lambda d: d.accept())
        pg.click("#demo-off-btn")
        pg.wait_for_selector("#pocket-demo-btn", state="visible")
        self.assertTrue(pg.is_hidden("#demo-banner"))
        self.assertEqual(pg.locator("#song-list li").count(), 0)
        self.assertEqual(pg.text_content("#who-btn").strip(), "You: Whole band")


if __name__ == "__main__":
    unittest.main()
