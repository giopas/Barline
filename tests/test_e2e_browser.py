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


if __name__ == "__main__":
    unittest.main()
