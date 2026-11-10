@echo off
REM Double-click "Start Barline" launcher for Windows.
REM Opens the desktop control panel (launcher\gui.py) -- pick a data folder,
REM start/stop the server, see the addresses to open on each phone/tablet.
cd /d "%~dp0.."
echo Starting Barline - Song and Setlist Planner...
python launcher\gui.py
