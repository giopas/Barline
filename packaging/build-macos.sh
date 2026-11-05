#!/bin/bash
# Build a standalone macOS .app of the SSP - Song and Setlist Planner launcher.
# Run this ON macOS (PyInstaller does not cross-compile).
#
# Requires: python3.org's Python (bundles Tk) or Homebrew's `python-tk`,
# and `pip install pyinstaller`.
set -e
cd "$(dirname "$0")/.."

python3 -c "import tkinter" 2>/dev/null || {
  echo "tkinter isn't available for this Python. With Homebrew: brew install python-tk" >&2
  exit 1
}

pyinstaller packaging/ssp.spec --distpath dist/macos --workpath build/macos --noconfirm

echo
echo "Built: dist/macos/SSP - Song and Setlist Planner.app"
echo "Not code-signed or notarised (see PROJECT_CHARTER.md section 4) -- the first"
echo "launch needs a right-click > Open (or System Settings > Privacy & Security > Open Anyway)."
echo "Zip the .app to distribute it."
