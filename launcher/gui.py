#!/usr/bin/env python3
"""
SSP - Song and Setlist Planner -- desktop launcher.

A small Tkinter control panel for the server (same spirit as QLC+ Swiss
Knife being a Tkinter desktop app): pick a data folder, pick a port, start
or stop the server, see the addresses to open on each phone/tablet, and
watch a live log -- without touching a terminal. This is a control panel
for the server process, not a second editor; the actual drafting/live UI
stays the one web app in web/static (see PROJECT_CHARTER.md's "no separate
native desktop editor" decision -- this doesn't reopen that, it's a launcher).

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

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER_DIR = os.path.join(_HERE, "..", "server")
for _p in (_HERE, _SERVER_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app as server_app  # server/app.py
import paths  # server/paths.py
import platform_dirs  # server/platform_dirs.py
import qr  # server/qr.py
import settings as launcher_settings  # launcher/settings.py


class LauncherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SSP - Song and Setlist Planner")
        self.root.minsize(560, 480)

        self.settings = launcher_settings.load()
        self.httpd = None
        self.store = None
        self.server_thread = None
        self.log_queue: "queue.Queue[str]" = queue.Queue()

        self.data_dir_var = tk.StringVar(value=self.settings.get("data_dir") or paths.default_data_dir())
        self.port_var = tk.StringVar(value=str(self.settings.get("port", server_app.DEFAULT_PORT)))
        self.static_dir_var = tk.StringVar(value=paths.default_static_dir())
        self.status_var = tk.StringVar(value="Stopped")
        self.advanced_visible = tk.BooleanVar(value=False)

        self._build_widgets()
        self._drain_log_queue()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- layout ------------------------------------------------------------

    def _build_widgets(self) -> None:
        pad = {"padx": 10, "pady": 6}

        header = ttk.Frame(self.root)
        header.pack(fill="x", **pad)
        ttk.Label(header, text="SSP - Song and Setlist Planner", font=("", 15, "bold")).pack(side="left")
        self.status_dot = tk.Canvas(header, width=12, height=12, highlightthickness=0)
        self.status_dot.pack(side="right", padx=(0, 4))
        self._draw_status_dot(False)
        ttk.Label(header, textvariable=self.status_var).pack(side="right")

        # -- data folder --------------------------------------------------
        data_frame = ttk.LabelFrame(self.root, text="Data folder (your band's songs and setlists)")
        data_frame.pack(fill="x", **pad)

        row1 = ttk.Frame(data_frame)
        row1.pack(fill="x", padx=8, pady=(8, 2))
        self.data_entry = ttk.Entry(row1, textvariable=self.data_dir_var)
        self.data_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row1, text="Browse…", command=self._browse_data_dir).pack(side="left", padx=(6, 0))

        row2 = ttk.Frame(data_frame)
        row2.pack(fill="x", padx=8, pady=(2, 8))
        ttk.Label(row2, text="Recent:").pack(side="left")
        self.recent_combo = ttk.Combobox(row2, state="readonly", values=self._recent_values())
        self.recent_combo.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.recent_combo.bind("<<ComboboxSelected>>", self._on_recent_selected)

        # -- server ---------------------------------------------------------
        server_frame = ttk.LabelFrame(self.root, text="Server")
        server_frame.pack(fill="x", **pad)

        row3 = ttk.Frame(server_frame)
        row3.pack(fill="x", padx=8, pady=8)
        ttk.Label(row3, text="Port:").pack(side="left")
        ttk.Entry(row3, textvariable=self.port_var, width=8).pack(side="left", padx=(6, 16))
        self.start_stop_btn = ttk.Button(row3, text="Start server", command=self._toggle_server)
        self.start_stop_btn.pack(side="left")
        self.open_browser_btn = ttk.Button(
            row3, text="Open in browser", command=self._open_browser, state="disabled"
        )
        self.open_browser_btn.pack(side="left", padx=(8, 0))
        self.demo_btn = ttk.Button(row3, text="Try the demo band", command=self._start_demo)
        self.demo_btn.pack(side="right")

        adv_toggle = ttk.Checkbutton(
            server_frame,
            text="Advanced: web app folder",
            variable=self.advanced_visible,
            command=self._toggle_advanced,
        )
        adv_toggle.pack(fill="x", padx=8, anchor="w")
        self.advanced_frame = ttk.Frame(server_frame)
        self.static_entry = ttk.Entry(self.advanced_frame, textvariable=self.static_dir_var)
        self.static_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(self.advanced_frame, text="Browse…", command=self._browse_static_dir).pack(side="left")
        # advanced_frame is packed/unpacked by _toggle_advanced

        # -- addresses --------------------------------------------------------
        self.addresses_frame = ttk.LabelFrame(self.root, text="Open on each phone/tablet (same Wi-Fi), or scan")
        self.qr_canvas = tk.Canvas(self.addresses_frame, width=148, height=148, highlightthickness=0, bg="white")
        self.qr_canvas.pack(side="left", padx=8, pady=8)
        self.addresses_text = tk.Text(self.addresses_frame, height=6, wrap="none")
        self.addresses_text.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)
        self.addresses_text.configure(state="disabled")
        # addresses_frame is packed/unpacked when the server starts/stops

        # -- log ------------------------------------------------------------
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="right", fill="y", pady=8, padx=(0, 8))

    def _recent_values(self) -> list:
        return self.settings.get("recent_data_dirs", [])

    # -- data / static folder pickers ---------------------------------------

    def _browse_data_dir(self) -> None:
        chosen = filedialog.askdirectory(
            title="Choose (or create) a folder for your band's songs and setlists",
            initialdir=self.data_dir_var.get() or os.path.expanduser("~"),
        )
        if chosen:
            self.data_dir_var.set(chosen)

    def _browse_static_dir(self) -> None:
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

    def _toggle_advanced(self) -> None:
        if self.advanced_visible.get():
            self.advanced_frame.pack(fill="x", padx=8, pady=(0, 8))
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
            messagebox.showerror("SSP - Song and Setlist Planner", f"Couldn't set up the demo:\n{exc}")
            return
        self._enqueue_log("Demo band copied to " + target + " (reset every time you press the demo button).")
        self._start_server(data_dir=target, remember=False)

    def _start_server(self, data_dir: str = None, remember: bool = True) -> None:
        if data_dir is None:
            data_dir = self.data_dir_var.get().strip()
        else:
            self.data_dir_var.set(data_dir)
        static_dir = self.static_dir_var.get().strip()
        if not data_dir:
            messagebox.showerror("SSP - Song and Setlist Planner", "Choose a data folder first.")
            return
        try:
            port = int(self.port_var.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("SSP - Song and Setlist Planner", "Port must be a number between 1 and 65535.")
            return

        try:
            httpd, store = server_app.build_server(data_dir, static_dir, port)
        except OSError as exc:
            messagebox.showerror("SSP - Song and Setlist Planner", f"Couldn't start the server:\n{exc}")
            return
        except Exception as exc:  # noqa: BLE001 - surface any startup problem to the user, not a traceback
            messagebox.showerror("SSP - Song and Setlist Planner", f"Couldn't start the server:\n{exc}")
            return

        self.httpd = httpd
        self.store = store
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
        server_app.Handler.log_hook = None

        def _shutdown():
            server_app.stop_server(httpd)
            self.log_queue.put("Stopped.")

        threading.Thread(target=_shutdown, daemon=True).start()
        self._set_running_ui(False, None)
        if getattr(self, "_pre_demo_dir", None) is not None:
            self.data_dir_var.set(self._pre_demo_dir)  # back to the band's own folder
            self._pre_demo_dir = None

    def _set_running_ui(self, running: bool, port) -> None:
        self.status_var.set("Running" if running else "Stopped")
        self._draw_status_dot(running)
        self.start_stop_btn.configure(text="Stop server" if running else "Start server")
        self.open_browser_btn.configure(state="normal" if running else "disabled")
        self.data_entry.configure(state="disabled" if running else "normal")
        self.static_entry.configure(state="disabled" if running else "normal")
        self.demo_btn.configure(state="disabled" if running else "normal")
        if running and port:
            self._show_addresses(port)
            self.addresses_frame.pack(fill="x", padx=10, pady=6, before=self._log_frame())
        else:
            self.addresses_frame.pack_forget()

    def _log_frame(self):
        return self.log_text.master

    def _show_addresses(self, port: int) -> None:
        ips = server_app.local_addresses()
        lines = [f"http://{ip}:{port}/" for ip in ips]
        lines.append(f"http://localhost:{port}/   (this computer only)")
        self._draw_qr(f"http://{ips[0]}:{port}/" if ips else None)
        self.addresses_text.configure(state="normal")
        self.addresses_text.delete("1.0", "end")
        self.addresses_text.insert("1.0", "\n".join(lines))
        self.addresses_text.configure(state="disabled")

    def _draw_qr(self, url) -> None:
        c = self.qr_canvas
        c.delete("all")
        if not url:
            c.create_text(74, 74, text="no Wi-Fi\naddress found", justify="center")
            return
        m = qr.encode(url)
        quiet = 2
        n = len(m) + 2 * quiet
        cell = 148 / n
        for y, row in enumerate(m):
            for x, v in enumerate(row):
                if v:
                    x0, y0 = (x + quiet) * cell, (y + quiet) * cell
                    c.create_rectangle(x0, y0, x0 + cell, y0 + cell, fill="black", outline="black")

    def _open_browser(self) -> None:
        port = self.port_var.get().strip()
        webbrowser.open(f"http://localhost:{port}/")

    # -- logging --------------------------------------------------------

    def _enqueue_log(self, message: str) -> None:
        self.log_queue.put(message)

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
        self.status_dot.delete("all")
        color = "#45c08a" if running else "#8a8f99"
        self.status_dot.create_oval(1, 1, 11, 11, fill=color, outline="")

    # -- shutdown -------------------------------------------------------

    def _on_close(self) -> None:
        if self.httpd is not None:
            try:
                server_app.stop_server(self.httpd)
            except Exception:  # noqa: BLE001 - closing on the way out, nothing useful to do with an error here
                pass
        launcher_settings.save(self.settings)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
