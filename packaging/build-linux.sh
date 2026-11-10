#!/bin/bash
# Build the standalone Linux app of Barline here (PyInstaller doesn't cross-compile).
# Pushing a version tag builds every OS on GitHub instead: .github/workflows/release.yml
#
# Needs python3 with tkinter (Debian/Ubuntu: sudo apt install python3-tk) and
# `pip install pyinstaller certifi` (certifi: the update check).
set -e
cd "$(dirname "$0")/.."
python3 -c "import tkinter" 2>/dev/null || {
  echo "tkinter isn't available for this Python. On Debian/Ubuntu: sudo apt install python3-tk" >&2
  exit 1
}
pyinstaller --noconfirm packaging/ssp.spec
dist/Barline/Barline --smoke
python3 packaging/make_archive.py
echo
echo "Built: dist/Barline/Barline   (download file in release/)"
