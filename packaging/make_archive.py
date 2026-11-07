#!/usr/bin/env python3
"""Pack the PyInstaller output (dist/) into the download for this OS.

    pyinstaller --noconfirm packaging/ssp.spec
    python packaging/make_archive.py      # -> release/SSP-<version>-<os>-<arch>.<ext>

  macOS    .dmg (drag SSP into Applications), and a .tar.gz the in-app updater uses
  Windows  -setup.exe (installer, per user, no admin; needs Inno Setup) and a portable .zip
  Linux    .tar.gz
"""
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))
from version import VERSION  # noqa: E402


def platform_key():
    system = {"Darwin": "macos", "Windows": "windows"}.get(platform.system(), "linux")
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    if system == "macos" and arch == "x64":
        arch = "x86_64"  # what Mac users see in "About This Mac" for Intel... close enough, and unambiguous
    return system, arch


def asset_name(ext: str, o: str = None, a: str = None) -> str:
    """The file name server/update.py looks for (its _ASSET_RE)."""
    if not o:
        o, a = platform_key()
    return f"SSP-{VERSION}-{o}-{a}.{ext}"


def main() -> int:
    dist, out = os.path.join(ROOT, "dist"), os.path.join(ROOT, "release")
    os.makedirs(out, exist_ok=True)
    system = platform.system()
    if system == "Darwin":
        app = os.path.join(dist, "SSP.app")
        # The updater's archive is a .tar.gz, not a .zip: Python's zipfile writes the .app's
        # symlinks (Frameworks/, Resources/) as plain text files and the updated app then
        # can't start (found the hard way in QLC+ Swiss Knife). tarfile keeps links and modes.
        with tarfile.open(os.path.join(out, asset_name("tar.gz")), "w:gz") as t:
            t.add(app, arcname="SSP.app")
        stage = os.path.join(out, "dmg-stage")
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage)
        subprocess.check_call(["ditto", app, os.path.join(stage, "SSP.app")])  # keeps the .app's links
        os.symlink("/Applications", os.path.join(stage, "Applications"))
        subprocess.check_call(["hdiutil", "create", "-volname", "SSP", "-srcfolder", stage,
                               "-ov", "-format", "UDZO", os.path.join(out, asset_name("dmg"))])
        shutil.rmtree(stage)
    elif system == "Windows":
        folder = os.path.join(dist, "SSP")
        with zipfile.ZipFile(os.path.join(out, asset_name("zip")), "w", zipfile.ZIP_DEFLATED) as zf:
            for d, _dirs, files in os.walk(folder):
                for f in files:
                    p = os.path.join(d, f)
                    zf.write(p, os.path.join("SSP", os.path.relpath(p, folder)))
        iscc = shutil.which("ISCC") or next((c for c in (
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe")) if os.path.exists(c)), None)
        if iscc:
            subprocess.check_call([iscc, f"/DAppVersion={VERSION}",
                                   os.path.join(ROOT, "packaging", "windows", "installer.iss")])
        else:
            print("Inno Setup (ISCC) not found: no installer, only the portable .zip.")
    else:
        with tarfile.open(os.path.join(out, asset_name("tar.gz")), "w:gz") as t:
            t.add(os.path.join(dist, "SSP"), arcname="SSP")
    for f in sorted(os.listdir(out)):
        print(f, os.path.getsize(os.path.join(out, f)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
