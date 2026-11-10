"""
Paper charts (0.13): a song or a setlist as a real PDF, built here with the
standard library alone, to print and put on a music stand or the floor.

Ideas and code from Song Notation Tool (github.com/giopas/song-notation-tool),
whose export engine solved the same problem for chord charts:

  * the PDF writer (`_assemble_pdf`): the standard Type 1 fonts every PDF
    reader has, Flate-compressed page streams, and an embedded-file
    attachment. Song Notation Tool took it from QLC+ Swiss Knife; no PDF
    library either way;
  * Size **Fit to page**: grow the type until the page is full without adding
    a page (and take a slightly smaller type if that saves a page turn), and
    **Floor**: the largest type that fits on one sheet, portrait or landscape,
    whichever gives bigger type -- for a sheet at your feet;
  * **Colour** or **Black & white**: colour labels the sections; black and
    white uses grey bands, not black ones (less toner, and black text on grey
    survives a photocopy better);
  * section names in a left-hand column (Song Notation Tool's "gutter"), which
    saves a line per section;
  * a section is never split across a page break;
  * a long title shrinks by itself instead of shrinking the whole chart;
  * the song travels inside its PDF (`song.ssp.json`, voice memos included),
    so Barline's Import reads a printed song's PDF back.

What a chart shows: the song's tempo, length and how it starts; its coloured
shape; then each section with its starting bar, a box per bar to count along
on, tempo changes, count-ins, and the hints -- every hint with who it's for,
or for one player the band-wide hints plus their own, marked with ">>".

A setlist starts with a running-order sheet in the largest type that fits on
one page (the one that gets taped to the floor), then one chart per song.
"""

from __future__ import annotations

import json
import re
import zlib

import models
import timeline
from version import VERSION

# Same palette as web/static/app.js, so a printout matches the screen.
PALETTE = ["#5b8cff", "#45c08a", "#e2b93b", "#e2574c", "#b073f0", "#39c2c9", "#f08a3c", "#6fcf97"]

SIZES = ("fit", "floor")
INKS = ("color", "bw")
EMBEDDED_NAME = "song.ssp.json"

# -- page geometry (points; A4) ----------------------------------------------
A4 = (595.0, 842.0)
MARGIN = 34.0        # clear of most printers' unprintable edge
FOOTER = 16.0        # space kept for the footer line above the bottom margin
CONT_HEAD = 18.0     # "Title (continued)" line on a song's later pages

# -- type sizes at 100% ------------------------------------------------------
TITLE = 20.0
META = 9.5
LABEL = 10.5
BODY = 10.0
SMALL = 8.0
BOX = 10.0
LEADING = 1.3

# Fit to page grows or shrinks within these; Floor goes much further up.
FIT_MIN, FIT_MAX = 0.8, 1.6
FLOOR_MIN, FLOOR_MAX = 0.6, 4.0
FLOOR_TITLE_MAX = 30.0
# Above this many bars a section shows its count, not a box per bar: nobody
# counts 140 boxes of a jam, and they'd fill the page.
MAX_BOXES = 64

INK = (0.07, 0.07, 0.07)
GREY = (0.40, 0.40, 0.40)
RULE = (0.82, 0.82, 0.82)
WHITE = (1.0, 1.0, 1.0)
NBSP = "\u00a0"  # no-break space: wrap_runs never breaks a line there


# ==============================================================================
#  Text: Helvetica metrics, WinAnsi encoding
# ==============================================================================

_HELV = (  # cp1252 bytes 32..255, 1/1000 em (Adobe's Helvetica AFM)
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667,
    611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500,
    222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
    761, 556, 0, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0, 0, 222, 222,
    333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 0, 500, 667, 278, 333, 556, 556, 556, 556,
    260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 556, 537, 278, 333,
    333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667,
    278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667,
    611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278, 556, 556,
    556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500
)
_HELV_BOLD = (  # cp1252 bytes 32..255, 1/1000 em (Adobe's Helvetica-Bold AFM)
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667,
    611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556,
    278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
    761, 556, 0, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0, 0, 278, 278,
    500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 0, 500, 667, 278, 333, 556, 556, 556, 556,
    280, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 611, 556, 278, 333,
    333, 365, 556, 834, 834, 834, 611, 722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667,
    278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667,
    611, 556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278, 611, 611,
    611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556
)
# R regular, B bold, I oblique (same widths as regular)
_FONTS = {"R": ("F1", _HELV), "B": ("F2", _HELV_BOLD), "I": ("F3", _HELV)}
# A few characters people type that WinAnsi doesn't have.
_SUBST = {"→": "->", "←": "<-", "↑": "^", "↓": "v", "♩": "", "♪": "",
          "♫": "", "✓": "v", "✔": "v", "✕": "x", "−": "-"}


