"""
Minimal, stdlib-only per-OS "where does this app's stuff live" helper.

Consistent with the project's "zero/minimal external dependencies" principle
(PROJECT_CHARTER.md section 2) -- no `platformdirs` package, just the same
few environment-variable/home-folder conventions QLC+ Swiss Knife and most
desktop apps use:

    Windows -> %APPDATA%\\SingleSongPlanner
    macOS   -> ~/Library/Application Support/SingleSongPlanner
    Linux   -> $XDG_CONFIG_HOME/single-song-planner or ~/.config/single-song-planner

One folder holds both the launcher's settings (config.json, see
launcher/settings.py) and, by default, the data/ folder the server reads
and writes songs/setlists to -- the same "one app folder" shape as most
desktop apps' app-support directories. The user can always point the data
folder somewhere else from the launcher GUI; this is only the default.
"""

from __future__ import annotations

import os
import platform

APP_NAME = "SingleSongPlanner"


def user_app_dir(app_name: str = APP_NAME) -> str:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
        return os.path.join(base, app_name)
    if system == "Darwin":
        return os.path.expanduser(f"~/Library/Application Support/{app_name}")
    # Linux and anything else POSIX-ish
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, app_name.lower().replace(" ", "-"))


def ensure_user_app_dir(app_name: str = APP_NAME) -> str:
    path = user_app_dir(app_name)
    os.makedirs(path, exist_ok=True)
    return path
