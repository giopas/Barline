@echo off
REM Build a standalone Windows package of the SSP - Song and Setlist Planner launcher.
REM Run this ON Windows (PyInstaller does not cross-compile).
REM
REM Requires: python.org's Python (bundles Tk by default) and `pip install pyinstaller`.

cd /d "%~dp0.."

python -c "import tkinter" 2>NUL
if errorlevel 1 (
  echo tkinter isn't available for this Python install. Use the python.org installer, which bundles it.
  exit /b 1
)

pyinstaller packaging\ssp.spec --distpath dist\windows --workpath build\windows --noconfirm

echo.
echo Built: dist\windows\SingleSongPlanner\
echo Run it with: dist\windows\SingleSongPlanner\SingleSongPlanner.exe
echo Zip the whole SingleSongPlanner\ folder to distribute it.
pause
