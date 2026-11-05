"""
Export (v0.7): getting songs out of SSP.

Two kinds:

  * Printable charts -- a plain, light-themed HTML page per song or per
    setlist, for the whole band or for one player (that player's hints plus
    the band-wide ones). Open it, then use the browser's Print -> "Save as
    PDF" for a PDF. Server-rendered, no script, so it prints the same
    everywhere.
  * A portable song file (`.ssp.json`) -- the song plus any recorded hint
    clips, base64-encoded, in one file you can email or put on a USB stick
    and import on another band's SSP. The plain `data/songs/<id>.json` is
    still portable on its own; this is the version that keeps the clips.
"""

from __future__ import annotations

import base64
import binascii
import copy
import html
import os

import models
import timeline

# Same palette as web/static/app.js, so a printout matches the screen.
PALETTE = ["#5b8cff", "#45c08a", "#e2b93b", "#e2574c", "#b073f0", "#39c2c9", "#f08a3c", "#6fcf97"]
EXPORT_FORMAT = 1


def _e(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def fmt_duration(ms: float) -> str:
    s = int(round(ms / 1000.0))
    return f"{s // 60}:{s % 60:02d}"


def _player_map(band: dict) -> dict:
    return {p["id"]: p for p in band.get("players", [])}


def _song_block(song: dict, band: dict, player_id: str = None) -> str:
    players = _player_map(band)
    sections = sorted(song.get("sections", []), key=lambda s: s.get("order", 0))
    total = sum(s["bars"] for s in sections) or 1
    shape = "".join(
        f'<div class="blk" style="flex-grow:{s["bars"]};background:{PALETTE[i % len(PALETTE)]}">'
        f'{_e(s["label"]) if s["bars"] / total > 0.06 else ""}</div>'
        for i, s in enumerate(sections)
    )
    rows = []
    bar = 1
    for i, s in enumerate(sections):
        bpm = s.get("bpm") or song["default_bpm"]
        ci = s.get("count_in") or {}
        ci_txt = f'{ci.get("bars")} bar{"s" if ci.get("bars") != 1 else ""} ({_e(ci.get("style"))})' \
            if ci.get("style", "none") != "none" and ci.get("bars") else ""
        hints = []
        for h in s.get("hints", []):
            vis = h.get("visibility", "all")
            if player_id and vis not in ("all", player_id):
                continue
            if not (h.get("text") or "").strip() and not h.get("audio"):
                continue
            who = ""
            cls = "hint"
            if vis != "all":
                p = players.get(vis)
                who = f'<span class="who">{_e(p["name"]) if p else "?"}</span> '
                if player_id and vis == player_id:
                    cls += " mine"
            clip = ' <span class="clip">(voice memo)</span>' if h.get("audio") else ""
            hints.append(f'<li class="{cls}">{who}{_e(h.get("text"))}{clip}</li>')
        tempo = f'<b>{bpm}</b>' if s.get("bpm") else str(bpm)
        rows.append(
            f'<tr><td class="sw" style="background:{PALETTE[i % len(PALETTE)]}"></td>'
            f'<td class="num">{bar}</td><td class="lbl">{_e(s["label"])}</td>'
            f'<td class="num">{s["bars"]}</td><td class="num">{tempo}</td><td>{ci_txt}</td>'
            f'<td><ul>{"".join(hints)}</ul></td></tr>'
        )
        bar += s["bars"]
    dur = fmt_duration(timeline.duration_ms(song)) if sections else "0:00"
    return (
        f'<section class="song"><h1>{_e(song["title"])}</h1>'
        f'<p class="meta">{song["default_bpm"]} BPM · {total if sections else 0} bars · about {dur}</p>'
        f'<div class="shape">{shape}</div>'
        '<table><thead><tr><th></th><th>Bar</th><th>Section</th><th>Bars</th><th>BPM</th>'
        '<th>Count-in</th><th>Hints</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></section>'
    )


_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
color:#111;background:#fff;margin:24px;font-size:13px}
h1{font-size:22px;margin:0 0 2px}.meta{color:#555;margin:0 0 10px}
.top{color:#555;font-size:12px;border-bottom:1px solid #ddd;padding-bottom:6px;margin-bottom:14px}
.shape{display:flex;gap:2px;height:22px;margin-bottom:12px;border-radius:4px;overflow:hidden}
.blk{color:#fff;font-size:10px;display:flex;align-items:center;justify-content:center;
white-space:nowrap;overflow:hidden;-webkit-print-color-adjust:exact;print-color-adjust:exact}
table{border-collapse:collapse;width:100%}th{text-align:left;font-size:11px;color:#555;
border-bottom:1px solid #ccc;padding:4px 6px}td{border-bottom:1px solid #eee;padding:5px 6px;vertical-align:top}
td.sw{width:6px;padding:0;-webkit-print-color-adjust:exact;print-color-adjust:exact}
td.num{text-align:right;width:40px;color:#333}td.lbl{font-weight:600;width:22%}
ul{margin:0;padding-left:16px}.who{font-weight:600}.mine{font-weight:700}
.mine::before{content:"\\2192 ";}.clip{color:#777;font-style:italic}
.song{page-break-after:always;margin-bottom:28px}.song:last-child{page-break-after:auto}
ol.setlist{font-size:15px;line-height:1.6}
@media print{body{margin:12mm}.noprint{display:none}}
.noprint{margin-bottom:14px;color:#555}
"""


def _page(title: str, body: str, band: dict, player_id: str = None) -> str:
    who = "whole band"
    p = _player_map(band).get(player_id) if player_id else None
    if p:
        who = f'{_e(p["name"])} ({_e(p["role"])})'
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{_e(title)}</title><style>{_CSS}</style></head><body>"
        "<p class=\"noprint\">Print this page (or Save as PDF) from your browser's menu.</p>"
        f'<div class="top">{_e(band.get("name", ""))} · chart for {who} · made with SSP</div>'
        f"{body}</body></html>"
    )


def song_html(song: dict, band: dict, player_id: str = None) -> str:
    return _page(song["title"], _song_block(song, band, player_id), band, player_id)


def setlist_html(setlist: dict, songs: dict, band: dict, player_id: str = None) -> str:
    present = [songs[s] for s in setlist["songs"] if s in songs]
    total = sum(timeline.duration_ms(s) for s in present)
    cover = (
        f'<section class="song"><h1>{_e(setlist["name"])}</h1>'
        f'<p class="meta">{len(present)} songs · about {fmt_duration(total)} of music</p>'
        '<ol class="setlist">'
        + "".join(f'<li>{_e(s["title"])} <span class="meta">— {s["default_bpm"]} BPM, '
                  f'{fmt_duration(timeline.duration_ms(s))}</span></li>' for s in present)
        + "</ol></section>"
    )
    return _page(setlist["name"], cover + "".join(_song_block(s, band, player_id) for s in present),
                 band, player_id)


# ---------------------------------------------------------------------------
# Portable song file
# ---------------------------------------------------------------------------

def bundle(song: dict, storage) -> dict:
    clips = {}
    for ref in sorted(models.audio_refs(song)):
        try:
            clips[ref] = base64.b64encode(storage.read_audio(ref)).decode("ascii")
        except (OSError, ValueError):
            pass  # a clip that went missing: export the song without it
    return {"ssp_export": EXPORT_FORMAT, "song": song, "audio": clips}


def unbundle(payload: dict, storage, taken_ids) -> dict:
    """A song ready to add to the store from an exported file (or a plain
    song .json). Gets a fresh id when its own is already used here, and
    fresh clip names, so importing never overwrites anything."""
    if not isinstance(payload, dict):
        raise models.ValidationError("that isn't an SSP song file")
    song = payload.get("song") if "ssp_export" in payload else payload
    if not isinstance(song, dict) or "sections" not in song:
        raise models.ValidationError("that isn't an SSP song file")
    song = copy.deepcopy(song)
    if not song.get("id") or song["id"] in taken_ids or not models.ID_RE.match(str(song["id"])):
        song["id"] = models.new_id()
    song.setdefault("title", "Imported song")
    song.setdefault("default_bpm", 120)
    clips = payload.get("audio", {}) if "ssp_export" in payload else {}
    renamed = {}
    for ref, b64 in (clips or {}).items():
        if not models.AUDIO_REF.match(str(ref)):
            continue
        try:
            data = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError, TypeError):
            continue
        if len(data) > models.MAX_AUDIO_BYTES:
            continue
        renamed[ref] = storage.save_audio(data, os.path.splitext(ref)[1][1:])
    for s in song.get("sections", []):
        for h in s.get("hints", []):
            if h.get("audio"):
                h["audio"] = renamed.get(h["audio"])
    song["updated_at"] = models.now()
    song.setdefault("created_at", models.now())
    models.validate_song(song)
    return song
