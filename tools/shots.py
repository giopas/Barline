#!/usr/bin/env python3
"""Retake every README/wiki screenshot and GIF from the demo band.

    python3 tools/shots.py            # everything
    python3 tools/shots.py stills     # just the PNGs
    python3 tools/shots.py gifs       # just the GIFs
    python3 tools/shots.py launcher   # the desktop control panel (13, and 18 with the band Wi-Fi on) (needs Tk + a display, or xvfb-run)

Starts its own server on a fresh copy of the fictional demo band (demo/),
so nothing real is ever shown and every run starts from the same songs.
The "connect a device" address is replaced with a made-up one
(192.168.1.20), so no real network address ends up in the repo.

Needs: pip install playwright pillow, and a Chromium (playwright install
chromium); for the paper-chart pictures, poppler's pdftoppm or pip install
pypdfium2. Writes to screenshots/ (or OUT_DIR as a second argument).

Part of the release routine (see WORKPLAN.md, "Release checklist"): any
change to what a screen looks like reruns this and commits the result.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import subprocess
import tempfile
import sys
import time
import urllib.request

try:  # not needed for the launcher shot, which only needs Tk
    from PIL import Image
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    Image = sync_playwright = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHAT = sys.argv[1] if len(sys.argv) > 1 else "all"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "screenshots")
FAKE_ADDR = "http://192.168.1.20:8420/"
DESKTOP = {"viewport": {"width": 1440, "height": 900}}

# a visible "finger" for the GIFs (headless browsers draw no cursor)
CURSOR_JS = """
(() => {
  if (document.getElementById('shot-cursor')) return;
  const d = document.createElement('div');
  d.id = 'shot-cursor';
  d.style.cssText = 'position:fixed;z-index:9999;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;' +
    'background:rgba(255,255,255,.35);border:2px solid #fff;pointer-events:none;transition:left .25s,top .25s;left:-50px;top:-50px';
  document.body.appendChild(d);
})();
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DemoServer:
    def __enter__(self):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        # a plain copy served as an ordinary band (not --demo), so the
        # pictures don't carry the "Demo band" banner
        self.tmp = tempfile.mkdtemp(prefix="ssp-shots-")
        data = os.path.join(self.tmp, "data")
        shutil.copytree(os.path.join(ROOT, "demo"), data)
        self.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "server", "app.py"), "--data", data,
                                      "--port", str(self.port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                urllib.request.urlopen(self.base + "/api/time", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        return self

    def __exit__(self, *exc):
        self.proc.terminate()
        self.proc.wait(5)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path):
        return json.loads(urllib.request.urlopen(self.base + path, timeout=5).read())

    def post(self, path, body, client=None):
        headers = {"Content-Type": "application/json"}
        if client:
            headers["X-SSP-Client"] = client
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), headers)
        return json.loads(urllib.request.urlopen(req, timeout=5).read())