def _enc(text) -> bytes:
    s = "".join(_SUBST.get(ch, ch) for ch in str(text if text is not None else ""))
    s = "".join(" " if ord(ch) < 32 else ch for ch in s)
    return s.encode("cp1252", "replace")


def text_width(text, size: float, font: str = "R") -> float:
    table = _FONTS[font][1]
    return sum(table[b - 32] for b in _enc(text) if b >= 32) * size / 1000.0


def _pdf_str(text) -> str:
    b = _enc(text).replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b.decode("latin-1")


def fit_size(text, max_width: float, desired: float, font: str = "R", floor: float = 0.0) -> float:
    """`desired`, or smaller if the text wouldn't fit in `max_width` (never
    below `floor`)."""
    w = text_width(text, desired, font)
    if w <= max_width or w <= 0:
        return desired
    return max(floor, desired * max_width / w)


def ellipsize(text: str, max_width: float, size: float, font: str = "R") -> str:
    if text_width(text, size, font) <= max_width:
        return text
    while text and text_width(text + "…", size, font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap_runs(runs, width: float, size: float) -> list:
    """Greedy word wrap of styled runs [(text, font, rgb)] into lines of
    runs. A word longer than the line is broken where it has to be."""
    tokens = []
    for text, font, rgb in runs:
        for m in re.finditer(r"[^ ]+ *| +", text or ""):
            tokens.append((m.group(), font, rgb))
    lines, cur = [[]], 0.0
    for word, font, rgb in tokens:
        if cur + text_width(word.rstrip(" "), size, font) > width and lines[-1]:
            lines.append([])
            cur = 0.0
            word = word.lstrip(" ")
            if not word:
                continue
        while word.strip(" ") and text_width(word.rstrip(" "), size, font) > width and not lines[-1]:
            cut = len(word)
            while cut > 1 and text_width(word[:cut], size, font) > width:
                cut -= 1
            lines[-1].append((word[:cut], font, rgb))
            lines.append([])
            word = word[cut:]
        if word:
            lines[-1].append((word, font, rgb))
            cur += text_width(word, size, font)
    return [_merge(ln) for ln in lines if ln] or [[]]


def _merge(line: list) -> list:
    """Adjacent runs in the same style as one, so a line is drawn (and
    copied out of a PDF viewer) as phrases, not word by word. The no-break
    spaces have done their job by now: they print as plain spaces."""
    out = []
    for text, font, rgb in line:
        text = text.replace(NBSP, " ")
        if out and out[-1][1] == font and out[-1][2] == rgb:
            out[-1] = (out[-1][0] + text, font, rgb)
        else:
            out.append((text, font, rgb))
    if out:
        out[-1] = (out[-1][0].rstrip(" "), out[-1][1], out[-1][2])
    return out


# ==============================================================================
#  Colour
# ==============================================================================

def _hex(h: str):
    n = int(h[1:], 16)
    return ((n >> 16) & 255) / 255.0, ((n >> 8) & 255) / 255.0, (n & 255) / 255.0


def section_rgb(index: int, ink: str):
    """A section's colour on white paper: the screen's colour, darkened
    (a colour made for a dark screen looks washed out in print). In black and
    white, a light grey band with black text."""
    if ink == "bw":
        return (0.80, 0.80, 0.80)
    r, g, b = _hex(PALETTE[index % len(PALETTE)])
    return (r * 0.80, g * 0.80, b * 0.80)


def label_rgb(ink: str):
    return INK if ink == "bw" else WHITE


def _tint(rgb, amount: float):
    return tuple(c + (1.0 - c) * amount for c in rgb)


# ==============================================================================
#  A page: drawing in top-down coordinates
# ==============================================================================

class Page:
    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.ops = []

    def text(self, x, y, s, size, font="R", rgb=INK):
        """`y` is the baseline, measured from the top of the page."""
        if not s:
            return
        self.ops.append(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg BT /{_FONTS[font][0]} {size:.2f} Tf "
                        f"{x:.2f} {self.h - y:.2f} Td ({_pdf_str(s)}) Tj ET")

    def runs(self, x, y, runs, size):
        for s, font, rgb in runs:
            self.text(x, y, s, size, font, rgb)
            x += text_width(s, size, font)

    def rect(self, x, y, w, h, fill=None, stroke=None, lw=0.5):
        """`y` is the rectangle's top edge, from the top of the page."""
        y0 = self.h - y - h
        if fill is not None:
            self.ops.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg {x:.2f} {y0:.2f} {w:.2f} {h:.2f} re f")
        if stroke is not None:
            self.ops.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG {lw:.2f} w "
                            f"{x:.2f} {y0:.2f} {w:.2f} {h:.2f} re S")

    def line(self, x1, y1, x2, y2, rgb=RULE, lw=0.5):
        self.ops.append(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} RG {lw:.2f} w "
                        f"{x1:.2f} {self.h - y1:.2f} m {x2:.2f} {self.h - y2:.2f} l S")

    def stream(self) -> bytes:
        return zlib.compress("\n".join(self.ops).encode("latin-1"))


