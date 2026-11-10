"""
Resolves the two paths Barline needs at startup -- where the (read-only, bundled)
web app lives, and where the (user-writable) data/ folder defaults to --
whether running from source (`python3 app.py`) or from a packaged
PyInstaller build (see packaging/).

When frozen by PyInstaller, bundled files are extracted to a temp directory
exposed as `sys._MEIPASS`; a packaged exe's "current directory" is not a
safe place to read from or write to, so:

  - the static web app is read from inside the bundle (read-only, fine)
  - the data/ folder defaults to the per-OS app-support directory
    (platform_dirs.user_app_dir()/data) -- writable, survives updates, and
    is exactly what "indicate where the folder to look for the files and
    engine is" (the launcher GUI) lets the user override.

Running from source keeps the original behaviour: static files and data/
default to their locations relative to this repo.
"""

from __future__ import annotations

import os
import sys

import platform_dirs

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def bundle_dir() -> str:
    """Root of the bundled, read-only resources (the repo root when running
    from source; the PyInstaller extraction dir when packaged)."""
    if is_frozen():
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.normpath(os.path.join(THIS_DIR, ".."))


def default_static_dir() -> str:
    return os.path.join(bundle_dir(), "web", "static")


def default_data_dir() -> str:
    if is_frozen():
        return os.path.join(platform_dirs.user_app_dir(), "data")
    return os.path.normpath(os.path.join(THIS_DIR, "..", "data"))


def demo_data_dir() -> str:
    """The fictional demo band shipped with Barline (read-only; app.py's
    prepare_demo() always serves a copy of it)."""
    return os.path.join(bundle_dir(), "demo")
