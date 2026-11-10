#!/usr/bin/env python3
"""
Draw Barline's app icon and write every file that uses it.

The icon is the bar square the editor draws for each bar (four beat dots
in a 2x2 grid), on a dark tile, with beat 1 lit white -- the downbeat, the
same "accent" the live view lights up on beat 1.

    python3 tools/make_icons.py

Writes:
    web/static/icon.svg              browser tab (vector)
    web/static/icon-192.png          web app manifest
    web/static/icon-512.png          web app manifest
    web/static/apple-touch-icon.png  iPhone/iPad home screen (180)
    web/static/icon-40.png           the control panel's header logo
    packaging/icons/icon-256.png     Linux
    packaging/icons/icon-1024.png    source size
    packaging/icons/icon.ico         Windows (16-256)
    packaging/icons/icon.icns        macOS

Needs Pillow (a developer tool only; the app itself doesn't use it).
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC = os.path.join(ROOT, "web", "static")
ICONS = os.path.join(ROOT, "packaging", "icons")

# Barline's own colors (web/static/style.css)
TILE = "#16181d"
BLUE = (91, 140, 255)
WHITE = (255, 255, 255)

# geometry on a 512 grid, shared by the SVG and the bitmap drawing
TILE_R = 112
BAR = (92, 92, 420, 420)
BAR_R = 68
BAR_STROKE = 16
DOT_R = 52
DOTS = [(196, 196), (316, 196), (196, 316), (316, 316)]  # beat 1 first
GLOW_R = 92

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">\
<defs><radialGradient id="g"><stop offset="0" stop-color="#fff" stop-opacity=".55"/>\
<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>\
<rect width="512" height="512" rx="{TILE_R}" fill="{TILE}"/>\
<rect x="{BAR[0]}" y="{BAR[1]}" width="{BAR[2] - BAR[0]}" height="{BAR[3] - BAR[1]}" rx="{BAR_R}" \
fill="#5b8cff" fill-opacity=".16" stroke="#5b8cff" stroke-width="{BAR_STROKE}"/>\
<circle cx="{DOTS[0][0]}" cy="{DOTS[0][1]}" r="{GLOW_R}" fill="url(#g)"/>\
<circle cx="{DOTS[0][0]}" cy="{DOTS[0][1]}" r="{DOT_R}" fill="#fff"/>\
{"".join(f'<circle cx="{x}" cy="{y}" r="{DOT_R}" fill="#5b8cff"/>' for x, y in DOTS[1:])}\
</svg>
"""


def draw(size: int, full_bleed: bool = False) -> Image.Image:
    """The icon at `size` px, drawn 4x larger and scaled down for smooth edges.
    full_bleed: square tile with no rounded corners (iOS rounds it itself)."""
    k = 4
    s = size * k / 512
    big = size * k

    def box(b):
        return [round(v * s) for v in b]

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if full_bleed:
        d.rectangle([0, 0, big, big], fill=TILE)
    else:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=round(TILE_R * s), fill=TILE)

    # bar square: tinted fill + outline
    inset = BAR_STROKE / 2
    outer = (BAR[0] - inset, BAR[1] - inset, BAR[2] + inset, BAR[3] + inset)
    d.rounded_rectangle(box(outer), radius=round((BAR_R + inset) * s), fill=BLUE + (255,))
    inner = (BAR[0] + inset, BAR[1] + inset, BAR[2] - inset, BAR[3] - inset)
    tint = tuple(round(t * 0.84 + b * 0.16) for t, b in zip((0x16, 0x18, 0x1D), BLUE))
    d.rounded_rectangle(box(inner), radius=round((BAR_R - inset) * s), fill=tint + (255,))

    # downbeat glow
    glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    gx, gy = DOTS[0]
    ImageDraw.Draw(glow).ellipse(box((gx - 70, gy - 70, gx + 70, gy + 70)), fill=WHITE + (110,))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=24 * s))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)

    for i, (x, y) in enumerate(DOTS):
        d.ellipse(box((x - DOT_R, y - DOT_R, x + DOT_R, y + DOT_R)), fill=(WHITE if i == 0 else BLUE) + (255,))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    os.makedirs(ICONS, exist_ok=True)
    with open(os.path.join(STATIC, "icon.svg"), "w", encoding="utf-8") as fh:
        fh.write(SVG)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("icon-40.png", 40)):
        draw(size).save(os.path.join(STATIC, name))
    draw(180, full_bleed=True).convert("RGB").save(os.path.join(STATIC, "apple-touch-icon.png"))
    big = draw(1024)
    big.save(os.path.join(ICONS, "icon-1024.png"))
    draw(256).save(os.path.join(ICONS, "icon-256.png"))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    # each size drawn on its own (not one bitmap squeezed), so 16 px stays crisp
    draw(256).save(os.path.join(ICONS, "icon.ico"), sizes=[(n, n) for n in sizes],
                   append_images=[draw(n) for n in sizes[:-1]])
    # macOS draws app icons inside a margin (824 of 1024), so the tile
    # sits at the same size as every other app in the Dock
    mac = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    mac.alpha_composite(draw(824), (100, 100))
    mac.save(os.path.join(ICONS, "icon.icns"))
    print("icons written: web/static/ and packaging/icons/")


if __name__ == "__main__":
    main()