# ==============================================================================
#  Song facts in words
# ==============================================================================

def fmt_duration(ms: float) -> str:
    s = int(round(ms / 1000.0))
    return f"{s // 60}:{s % 60:02d}"


def _sections(song: dict) -> list:
    return sorted(song.get("sections", []), key=lambda s: s.get("order", 0))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def count_in_text(section: dict) -> str:
    ci = section.get("count_in") or {}
    if ci.get("style", "none") == "none" or not ci.get("bars"):
        return ""
    return f"{_plural(ci['bars'], 'bar')}, {ci['style']}"


def start_text(song: dict) -> str:
    """How the song starts, as a run starts it (timeline's lead-in rule)."""
    secs = _sections(song)
    if not secs:
        return ""
    ci = count_in_text(secs[0])
    return f"count-in {ci}" if ci else f"{_plural(timeline.LEAD_IN_BARS, 'bar')} lead-in click"


def _who(band: dict, player_id):
    p = {p["id"]: p for p in band.get("players", [])}.get(player_id) if player_id else None
    return p


def chart_for(band: dict, player_id) -> str:
    p = _who(band, player_id)
    return f"{p['name']} ({p['role']})" if p else "whole band"


# ==============================================================================
#  A song chart, as blocks laid out at a scale
# ==============================================================================

class Block:
    """Something stacked down the page: a height and a way to draw it."""

    def __init__(self, height: float, draw):
        self.height = height
        self.draw = draw  # draw(page, x, y_top)


def _hint_runs(h: dict, players: dict, player_id, ink_rgb) -> tuple:
    """(bullet, runs, mine) for one hint, or None if it isn't on this chart."""
    vis = h.get("visibility", "all")
    if player_id and vis not in ("all", player_id):
        return None
    text = (h.get("text") or "").strip()
    if not text and not h.get("audio"):
        return None
    mine = bool(player_id) and vis == player_id
    runs = []
    if vis != "all" and not mine:
        p = players.get(vis)
        runs.append((f"{p['name'] if p else '?'}: ", "B", ink_rgb))
    if text:
        runs.append((text, "B" if mine else "R", ink_rgb))
    if h.get("audio"):
        runs.append((" (voice memo)" if text else "(voice memo)", "I", GREY))
    return ("»" if mine else "•", runs, mine)


