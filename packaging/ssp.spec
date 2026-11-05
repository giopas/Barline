# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the SSP - Song and Setlist Planner desktop launcher.
#
# Packages launcher/gui.py (the Tkinter control panel) together with the
# server package and the web app's static files into a standalone,
# double-click-to-run build -- same idea as QLC+ Swiss Knife's packaged
# builds, so a band member doesn't need Python installed at all.
#
# PyInstaller can't cross-compile: run this ON each target OS (see the
# platform-specific scripts alongside this file). The one-directory
# ("onedir") output below starts faster than --onefile and is easier to
# inspect/debug; zip the resulting folder to distribute it.
#
# Usage (from the repo root):
#   pyinstaller packaging/ssp.spec --distpath dist --workpath build --noconfirm

import os
import sys

block_cipher = None

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 - SPECPATH is injected by PyInstaller
SERVER_DIR = os.path.join(ROOT, "server")
LAUNCHER_DIR = os.path.join(ROOT, "launcher")
STATIC_DIR = os.path.join(ROOT, "web", "static")

# Technical identifier only -- kept stable across the "SSP - Song and
# Setlist Planner" rename so it doesn't move or orphan a user's already
# -saved settings file or data folder (see server/platform_dirs.py, which
# uses the same name). The binary/folder on disk stays "SingleSongPlanner";
# only user-facing display strings below (window titles, the macOS bundle
# name) carry the new name.
APP_NAME = "SingleSongPlanner"

a = Analysis(  # noqa: F821
    [os.path.join(LAUNCHER_DIR, "gui.py")],
    pathex=[SERVER_DIR, LAUNCHER_DIR],
    binaries=[],
    # Bundles the web app's static files read-only inside the package, at
    # the same "web/static" relative path server/paths.py expects under
    # sys._MEIPASS. The data/ folder (actual song/setlist storage) is never
    # bundled -- it's created at runtime wherever the user points the
    # launcher (defaulting to the per-OS app-support folder; see
    # server/platform_dirs.py).
    # The fictional demo band (demo/) is bundled read-only too, for the
    # launcher's "Try the demo band" button (always served from a copy).
    datas=[(STATIC_DIR, os.path.join("web", "static")), (os.path.join(ROOT, "demo"), "demo")],
    hiddenimports=["app", "paths", "platform_dirs", "storage", "models", "settings", "timeline",
                   "transport", "events", "export", "click_track", "qr", "version"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed app -- no terminal popping up alongside the GUI
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

# On macOS, wrap the onedir build into a proper double-clickable .app.
# No code signing / notarisation yet -- matches the charter's "later if
# someone asks" stance (PROJECT_CHARTER.md section 4); an unsigned .app
# will need an explicit "Open anyway" the first time (see README).
if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="SSP - Song and Setlist Planner.app",
        icon=None,
        bundle_identifier="com.giopas.singlesongplanner",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleName": "SSP - Song and Setlist Planner",
        },
    )
