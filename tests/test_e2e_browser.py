"""Two and three real browsers against one server -- the charter's "two
connected clients" smoke test, automated (it doesn't replace trying it on
a real tablet over real Wi-Fi before a push; see PROJECT_CHARTER.md 6).

Needs Playwright with Chromium (pip install playwright; playwright install
chromium). Skipped otherwise.

    python3 -m unittest tests.test_e2e_browser
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_server import Server, demo_song  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class BrowserSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Server()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.s.close()

    def page(self, **ctx):
        context = self.browser.new_context(bypass_csp=True, **ctx)  # lets the test evaluate JS; the app itself never needs it
        context.add_init_script("localStorage.setItem('ssp.asked','true')")
        pg = context.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        self.addCleanup(lambda: self.assertEqual(errors, [], "browser errors"))
        self.addCleanup(context.close)
        return pg

    def test_edit_shows_up_on_other_device_and_keeps_their_cursor(self):
        song = demo_song(self.s, "Lantern Parade")
        a, b = self.page(), self.page()
        for pg in (a, b):
            pg.goto(f"{self.s.base}/#/song/{song['id']}")
            pg.wait_for_selector(".section-card")
        # b is typing in the first hint of section 3 while a renames section 2
        b_input = b.locator(".hint-text").first
        b_input.click()
        a.locator(".section-label").nth(1).fill("Verse 1 (quiet)")
        b.wait_for_function("document.querySelectorAll('.section-label')[1].value === 'Verse 1 (quiet)'", timeout=5000)
        self.assertEqual(b.evaluate("document.activeElement.dataset.focusKey"),
                         b_input.get_attribute("data-focus-key"))
        # and the server has it
        self.assertEqual(self.s.store.songs[song["id"]]["sections"][1]["label"], "Verse 1 (quiet)")

    def test_three_devices_follow_one_run(self):
        song = demo_song(self.s, "Night Bus to Nowhere")
        band = self.s.store.get_band()
        ruby = next(p for p in band["players"] if p["name"] == "Ruby")["id"]
        lap = self.page(viewport={"width": 1280, "height": 800})
        tab = self.page(**self.pw.devices["iPad (gen 7) landscape"])
        phone = self.page(**self.pw.devices["iPhone 13"])
        lap.goto(f"{self.s.base}/#/song/{song['id']}")
        lap.wait_for_selector(".section-card")
        tab.goto(f"{self.s.base}/#/live?player={ruby}")
        phone.goto(f"{self.s.base}/#/live")
        lap.click("#song-live-btn")
        for pg in (tab, phone):
            pg.wait_for_function(f"document.getElementById('live-song-title').textContent === {song['title']!r}")
        tab.click("#live-start")
        lap.wait_for_selector("#live-stop:not(.hidden)")
        tab.wait_for_timeout(4200)  # 1.5 s lead + 1 count-in bar at 168 BPM + into the intro
        subs = [pg.locator("#now-label").inner_text() for pg in (lap, tab, phone)]
        self.assertEqual(len(set(subs)), 1, subs)
        self.assertEqual(lap.locator("#live-driver").inner_text(), "Started by Ruby")
        phone.click("#live-stop")
        tab.wait_for_selector("#live-start:not(.hidden)")
        self.assertEqual(self.s.store.hub and self.s.httpd.ssp_transport.snapshot()["state"], "stopped")

    def test_click_stops_when_screen_goes_off_and_comes_back(self):
        """Android keeps sound going with the screen off but drops the
        connection: the click must stop when the page is hidden, and pick
        the run back up when it's on screen again."""
        song = demo_song(self.s, "Slow Tide")
        pg = self.page(viewport={"width": 1024, "height": 768})
        pg.goto(f"{self.s.base}/#/song/{song['id']}")
        pg.wait_for_selector(".section-card")
        pg.click("#song-live-btn")
        pg.wait_for_selector("#live-chart .chart-row")
        pg.click("#click-toggle")  # the tap that allows sound
        pg.click("#live-start")
        pg.wait_for_function("window.SSP.metronome.job !== null")
        hide = """(h) => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => h});
                           document.dispatchEvent(new Event('visibilitychange')); }"""
        pg.evaluate(hide, True)
        self.assertTrue(pg.evaluate("window.SSP.metronome.job === null"))
        pg.evaluate(hide, False)
        pg.wait_for_function("window.SSP.metronome.job !== null", timeout=5000)
        # stopped elsewhere while hidden: coming back doesn't restart it
        pg.evaluate(hide, True)
        self.s.httpd.ssp_transport.stop()
        pg.evaluate(hide, False)
        pg.wait_for_selector("#live-start:not(.hidden)")
        self.assertTrue(pg.evaluate("window.SSP.metronome.job === null"))

    def test_sound_is_scheduled_before_the_engine_reports_running(self):
        """Safari starts its audio engine a moment after the tap; the click
        must not wait for that (it used to, and the iPad stayed silent)."""
        pg = self.page()
        pg.goto(f"{self.s.base}/#/live")
        pg.wait_for_selector("#live-view:not(.hidden)")
        ok = pg.evaluate("""() => { const m = window.SSP.metronome; m.unlock();
            const real = m.ctx; Object.defineProperty(real, 'state', {configurable: true, get: () => 'suspended'});
            return m.unlocked; }""")
        self.assertTrue(ok)

    # -- 0.10: drummer adoption ------------------------------------------------

    def test_paste_a_list_makes_songs_and_a_setlist(self):
        pg = self.page(viewport={"width": 1100, "height": 800})
        pg.goto(f"{self.s.base}/#/")
        pg.click("#empty-quick-btn")
        pg.click(".tab[data-tab=quick-list]")
        pg.fill("#q-paste", "Quick One - 128 - 3:00\n2. Quick Two, 96\nHarbour Lights")
        pg.wait_for_selector("#q-preview tr >> nth=3")
        pg.fill("#q-setlist-name", "Pasted set")
        pg.click("#q-list-add")
        pg.wait_for_function("location.hash.startsWith('#/setlist/')")
        sl = next(x for x in self.s.store.setlists.values() if x["name"] == "Pasted set")
        titles = [self.s.store.songs[i]["title"] for i in sl["songs"]]
        self.assertEqual(titles, ["Quick One", "Quick Two", "Harbour Lights"])
        one = self.s.store.songs[sl["songs"][0]]
        self.assertEqual(one["default_bpm"], 128)
        self.assertEqual(one["sections"][0]["bars"], 96)  # 3:00 at 128 BPM
        # pasting an existing title reuses it, no duplicate
        self.assertEqual(sum(1 for x in self.s.store.songs.values() if x["title"] == "Harbour Lights"), 1)

    def test_quick_song_with_tap_tempo(self):
        pg = self.page()
        pg.goto(f"{self.s.base}/#/")
        pg.click("#new-song-btn")
        pg.fill("#q-title", "Tapped Tune")
        for _ in range(5):
            pg.dispatch_event("#q-tap", "pointerdown")
            pg.wait_for_timeout(500)
        bpm = int(pg.input_value("#q-bpm"))
        self.assertTrue(100 <= bpm <= 135, bpm)  # ~120, give the test machine some slack
        pg.click("#q-add")
        pg.wait_for_function("document.getElementById('q-added').textContent.includes('Tapped Tune')")
        self.assertTrue(any(x["title"] == "Tapped Tune" for x in self.s.store.songs.values()))

    def test_click_settings_shape_the_live_click(self):
        song = demo_song(self.s, "Paper Boats")
        pg = self.page()
        pg.goto(f"{self.s.base}/#/song/{song['id']}")
        pg.wait_for_selector(".section-card")
        pg.click("#song-click-settings")
        pg.select_option("#ck-subdivision", "16")
        pg.check("#ck-voice")
        pg.select_option("#ck-channel", "right")
        opts = pg.evaluate("JSON.parse(localStorage.getItem('ssp.clickopts'))")
        self.assertEqual((opts["subdivision"], opts["voice"], opts["channel"]), ("16", True, "right"))
        pg.click("#ck-test")
        pg.wait_for_function("window.SSP.metronome.job !== null")
        kinds = pg.evaluate("window.SSP.metronome.job.events.map(e => e.kind)")
        self.assertEqual(kinds[:4], ["voice"] * 4)           # spoken count-in
        self.assertEqual(kinds.count("sub"), 2 * 4 * 3)        # 2 bars of 16ths
        pg.wait_for_function("document.getElementById('ck-diag').textContent.includes('running')")
        pg.keyboard.press("Escape")
        pg.reload()
        pg.wait_for_selector(".section-card")
        self.assertEqual(pg.evaluate("window.SSP.metronome.opts.subdivision"), "16")

    def test_drummer_gets_the_big_view(self):
        band = self.s.store.get_band()
        ruby = next(p for p in band["players"] if p["role"] == "Drums")["id"]
        mia = next(p for p in band["players"] if p["role"] == "Vocals")["id"]
        song = demo_song(self.s, "Harbour Lights")
        self.s.httpd.ssp_transport.cue(song["id"])
        drum = self.page(**self.pw.devices["iPad (gen 7) landscape"])
        drum.goto(f"{self.s.base}/#/live?player={ruby}")
        drum.wait_for_selector("#live-view.big")
        self.assertEqual(drum.inner_text("#st-bpm"), "124")
        voc = self.page()
        voc.goto(f"{self.s.base}/#/live?player={mia}")
        voc.wait_for_selector("#live-view:not(.hidden)")
        self.assertFalse(voc.evaluate("document.getElementById('live-view').classList.contains('big')"))
        drum.click("#live-start")
        drum.wait_for_function("document.getElementById('st-bar-k').textContent.startsWith('bar of')", timeout=6000)
        self.assertRegex(drum.inner_text("#st-bar"), r"^\d+/\d+$")
        self.s.httpd.ssp_transport.stop()

    def test_solo_mode_plays_on_its_own(self):
        song = demo_song(self.s, "Coffee at Midnight")
        self.s.httpd.ssp_transport.cue(song["id"])
        pg = self.page()
        pg.goto(f"{self.s.base}/#/live")
        pg.wait_for_function(f"document.getElementById('live-song-title').textContent === {song['title']!r}")
        pg.click("#live-solo")
        pg.click("#click-toggle")
        pg.click("#live-start")
        pg.wait_for_selector("#live-stop:not(.hidden)")
        pg.wait_for_function("window.SSP.metronome.job !== null")
        self.assertEqual(self.s.httpd.ssp_transport.snapshot()["state"], "stopped")  # the band isn't playing
        pg.click("#live-stop")
        pg.wait_for_selector("#live-start:not(.hidden)")
        pg.click("#live-solo")  # back with the band
        self.assertFalse(pg.evaluate("document.body.classList.contains('is-solo')"))

    def test_server_drop_mid_song_keeps_the_click_going(self):
        song = demo_song(self.s, "Slow Tide")
        pg = self.page()
        pg.goto(f"{self.s.base}/#/live")
        self.s.httpd.ssp_transport.cue(song["id"])
        pg.wait_for_function(f"document.getElementById('live-song-title').textContent === {song['title']!r}")
        pg.wait_for_timeout(1200)  # the device's own copy of the songs (solo needs it)
        pg.click("#click-toggle")
        pg.click("#live-start")
        pg.wait_for_function("window.SSP.metronome.job !== null")
        # the Wi-Fi drops: the event stream goes quiet
        pg.evaluate("() => { const S = window.SSPSync; S.source.close(); S.connected = false; S.emit('status', {data: false}); }")
        pg.wait_for_function("document.body.classList.contains('is-solo')", timeout=15000)
        self.assertTrue(pg.evaluate("window.SSP.metronome.job !== null"))
        self.assertIn("out of reach", pg.inner_text("#live-solo-note"))
        pg.evaluate("window.SSPSync.connect()")  # ...and comes back mid-song: stays solo until stopped
        pg.wait_for_function("window.SSPSync.connected")
        self.assertTrue(pg.evaluate("document.body.classList.contains('is-solo')"))
        pg.click("#live-stop")  # local stop; then it rejoins the band
        pg.wait_for_function("!document.body.classList.contains('is-solo')", timeout=10000)
        self.s.httpd.ssp_transport.stop()

    def test_live_view_tries_to_keep_the_screen_on(self):
        pg = self.page()
        pg.goto(f"{self.s.base}/#/live")
        pg.wait_for_selector("#live-view:not(.hidden)")
        pg.click("#live-start", trial=True)
        pg.mouse.click(5, 5)
        pg.wait_for_selector("video.keep-awake", state="attached")


if __name__ == "__main__":
    unittest.main()