def song_blocks(song: dict, band: dict, player_id, s: float, width: float, ink: str,
                floor: bool = False, col_width: float = None) -> list:
    """The song's header block (`width` points wide) and one block per
    section (`col_width` wide, the same when there is one column), at
    scale `s`."""
    players = {p["id"]: p for p in band.get("players", [])}
    secs = _sections(song)
    total = sum(x["bars"] for x in secs)
    blocks = []

    # -- header: title, facts, the song's shape ----------------------------
    who = chart_for(band, player_id)
    who_txt = f"Chart for {who}"
    who_size = META * s if not floor else min(META * s, 14.0)
    who_w = text_width(who_txt, who_size, "R")
    title_max = min(TITLE * s, FLOOR_TITLE_MAX) if floor else TITLE * s
    title_size = fit_size(song["title"], width - who_w - 12 * s, title_max, "B", floor=8.0)
    title_text = ellipsize(song["title"], width - who_w - 12 * s, title_size, "B")
    meta_size = who_size
    facts = [f"{song['default_bpm']} BPM"]
    if not floor:
        facts.append(_plural(total, "bar"))
        if secs:
            facts.append(f"about {fmt_duration(timeline.duration_ms(song))}")
    st = start_text(song)
    if st:
        facts.append(f"starts with {st}")
    meta_runs = [(" · ".join(facts), "R", GREY)]
    if player_id and _who(band, player_id):
        meta_runs.append((f"    » = {players[player_id]['name']}'s own hints", "B", GREY))
    meta_lines = wrap_runs(meta_runs, width, meta_size)
    title_h = title_max * 1.05
    meta_h = len(meta_lines) * meta_size * 1.4
    strip_h = 0 if floor or not secs else 16 * s
    head_h = title_h + 4 * s + meta_h + (strip_h + 8 * s if strip_h else 0) + 6 * s

    def draw_head(pg, x, y):
        base = y + title_max * 0.82
        pg.text(x, base, title_text, title_size, "B")
        pg.text(x + width - who_w, base, who_txt, who_size, "R", GREY)
        yy = y + title_h + 4 * s
        for ln in meta_lines:
            pg.runs(x, yy + meta_size, ln, meta_size)
            yy += meta_size * 1.4
        if strip_h:
            yy += 2 * s
            gap = 1.5 * s
            avail = width - gap * (len(secs) - 1)
            xx = x
            for i, sec in enumerate(secs):
                w = avail * sec["bars"] / (total or 1)
                pg.rect(xx, yy, w, strip_h, fill=section_rgb(i, ink))
                lsz = 7.0 * s
                if text_width(sec["label"], lsz, "B") <= w - 4 * s:
                    pg.text(xx + (w - text_width(sec["label"], lsz, "B")) / 2, yy + strip_h * 0.5 + lsz * 0.35,
                            sec["label"], lsz, "B", label_rgb(ink))
                xx += w + gap

    blocks.append(Block(head_h, draw_head))
    if not secs:
        blocks.append(Block(BODY * s * 2, lambda pg, x, y: pg.text(
            x, y + BODY * s, "No sections yet.", BODY * s, "I", GREY)))
        return blocks

    # -- section names: in a left-hand column (saves a line per section), or
    # on a band across the top when two columns make the page too narrow
    # for one (Song Notation Tool's "gutter" and "banner")
    colw = col_width or width
    banner = colw < width - 1
    lab = LABEL * s
    if banner:
        gutter, x_off = colw, 0.0
    else:
        gutter = min(max(text_width(x["label"], lab, "B") for x in secs) + 12 * s, colw * 0.3)
        gutter = max(gutter, 60 * s)
        x_off = gutter + 10 * s
    body = BODY * s
    small = SMALL * s
    line_h = body * LEADING
    rw = max(colw - x_off, 40 * s)
    box = BOX * s
    box_gap = 2.5 * s
    group_gap = 6.5 * s
    # boxes per row: a whole number of 4-bar groups that fits
    group_w = 4 * box + 3 * box_gap
    groups_per_row = max(1, int((rw + group_gap) // (group_w + group_gap)))
    per_row = groups_per_row * 4

    bar = 1
    prev_bpm = song["default_bpm"]
    for i, sec in enumerate(secs):
        color = section_rgb(i, ink)
        bpm = sec.get("bpm") or song["default_bpm"]
        # (no-break spaces keep "62 BPM" and "1 bar, sticks" on one line)
        info = [(_plural(sec["bars"], "bar").replace(" ", NBSP), "B", INK)]
        if bpm != prev_bpm:
            info.append((f"  ·  {bpm}{NBSP}BPM", "B", INK))
        ci = count_in_text(sec)
        if ci:
            info.append((f"  ·  count-in {ci.replace(' ', NBSP)}", "R", INK))
        info_lines = wrap_runs(info, rw, body)
        boxes = sec["bars"] <= MAX_BOXES
        rows = -(-sec["bars"] // per_row) if boxes else 0
        boxes_h = rows * (box + 3 * s) + 2 * s if boxes else 0
        hints = []
        for h in sec.get("hints", []):
            hr = _hint_runs(h, players, player_id, INK)
            if hr:
                bullet, runs, mine = hr
                indent = text_width(bullet + " ", body, "B")
                hints.append((bullet, wrap_runs(runs, rw - indent, body), indent, mine))
        hint_h = sum(len(ln) for _, ln, _, _ in hints) * line_h + (2 * s if hints else 0)
        right_h = len(info_lines) * line_h + boxes_h + hint_h
        band_h = lab * 1.55
        gap = 9 * s
        if banner:
            height = band_h + 4 * s + right_h + gap
        else:
            height = max(band_h + 3 * s + small * 1.2, right_h) + gap

        def draw_sec(pg, x, y, sec=sec, i=i, color=color, info_lines=info_lines, boxes=boxes,
                     hints=hints, bar=bar, band_h=band_h, gap=gap, height=height, rows=rows):
            pg.rect(x, y, gutter, band_h, fill=color)
            where = f"bar {bar}"
            if banner:  # "bar 17" inside the band, on the right
                where_w = text_width(where, small, "R")
                pg.text(x + gutter - 5 * s - where_w, y + band_h * 0.5 + small * 0.36, where, small, "R", label_rgb(ink))
                room = gutter - where_w - 16 * s
            else:
                pg.text(x + 1 * s, y + band_h + 3 * s + small * 0.9, where, small, "R", GREY)
                room = gutter - 8 * s
            lsz = fit_size(sec["label"], room, lab, "B", floor=5.0)
            pg.text(x + 5 * s, y + band_h * 0.5 + lsz * 0.36, ellipsize(sec["label"], room, lsz, "B"),
                    lsz, "B", label_rgb(ink))
            xr = x + x_off
            yy = y + (band_h + 4 * s if banner else 0)
            for ln in info_lines:
                pg.runs(xr, yy + body * 0.95, ln, body)
                yy += line_h
            if boxes:
                yy += 1 * s
                stroke = (0.35, 0.35, 0.35) if ink == "bw" else color
                fill = None if ink == "bw" else _tint(color, 0.85)
                for b in range(sec["bars"]):
                    r, c = divmod(b, per_row)
                    g, k = divmod(c, 4)
                    bx = xr + g * (group_w + group_gap) + k * (box + box_gap)
                    by = yy + r * (box + 3 * s)
                    pg.rect(bx, by, box, box, fill=fill, stroke=stroke, lw=0.7 * s)
                yy += rows * (box + 3 * s) + 1 * s
            if hints:
                yy += 2 * s
            for bullet, lines, indent, mine in hints:
                pg.text(xr, yy + body * 0.95, bullet, body, "B" if mine else "R", INK)
                for ln in lines:
                    pg.runs(xr + indent, yy + body * 0.95, ln, body)
                    yy += line_h
            pg.line(x, y + height - gap / 2, x + colw, y + height - gap / 2, RULE, 0.5)

        blocks.append(Block(height, draw_sec))
        bar += sec["bars"]
        prev_bpm = bpm
    return blocks


COLUMN_GAP = 22.0   # between two columns, with a rule down the middle


def _paginate(blocks, page_h: float, columns: int = 1, col_w: float = 0.0) -> list:
    """Stack blocks onto pages: the header across the top of the first page,
    then the sections down one column, then the next. A section that doesn't
    fit what's left starts the next column or page (sections are never
    split). Later pages lose CONT_HEAD of room to the "continued" line.
    Returns [[(block, x_offset, y_offset)], ...]."""
    head, rest = blocks[0], blocks[1:]
    pages, cur = [], [(head, 0.0, 0.0)]
    top, room, col, used = head.height, page_h - head.height, 0, 0.0
    for b in rest:
        if used and used + b.height > room + 0.01:
            col, used = col + 1, 0.0
            if col >= columns:
                pages.append(cur)
                cur, top, room, col = [], 0.0, page_h - CONT_HEAD, 0
        cur.append((b, col * (col_w + COLUMN_GAP), top + used))
        used += b.height
    pages.append(cur)
    return pages


def _orient_size(orient: str):
    return (A4[1], A4[0]) if orient == "landscape" else A4


def _content(orient: str):
    w, h = _orient_size(orient)
    return w - 2 * MARGIN, h - 2 * MARGIN - FOOTER


def _col_width(orient: str, columns: int) -> float:
    cw, _ = _content(orient)
    return (cw - COLUMN_GAP * (columns - 1)) / columns


def _layout(song, band, player_id, s, orient, ink, floor, columns=1):
    cw, ch = _content(orient)
    colw = _col_width(orient, columns)
    return _paginate(song_blocks(song, band, player_id, s, cw, ink, floor, colw), ch, columns, colw)


def _largest(pred, lo: float, hi: float, steps: int = 14):
    """The largest scale in [lo, hi] for which pred holds (pred is assumed
    true below some point and false above it), or None."""
    if pred(hi):
        return hi
    if not pred(lo):
        return None
    for _ in range(steps):
        mid = (lo + hi) / 2
        if pred(mid):
            lo = mid
        else:
            hi = mid
    return lo


# Two columns have to give at least this much bigger type to be worth the
# split (Song Notation Tool's _AUTO_COLUMN_GAIN).
COLUMN_GAIN = 1.05


def resolve(song: dict, band: dict, player_id=None, size: str = "fit", ink: str = "color"):
    """(scale, orientation, columns) for a song chart -- Song Notation
    Tool's rules.

    Fit to page: portrait, one column; the page count is what 100% needs, or
    one page if a slightly smaller type (down to FIT_MIN) gets the song onto
    one sheet; then the type grows (up to FIT_MAX) until that page count is
    full.

    Floor: the largest type on one page. Portrait and landscape, one and two
    columns are all tried and the biggest type wins (two columns only when
    they're COLUMN_GAIN bigger; portrait on a tie). A song too long for one
    page at FLOOR_MIN prints at FLOOR_MIN on more pages."""
    floor = size == "floor"

    def pages(s, orient, cols=1):
        return len(_layout(song, band, player_id, s, orient, ink, floor, cols))

    if floor:
        best = None
        for cols in (1, 2):
            for orient in ("portrait", "landscape"):
                s = _largest(lambda v, o=orient, c=cols: pages(v, o, c) <= 1, FLOOR_MIN, FLOOR_MAX) or FLOOR_MIN
                need = (best[0] * (COLUMN_GAIN if cols > best[2] else 1.0) + 1e-6) if best else 0
                if best is None or s > need:
                    best = (s, orient, cols)
        return best
    target = 1 if pages(FIT_MIN, "portrait") <= 1 else pages(1.0, "portrait")
    s = _largest(lambda v: pages(v, "portrait") <= target, FIT_MIN, FIT_MAX) or FIT_MIN
    return s, "portrait", 1


def _footer(pg: Page, left: str, right: str):
    y = pg.h - MARGIN + 2
    pg.line(MARGIN, y - 10, pg.w - MARGIN, y - 10, RULE, 0.4)
    right_w = text_width(right, 7.5, "R")
    pg.text(MARGIN, y, ellipsize(left, pg.w - 2 * MARGIN - right_w - 20, 7.5), 7.5, "R", GREY)
    pg.text(pg.w - MARGIN - right_w, y, right, 7.5, "R", GREY)


def song_pages(song: dict, band: dict, player_id=None, size: str = "fit", ink: str = "color",
               where: str = "") -> list:
    """The song's chart as Page objects. `where` goes in the footer
    ("Friday set: song 2 of 6")."""
    floor = size == "floor"
    s, orient, cols = resolve(song, band, player_id, size, ink)
    laid = _layout(song, band, player_id, s, orient, ink, floor, cols)
    colw = _col_width(orient, cols)
    _, content_h = _content(orient)
    w, h = _orient_size(orient)
    left = " · ".join(x for x in (band.get("name", ""), f"chart for {chart_for(band, player_id)}",
                                       f"made with Barline {VERSION}") if x)
    out = []
    for n, placed in enumerate(laid):
        pg = Page(w, h)
        top = MARGIN
        if n > 0:
            pg.text(MARGIN, top + 10, f"{song['title']} (continued)", 10, "B", GREY)
            top += CONT_HEAD
        for block, x, y in placed:
            block.draw(pg, MARGIN + x, top + y)
        if cols > 1:  # a rule down the gutter, so two columns never read as one
            first = placed[1][2] if n == 0 and len(placed) > 1 else 0.0
            xr = MARGIN + colw + COLUMN_GAP / 2
            pg.line(xr, top + first, xr, MARGIN + content_h, RULE, 0.6)
        right = " · ".join(x for x in (where, f"page {n + 1} of {len(laid)}" if len(laid) > 1 else "") if x)
        _footer(pg, left, right)
        out.append(pg)
    return out


# ==============================================================================
#  The setlist sheet: the running order in the largest type that fits
# ==============================================================================

SHEET_MAX = 60.0   # title size cap: a five-song set shouldn't look like a poster
SHEET_MIN = 14.0   # below this it flows onto another page instead
SHEET_ROW = 1.85   # a row's height in title sizes: the title, then its details


def _song_meta(song: dict) -> str:
    secs = _sections(song)
    first = count_in_text(secs[0]) if secs else ""
    first = f"count-in {first}" if first else "lead-in click"
    dur = fmt_duration(timeline.duration_ms(song)) if secs else "0:00"
    return f"{song['default_bpm']} BPM \u00b7 {first} \u00b7 {dur}"


def setlist_sheet(setlist: dict, present: list, band: dict) -> list:
    """The running order on one page, in the largest type that fits: the
    sheet taped to the floor. Each title gets the full width, with its
    tempo, how it starts and how long it is in small type underneath."""
    w, h = A4
    cw = w - 2 * MARGIN
    total = sum(timeline.duration_ms(x) for x in present)
    head_h = 50.0
    area = h - 2 * MARGIN - FOOTER - head_h
    n = max(1, len(present))

    def num_w(z):
        return text_width(f"{len(present)}.", z, "B") + z * 0.4

    def titles_fit(z):
        return all(text_width(x["title"], z, "B") <= cw - num_w(z) for x in present)

    # One size for every title: as big as the page height allows, smaller
    # if that makes every title fit its line -- but a single very long title
    # doesn't drag the whole sheet below 70%: it shrinks on its own.
    z_top = max(SHEET_MIN, min(SHEET_MAX, area / (n * SHEET_ROW)))
    z_low = max(SHEET_MIN, z_top * 0.7)
    z = _largest(titles_fit, z_low, z_top) or z_low
    row_h = z * SHEET_ROW
    m = max(9.0, z * 0.3)
    nw = num_w(z)
    per_page = max(1, int(area // row_h))
    sub = " \u00b7 ".join(x for x in (band.get("name", ""), _plural(len(present), "song"),
                                      f"about {fmt_duration(total)} of music") if x)
    pages = []
    chunks = [present[i:i + per_page] for i in range(0, len(present), per_page)] or [[]]
    for p, chunk in enumerate(chunks):
        pg = Page(w, h)
        name_sz = fit_size(setlist["name"], cw, 18.0, "B", floor=9.0)
        pg.text(MARGIN, MARGIN + 16, setlist["name"], name_sz, "B")
        pg.text(MARGIN, MARGIN + 31, sub, 9.5, "R", GREY)
        pg.line(MARGIN, MARGIN + 40, w - MARGIN, MARGIN + 40, INK, 0.8)
        y = MARGIN + head_h
        if not present:
            pg.text(MARGIN, y + 20, "No songs in this set yet.", 14, "I", GREY)
        for k, song in enumerate(chunk):
            idx = p * per_page + k + 1
            base = y + z * 0.95
            pg.text(MARGIN, base, f"{idx}.", z, "B", GREY)
            tz = fit_size(song["title"], cw - nw, z, "B", floor=z * 0.5)
            pg.text(MARGIN + nw, base, ellipsize(song["title"], cw - nw, tz, "B"), tz, "B")
            # details clear of the title's descenders
            pg.text(MARGIN + nw, base + z * 0.25 + m * 1.05, ellipsize(_song_meta(song), cw - nw, m), m, "R", GREY)
            if k < len(chunk) - 1:
                pg.line(MARGIN, y + row_h - z * 0.1, w - MARGIN, y + row_h - z * 0.1, RULE, 0.5)
            y += row_h
        right = f"page {p + 1} of {len(chunks)}" if len(chunks) > 1 else ""
        left = " \u00b7 ".join(x for x in (band.get("name", ""), "set list", f"made with Barline {VERSION}") if x)
        _footer(pg, left, right)
        pages.append(pg)
    return pages


# ==============================================================================
#  The PDF file
# ==============================================================================

def _assemble_pdf(pages, title: str = "", attachment: bytes = None) -> bytes:
    """Raw PDF bytes from Page objects (each with its own size), with
    `attachment` (the song file) embedded when given. Ported from Song
    Notation Tool's export.py (itself from QLC+ Swiss Knife): no external
    libraries, the three base fonts every reader has."""
    raw = "%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = []

    def add(s):
        nonlocal raw
        offsets.append(len(raw))
        raw += s

    def obj(n, c):
        return f"{n} 0 obj\n{c}\nendobj\n"

    def sobj(n, data, extra=""):
        body = data.decode("latin-1")
        return obj(n, f"<< /Length {len(data)} /Filter /FlateDecode{extra} >>\nstream\n{body}\nendstream")

    font_res = "<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >>"
    kids, po, so = [], [], []
    cid = 7
    for pg in pages:
        kids.append(f"{cid} 0 R")
        po.append(obj(cid, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pg.w:.2f} {pg.h:.2f}] "
                           f"/Contents {cid + 1} 0 R /Resources {font_res} >>"))
        so.append(sobj(cid + 1, pg.stream()))
        cid += 2

    names = ""
    if attachment is not None:
        so.append(sobj(cid, zlib.compress(attachment), " /Type /EmbeddedFile"))
        so.append(obj(cid + 1, f"<< /Type /Filespec /F ({EMBEDDED_NAME}) /UF ({EMBEDDED_NAME}) "
                               f"/Desc (The song, to import back into Barline) /EF << /F {cid} 0 R >> >>"))
        names = f" /Names << /EmbeddedFiles << /Names [({EMBEDDED_NAME}) {cid + 1} 0 R] >> >>"
        cid += 2

    add(obj(1, f"<< /Type /Catalog /Pages 2 0 R{names} >>"))
    add(obj(2, f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"))
    add(obj(3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"))
    add(obj(4, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"))
    add(obj(5, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>"))
    add(obj(6, f"<< /Title ({_pdf_str(title)}) /Producer (Barline {VERSION}) /Creator (Barline - Song and Setlist Planner) >>"))
    for p, s in zip(po, so):
        add(p)
        add(s)
    for s in so[len(po):]:
        add(s)

    n = cid - 1
    xoff = len(raw)
    raw += f"xref\n0 {n + 1}\n0000000000 65535 f \n"
    for o in offsets:
        raw += f"{o:010d} 00000 n \n"
    raw += f"trailer\n<< /Size {n + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xoff}\n%%EOF\n"
    return raw.encode("latin-1")


def _check(size, ink):
    if size not in SIZES:
        raise models.ValidationError(f"size is one of {', '.join(SIZES)}")
    if ink not in INKS:
        raise models.ValidationError(f"ink is one of {', '.join(INKS)}")


def song_pdf(song: dict, band: dict, player_id=None, size: str = "fit", ink: str = "color",
             bundle: dict = None) -> bytes:
    """One song's chart. `bundle` (export.bundle()) is embedded, so the PDF
    can be imported back."""
    _check(size, ink)
    attachment = json.dumps(bundle, ensure_ascii=False).encode("utf-8") if bundle is not None else None
    return _assemble_pdf(song_pages(song, band, player_id, size, ink), song["title"], attachment)


def setlist_pdf(setlist: dict, songs: dict, band: dict, player_id=None, size: str = "fit",
                ink: str = "color", parts: str = "all") -> bytes:
    """The running-order sheet, then (parts="all") one chart per song, each
    starting on a new page."""
    _check(size, ink)
    if parts not in ("all", "list"):
        raise models.ValidationError("parts is all or list")
    present = [songs[x] for x in setlist["songs"] if x in songs]
    pages = setlist_sheet(setlist, present, band)
    if parts == "all":
        for k, song in enumerate(present):
            pages += song_pages(song, band, player_id, size, ink,
                                where=f"{setlist['name']}: song {k + 1} of {len(present)}")
    return _assemble_pdf(pages, setlist["name"])


def read_embedded(data: bytes):
    """The song file attached to one of Barline's PDFs, as a dict, or None (a PDF
    from another program, a setlist PDF, or one older than 0.13)."""
    m = re.search(rb"/EF << /F (\d+) 0 R >>", data)
    if not m:
        return None
    head = re.search(rb"(?m)^" + m.group(1) + rb" 0 obj\n<< /Length (\d+) /Filter /FlateDecode[^>]*>>\nstream\n",
                     data)
    if not head:
        return None
    raw = data[head.end():head.end() + int(head.group(1))]
    try:
        out = json.loads(zlib.decompress(raw).decode("utf-8"))
    except (zlib.error, ValueError, UnicodeDecodeError):
        return None
    return out if isinstance(out, dict) else None
