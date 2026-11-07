@echo off
rem Build SSP for Windows here (PyInstaller doesn't cross-compile).
rem Pushing a version tag builds every OS on GitHub instead: .github\workflows\release.yml
rem
rem Needs Python from python.org (tkinter included) and `pip install pyinstaller`.
rem With Inno Setup 6 installed, the installer (-setup.exe) is built too.
cd /d "%~dp0\.."
python -c "import tkinter" 2>nul || (echo tkinter isn't available for this Python. Use the installer from python.org. & exit /b 1)
pyinstaller --noconfirm packaging\ssp.spec || exit /b 1
"dist\SSP\SSP Server.exe" --smoke || exit /b 1
python packaging\make_archive.py || exit /b 1
echo.
echo Built: dist\SSP\SSP.exe   (downloads in release\)
