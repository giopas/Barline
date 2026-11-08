#!/usr/bin/env python3
"""
SSP - Song and Setlist Planner -- desktop launcher.

A small Tkinter control panel for the server (same spirit as QLC+ Swiss
Knife being a desktop app, and dressed like it: a dark window, a top bar
with the status, numbered cards): pick a data folder, pick a port, start
or stop the server, scan the QR code on each phone/tablet, see who's
connected and what's on stage, and watch a live log -- without touching a
terminal. This is a control panel for the server process, not a second
editor; the actual drafting/live UI stays the one web app in web/static
(see PROJECT_CHARTER.md's "no separate native desktop editor" decision --
this doesn't reopen that, it's a launcher).

Settings (which data folder, which port, and a short list of recently used
data folders -- "sessions") persist between runs via launcher/settings.py.

Runs the same from source (`python3 launcher/gui.py`) or from a packaged
build (see packaging/) -- server/paths.py resolves the right defaults
either way.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER_DIR = os.path.join(_HERE, "..", "server")
for _p in (_HERE, _SERVER_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app as server_app  # server/app.py
import hotspot  # server/hotspot.py
import paths  # server/paths.py
import platform_dirs  # server/platform_dirs.py
import qr  # server/qr.py
import settings as launcher_settings  # launcher/settings.py
import update  # server/update.py

TITLE = "SSP - Song and Setlist Planner"

# SSP's own colors (web/static/style.css), laid out the way Swiss Knife's
# tokens.css does it: a dark window, slightly lighter cards, one accent.
C = {
    "bg": "#121418",
    "bar": "#191b20",
    "card": "#1d2026",
    "line": "#2c3039",
    "field": "#0f1114",
    "text": "#e8e9ec",
    "dim": "#9aa0ab",
    "faint": "#6b717d",
    "accent": "#5b8cff",
    "accent_hover": "#7aa3ff",
    "accent_soft": "#232f4d",
    "btn": "#2a2e37",
    "btn_hover": "#353a45",
    "ok": "#45c08a",
    "ok_soft": "#1b3229",
    "danger": "#ff8a80",
    "danger_soft": "#3b2224",
    "danger_hover": "#4a2a2d",
}


# -- small building blocks ------------------------------------------------

class FlatButton(tk.Label):
    """A colored button that looks the same on every OS (ttk/tk buttons
    ignore colors on macOS). Keyboard: Tab to it, Space/Return to press."""

    KINDS = {
        # kind: (background, text, hover background)
        "primary": (C["accent"], "#ffffff", C["accent_hover"]),
        "danger": (C["danger_soft"], C["danger"], C["danger_hover"]),
        "secondary": (C["btn"], C["text"], C["btn_hover"]),
        "ghost": (None, C["accent"], C["accent_soft"]),  # None: the parent's background
        "quiet": (None, C["dim"], C["btn"]),
    }

    def __init__(self, parent, text, command, kind="secondary", font=None, padx=14, pady=7):
        super().__init__(parent, text=text, font=font, padx=padx, pady=pady, cursor="hand2",
                         takefocus=1, highlightthickness=1)
        self.command = command
        self.kind = kind
        self.enabled = True
        self.hover = False
        self._paint()
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Return>", self._click)
        self.bind("<space>", self._click)
        self.bind("<FocusIn>", lambda _e: self._paint())
        self.bind("<FocusOut>", lambda _e: self._paint())

    def set(self, text=None, enabled=None, kind=None) -> None:
        if text is not None:
            self.configure(text=text)
        if enabled is not None:
            self.enabled = enabled
        if kind is not None:
            self.kind = kind
        self._paint()

    def _set_hover(self, on: bool) -> None:
        self.hover = on
        self._paint()

    def _click(self, event=None) -> None:
        if not self.enabled:
            return
        if event is not None and event.type == tk.EventType.ButtonRelease:
            # released outside the button: not a click
            if not (0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()):
                return
        self.command()

    def _paint(self) -> None:
        bg, fg, hover_bg = self.KINDS[self.kind]
        parent_bg = self.master.cget("bg")
        if not self.enabled:
            bg, fg, hover_bg = (None if bg is None else C["btn"]), C["faint"], None
        bg = bg or parent_bg
        try:
            focused = self.focus_displayof() is self
        except (KeyError, tk.TclError):
            focused = False
        self.configure(bg=hover_bg if (self.hover and hover_bg) else bg, fg=fg,
                       cursor="hand2" if self.enabled else "arrow",
                       highlightbackground=parent_bg,
                       highlightcolor=C["accent_hover"] if focused else parent_bg)


class Card(tk.Frame):
    """A Swiss Knife-style card: a numbered badge, a title, a hint line,
    and a body frame for the content."""

    def __init__(self, parent, number, title, hint, fonts):
        super().__init__(parent, bg=C["card"], highlightthickness=1, highlightbackground=C["line"])
        head = tk.Frame(self, bg=C["card"])
        head.pack(fill="x", padx=16, pady=(14, 0))
        badge = tk.Canvas(head, width=22, height=22, bg=C["card"], highlightthickness=0)
        badge.create_oval(1, 1, 21, 21, fill=C["accent_soft"], outline="")
        badge.create_text(11, 11, text=str(number), fill=C["accent"], font=fonts["badge"])
        badge.pack(side="left")
        tk.Label(head, text=title, bg=C["card"], fg=C["text"], font=fonts["h"]).pack(side="left", padx=(8, 0))
        self.hint = tk.Label(self, text=hint, bg=C["card"], fg=C["dim"], font=fonts["small"],
                             anchor="w", justify="left")
        self.hint.pack(fill="x", padx=16, pady=(4, 0))
        self.body = tk.Frame(self, bg=C["card"])
        self.body.pack(fill="both", expand=True, padx=16, pady=(10, 16))


def _pick_family(preferred, fallback):
    available = set(tkfont.families())
    for name in preferred:
        if name in available:
            return name
    return fallback


# -- the window -------------------------------------------------------------

class LauncherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(TITLE)
        self.root.configure(bg=C["bg"])
        self.root.minsize(820, 640)

        self.settings = launcher_settings.load()
        self.httpd = None
        self.store = None
        self.server_thread = None
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self._live_sig = None
        self._demo = False
        self.update_info = None  # the last update check's answer (server/update.py)
        self._update_busy = False
        self._ips = []  # this computer's addresses, best first (polled while running)
        self._port = None
        self.wifi = None  # the band Wi-Fi when there is one: {"ssid", "password", "ours"}
        self.qr_mode = "open"  # which QR the Connect card shows: "join" (Wi-Fi) or "open" (SSP)
        self._wifi_busy = False
        self._wifi_dialog = None

        self.data_dir_var = tk.StringVar(value=self.settings.get("data_dir") or paths.default_data_dir())
        self.port_var = tk.StringVar(value=str(self.settings.get("port", server_app.DEFAULT_PORT)))
        self.static_dir_var = tk.StringVar(value=paths.default_static_dir())
        self.status_var = tk.StringVar(value="Stopped")
        self.footer_var = tk.StringVar(value="")
        self.advanced_visible = tk.BooleanVar(value=False)

        self._make_fonts()
        self._make_style()
        self._build_widgets()
        self._set_running_ui(False, None)
        self.footer_var.set("Ready. Pick your songs folder and start the server.")
        self._drain_log_queue()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if update.enabled():
            self.root.after(1500, lambda: self._check_updates(force=False, quiet=True))

    # -- look -----------------------------------------------------------------

    def _make_fonts(self) -> None:
        base = tkfont.nametofont("TkDefaultFont").actual()
        family = _pick_family(["Inter", "SF Pro Text", "Segoe UI"], base["family"])
        mono = _pick_family(["SF Mono", "Menlo", "JetBrains Mono", "Cascadia Mono", "Consolas",
                             "DejaVu Sans Mono"], tkfont.nametofont("TkFixedFont").actual()["family"])
        self.fonts = {
            "brand": (family, 16, "bold"),
            "title": (family, 12),
            "h": (family, 13, "bold"),
            "badge": (family, 10, "bold"),
            "body": (family, 12),
            "bold": (family, 12, "bold"),
            "small": (family, 11),
            "caps": (family, 10, "bold"),
            "button": (family, 12),
            "big_button": (family, 13, "bold"),
            "mono": (mono, 11),
            "chip": (mono, 10),
            "url": (mono, 15, "bold"),
            "band": (family, 15, "bold"),
        }

    def _make_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")  # the one built-in theme that takes colors everywhere
        field = dict(fieldbackground=C["field"], foreground=C["text"], background=C["btn"],
                     bordercolor=C["line"], lightcolor=C["field"], darkcolor=C["field"],
                     insertcolor=C["text"], arrowcolor=C["dim"], arrowsize=14, padding=6,
                     selectbackground=C["accent_soft"], selectforeground=C["text"])
        style.configure("TEntry", **field)
        style.map("TEntry", bordercolor=[("focus", C["accent"])], lightcolor=[("focus", C["accent"])],
                  foreground=[("disabled", C["faint"])], fieldbackground=[("disabled", C["card"])])
        style.configure("TCombobox", **field)
        style.map("TCombobox", fieldbackground=[("disabled", C["card"]), ("readonly", C["field"])],
                  foreground=[("disabled", C["faint"]), ("readonly", C["text"])],
                  background=[("active", C["btn_hover"]), ("readonly", C["btn"])],
                  bordercolor=[("focus", C["accent"])], arrowcolor=[("disabled", C["faint"])],
                  selectbackground=[("readonly", C["field"])], selectforeground=[("readonly", C["text"])])
        self.root.option_add("*TCombobox*Listbox.background", C["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["accent_soft"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", C["text"])
        self.root.option_add("*TCombobox*Listbox.font", self.fonts["body"])
        style.configure("TCheckbutton", background=C["card"], foreground=C["dim"], font=self.fonts["small"],
                        indicatorbackground=C["field"], indicatorforeground=C["accent"], focuscolor=C["card"],
                        bordercolor=C["line"], lightcolor=C["field"], darkcolor=C["field"])
        style.map("TCheckbutton", background=[("active", C["card"])], foreground=[("active", C["text"])],
                  indicatorbackground=[("selected", C["field"])])
        style.configure("Vertical.TScrollbar", background=C["btn"], troughcolor=C["field"],
                        bordercolor=C["field"], lightcolor=C["btn"], darkcolor=C["btn"],
                        arrowcolor=C["dim"], gripcount=0)
        style.map("Vertical.TScrollbar", background=[("active", C["btn_hover"])])

    def _label(self, parent, text="", font="body", fg="text", **kw):
        kw = dict({"anchor": "w", "justify": "left"}, **kw)
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=C[fg], font=self.fonts[font], **kw)

    # -- layout ---------------------------------------------------------------

    def _build_widgets(self) -> None:
        f = self.fonts

        # -- top bar: logo, name, version, status pill -------------------------
        bar = tk.Frame(self.root, bg=C["bar"])
        bar.pack(fill="x")
        self._top_line = tk.Frame(self.root, bg=C["line"], height=1)
        self._top_line.pack(fill="x")
        inner = tk.Frame(bar, bg=C["bar"])
        inner.pack(fill="x", padx=18, pady=12)
        self.logo = None
        try:
            self.logo = tk.PhotoImage(file=os.path.join(paths.default_static_dir(), "icon-40.png"))
            tk.Label(inner, image=self.logo, bg=C["bar"]).pack(side="left", padx=(0, 12))
        except tk.TclError:
            pass
        tk.Label(inner, text="SSP", bg=C["bar"], fg=C["text"], font=f["brand"]).pack(side="left")
        tk.Label(inner, text="Song and Setlist Planner", bg=C["bar"], fg=C["dim"],
                 font=f["title"]).pack(side="left", padx=(10, 10), pady=(3, 0))
        tk.Label(inner, text=f" v{server_app.VERSION} ", bg=C["btn"], fg=C["dim"],
                 font=f["chip"]).pack(side="left", pady=(3, 0))

        self.pill = tk.Frame(inner, bg=C["btn"])
        self.pill.pack(side="right")
        self.pill_dot = tk.Canvas(self.pill, width=10, height=10, highlightthickness=0, bg=C["btn"])
        self.pill_dot.pack(side="left", padx=(12, 6), pady=8)
        self.pill_label = tk.Label(self.pill, textvariable=self.status_var, bg=C["btn"], fg=C["text"],
                                   font=f["bold"])
        self.pill_label.pack(side="left", padx=(0, 14))
        self.status_dot = self.pill_dot  # older name, kept for anyone scripting this

        # -- update banner: only when a newer version is out --------------------
        self.update_banner = tk.Frame(self.root, bg=C["accent_soft"])
        ub = tk.Frame(self.update_banner, bg=C["accent_soft"])
        ub.pack(fill="x", padx=18, pady=8)
        self.update_text = tk.Label(ub, text="", bg=C["accent_soft"], fg=C["text"], font=f["bold"], anchor="w")
        self.update_text.pack(side="left")
        self.update_sub = tk.Label(ub, text="", bg=C["accent_soft"], fg=C["dim"], font=f["small"], anchor="w")
        self.update_sub.pack(side="left", padx=(10, 0))
        FlatButton(ub, "✕", self._hide_update_banner, kind="quiet", font=f["small"], padx=6, pady=2).pack(side="right")
        self.update_btn = FlatButton(ub, "Update and restart", self._install_update, kind="primary",
                                     font=f["button"], padx=12, pady=5)
        self.update_btn.pack(side="right", padx=(8, 4))
        self.notes_btn = FlatButton(ub, "What's new", self._open_release_page, font=f["button"], padx=12, pady=5)
        self.notes_btn.pack(side="right")

        # -- status line at the very bottom (packed first so it stays visible) --
        foot = tk.Frame(self.root, bg=C["bar"])
        foot.pack(side="bottom", fill="x")
        tk.Frame(self.root, bg=C["line"], height=1).pack(side="bottom", fill="x")
        self.log_btn = FlatButton(foot, "Show log  ▴", self._toggle_log, kind="quiet", font=f["small"],
                                  padx=8, pady=2)
        self.log_btn.pack(side="right", padx=(0, 12), pady=4)
        self.check_btn = FlatButton(foot, "Check for updates", lambda: self._check_updates(force=True),
                                    kind="quiet", font=f["small"], padx=8, pady=2)
        self.check_btn.pack(side="right", pady=4)
        self.auto_btn = FlatButton(foot, "", self._toggle_auto_update, kind="quiet", font=f["small"], padx=8, pady=2)
        self.auto_btn.pack(side="right", pady=4)
        self._paint_auto_btn()
        tk.Label(foot, textvariable=self.footer_var, bg=C["bar"], fg=C["dim"], font=f["small"],
                 anchor="w").pack(side="left", padx=18, pady=6)

        # -- log: hidden until "Show log" (packed above the footer) -------------
        self.log_panel = tk.Frame(self.root, bg=C["field"], highlightthickness=1, highlightbackground=C["line"])
        self.log_text = tk.Text(self.log_panel, height=8, wrap="word", state="disabled", bg=C["field"],
                                fg=C["dim"], font=f["mono"], relief="flat", borderwidth=0, highlightthickness=0,
                                padx=14, pady=10, insertbackground=C["text"], selectbackground=C["accent_soft"])
        scroll = ttk.Scrollbar(self.log_panel, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_visible = False

        # -- body: two columns of cards, the log underneath ---------------------
        self._body = body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=16)
        body.columnconfigure(0, weight=3, uniform="col")
        body.columnconfigure(1, weight=2, uniform="col")

        left = tk.Frame(body, bg=C["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = tk.Frame(body, bg=C["bg"])
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # 1 -- songs folder
        card1 = Card(left, 1, "Songs folder", "Your band's songs, setlists and voice memos live here.", f)
        card1.pack(fill="x")
        self.band_label = self._label(card1.body, "", font="band")
        self.band_meta = self._label(card1.body, "", font="small", fg="dim")
        self._folder_row = row = tk.Frame(card1.body, bg=C["card"])
        row.pack(fill="x")
        self.data_entry = ttk.Entry(row, textvariable=self.data_dir_var, font=f["body"])
        self.data_entry.pack(side="left", fill="x", expand=True)
        self.browse_btn = FlatButton(row, "Browse…", self._browse_data_dir, font=f["button"])
        self.browse_btn.pack(side="left", padx=(8, 0))
        row = tk.Frame(card1.body, bg=C["card"])
        row.pack(fill="x", pady=(8, 0))
        self._label(row, "Recent", font="small", fg="dim").pack(side="left", padx=(0, 8))
        self.recent_combo = ttk.Combobox(row, state="readonly", values=self._recent_values(), font=f["body"])
        self.recent_combo.pack(side="left", fill="x", expand=True)
        self.recent_combo.bind("<<ComboboxSelected>>", self._on_recent_selected)

        # 2 -- server
        card2 = Card(left, 2, "Server", "One server for the whole band: this computer, or a Raspberry Pi.", f)
        card2.pack(fill="x", pady=(16, 0))
        row = tk.Frame(card2.body, bg=C["card"])
        row.pack(fill="x")
        self.start_stop_btn = FlatButton(row, "▶  Start server", self._toggle_server, kind="primary",
                                         font=f["big_button"], padx=18, pady=9)
        self.start_stop_btn.pack(side="left")
        self.open_browser_btn = FlatButton(row, "Open in browser", self._open_browser, font=f["button"], pady=9)
        self.open_browser_btn.pack(side="left", padx=(8, 0))
        self.port_entry = ttk.Entry(row, textvariable=self.port_var, width=6, font=f["body"])
        self.port_entry.pack(side="right")
        self._label(row, "Port", font="small", fg="dim").pack(side="right", padx=(16, 6))

        row = tk.Frame(card2.body, bg=C["card"])
        row.pack(fill="x", pady=(12, 0))
        self.demo_btn = FlatButton(row, "Try the demo band", self._start_demo, kind="ghost",
                                   font=f["button"], padx=8, pady=4)
        self.demo_btn.pack(side="left")
        self._label(row, "a throwaway copy, your songs aren't touched", font="small",
                    fg="faint").pack(side="left", padx=(4, 0))
        self.adv_btn = FlatButton(card2.body, "▸  Advanced: web app folder", self._toggle_advanced_btn,
                                  kind="quiet", font=f["small"], padx=4, pady=2)
        self.adv_btn.pack(pady=(8, 0), anchor="w")
        self.advanced_frame = tk.Frame(card2.body, bg=C["card"])
        self.static_entry = ttk.Entry(self.advanced_frame, textvariable=self.static_dir_var, font=f["body"])
        self.static_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        FlatButton(self.advanced_frame, "Browse…", self._browse_static_dir, font=f["button"]).pack(side="left")
        # advanced_frame is packed/unpacked by _toggle_advanced

        # 3 -- connect (right column)
        card3 = Card(right, 3, "Connect phones & tablets", "Same Wi-Fi as this computer, then scan.", f)
        card3.pack(fill="both", expand=True)
        self.connect_card = card3
        # with a band Wi-Fi: two codes, join the Wi-Fi first, then open SSP
        self.qr_tabs = tk.Frame(card3.body, bg=C["card"])
        self.tab_join = FlatButton(self.qr_tabs, "1 · Join Wi-Fi", lambda: self._set_qr_mode("join"),
                                   font=f["small"], padx=10, pady=3)
        self.tab_join.pack(side="left", padx=(0, 6))
        self.tab_open = FlatButton(self.qr_tabs, "2 · Open SSP", lambda: self._set_qr_mode("open"),
                                   font=f["small"], padx=10, pady=3)
        self.tab_open.pack(side="left")
        self.qr_canvas = tk.Canvas(card3.body, width=196, height=196, highlightthickness=0, bg=C["card"])
        self.qr_canvas.pack(pady=(4, 12))
        self.url_label = self._label(card3.body, "", font="url", fg="accent", cursor="hand2")
        self.url_label.configure(anchor="center", justify="center")
        self.url_label.pack(fill="x")
        self.url_label.bind("<Button-1>", lambda _e: self._open_url(self.url_label.cget("text")))
        self.other_urls = self._label(card3.body, "", font="mono", fg="dim")
        self.other_urls.configure(anchor="center", justify="center")
        self.other_urls.pack(fill="x", pady=(6, 0))
        self.addresses_frame = card3  # older name, kept for anyone scripting this

        # no network here? this computer can be the band's Wi-Fi (server/hotspot.py)
        wifi_row = tk.Frame(card3.body, bg=C["card"])
        wifi_row.pack(fill="x", side="bottom")
        tk.Frame(card3.body, bg=C["line"], height=1).pack(fill="x", pady=(12, 8), side="bottom")
        self.wifi_label = self._label(wifi_row, "", font="small", fg="dim")
        self.wifi_label.configure(anchor="w", justify="left")
        self.wifi_label.pack(side="left", fill="x", expand=True)
        self.wifi_btn = FlatButton(wifi_row, "Make a Wi-Fi", self._wifi_button, kind="ghost",
                                   font=f["button"], padx=8, pady=4)
        self.wifi_btn.pack(side="right")
        self._paint_wifi()

        # 4 -- on stage (full width)
        card4 = Card(body, 4, "On stage", "Who's connected, and what the band sees right now.", f)
        card4.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(16, 0))
        self.live_song = self._label(card4.body, "", font="bold")
        self.live_song.pack(fill="x")
        self.devices_frame = tk.Frame(card4.body, bg=C["card"])
        self.devices_frame.pack(fill="x", pady=(8, 0))


    def _recent_values(self) -> list:
        return self.settings.get("recent_data_dirs", [])

    # -- data / static folder pickers ---------------------------------------

    def _browse_data_dir(self) -> None:
        if self.httpd is not None:
            return
        chosen = filedialog.askdirectory(
            title="Choose (or create) a folder for your band's songs and setlists",
            initialdir=self.data_dir_var.get() or os.path.expanduser("~"),
        )
        if chosen:
            self.data_dir_var.set(chosen)

    def _browse_static_dir(self) -> None:
        if self.httpd is not None:
            return
        chosen = filedialog.askdirectory(
            title="Choose the web app folder (web/static) -- advanced, leave default normally",
            initialdir=self.static_dir_var.get() or os.path.expanduser("~"),
        )
        if chosen:
            self.static_dir_var.set(chosen)

    def _on_recent_selected(self, _event=None) -> None:
        value = self.recent_combo.get()
        if value:
            self.data_dir_var.set(value)

    # -- updates (server/update.py, the same as QLC+ Swiss Knife) -----------

    def _paint_auto_btn(self) -> None:
        self.auto_btn.set(text="Auto-check updates: on" if update.enabled() else "Auto-check updates: off")

    def _toggle_auto_update(self) -> None:
        update.set_enabled(not update.enabled())
        self._paint_auto_btn()
        if update.enabled():
            self._check_updates(force=False, quiet=True)

    def _check_updates(self, force: bool, quiet: bool = False) -> None:
        """Ask GitHub in the background (a few seconds at most); the window
        never waits on the network. quiet: say nothing unless there's news."""
        if self._update_busy:
            return
        self._update_busy = True
        self.check_btn.set(text="Checking…", enabled=False)
        box = {}

        def work():
            box["info"] = update.check(force=force)

        def wait():
            if "info" not in box:
                self.root.after(200, wait)
                return
            self._update_busy = False
            self.check_btn.set(text="Check for updates", enabled=True)
            self._show_update(box["info"], quiet)

        threading.Thread(target=work, daemon=True).start()
        self.root.after(200, wait)

    def _show_update(self, info: dict, quiet: bool) -> None:
        self.update_info = info
        if info.get("newer"):
            self.update_text.configure(text=f"SSP {info.get('latest')} is out")
            if info.get("can_install") and info.get("asset"):
                size = (info["asset"].get("size") or 0) / 1e6
                sub = f"you have {info['current']} · {size:.0f} MB, checked before it's installed" if size \
                    else f"you have {info['current']}"
                self.update_btn.set(text="Update and restart", enabled=True, kind="primary")
                self.update_btn.pack(side="right", padx=(8, 4))
            elif info.get("pending"):
                sub = f"you have {info['current']} · the download for this computer is still being built, " \
                      "try again in a few minutes"
                self.update_btn.pack_forget()
            else:  # running from the source code
                sub = f"you have {info['current']} · update with  git pull  in the SSP folder"
                self.update_btn.pack_forget()
            self.update_sub.configure(text=sub)
            self.update_banner.pack(fill="x", after=self._top_line)
            self._enqueue_log(f"Update: SSP {info.get('latest')} is available (this is {info['current']}).")
        elif not quiet:
            if info.get("error"):
                msg = "Couldn't check for updates (no internet?). SSP doesn't need it."
            else:
                msg = f"You have the latest version ({info['current']})."
            self.footer_var.set(msg)
            self._enqueue_log(msg)

    def _hide_update_banner(self) -> None:
        self.update_banner.pack_forget()

    def _open_release_page(self) -> None:
        url = (self.update_info or {}).get("url") or ""
        if not url.startswith(f"https://github.com/{update.REPO}/"):
            url = f"https://github.com/{update.REPO}/releases/latest"  # only the project's own pages
        webbrowser.open(url)

    def _install_update(self) -> None:
        info = self.update_info or {}
        if self._update_busy or not info.get("newer"):
            return
        running = self.httpd is not None
        if not messagebox.askyesno(
                TITLE,
                f"Update SSP to {info.get('latest')}?\n\n"
                "SSP downloads it from GitHub, checks it against the release's SHA-256 list, "
                "then closes and starts again."
                + ("\n\nThe server stops for a moment: phones and tablets reconnect on their own "
                   "once you press Start again." if running else "")
                + "\n\nYour songs and settings aren't touched."):
            return
        self._update_busy = True
        self.update_btn.set(text="Downloading…", enabled=False)
        self.footer_var.set(f"Downloading SSP {info.get('latest')}…")
        box = {}
        threading.Thread(target=lambda: box.update(res=update.install(info)), daemon=True).start()

        def wait():
            if "res" not in box:
                self.root.after(250, wait)
                return
            self._update_busy = False
            res = box["res"]
            self._enqueue_log("Update: " + res.get("message", ""))
            if res.get("ok") and res.get("restart"):
                self.footer_var.set(res["message"])
                self.root.after(800, self._on_close)  # the swap script waits for this process to end
            else:
                self.update_btn.set(text="Update and restart", enabled=True)
                messagebox.showerror(TITLE, res.get("message") or "Couldn't update.")

        self.root.after(250, wait)

    def _toggle_advanced_btn(self) -> None:
        self.advanced_visible.set(not self.advanced_visible.get())
        self.adv_btn.set(text=("▾" if self.advanced_visible.get() else "▸") + "  Advanced: web app folder")
        self._toggle_advanced()

    def _toggle_log(self) -> None:
        """Show/hide the log under the cards; the window grows to make room."""
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_panel.pack(side="bottom", fill="x", before=self._body)
            self.root.update_idletasks()
            self.root.geometry(f"{w}x{h + self.log_panel.winfo_reqheight()}")
        else:
            extra = self.log_panel.winfo_height()
            self.log_panel.pack_forget()
            self.root.geometry(f"{w}x{max(h - extra, 640)}")
        self.log_btn.set(text="Hide log  ▾" if self.log_visible else "Show log  ▴")

    def _toggle_advanced(self) -> None:
        if self.advanced_visible.get():
            self.advanced_frame.pack(fill="x", pady=(8, 0))
        else:
            self.advanced_frame.pack_forget()

    # -- server lifecycle -----------------------------------------------

    def _toggle_server(self) -> None:
        if self.httpd is None:
            self._start_server()
        else:
            self._stop_server()

    def _start_demo(self) -> None:
        """Serve a fresh copy of the fictional demo band from the app-support
        folder -- a safe place to click around that never touches real songs.
        It's reset each time this button is pressed."""
        if self.httpd is not None:
            self._stop_server()
        self._pre_demo_dir = self.data_dir_var.get()
        try:
            target = server_app.prepare_demo(os.path.join(platform_dirs.user_app_dir(), "demo-data"))
        except OSError as exc:
            messagebox.showerror(TITLE, f"Couldn't set up the demo:\n{exc}")
            return
        self._enqueue_log("Demo band copied to " + target + " (reset every time you press the demo button).")
        self._start_server(data_dir=target, remember=False, demo=True)

    def _start_server(self, data_dir: str = None, remember: bool = True, demo: bool = False) -> None:
        if data_dir is None:
            data_dir = self.data_dir_var.get().strip()
        else:
            self.data_dir_var.set(data_dir)
        static_dir = self.static_dir_var.get().strip()
        if not data_dir:
            messagebox.showerror(TITLE, "Choose a data folder first.")
            return
        try:
            port = int(self.port_var.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror(TITLE, "Port must be a number between 1 and 65535.")
            return

        try:
            # in the demo, the web app's "Back to my band" goes to the folder
            # that was picked before the demo button was pressed
            home = (getattr(self, "_pre_demo_dir", None) or None) if demo else None
            httpd, store = server_app.build_server(data_dir, static_dir, port, demo=demo, home_dir=home)
        except OSError as exc:
            messagebox.showerror(TITLE, f"Couldn't start the server:\n{exc}")
            return
        except Exception as exc:  # noqa: BLE001 - surface any startup problem to the user, not a traceback
            messagebox.showerror(TITLE, f"Couldn't start the server:\n{exc}")
            return

        self.httpd = httpd
        self.store = store
        self._demo = demo
        server_app.Handler.log_hook = self._enqueue_log

        banner = server_app.startup_banner(httpd, store, data_dir, static_dir)
        self._enqueue_log(banner)

        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

        if remember:
            self.settings = launcher_settings.remember_data_dir(self.settings, data_dir)
        self.settings["port"] = port
        launcher_settings.save(self.settings)
        self.recent_combo.configure(values=self._recent_values())

        self._set_running_ui(True, port)

    def _stop_server(self) -> None:
        if self.httpd is None:
            return
        self._enqueue_log("Shutting down...")
        httpd = self.httpd
        self.httpd = None
        self.store = None
        server_app.Handler.log_hook = None

        def _shutdown():
            server_app.stop_server(httpd)
            self.log_queue.put("Stopped.")

        threading.Thread(target=_shutdown, daemon=True).start()
        self._set_running_ui(False, None)
        if getattr(self, "_pre_demo_dir", None) is not None:
            self.data_dir_var.set(self._pre_demo_dir)  # back to the band's own folder
            self._pre_demo_dir = None
        self._demo = False

    def _set_running_ui(self, running: bool, port) -> None:
        self.status_var.set("Running" if running else "Stopped")
        self._draw_status_dot(running)
        self.start_stop_btn.set(text="■  Stop server" if running else "▶  Start server",
                                kind="danger" if running else "primary")
        self.open_browser_btn.set(enabled=running)
        self.browse_btn.set(enabled=not running)
        self.demo_btn.set(enabled=not running)
        state = "disabled" if running else "normal"
        for entry in (self.data_entry, self.static_entry, self.port_entry):
            entry.configure(state=state)
        self.recent_combo.configure(state="disabled" if running else "readonly")
        self._live_sig = None
        if running and port:
            self._show_addresses(port)
            self._refresh_live()
            self.root.after(4000, self._poll_addresses)
        else:
            self._show_addresses(None)
            self._show_band(None)
            self._show_live(None, [])
            self.footer_var.set("Stopped. Your songs are saved.")

    # -- addresses / QR ---------------------------------------------------

    def _show_addresses(self, port) -> None:
        self._port = port
        self._ips = server_app.local_addresses() if port else []
        self._render_connect()

    def _poll_addresses(self) -> None:
        """While the server runs, look again every few seconds (in the
        background: it runs ifconfig/ip/ipconfig), so a Wi-Fi turned on in
        System Settings, a hotspot coming up or a network change show up
        without a restart."""
        if self.httpd is None:
            return
        port = self._port
        box = {}

        def work():
            box["ips"] = server_app.local_addresses()

        def done():
            if "ips" not in box:
                self.root.after(150, done)
                return
            if self.httpd is not None and self._port == port and box["ips"] != self._ips:
                self._ips = box["ips"]
                self._render_connect()
            self.root.after(4000, self._poll_addresses)

        threading.Thread(target=work, daemon=True).start()
        self.root.after(150, done)

    def _set_qr_mode(self, mode: str) -> None:
        self.qr_mode = mode
        self._render_connect()

    def _render_connect(self) -> None:
        port, ips = self._port, self._ips
        wifi = self.wifi
        if wifi:
            self.qr_tabs.pack(before=self.qr_canvas, pady=(0, 6))
            self.tab_join.set(kind="primary" if self.qr_mode == "join" else "secondary")
            self.tab_open.set(kind="primary" if self.qr_mode == "open" else "secondary")
        else:
            self.qr_tabs.pack_forget()
            self.qr_mode = "open"
        if wifi and self.qr_mode == "join":
            self.url_label.configure(text=wifi["ssid"], cursor="arrow")
            self.other_urls.configure(text=f"password  {wifi['password']}\n"
                                           "joined? tap 2 · Open SSP")
            self._draw_qr(qr.wifi_text(wifi["ssid"], wifi["password"]))
            self._paint_wifi()
            return
        self.url_label.configure(cursor="hand2")
        if not port:
            self.url_label.configure(text="")
            self.other_urls.configure(text="The QR code and address\nappear here once the server runs.")
            self._draw_qr(None)
            self._paint_wifi()
            return
        main = f"http://{ips[0]}:{port}/" if ips else f"http://localhost:{port}/"
        self.url_label.configure(text=main.replace("http://", "").rstrip("/"))
        others = [f"{ip}:{port}" for ip in ips[1:]]
        others.append(f"localhost:{port}  (this computer)")
        if not ips:
            others = ["No network here yet:", "make one below."]
        self.other_urls.configure(text="\n".join(others))
        self._draw_qr(main if ips else None)
        self._paint_wifi()

    # -- band Wi-Fi (server/hotspot.py) -----------------------------------

    def _wifi_values(self) -> tuple:
        """The saved name and password, made up (and saved) the first time."""
        ssid = self.settings.get("hotspot_ssid") or hotspot.DEFAULT_SSID
        password = self.settings.get("hotspot_password")
        if not password or hotspot.check(ssid, password):
            password = hotspot.make_password()
            self.settings["hotspot_ssid"], self.settings["hotspot_password"] = ssid, password
            launcher_settings.save(self.settings)
        return ssid, password

    def _paint_wifi(self) -> None:
        wifi = self.wifi
        if self._wifi_busy:
            self.wifi_btn.set(enabled=False)
            return
        if wifi:
            self.wifi_label.configure(text=f"Band Wi-Fi: {wifi['ssid']}", fg=C["ok"], font=self.fonts["bold"])
            self.wifi_btn.set(text="Turn off" if wifi.get("ours") else "Turn off…", kind="secondary", enabled=True)
            return
        offline = self.httpd is not None and not self._ips
        self.wifi_label.configure(text="No network here?" if not offline else "No network: make one",
                                  fg=C["text"] if offline else C["dim"],
                                  font=self.fonts["bold" if offline else "small"])
        self.wifi_btn.set(text="Make a Wi-Fi", kind="primary" if offline else "ghost", enabled=True)

    def _wifi_button(self) -> None:
        if self._wifi_busy:
            return
        if self.wifi:
            self._wifi_off()
        else:
            self._open_wifi_dialog()

    def _set_wifi(self, wifi) -> None:
        """Remember the band Wi-Fi (or None), and give the web app's Connect
        screen the same "join" QR code."""
        self.wifi = wifi
        server_app.Handler.wifi_ssid = wifi["ssid"] if wifi else None
        server_app.Handler.wifi_password = wifi["password"] if wifi else None
        self.qr_mode = "join" if wifi else "open"
        self._render_connect()
        if self.httpd is not None:  # the hotspot's address takes a moment to appear
            for ms in (1500, 4000, 8000):
                self.root.after(ms, lambda p=self._port: self._port == p and self._show_addresses(p))

    def _open_wifi_dialog(self) -> None:
        if self._wifi_dialog is not None and self._wifi_dialog.winfo_exists():
            self._wifi_dialog.lift()
            return
        f = self.fonts
        ssid, password = self._wifi_values()
        one_click = hotspot.one_click()
        steps = hotspot.steps()

        d = tk.Toplevel(self.root)
        self._wifi_dialog = d
        d.title("Band Wi-Fi")
        d.configure(bg=C["card"])
        d.transient(self.root)
        d.resizable(False, False)
        box = tk.Frame(d, bg=C["card"])
        box.pack(fill="both", expand=True, padx=22, pady=18)
        self._label(box, "Make this computer the band's Wi-Fi", font="h").pack(anchor="w")
        intro = ("For a room with no network: phones and tablets join this Wi-Fi, then scan SSP's code. "
                 "It has no internet, and it's only for the band.")
        if one_click and self._ips:
            intro += " While it's on, this computer leaves the network it's on now."
        self._label(box, intro, font="small", fg="dim", wraplength=430, justify="left").pack(anchor="w", pady=(4, 12))

        grid = tk.Frame(box, bg=C["card"])
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        self._wifi_ssid_var = tk.StringVar(value=ssid)
        self._wifi_pass_var = tk.StringVar(value=password)
        self._label(grid, "Name", font="small", fg="dim").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(grid, textvariable=self._wifi_ssid_var, font=f["body"]).grid(row=0, column=1, sticky="ew", pady=4)
        self._label(grid, "Password", font="small", fg="dim").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(grid, textvariable=self._wifi_pass_var, font=f["mono"]).grid(row=1, column=1, sticky="ew", pady=4)
        FlatButton(grid, "New", lambda: self._wifi_pass_var.set(hotspot.make_password()), kind="quiet",
                   font=f["small"], padx=8, pady=3).grid(row=1, column=2, padx=(6, 0))

        self._wifi_steps = self._label(box, "\n".join(steps), font="small", fg="text", wraplength=430,
                                       justify="left")
        if steps and not one_click:
            self._wifi_steps.pack(anchor="w", pady=(12, 0))
        self._wifi_msg = self._label(box, "", font="small", fg="danger", wraplength=430, justify="left")
        self._wifi_msg.pack(anchor="w", pady=(10, 0))

        btns = tk.Frame(box, bg=C["card"])
        btns.pack(fill="x", pady=(10, 0))
        if one_click:
            self._wifi_go = FlatButton(btns, "Turn on Wi-Fi", self._wifi_on, kind="primary", font=f["button"])
        else:
            self._wifi_go = FlatButton(btns, "Open Sharing settings" if steps is hotspot.MAC_STEPS
                                       else "Open settings", self._wifi_open_settings, kind="primary",
                                       font=f["button"])
        self._wifi_go.pack(side="right")
        self._wifi_done = FlatButton(btns, "It's on", self._wifi_manual_done, font=f["button"])
        if not one_click:
            self._wifi_done.pack(side="right", padx=(0, 8))
        FlatButton(btns, "Cancel", d.destroy, kind="quiet", font=f["button"]).pack(side="left")
        d.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - d.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + 120
        d.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _wifi_entered(self):
        """The dialog's name and password, saved, or None (and a message) if they won't do."""
        ssid = self._wifi_ssid_var.get().strip()
        password = self._wifi_pass_var.get()
        problem = hotspot.check(ssid, password)
        if problem:
            self._wifi_msg.configure(text=problem, fg=C["danger"])
            return None
        self.settings["hotspot_ssid"], self.settings["hotspot_password"] = ssid, password
        launcher_settings.save(self.settings)
        return ssid, password

    def _wifi_on(self) -> None:
        values = self._wifi_entered()
        if not values or self._wifi_busy:
            return
        ssid, password = values
        self._wifi_busy = True
        self._wifi_go.set(text="Turning on…", enabled=False)
        self._wifi_msg.configure(text="This can take a few seconds.", fg=C["dim"])
        self._paint_wifi()
        box = {}
        threading.Thread(target=lambda: box.update(r=hotspot.start(ssid, password)), daemon=True).start()

        def wait():
            if "r" not in box:
                self.root.after(150, wait)
                return
            self._wifi_busy = False
            r = box["r"]
            dialog = self._wifi_dialog if self._wifi_dialog is not None and self._wifi_dialog.winfo_exists() else None
            if r["ok"]:
                self._enqueue_log("Band Wi-Fi: " + r["message"])
                self._set_wifi({"ssid": ssid, "password": password, "ours": True})
                self.footer_var.set(f'Band Wi-Fi "{ssid}" is on: phones scan code 1, then 2.')
                if dialog:
                    dialog.destroy()
                return
            self._enqueue_log("Band Wi-Fi didn't start: " + r["message"])
            self._paint_wifi()
            if dialog:
                self._wifi_msg.configure(text=r["message"], fg=C["danger"])
                self._wifi_go.set(text="Try again", enabled=True)
                if r.get("manual"):  # the system's own settings are the way: open them, show the steps
                    hotspot.open_settings()
                    self._wifi_steps.pack(anchor="w", pady=(12, 0), before=self._wifi_msg)
                    self._wifi_done.pack(side="right", padx=(0, 8))

        self.root.after(150, wait)

    def _wifi_open_settings(self) -> None:
        if not self._wifi_entered():
            return
        if hotspot.open_settings():
            self._wifi_msg.configure(text='Settings are open. Once Wi-Fi sharing is on, click "It\'s on".',
                                     fg=C["dim"])
        else:
            self._wifi_msg.configure(text="Couldn't open the settings: open them by hand.", fg=C["danger"])

    def _wifi_manual_done(self) -> None:
        """Turned on in the system's settings: SSP only shows the join code."""
        values = self._wifi_entered()
        if not values:
            return
        self._set_wifi({"ssid": values[0], "password": values[1], "ours": False})
        self.footer_var.set(f'Band Wi-Fi "{values[0]}": phones scan code 1, then 2.')
        if self._wifi_dialog is not None:
            self._wifi_dialog.destroy()

    def _wifi_off(self) -> None:
        wifi = self.wifi
        if not wifi:
            return
        if not wifi.get("ours"):
            hotspot.open_settings()
            self._set_wifi(None)
            self.footer_var.set("Turn the Wi-Fi off in the settings that just opened.")
            return
        self._wifi_busy = True
        self.wifi_btn.set(text="Turning off…", enabled=False)
        box = {}
        threading.Thread(target=lambda: box.update(r=hotspot.stop()), daemon=True).start()

        def wait():
            if "r" not in box:
                self.root.after(150, wait)
                return
            self._wifi_busy = False
            self._enqueue_log("Band Wi-Fi: " + box["r"]["message"])
            self._set_wifi(None)
            self.footer_var.set(box["r"]["message"])

        self.root.after(150, wait)

    def _draw_qr(self, url) -> None:
        c = self.qr_canvas
        c.delete("all")
        size = int(c.cget("width"))
        if not url:
            # a dashed frame with the bar square, faint, as a placeholder
            c.create_rectangle(2, 2, size - 2, size - 2, outline=C["line"], dash=(4, 4), width=2)
            m = size / 2
            c.create_rectangle(m - 34, m - 34, m + 34, m + 34, outline=C["line"], width=3)
            for dx in (-15, 15):
                for dy in (-15, 15):
                    c.create_oval(m + dx - 9, m + dy - 9, m + dx + 9, m + dy + 9, fill=C["line"], outline="")
            return
        matrix = qr.encode(url)
        quiet = 3
        n = len(matrix) + 2 * quiet
        cell = size // n
        offset = (size - cell * n) // 2
        c.create_rectangle(offset, offset, offset + cell * n, offset + cell * n, fill="#ffffff", outline="")
        for y, row in enumerate(matrix):
            for x, v in enumerate(row):
                if v:
                    x0, y0 = offset + (x + quiet) * cell, offset + (y + quiet) * cell
                    c.create_rectangle(x0, y0, x0 + cell, y0 + cell, fill="#000000", outline="")

    def _open_browser(self) -> None:
        if self.httpd is None:
            return
        port = self.port_var.get().strip()
        webbrowser.open(f"http://localhost:{port}/")

    def _open_url(self, text: str) -> None:
        if text and self.httpd is not None:
            webbrowser.open("http://" + text + "/")

    # -- band, devices, what's on stage (polled while running) ----------------

    def _refresh_live(self) -> None:
        store = self.store
        if store is None:
            return
        try:
            band = store.band or {}
            hub, tr = server_app.Handler.hub, server_app.Handler.transport
            presence = hub.presence() if hub else []
            snap = tr.snapshot() if tr else {}
            sig = (band.get("name"), len(band.get("players", [])), len(store.songs), len(store.setlists),
                   tuple((p["client_id"], p["player_id"], p["device"]) for p in presence),
                   snap.get("state"), snap.get("song_id"), snap.get("setlist_id"), self._demo)
            if sig != self._live_sig:
                self._live_sig = sig
                self._show_band(store)
                self._show_live(snap, presence, band)
                n = len(presence)
                self.status_var.set("Running" if not n else f"Running · {n} device{'s' if n != 1 else ''}")
                where = "the demo band (a throwaway copy)" if self._demo else (band.get("name") or "your band")
                self.footer_var.set(f"Serving {where}.")
        except Exception:  # noqa: BLE001 - a display glitch must never take the server down
            pass
        self.root.after(1000, self._refresh_live)

    def _show_band(self, store) -> None:
        if store is None:
            self.band_label.pack_forget()
            self.band_meta.pack_forget()
            return
        band = store.band or {}
        songs, sets, players = len(store.songs), len(store.setlists), len(band.get("players", []))

        def n(count, word):
            return f"{count} {word}{'' if count == 1 else 's'}"

        self.band_label.configure(text=(band.get("name") or "Unnamed band") + ("  ·  demo" if self._demo else ""))
        self.band_meta.configure(text=" · ".join((n(songs, "song"), n(sets, "setlist"), n(players, "player"))))
        self.band_label.pack(fill="x", before=self._folder_row)
        self.band_meta.pack(fill="x", pady=(0, 10), before=self._folder_row)

    def _show_live(self, snap, presence, band=None) -> None:
        for w in self.devices_frame.winfo_children():
            w.destroy()
        if snap is None:
            self.live_song.configure(text="Nothing yet: start the server, then open SSP on each device.",
                                     fg=C["dim"], font=self.fonts["body"])
            return
        store = self.store
        song = store.songs.get(snap.get("song_id")) if store and snap.get("song_id") else None
        setlist = store.setlists.get(snap.get("setlist_id")) if store and snap.get("setlist_id") else None
        if song:
            playing = snap.get("state") == "running"
            text = f"{'▶  Playing' if playing else 'Cued'}:  {song.get('title') or 'Untitled'}"
            if setlist:
                text += f"    ·    {setlist.get('name') or 'Setlist'}"
            self.live_song.configure(text=text, fg=C["ok"] if playing else C["text"], font=self.fonts["bold"])
        else:
            self.live_song.configure(text="No song on the live screens yet.", fg=C["dim"],
                                     font=self.fonts["body"])

        players = {p["id"]: p for p in (band or {}).get("players", [])}
        if not presence:
            self._label(self.devices_frame, "No devices connected. Scan the QR code on a phone or tablet.",
                        font="small", fg="faint").pack(anchor="w")
            return
        shown = presence[:6]
        for p in shown:
            chip = tk.Frame(self.devices_frame, bg=C["btn"])
            chip.pack(side="left", padx=(0, 8), pady=2)
            dot = tk.Canvas(chip, width=8, height=8, bg=C["btn"], highlightthickness=0)
            dot.create_oval(0, 0, 8, 8, fill=C["ok"], outline="")
            dot.pack(side="left", padx=(10, 6), pady=7)
            player = players.get(p.get("player_id"))
            if player:
                who = player.get("name") or "Player"
                if player.get("role"):
                    who += f" · {player['role']}"
            else:
                who = "Whole band"
            tk.Label(chip, text=who, bg=C["btn"], fg=C["text"], font=self.fonts["small"]).pack(side="left")
            if p.get("device"):
                tk.Label(chip, text="  " + p["device"], bg=C["btn"], fg=C["faint"],
                         font=self.fonts["small"]).pack(side="left")
            tk.Frame(chip, bg=C["btn"], width=10).pack(side="left")
        if len(presence) > len(shown):
            self._label(self.devices_frame, f"+{len(presence) - len(shown)} more", font="small",
                        fg="dim").pack(side="left")

    # -- logging --------------------------------------------------------

    def _enqueue_log(self, message: str) -> None:
        self.log_queue.put(message)

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _drain_log_queue(self) -> None:
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", message + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._drain_log_queue)

    def _draw_status_dot(self, running: bool) -> None:
        bg = C["ok_soft"] if running else C["btn"]
        for w in (self.pill, self.pill_dot, self.pill_label):
            w.configure(bg=bg)
        self.pill_label.configure(fg=C["ok"] if running else C["dim"])
        self.pill_dot.delete("all")
        self.pill_dot.create_oval(1, 1, 9, 9, fill=C["ok"] if running else C["faint"], outline="")

    # -- shutdown -------------------------------------------------------

    def _on_close(self) -> None:
        if self.wifi and self.wifi.get("ours"):  # SSP turned it on: SSP turns it off
            try:
                hotspot.stop()
            except Exception:  # noqa: BLE001 - closing on the way out
                pass
        if self.httpd is not None:
            try:
                server_app.stop_server(self.httpd)
            except Exception:  # noqa: BLE001 - closing on the way out, nothing useful to do with an error here
                pass
        launcher_settings.save(self.settings)
        self.root.destroy()


# A windowed build on Windows has no console: print() and the server's log
# would write to None and crash. Send them nowhere instead.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))


def smoke() -> int:
    """Check a packaged build without opening a window (the release
    workflow runs this on every OS): the server starts from the bundle,
    serves the web app, the spoken count-in and the API, and the demo band
    is there. Prints what it checked; exit code 0 when all is well."""
    import tempfile
    import urllib.request

    data = tempfile.mkdtemp(prefix="ssp-smoke-")
    httpd, _store = server_app.build_server(data, paths.default_static_dir(), 0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    ok = True
    try:
        for path, want in (("/", b"<title>"), ("/app.js", b"Metronome"), ("/voice/one.wav", b"RIFF"),
                           ("/manifest.webmanifest", b"standalone"), ("/api/state", b"songs")):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
                body = r.read()
            good = r.status == 200 and want in body
            ok = ok and good
            print(f"{'ok ' if good else 'BAD'} {path}")
        demo = os.path.isfile(os.path.join(paths.demo_data_dir(), "band.json"))
        ok = ok and demo
        print(f"{'ok ' if demo else 'BAD'} demo band")
    finally:
        server_app.stop_server(httpd)
    print(f"SSP {server_app.VERSION}: {'smoke test passed' if ok else 'smoke test FAILED'}")
    return 0 if ok else 1


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--smoke"]:
        sys.exit(smoke())
    if args[:1] == ["--headless"]:
        # the packaged app as a plain server, no window (e.g. a Linux box
        # with no screen): any server option works, e.g. --headless --port 80
        sys.argv = [sys.argv[0]] + args[1:]
        server_app.main()
        return
    update.cleanup_after_update()  # a packaged app just updated: remove the previous version
    root = tk.Tk()
    try:  # the app's icon in the window / taskbar
        root.iconphoto(True, tk.PhotoImage(file=os.path.join(paths.default_static_dir(), "icon-192.png")))
    except tk.TclError:
        pass
    root.geometry("940x790")
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
