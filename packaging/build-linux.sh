#!/bin/bash
# Build a standalone Linux package of the Single Song Planner launcher.
# Run this ON Linux (PyInstaller does not cross-compile).
#
# Requires: python3 with tkinter (on Debian/Ubuntu: `sudo apt install python3-tk`)
# and `pip install pyinstaller`.
set -e
cd "$(dirname "$0")/.."

python3 -c "import tkinter" 2>/dev/null || {
  echo "tkinter isn't available for this Python. On Debian/Ubuntu: sudo apt install python3-tk" >&2
  exit 1
}

pyinstaller packaging/ssp.spec --distpath dist/linux --workpath build/linux --noconfirm

echo
echo "Built: dist/linux/SingleSongPlanner/"
echo "Run it with: dist/linux/SingleSongPlanner/SingleSongPlanner"
echo "Zip the whole SingleSongPlanner/ folder to distribute it."
