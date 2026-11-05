#!/bin/bash
# Double-click "Start SSP" launcher for macOS.
# Opens the desktop control panel (launcher/gui.py) -- pick a data folder,
# start/stop the server, see the addresses to open on each phone/tablet.
# For a headless Pi instead, run server/app.py directly (see launchers/ssp.service).
set -e
cd "$(dirname "$0")/.."
echo "Starting Single Song Planner..."
python3 launcher/gui.py
