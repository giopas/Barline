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

    def test_drag_a_setlist_song_and_the_song_list_follows(self):
        setlist = next(sl for sl in self.s.store.setlists.values() if sl["name"].startswith("Friday"))
        titles = lambda pg, sel: pg.eval_on_selector_all(sel, "ls => ls.map(l => l.textContent)")  # noqa: E731
        a, b = self.page(), self.page()
        for pg in (a, b):
            pg.goto(f"{self.s.base}/#/setlist/{setlist['id']}")
            pg.wait_for_selector("#setlist-songs li .drag-handle")
        first = titles(a, "#setlist-songs .setlist-song-title")
        # the song list on the left is in the setlist's order, the rest after
        self.assertEqual(titles(a, "#song-list li .item-name")[:len(first)], first)
        handle = a.locator("#setlist-songs li .drag-handle").nth(0).bounding_box()
        target = a.locator("#setlist-songs li").nth(2).bounding_box()
        a.mouse.move(handle["x"] + 4, handle["y"] + 4)
        a.mouse.down()
        for i in range(1, 11):
            a.mouse.move(handle["x"] + 4, handle["y"] + (target["y"] + target["height"] - 4 - handle["y"]) * i / 10)
        a.mouse.up()
        moved = first[1:3] + [first[0]] + first[3:]
        self.assertEqual(titles(a, "#setlist-songs .setlist-song-title"), moved)
        self.assertEqual(titles(a, "#song-list li .item-name")[:len(moved)], moved)
        # saved, and the other device's list follows
        b.wait_for_function(f"[...document.querySelectorAll('#setlist-songs .setlist-song-title')].map(e => e.textContent).join('|') === {('|'.join(moved))!r}", timeout=5000)
        self.assertEqual(titles(b, "#song-list li .item-name")[:len(moved)], moved)
        # search and tag filter: matching rows only, and no dragging while filtered
        a.fill("#setlist-search", "ballad")
        self.assertEqual(titles(a, "#setlist-songs .setlist-song-title"), ["Paper Boats", "Slow Tide"])
        self.assertTrue(a.evaluate("document.getElementById('setlist-songs').classList.contains('filtering')"))
        a.fill("#setlist-search", "")
        a.locator("#tag-filter .chip", has_text="Fast").click()
        self.assertEqual(titles(a, "#song-list li .item-name"), ["Night Bus to Nowhere", "Lantern Parade"])
        a.locator("#tag-filter .tag-clear").click()
        # put it back for the other tests
        self.s.store.put_setlist(setlist["id"], dict(setlist, songs=[s for s in setlist["songs"]]))

    def test_tag_a_song(self):
        song = demo_song(self.s, "Encore Jam")
        a = self.page()
        a.goto(f"{self.s.base}/#/song/{song['id']}")
        a.wait_for_selector("#song-tag-input")
        a.fill("#song-tag-input", "own SONG")  # takes the spelling already in use
        a.press("#song-tag-input", "Enter")
        a.fill("#song-tag-input", "Late night")
        a.press("#song-tag-input", "Enter")
        a.wait_for_function("document.querySelectorAll('#tag-filter .chip').length >= 9")
        for _ in range(50):
            if self.s.store.songs[song["id"]].get("tags") == ["Jam", "Encore", "Own song", "Late night"]:
                break
            a.wait_for_timeout(100)
        self.assertEqual(self.s.store.songs[song["id"]]["tags"], ["Jam", "Encore", "Own song", "Late night"])
        a.locator("#song-tag-chips .tag-remove").last.click()
        a.wait_for_timeout(800)
        self.assertEqual(self.s.store.songs[song["id"]]["tags"], ["Jam", "Encore", "Own song"])

    def test_count_ins_in_one_go(self):
        song = demo_song(self.s, "Paper Boats")
        a, b = self.page(), self.page()
        for pg in (a, b):
            pg.goto(f"{self.s.base}/#/song/{song['id']}")
            pg.wait_for_selector(".section-card")
        a.click("#song-countins-btn")
        a.wait_for_selector("#countin-modal:not(.hidden)")
        self.assertIn("This song", a.locator("#ci-scope option").first.inner_text())
        a.select_option("#ci-start-bars", "2")
        a.select_option("#ci-start-style", "sticks")
        a.select_option("#ci-chg-bars", "1")
        a.select_option("#ci-chg-style", "click")
        a.uncheck("#ci-keep")
        a.click("#ci-apply")
        a.wait_for_function("document.getElementById('ci-result').textContent.startsWith('Done')")
        n = len(song["sections"])
        want = [2] + [1] * (n - 1)
        # this device's editor, the other device's editor and the server agree
        js = "[...document.querySelectorAll('.count-in-bars')].map(i => +i.value).join()"
        a.wait_for_function(f"{js} === {','.join(map(str, want))!r}")
        b.wait_for_function(f"{js} === {','.join(map(str, want))!r}", timeout=5000)
        got = sorted(self.s.store.songs[song["id"]]["sections"], key=lambda x: x["order"])
        self.assertEqual([x["count_in"]["bars"] for x in got], want)
        self.assertEqual(got[0]["count_in"]["style"], "sticks")
        # and from a setlist, for every song in it
        sl = next(x for x in self.s.store.setlists.values())
        a.keyboard.press("Escape")
        a.goto(f"{self.s.base}/#/setlist/{sl['id']}")
        a.click("#setlist-countins-btn")
        self.assertIn(sl["name"], a.locator("#ci-scope option").first.inner_text())
        a.select_option("#ci-start-bars", "0")
        a.select_option("#ci-chg-bars", "")
        a.click("#ci-apply")
        a.wait_for_function("document.getElementById('ci-result').textContent !== ''")
        for sid in sl["songs"]:
            first = min(self.s.store.songs[sid]["sections"], key=lambda x: x["order"])
            self.assertEqual(first["count_in"]["style"], "none")

    def test_jump_to_a_section_and_nudge(self):
        song = demo_song(self.s, "Lantern Parade")
        secs = sorted(song["sections"], key=lambda x: x["order"])
        target = secs[2]
        self.s.httpd.ssp_transport.cue(song["id"])
        tab = self.page(**self.pw.devices["iPad (gen 7) landscape"])
        phone = self.page(**self.pw.devices["iPhone 13"])
        for pg in (tab, phone):
            pg.goto(f"{self.s.base}/#/live")
            pg.wait_for_function(f"document.getElementById('live-song-title').textContent === {song['title']!r}")
        tab.click("#live-start")
        phone.wait_for_selector("#live-jump-btn:not(.hidden)")
        tab.wait_for_timeout(2200)  # past the lead time
        run = self.s.httpd.ssp_transport.snapshot()["run"]
        # tablet: tap the row (arms it), then "Jump here"
        row = tab.locator(f"#live-chart .chart-row[data-section-id='{target['id']}']")
        row.click()
        self.assertIn("jump-armed", row.get_attribute("class"))
        row.locator(".chart-jump").click()
        for pg in (tab, phone):
            pg.wait_for_function(f"document.getElementById('now-label').textContent === {target['label']!r}", timeout=8000)
        snap = self.s.httpd.ssp_transport.snapshot()
        self.assertEqual((snap["run"], snap["rev"]), (run, 1))
        # phone: the Jump sheet, back to the first section
        phone.click("#live-jump-btn")
        phone.locator("#live-jump-list .jump-to").first.click()
        for pg in (tab, phone):
            pg.wait_for_function(f"document.getElementById('now-label').textContent === {secs[0]['label']!r}", timeout=8000)
        # nudge from the sheet and from the keyboard
        before = self.s.httpd.ssp_transport.snapshot()["started_at"]
        phone.click("#live-jump-btn")
        phone.click("#live-nudge summary")
        phone.click("#live-nudge [data-nudge='20']")
        tab.keyboard.press("]")
        for _ in range(50):
            snap = self.s.httpd.ssp_transport.snapshot()
            if snap["rev"] >= 4:
                break
            tab.wait_for_timeout(100)
        beat = snap["timeline"]["bars"][0]["beat_ms"]
        self.assertAlmostEqual(before - snap["started_at"], 20 + beat, delta=1)
        tab.click("#live-stop")
        phone.wait_for_selector("#live-jump-btn.hidden", state="attached")

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
        pg.wait_for_function("window.Barline.metronome.job !== null")
        hide = """(h) => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => h});
                           document.dispatchEvent(new Event('visibilitychange')); }"""
        pg.evaluate(hide, True)
        self.assertTrue(pg.evaluate("window.Barline.metronome.job === null"))
        pg.evaluate(hide, False)
        pg.wait_for_function("window.Barline.metronome.job !== null", timeout=5000)
        # stopped elsewhere while hidden: coming back doesn't restart it
        pg.evaluate(hide, True)
        self.s.httpd.ssp_transport.stop()
        pg.evaluate(hide, False)
        pg.wait_for_selector("#live-start:not(.hidden)")
        self.assertTrue(pg.evaluate("window.Barline.metronome.job === null"))

    def test_sound_is_scheduled_before_the_engine_reports_running(self):
        """Safari starts its audio engine a moment after the tap; the click
        must not wait for that (it used to, and the iPad stayed silent)."""
        pg = self.page()
        pg.goto(f"{self.s.base}/#/live")
        pg.wait_for_selector("#live-view:not(.hidden)")
        ok = pg.evaluate("""() => { const m = window.Barline.metronome; m.unlock();
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
        pg.wait_for_function("window.Barline.metronome.job !== null")
        kinds = pg.evaluate("window.Barline.metronome.job.events.map(e => e.kind)")
        self.assertEqual(kinds[:4], ["voice"] * 4)           # spoken count-in
        self.assertEqual(kinds.count("sub"), 2 * 4 * 3)        # 2 bars of 16ths
        pg.wait_for_function("document.getElementById('ck-diag').textContent.includes('running')")
        pg.keyboard.press("Escape")
        pg.reload()
        pg.wait_for_selector(".section-card")
        self.assertEqual(pg.evaluate("window.Barline.metronome.opts.subdivision"), "16")

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

    def test_export_a_setlist_and_import_it_back_changes_nothing(self):
        import json
        import tempfile
        sl = next(iter(self.s.store.setlists.values()))
        before = len(self.s.store.songs), len(self.s.store.setlists)
        pg = self.page(accept_downloads=True)
        pg.goto(f"{self.s.base}/#/setlist/{sl['id']}")
        pg.wait_for_selector("#setlist-export-btn")
        with pg.expect_download() as dl:
            pg.click("#setlist-export-btn")
        path = os.path.join(tempfile.mkdtemp(prefix="ssp-dl-"), "set.ssp.json")
        dl.value.save_as(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual((data["ssp_export"], [x["id"] for x in data["setlists"]]), (2, [sl["id"]]))
        self.assertEqual([x["id"] for x in data["songs"]], [i for i in sl["songs"] if i in self.s.store.songs])
        self.assertEqual(len(data["band"]["players"]), len(self.s.store.band["players"]))
        pg.set_input_files("#import-file", path)
        pg.wait_for_selector("#import-modal:not(.hidden)")
        self.assertEqual(pg.locator(".import-item").count(), pg.locator(".import-same").count())
        self.assertIn("already here: kept as it is", pg.text_content("#import-extra"))
        pg.click("#import-apply")
        pg.wait_for_selector("#import-modal.hidden", state="attached")
        self.assertEqual((len(self.s.store.songs), len(self.s.store.setlists)), before)

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
        pg.wait_for_function("window.Barline.metronome.job !== null")
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
        pg.wait_for_function("window.Barline.metronome.job !== null")
        # the Wi-Fi drops: the event stream goes quiet
        pg.evaluate("() => { const S = window.SSPSync; S.source.close(); S.connected = false; S.emit('status', {data: false}); }")
        pg.wait_for_function("document.body.classList.contains('is-solo')", timeout=15000)
        self.assertTrue(pg.evaluate("window.Barline.metronome.job !== null"))
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
