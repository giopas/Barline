#!/usr/bin/env python3
"""
Build Barline Pocket (0.18): the web app as a static site, no server.

    python3 tools/build_pocket.py [--out dist/pocket]

Takes web/static/ as it is and makes a copy that runs on its own:
  * index.html loads pocket.js (answers the app's /api/ calls in the page,
    keeping the songs in the browser's own storage) and registers sw.js;
    every path is made relative, so it works in a sub-folder
    (https://<user>.github.io/barline/);
  * manifest.webmanifest names it "Barline Pocket", for the home screen;
  * sw.js keeps every file for offline use, refreshed when a new version
    is published;
  * demo.ssp.json is the demo band (demo/) as one file, for "Try the demo
    band".

The release workflow runs this and publishes the folder to GitHub Pages.
Standard library only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")
DEMO = os.path.join(ROOT, "demo")
sys.path.insert(0, os.path.join(ROOT, "server"))

from version import VERSION  # noqa: E402

MANIFEST = {
    "name": "Barline Pocket",
    "short_name": "Barline",
    "description": "Your band's song structures and click, on this device: practise and take notes away from the band.",
    "start_url": "./",
    "scope": "./",
    "display": "standalone",
    "orientation": "any",
    "background_color": "#16181d",
    "theme_color": "#16181d",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "icon.svg", "sizes": "any", "type": "image/svg+xml"},
    ],
}

SW = """// Barline Pocket's service worker (tools/build_pocket.py writes it).
// Every file is kept for offline use; a new version replaces them all.
const CACHE = %(cache)s;
const FILES = %(files)s;

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("barline-pocket-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (ev) => {
  const req = ev.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  ev.respondWith(
    caches.match(req, { ignoreSearch: true }).then((hit) => {
      if (hit) return hit;
      return fetch(req).catch(() => (req.mode === "navigate" ? caches.match("./") : Response.error()));
    })
  );
});
"""


def demo_file() -> dict:
    """The demo band (demo/) as one Barline file (ssp_export 2)."""
    with open(os.path.join(DEMO, "band.json"), encoding="utf-8") as f:
        band = json.load(f)
    songs, setlists, audio = [], [], {}
    for name in sorted(os.listdir(os.path.join(DEMO, "songs"))):
        with open(os.path.join(DEMO, "songs", name), encoding="utf-8") as f:
            songs.append(json.load(f))
    for name in sorted(os.listdir(os.path.join(DEMO, "setlists"))):
        with open(os.path.join(DEMO, "setlists", name), encoding="utf-8") as f:
            setlists.append(json.load(f))
    clips = os.path.join(DEMO, "audio")
    used = {h["audio"] for s in songs for sec in s["sections"] for h in sec.get("hints", []) if h.get("audio")}
    for ref in sorted(used):
        path = os.path.join(clips, ref)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                audio[ref] = base64.b64encode(f.read()).decode("ascii")
    songs.sort(key=lambda s: s["title"].lower())
    return {"ssp_export": 2, "band": band, "songs": songs, "setlists": setlists, "audio": audio}


def build(out: str) -> list:
    if os.path.isdir(out):
        shutil.rmtree(out)
    shutil.copytree(STATIC, out, ignore=shutil.ignore_patterns(".*", "__pycache__"))

    index = os.path.join(out, "index.html")
    with open(index, encoding="utf-8") as f:
        html = f.read()
    html = re.sub(r'(src|href)="/(?!/)', r'\1="', html)
    html = html.replace("<title>Barline", "<title>Barline Pocket", 1)
    hook = (f'<script>window.BARLINE_VERSION = {json.dumps(VERSION)};</script>\n'
            '  <script src="pocket.js"></script>\n'
            '  <script>if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});</script>\n'
            '  <script src="files.js"></script>')
    if '<script src="files.js"></script>' not in html:
        raise SystemExit("index.html has no files.js script tag to hook Pocket in front of")
    html = html.replace('<script src="files.js"></script>', hook, 1)
    with open(index, "w", encoding="utf-8") as f:
        f.write(html)

    with open(os.path.join(out, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f, indent=2)
    with open(os.path.join(out, "demo.ssp.json"), "w", encoding="utf-8") as f:
        json.dump(demo_file(), f, ensure_ascii=False)
    open(os.path.join(out, ".nojekyll"), "w").close()

    files = []
    digest = hashlib.sha256(VERSION.encode())
    for dirpath, _dirs, names in os.walk(out):
        for name in sorted(names):
            if name.startswith(".") or name == "sw.js":
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, out).replace(os.sep, "/")
            files.append(rel)
            with open(path, "rb") as f:
                digest.update(rel.encode() + f.read())
    files.sort()
    sw = SW % {"cache": json.dumps(f"barline-pocket-{VERSION}-{digest.hexdigest()[:10]}"),
               "files": json.dumps(["./"] + files, indent=0)}
    with open(os.path.join(out, "sw.js"), "w", encoding="utf-8") as f:
        f.write(sw)
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "dist", "pocket"))
    args = ap.parse_args()
    files = build(args.out)
    print(f"Barline Pocket {VERSION}: {len(files)} files in {args.out}")


if __name__ == "__main__":
    main()
