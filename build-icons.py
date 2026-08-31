#!/usr/bin/env python3
"""Regenerates the icon set from assets/icon.png.

    python3 build-icons.py

Android does not use one icon for everything, and handing it the same file for
every purpose is what produces clipped corners and blobby notification badges.
Three variants come out of here:

  icon-192 / icon-512          purpose "any"        — shown as drawn, unmasked
  icon-maskable-512            purpose "maskable"   — content pulled inside the
                               safe zone, full bleed to the edges
  icon-monochrome-512          purpose "monochrome" — alpha-only silhouette

The maskable safe zone is a circle of 80% of the icon's width. Anything outside
it may be cropped, and how much depends on the launcher's mask shape (circle,
squircle, rounded square, teardrop). The source art's corners sit at radius
220px on a 512px canvas against a 205px safe radius, so it is scaled down to
bring them inside with a little margin.

Requires Pillow:  pip install Pillow
"""
import math
import os

from PIL import Image

SRC = 'assets/icon.png'
OUT = 'assets'

# Fraction of the original artwork kept. The corners land at r=220 on a 512
# canvas; 0.88 pulls them to r~194, comfortably inside the 205px safe radius
# without shrinking the mark so far that it looks lost in the tile.
MASKABLE_SCALE = 0.88

# Luminance above which a pixel counts as foreground for the monochrome cut.
# Background navy sits near 30 and the card interior lower still; the white
# elements are 255 and the amber edge about 185, so this keeps the mark and the
# accent while dropping the interior and the faint starfield dots.
MONO_THRESHOLD = 120


def luminance(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def content_radius(im, tol=26):
    """Distance from centre to the furthest pixel that is not flat background."""
    w, h = im.size
    px = im.load()
    bg = px[4, 4]
    cx, cy = w / 2, h / 2
    worst = 0.0
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > tol or p[3] < 250:
                worst = max(worst, math.hypot(x - cx, y - cy))
    return worst, bg


def save(im, name):
    path = os.path.join(OUT, name)
    im.save(path, 'PNG', optimize=True)
    print(f'{path}: {im.size[0]}x{im.size[1]}, {os.path.getsize(path)} bytes')


def main():
    src = Image.open(SRC).convert('RGBA')
    w, h = src.size
    if w != h:
        raise SystemExit(f'{SRC} must be square, got {w}x{h}')

    radius, bg = content_radius(src)
    safe = w * 0.8 / 2
    print(f'source {w}x{h}, background {bg[:3]}')
    print(f'content reaches r={radius:.0f}px, safe zone r={safe:.0f}px '
          f'({"inside" if radius <= safe else "OUTSIDE — scaling"})')

    # --- purpose "any": shown exactly as drawn, so just resize ---
    save(src.resize((512, 512), Image.LANCZOS), 'icon-512.png')
    save(src.resize((192, 192), Image.LANCZOS), 'icon-192.png')

    # --- purpose "maskable": shrink the art, keep the background full bleed ---
    # Scaling the whole square and pasting it centred on a plate of the same
    # background colour keeps the bleed seamless: the border it grows into is
    # the same navy the source already ends in.
    inner = int(round(w * MASKABLE_SCALE))
    plate = Image.new('RGBA', (w, h), bg)
    plate.paste(src.resize((inner, inner), Image.LANCZOS), ((w - inner) // 2, (h - inner) // 2))
    new_radius = radius * MASKABLE_SCALE
    print(f'maskable: content now reaches r={new_radius:.0f}px '
          f'({"ok" if new_radius <= safe else "STILL OUTSIDE"})')
    save(plate, 'icon-maskable-512.png')

    # --- purpose "monochrome": alpha only ---
    # The OS throws the colour away and tints the alpha channel, so every pixel
    # is painted white and only opacity carries the shape. It gets the same
    # safe-zone treatment, since a themed icon is a masked icon too.
    mono = Image.new('RGBA', (w, h), (255, 255, 255, 0))
    spx, mpx = src.load(), mono.load()
    for y in range(h):
        for x in range(w):
            p = spx[x, y]
            if p[3] > 200 and luminance(p) >= MONO_THRESHOLD:
                mpx[x, y] = (255, 255, 255, 255)
    shrunk = Image.new('RGBA', (w, h), (255, 255, 255, 0))
    shrunk.paste(mono.resize((inner, inner), Image.LANCZOS),
                 ((w - inner) // 2, (h - inner) // 2))
    opaque = sum(1 for y in range(h) for x in range(w) if shrunk.load()[x, y][3] > 128)
    print(f'monochrome: {opaque / (w * h) * 100:.1f}% of the tile is opaque')
    save(shrunk, 'icon-monochrome-512.png')

    # Notification badges are alpha-only too: Android draws the silhouette in a
    # small circle and discards the colour, so a full-colour icon there renders
    # as a featureless blob. 96px is the documented badge size.
    save(shrunk.resize((96, 96), Image.LANCZOS), 'icon-badge-96.png')


if __name__ == '__main__':
    main()