class Shooter:
    def __init__(self, pw, srv):
        self.pw, self.srv = pw, srv
        self.browser = pw.chromium.launch()
        os.makedirs(OUT, exist_ok=True)
        self.songs = {s["title"]: s["id"] for s in srv.get("/api/songs")}
        self.setlists = {s["name"]: s["id"] for s in srv.get("/api/setlists")}
        self.players = {p["name"]: p["id"] for p in srv.get("/api/band")["players"]}

    def page(self, device=None, player=None, **extra):
        ctx_args = dict(self.pw.devices[device]) if device else dict(DESKTOP)
        ctx_args.update(extra)
        ctx = self.browser.new_context(bypass_csp=True, **ctx_args)
        ctx.add_init_script("localStorage.setItem('ssp.asked','true');"
                            f"localStorage.setItem('ssp.player', {json.dumps(json.dumps(player))});")
        pg = ctx.new_page()
        pg.route("**/api/connect", lambda r: r.fulfill(json={"port": 8420, "addresses": [FAKE_ADDR]}))
        pg.set_default_timeout(8000)
        return pg

    def save(self, pg, name, full_page=False):
        path = os.path.join(OUT, name)
        pg.screenshot(path=path, full_page=full_page)
        print("  ✓", name)

    def cue(self, title, setlist=None):
        self.srv.post("/api/transport", {"action": "cue", "song_id": self.songs[title],
                                         "setlist_id": self.setlists.get(setlist)})

    def start(self, title, from_label=None, setlist=None, by=None):
        """Start a run as if pressed on page `by` (so it reads "Started by Ruby")."""
        song = self.srv.get(f"/api/songs/{self.songs[title]}")
        sec = next((s["id"] for s in song["sections"] if s["label"] == from_label), None)
        client = by.evaluate("window.SSPSync.clientId") if by else None
        return self.srv.post("/api/transport", {"action": "start", "song_id": song["id"], "start_section_id": sec,
                                                "setlist_id": self.setlists.get(setlist), "lead_ms": 400}, client)

    def stop(self):
        self.srv.post("/api/transport", {"action": "stop"})

    # -----------------------------------------------------------------
    def stills(self):
        hl = self.songs["Harbour Lights"]
        lap = self.page()
        lap.goto(f"{self.srv.base}/#/song/{hl}")
        lap.wait_for_selector(".section-card")
        lap.wait_for_timeout(500)
        self.save(lap, "01-editor.png")

        lap.goto(f"{self.srv.base}/#/setlist/{self.setlists['Friday at the Harbour Bar']}")
        lap.wait_for_selector("#setlist-songs li")
        lap.wait_for_timeout(300)
        self.save(lap, "02-setlist.png")

        lap.goto(f"{self.srv.base}/#/band")
        lap.wait_for_selector(".player-row")
        lap.wait_for_timeout(300)
        self.save(lap, "03-band.png")

        lap.goto(f"{self.srv.base}/#/song/{hl}")
        lap.wait_for_selector(".section-card")
        lap.click("#connect-btn")
        lap.wait_for_selector("#connect-qr")
        lap.locator(".connect-players .chip").filter(has_text="Ruby").click()
        lap.wait_for_timeout(500)
        self.save(lap, "04-connect.png")
        lap.keyboard.press("Escape")
        lap.goto(f"{self.srv.base}/#/")

        # live: three devices, one run, frozen mid-chorus
        tab = self.page("iPad (gen 7) landscape", self.players["Ruby"])
        phone = self.page("iPhone 13", self.players["Sam"])
        self.cue("Harbour Lights", "Friday at the Harbour Bar")
        for pg in (lap, tab, phone):
            pg.goto(f"{self.srv.base}/#/live")
            pg.wait_for_selector("#live-chart .chart-row", state="attached")
        lap.wait_for_timeout(400)
        self.save(tab, "05-live-ready-tablet.png")

        t = self.start("Harbour Lights", "Chorus", "Friday at the Harbour Bar", by=tab)
        first = t["timeline"]["bars"][0]
        bar_ms = first["beat_ms"] * 4
        # into the 3rd bar of the chorus, on beat 2: past the count-in
        target = t["started_at"] + bar_ms * 3 + first["beat_ms"] * 1.3
        wait = (target - time.time() * 1000) / 1000
        time.sleep(max(0, wait))
        self.save(lap, "06-live-laptop.png")
        self.save(tab, "07-live-tablet-drums.png")
        self.save(phone, "08-live-phone-bass.png")
        self.stop()

        # count-in close-up: Night Bus (verbal count-in into the last chorus)
        t = self.start("Night Bus to Nowhere", "Last chorus", by=tab)
        first = t["timeline"]["bars"][0]
        time.sleep(max(0, (t["started_at"] + first["beat_ms"] * 2.2 - time.time() * 1000) / 1000))
        self.save(tab, "09-live-count-in.png")
        self.stop()

        # paper charts (0.13): the PDFs themselves, drawn as pictures --
        # one player's chart, the set's running order next to a floor sheet
        self.save_pdf(f"/export/song/{hl}?player={self.players['Sam']}", "10-print-chart-bass.png")
        friday = self.setlists["Friday at the Harbour Bar"]
        self.save_pdfs([f"/export/setlist/{friday}?parts=list",
                        f"/export/song/{self.songs['Lantern Parade']}?size=floor&ink=bw"],
                       "16-paper-setlist-and-floor.png")
        lap.goto(f"{self.srv.base}/#/setlist/{friday}")
        lap.wait_for_selector("#setlist-songs li")
        lap.click("#setlist-print-btn")
        lap.wait_for_selector("#print-modal:not(.hidden)")
        lap.wait_for_timeout(300)
        self.save(lap, "17-print-dialog.png")
        lap.keyboard.press("Escape")

        # phone: who's holding this device, and editing on the go
        p2 = self.page("iPhone 13", None)
        p2.add_init_script("localStorage.removeItem('ssp.asked')")
        p2.goto(f"{self.srv.base}/#/song/{self.songs['Paper Boats']}")
        p2.wait_for_selector("#who-modal:not(.hidden)")
        p2.wait_for_timeout(300)
        self.save(p2, "11-phone-who.png")
        p2.locator("#who-options .who-option").filter(has_text="Theo").click()
        p2.wait_for_timeout(300)
        p2.locator(".section-card").nth(5).scroll_into_view_if_needed()
        p2.wait_for_timeout(300)
        self.save(p2, "12-phone-editor.png")
        # 0.10: the drummer's click settings + click check, and quick add
        tab.goto(f"{self.srv.base}/#/live")
        tab.wait_for_selector("#live-view:not(.hidden)")
        tab.evaluate("window.Barline.saveClick({subdivision: '8', voice: true, channel: 'left'})")
        tab.click("#live-click-settings")
        tab.wait_for_timeout(300)
        self.save(tab, "14-click-settings.png")
        tab.keyboard.press("Escape")

        lap.goto(f"{self.srv.base}/#/")
        lap.click("#new-song-btn")
        lap.click(".tab[data-tab=quick-list]")
        lap.fill("#q-paste", "Seven Seas - 124 - 3:52\nRoxanna, 134\nHarbour Lights\nTake Ten 174 5:24")
        lap.fill("#q-setlist-name", "Saturday in the park")
        lap.wait_for_timeout(300)
        self.save(lap, "15-quick-add.png")
        lap.keyboard.press("Escape")

        # 0.16: count-ins in one go, and the Jump sheet mid-song
        lap.goto(f"{self.srv.base}/#/song/{hl}")
        lap.wait_for_selector(".section-card")
        lap.click("#song-countins-btn")
        lap.select_option("#ci-start-bars", "1")
        lap.select_option("#ci-start-style", "sticks")
        lap.select_option("#ci-chg-bars", "1")
        lap.check("#ci-tempo")
        lap.wait_for_timeout(300)
        self.save(lap, "19-count-ins.png")
        lap.keyboard.press("Escape")

        self.cue("Harbour Lights", "Friday at the Harbour Bar")
        tab.goto(f"{self.srv.base}/#/live")
        tab.wait_for_selector("#live-chart .chart-row", state="attached")
        t = self.start("Harbour Lights", "Verse 1", "Friday at the Harbour Bar", by=tab)
        first = t["timeline"]["bars"][0]
        time.sleep(max(0, (t["started_at"] + first["beat_ms"] * 4 * 2.4 - time.time() * 1000) / 1000))
        tab.click("#live-jump-btn")
        tab.click("#live-nudge summary")
        tab.wait_for_timeout(300)
        self.save(tab, "20-live-jump.png")
        self.stop()
        for pg in (lap, tab, phone, p2):
            pg.context.close()

    # -----------------------------------------------------------------
    def pdf_image(self, path, dpi=110):
        """The first page of a PDF from the server, as a picture: poppler's
        pdftoppm if it's installed, else pypdfium2 (pip install pypdfium2)."""
        pdf = urllib.request.urlopen(self.srv.base + path, timeout=30).read()
        if shutil.which("pdftoppm"):
            with tempfile.TemporaryDirectory() as tmp:
                with open(os.path.join(tmp, "in.pdf"), "wb") as f:
                    f.write(pdf)
                subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1", "-singlefile",
                                os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out")], check=True)
                return Image.open(os.path.join(tmp, "out.png")).convert("RGB")
        import pypdfium2  # noqa: PLC0415 - only needed here
        return pypdfium2.PdfDocument(pdf)[0].render(scale=dpi / 72).to_pil().convert("RGB")

    def save_pdf(self, path, name):
        img = self.pdf_image(path)
        frame = Image.new("RGB", (img.width + 2, img.height + 2), (200, 200, 200))  # a thin page edge
        frame.paste(img, (1, 1))
        frame.save(os.path.join(OUT, name), optimize=True)
        print("  ✓", name)

    def save_pdfs(self, paths, name):
        self.side_by_side([self.pdf_image(p, dpi=80) for p in paths], gap=24, bg=(225, 225, 225)).save(
            os.path.join(OUT, name), optimize=True)
        print("  ✓", name)

    @staticmethod
    def grab(pg, scale_to=None):
        img = Image.open(io.BytesIO(pg.screenshot())).convert("RGB")
        if scale_to:
            w = scale_to
            img = img.resize((w, round(img.height * w / img.width)), Image.LANCZOS)
        return img

    @staticmethod
    def side_by_side(images, gap=16, bg=(15, 17, 20)):
        h = max(i.height for i in images)
        w = sum(i.width for i in images) + gap * (len(images) + 1)
        canvas = Image.new("RGB", (w, h + 2 * gap), bg)
        x = gap
        for im in images:
            canvas.paste(im, (x, gap + (h - im.height) // 2))
            x += im.width + gap
        return canvas

    @staticmethod
    def write_gif(frames, name, ms):
        path = os.path.join(OUT, name)
        pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
        durations = ms if isinstance(ms, list) else [ms] * len(pal)
        pal[0].save(path, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True)
        print("  ✓", name, f"({len(frames)} frames, {os.path.getsize(path) // 1024} KB)")

    def point(self, pg, locator):
        box = locator.bounding_box()
        pg.evaluate(CURSOR_JS)
        pg.evaluate(f"(() => {{const c=document.getElementById('shot-cursor'); c.style.left='{box['x'] + box['width'] / 2}px';"
                    f"c.style.top='{box['y'] + box['height'] / 2}px';}})()")
        pg.wait_for_timeout(280)

    def gif_planning(self):
        """Drafting a song: add a section, name it, set its bars, duplicate it, aim a hint."""
        sid = self.songs["Coffee at Midnight"]
        pg = self.page(viewport={"width": 1280, "height": 800})
        pg.goto(f"{self.srv.base}/#/song/{sid}")
        pg.wait_for_selector(".section-card")
        frames, times = [], []

        def snap(ms=350):
            frames.append(self.grab(pg, 960))
            times.append(ms)

        snap(1200)
        add = pg.locator("#add-section-btn")
        self.point(pg, add)
        snap()
        add.click()
        pg.wait_for_timeout(250)
        last = pg.locator(".section-card").last
        last.scroll_into_view_if_needed()
        pg.evaluate("window.scrollTo(0, 0)")
        pg.locator("#main").evaluate("m => m.scrollTo(0, m.scrollHeight)")
        snap()
        label = last.locator(".section-label")
        for ch in "Bridge":
            label.press_sequentially(ch)
            snap(140)
        bars = last.locator(".section-bars")
        self.point(pg, bars)
        bars.fill("8")
        pg.wait_for_timeout(150)
        snap(500)
        bpm = last.locator(".section-bpm")
        self.point(pg, bpm)
        bpm.fill("92")
        pg.wait_for_timeout(150)
        snap(500)
        addh = last.locator(".add-hint")
        self.point(pg, addh)
        addh.click()
        pg.wait_for_timeout(200)
        hint = last.locator(".hint-text").last
        for ch in "Half-time, follow Ruby":
            hint.press_sequentially(ch)
            if ch == " ":
                snap(110)
        snap(300)
        vis = last.locator(".hint-visibility").last
        self.point(pg, vis)
        vis.select_option(label="For Sam (Bass)")
        pg.wait_for_timeout(200)
        snap(700)
        dup = last.locator(".duplicate-section")
        self.point(pg, dup)
        snap()
        dup.click()
        pg.wait_for_timeout(300)
        pg.locator("#main").evaluate("m => m.scrollTo(0, m.scrollHeight)")
        snap(600)
        pg.locator("#main").evaluate("m => m.scrollTo({top: 0})")
        pg.wait_for_timeout(200)
        snap(2200)
        self.write_gif(frames, "planning.gif", times)
        pg.context.close()

    def gif_sync(self):
        """A laptop edits; a phone on the same Wi-Fi updates by itself."""
        sid = self.songs["Slow Tide"]
        lap = self.page(player=self.players["Theo"], viewport={"width": 1280, "height": 800})
        phone = self.page("iPhone 13", self.players["Sam"])
        for pg in (lap, phone):
            pg.goto(f"{self.srv.base}/#/song/{sid}")
            pg.wait_for_selector(".section-card")
            pg.wait_for_timeout(600)  # let the first render and the clock sync settle
        phone.locator(".section-card").nth(3).scroll_into_view_if_needed()
        lap.locator(".section-card").nth(3).scroll_into_view_if_needed()
        frames, times = [], []

        def snap(ms=300):
            frames.append(self.side_by_side([self.grab(lap, 900), self.grab(phone, 290)]))
            times.append(ms)

        snap(1200)
        card = lap.locator(".section-card").nth(3)
        label = card.locator(".section-label")
        self.point(lap, label)
        label.fill("")
        for i, ch in enumerate("Interlude (keys solo)"):
            label.press_sequentially(ch)
            if i % 3 == 2:
                lap.wait_for_timeout(120)
                snap(160)
        lap.wait_for_timeout(900)
        snap(1200)
        bars = card.locator(".section-bars")
        self.point(lap, bars)
        bars.fill("8")
        snap(250)
        lap.wait_for_timeout(900)
        snap(1500)
        addh = card.locator(".add-hint")
        self.point(lap, addh)
        addh.click()
        h = card.locator(".hint-text").last
        for i, ch in enumerate("Bass sits out"):
            h.press_sequentially(ch)
            if i % 4 == 3:
                snap(160)
        vis = card.locator(".hint-visibility").last
        self.point(lap, vis)
        vis.select_option(label="For Sam (Bass)")
        snap(400)
        lap.wait_for_timeout(1000)
        snap(2800)
        self.write_gif(frames, "sync.gif", times)
        lap.context.close()
        phone.context.close()

    def gif_live(self):
        """One tap on the drummer's tablet; tablet and phone follow the song together."""
        tab = self.page("iPad (gen 7) landscape", self.players["Ruby"])
        phone = self.page("iPhone 13", self.players["Sam"])
        self.cue("Night Bus to Nowhere", "Friday at the Harbour Bar")
        for pg in (tab, phone):
            pg.goto(f"{self.srv.base}/#/live")
            pg.wait_for_selector("#live-chart .chart-row", state="attached")
        # Ruby's a drummer, so her tablet is in big view: pick the start in the strip
        tab.locator("#live-shape .song-shape-block").filter(has_text="Chorus").first.click()
        tab.wait_for_timeout(400)
        frames, times = [], []

        def snap(ms):
            frames.append(self.side_by_side([self.grab(tab, 760), self.grab(phone, 270)]))
            times.append(ms)

        snap(1300)
        go = tab.locator("#live-start")
        self.point(tab, go)
        snap(500)
        go.click()
        stamps = []
        t0 = time.time()
        while time.time() - t0 < 9.5:
            stamps.append(time.time())
            snap(0)
        # each frame shows until the next one was taken, so the GIF plays in real time
        for i in range(len(stamps) - 1):
            times[2 + i] = max(20, round((stamps[i + 1] - stamps[i]) * 1000))
        times[-1] = 100
        stop = phone.locator("#live-stop")
        self.point(phone, stop)
        stop.click()
        phone.wait_for_timeout(500)
        snap(2200)
        self.write_gif(frames, "live.gif", times[: len(frames)])
        tab.context.close()
        phone.context.close()

    def close(self):
        self.browser.close()


def grab_screen(x, y, w, h, path):
    """Save part of the screen: Pillow if it's installed, else macOS's own
    screencapture (Terminal may ask for Screen Recording permission the
    first time), else ImageMagick's import (Linux)."""
    try:
        from PIL import ImageGrab
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
        return
    except Exception:  # noqa: BLE001 - no Pillow, or no grab support here
        pass
    if sys.platform == "darwin":
        subprocess.run(["screencapture", "-x", "-o", f"-R{x},{y},{w},{h}", path], check=True)
    else:
        subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", path], check=True)


def launcher_shot():
    """The Tk control panel, running the demo band. Needs Tk and a display."""
    sys.path[:0] = [os.path.join(ROOT, "launcher"), os.path.join(ROOT, "server")]
    import tkinter as tk
    import app as server_app
    import gui

    server_app.local_addresses = lambda: ["192.168.1.20"]  # no real address in the picture
    gui.update.check = lambda force=False: gui.update.status()  # pictures never ask GitHub
    root = tk.Tk()
    root.geometry("940x790")
    panel = gui.LauncherApp(root)
    panel.port_var.set("8420")
    try:  # show the default port in the picture when it's free
        with socket.socket() as probe:
            probe.bind(("0.0.0.0", 8420))
        port = 8420
    except OSError:
        port = free_port()

    def go():
        panel.port_var.set(str(port))
        panel._start_demo()
        panel.data_dir_var.set("~/Library/Application Support/SingleSongPlanner/demo-data")
        # two pretend devices and a cued song, so "On stage" has something to show
        store, hub = panel.store, server_app.Handler.hub
        players = {p["role"]: p["id"] for p in store.band.get("players", [])}
        hub.subscribe("shot-ipad", players.get("Drums"), "iPad")
        hub.subscribe("shot-phone", players.get("Bass"), "Android phone")
        setlist = next(iter(sorted(store.setlists.values(), key=lambda s: s.get("name", ""))), None)
        if setlist and setlist.get("songs"):
            server_app.Handler.transport.cue(setlist["songs"][0], setlist["id"])
        root.after(1500, shoot)

    def shoot():
        root.update()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        grab_screen(x, y, w, h, os.path.join(OUT, "13-launcher.png"))
        print("  ✓ 13-launcher.png")
        # the band Wi-Fi on (made up: no radio is touched), code 1 showing
        panel._set_wifi({"ssid": "Barline-Band", "password": "kmrt-vhae-4827", "ours": True})
        panel.footer_var.set('Band Wi-Fi "Barline-Band" is on: phones scan code 1, then 2.')
        root.after(500, shoot_wifi)

    def shoot_wifi():
        root.update()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        grab_screen(x, y, w, h, os.path.join(OUT, "18-launcher-wifi.png"))
        print("  ✓ 18-launcher-wifi.png")
        panel.wifi = None  # never call the real hotspot.stop() on the way out
        server_app.Handler.wifi_ssid = server_app.Handler.wifi_password = None
        panel._stop_server()
        root.after(600, root.destroy)

    root.after(400, go)
    root.mainloop()


def main():
    if WHAT == "launcher":
        return launcher_shot()
    with DemoServer() as srv, sync_playwright() as pw:
        shooter = Shooter(pw, srv)
        try:
            if WHAT in ("all", "stills"):
                print("stills:")
                shooter.stills()
            if WHAT in ("all", "gifs"):
                print("gifs:")
                shooter.gif_planning()
                shooter.gif_sync()
                shooter.gif_live()
        finally:
            shooter.close()
    print("written to", OUT)


if __name__ == "__main__":
    main()
