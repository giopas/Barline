#!/bin/bash
# Build SSP.app and the .dmg on this Mac (PyInstaller doesn't cross-compile;
# the app is for this Mac's chip, Apple silicon or Intel).
# Pushing a version tag builds every OS on GitHub instead: .github/workflows/release.yml
#
# Needs a python3 with tkinter (the python.org installer has it) and
# `pip install pyinstaller certifi` (certifi: the update check).
set -e
cd "$(dirname "$0")/.."
python3 -c "import tkinter" 2>/dev/null || {
  echo "tkinter isn't available for this Python. Use the installer from python.org." >&2
  exit 1
}
pyinstaller --noconfirm packaging/ssp.spec
dist/SSP.app/Contents/MacOS/SSP --smoke
python3 packaging/make_archive.py
echo
echo "Built: dist/SSP.app   (and the .dmg in release/)"
echo "Not signed: the first time, right-click SSP.app -> Open (or System Settings -> Privacy & Security -> Open Anyway)."
