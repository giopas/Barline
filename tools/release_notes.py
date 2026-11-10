#!/usr/bin/env python3
"""The title and text of a GitHub release, from CHANGELOG.md.

    python3 tools/release_notes.py v0.10.0                # the title, then the notes
    python3 tools/release_notes.py v0.10.0 --out notes.md # notes into a file, title printed

A version's section starts with a heading like

    ## [0.10.0] -- 2026-11-07

and the line after it (if it's a plain sentence) is used as the short title:
"v0.10.0 · Making Barline easy for a drummer to switch to from a metronome app."
The release workflow (.github/workflows/release.yml) runs this on a v* tag.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "giopas/barline"
_HEAD = re.compile(r"^## \[(?P<ver>[^\]]+)\]")

DOWNLOADS = """
### Downloads

| | |
|---|---|
| **macOS** (Apple silicon: M1 and later) | `Barline-{v}-macos-arm64.dmg` |
| **macOS** (Intel) | `Barline-{v}-macos-x86_64.dmg` |
| **Windows** | `Barline-{v}-windows-x64-setup.exe` (installer) or `Barline-{v}-windows-x64.zip` (no install) |
| **Linux** | `Barline-{v}-linux-x64.tar.gz` |

Open Barline, pick a folder for your songs, press **Start server**, and scan the QR
code with each phone and tablet. No Python needed. The apps aren't signed yet:
on a Mac, the first time, right-click Barline -> **Open** (macOS 15+: System Settings ->
Privacy & Security -> **Open Anyway**; "damaged"? run
`xattr -dr com.apple.quarantine "/Applications/Barline.app"`); on Windows, "More info"
-> **Run anyway**. Allow Barline through the firewall when asked, or phones can't connect. `SHA256SUMS` lists every file's checksum. The macOS
`.tar.gz` files are for the app's own **Update and restart**; download the
`.dmg` instead. Already have Barline 0.12 or later? It offers this update itself.
A Raspberry Pi runs Barline from the source instead: see the wiki page
"Running on a Raspberry Pi". Full history: [CHANGELOG](https://github.com/{repo}/blob/main/CHANGELOG.md).
"""


def section(version: str, text: str):
    """(short title, body) of one version's section; ValueError if missing."""
    v = version.lstrip("v")
    lines = text.splitlines()
    start = next((i + 1 for i, line in enumerate(lines)
                  if _HEAD.match(line) and _HEAD.match(line).group("ver") == v), None)
    if start is None:
        raise ValueError(f"CHANGELOG.md has no section for {v}")
    end = next((j for j in range(start, len(lines)) if lines[j].startswith("## ")), len(lines))
    body = "\n".join(lines[start:end]).strip()
    first = body.split("\n\n", 1)[0].strip()
    title = " ".join(first.split()) if first and not first.startswith(("#", "-", "*", "|")) else ""
    return title, body


def release(version: str, text: str):
    tag = "v" + version.lstrip("v")
    title, body = section(tag, text)
    name = f"{tag} · {title.rstrip('.')}" if title and len(title) <= 80 else tag
    return name, body + "\n" + DOWNLOADS.format(v=tag.lstrip("v"), repo=REPO)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tag")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        name, notes = release(args.tag, f.read())
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(notes)
        print(name)
    else:
        print(name + "\n\n" + notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
