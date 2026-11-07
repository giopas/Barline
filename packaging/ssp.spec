# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for SSP - Song and Setlist Planner: the server, the web
# app and the desktop control panel (launcher/gui.py) as one standalone
# app, so a band member doesn't need Python installed at all. Same idea as
# QLC+ Swiss Knife's packaged builds.
#
#   pip install pyinstaller
#   pyinstaller --noconfirm packaging/ssp.spec
#
# -> dist/SSP.app (macOS), dist/SSP/SSP.exe + SSP Server.exe (Windows),
#    dist/SSP/SSP (Linux). Check a build with:  <the app> --smoke
# PyInstaller can't cross-compile: each OS builds its own (the release
# workflow, .github/workflows/release.yml, does all of them on a tag).
#
# The app's *settings and songs* folder keeps its old technical name
# (platform_dirs.APP_NAME = "SingleSongPlanner", and the macOS bundle id),
# so nobody's saved songs move. Only the program's own name is "SSP".

import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 - injected by PyInstaller
SERVER_DIR = os.path.join(ROOT, "server")
LAUNCHER_DIR = os.path.join(ROOT, "launcher")
ICONS = os.path.join(ROOT, "packaging", "icons")

sys.path.insert(0, SERVER_DIR)
from version import VERSION  # noqa: E402

a = Analysis(  # noqa: F821
    [os.path.join(LAUNCHER_DIR, "gui.py")],
    pathex=[SERVER_DIR, LAUNCHER_DIR],
    binaries=[],
    # the web app (read-only, where server/paths.py looks for it) and the
    # fictional demo band. Songs are never bundled: they live in the
    # user's own folder (server/platform_dirs.py).
    datas=[(os.path.join(ROOT, "web", "static"), os.path.join("web", "static")),
           (os.path.join(ROOT, "demo"), "demo")],
    hiddenimports=["app", "paths", "platform_dirs", "storage", "models", "settings", "timeline",
                   "transport", "events", "export", "click_track", "qr", "version"],
    excludes=["pytest", "playwright", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

NAME = "SSP"
WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"

exe = EXE(  # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=NAME,
    console=not (WIN or MAC),  # Linux: run from a terminal it shows the log; double-clicked it doesn't matter
    upx=False,
    icon=os.path.join(ICONS, "icon.ico") if WIN else None,
)
if WIN:
    # a window-only exe has no console: a second one that does, for
    # "SSP Server.exe --headless" (a plain server in a terminal) and --smoke
    exe_console = EXE(  # noqa: F821
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="SSP Server",
        console=True,
        upx=False,
        icon=os.path.join(ICONS, "icon.ico"),
    )
    coll = COLLECT(exe, exe_console, a.binaries, a.datas, name=NAME, upx=False)  # noqa: F821
else:
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)  # noqa: F821

if MAC:
    app = BUNDLE(  # noqa: F821
        coll,
        name="SSP.app",
        icon=os.path.join(ICONS, "icon.icns"),
        bundle_identifier="com.giopas.singlesongplanner",  # unchanged since 0.1: keeps macOS settings in place
        info_plist={
            "CFBundleName": "SSP",
            "CFBundleDisplayName": "SSP - Song and Setlist Planner",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSLocalNetworkUsageDescription": "SSP serves your band's songs to phones and tablets on this Wi-Fi.",
        },
    )
