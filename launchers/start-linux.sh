#!/bin/bash
# Double-click (or run from a terminal) "Start SSP" launcher for Linux.
# Opens the desktop control panel (launcher/gui.py) -- pick a data folder,
# start/stop the server, see the addresses to open on each phone/tablet.
# For a headless Pi instead, run server/app.py directly (see ssp.service).
set -e
cd "$(dirname "$0")/.."
echo "Starting SSP - Song and Setlist Planner..."
python3 launcher/gui.py
