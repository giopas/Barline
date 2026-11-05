"""
Launcher settings: where SSP's desktop control panel remembers what you
told it last time -- which data folder, which port, and the handful of
data folders you've used recently ("sessions", in the sense QLC+ Swiss
Knife uses the term for its recent-workspace list).

One JSON file, in the per-OS app-support folder (see server/platform_dirs.py):

    Windows -> %APPDATA%\\SingleSongPlanner\\config.json
    macOS   -> ~/Library/Application Support/SingleSongPlanner/config.json
    Linux   -> ~/.config/single-song-planner/config.json

This is launcher/UI state only -- never the band's actual song data, which
always lives in whichever data/ folder the config points at (server/storage.py).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

# server/ holds platform_dirs.py; add it to the path so this module works
# whether it's run from source (python3 launcher/gui.py) or bundled by
# PyInstaller alongside server/ (see packaging/).
_SERVER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

import platform_dirs  # noqa: E402

MAX_RECENT = 8

DEFAULTS = {
    "data_dir": None,  # None -> caller falls back to paths.default_data_dir()
    "port": 8420,
    "recent_data_dirs": [],
}


def config_path() -> str:
    app_dir = platform_dirs.ensure_user_app_dir()
    return os.path.join(app_dir, "config.json")


def _atomic_write(path: str, payload: dict) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def load() -> dict:
    path = config_path()
    if not os.path.exists(path):
        return dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save(settings: dict) -> None:
    payload = {k: settings.get(k, DEFAULTS[k]) for k in DEFAULTS}
    _atomic_write(config_path(), payload)


def remember_data_dir(settings: dict, data_dir: str) -> dict:
    """Set `data_dir` as the current one and push it to the front of the
    recent list (deduplicated, capped at MAX_RECENT) -- the "sessions"
    dropdown in the launcher GUI reads this list."""
    data_dir = os.path.abspath(data_dir)
    recent = [d for d in settings.get("recent_data_dirs", []) if d != data_dir]
    recent.insert(0, data_dir)
    settings = dict(settings)
    settings["data_dir"] = data_dir
    settings["recent_data_dirs"] = recent[:MAX_RECENT]
    return settings


def forget_data_dir(settings: dict, data_dir: str) -> dict:
    data_dir = os.path.abspath(data_dir)
    settings = dict(settings)
    settings["recent_data_dirs"] = [d for d in settings.get("recent_data_dirs", []) if d != data_dir]
    if settings.get("data_dir") == data_dir:
        settings["data_dir"] = settings["recent_data_dirs"][0] if settings["recent_data_dirs"] else None
    return settings
