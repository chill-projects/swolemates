"""Regenerate public/ icons from design/logo-source.jpg.

    uv run --with pillow python design/make-icons.py design/logo-source.jpg public

Kept in the repo so the icon set is reproducible: the source art is a JPEG on a
white field, and every size in public/ is derived from it rather than hand-edited.
"""

import sys

from PIL import Image, ImageDraw

SRC = sys.argv[1]
OUT = sys.argv[2]
TEAL = (14, 92, 86)  # --teal, the wordmark colour

im = Image.open(SRC).convert("RGB")
w, h = im.size

# Knock out the white field by flooding in from the corners rather than thresholding
# every white-ish pixel, so nothing inside the artwork gets punched out. The tan
# outline is far enough from white for a generous tolerance to eat the JPEG halo.
SENTINEL = (255, 0, 255)
flood = im.copy()
for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
    ImageDraw.floodfill(flood, corner, SENTINEL, thresh=60)

rgba = im.convert("RGBA")
px_flood, px_out = flood.load(), rgba.load()
for y in range(h):
    for x in range(w):
        if px_flood[x, y] == SENTINEL:
            px_out[x, y] = (255, 255, 255, 0)

# Trim to the artwork, then centre it on a square canvas.
bbox = rgba.getbbox()
art = rgba.crop(bbox)
side = max(art.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(art, ((side - art.width) // 2, (side - art.height) // 2), art)


def scaled(size, inset=1.0):
    """The logo at `size`, occupying `inset` of that box, on transparency."""
    box = round(size * inset)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    art = square.resize((box, box), Image.LANCZOS)
    canvas.paste(art, ((size - box) // 2, (size - box) // 2), art)
    return canvas


def on_teal(size, inset):
    canvas = Image.new("RGBA", (size, size), TEAL + (255,))
    canvas.alpha_composite(scaled(size, inset))
    return canvas.convert("RGB")


def compact(img):
    """Palette-quantise before saving. The artwork is four flat colours plus
    anti-aliasing, so 256 indexed colours are visually lossless and cut the files
    by roughly 6x — these ship in the service worker's precache."""
    return img.quantize(colors=256, method=Image.FASTOCTREE).convert("RGBA")


# Transparent: these sit on the app bar and in browser UI, which may be light or dark.
compact(scaled(512)).save(f"{OUT}/icon-512.png", optimize=True)
compact(scaled(192)).save(f"{OUT}/icon-192.png", optimize=True)

# Opaque: iOS composites an apple-touch-icon onto a solid colour, and a maskable icon
# is cropped to a circle by the launcher — 60% keeps the artwork inside the safe zone.
on_teal(180, 0.80).save(f"{OUT}/apple-touch-icon.png", optimize=True)
on_teal(512, 0.60).save(f"{OUT}/icon-maskable-512.png", optimize=True)

# Browsers only ever pick 16/32/48 out of an .ico; the larger sizes are dead weight
# on a file every first page load fetches.
scaled(64).save(f"{OUT}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
print("wrote:", ", ".join(sorted(["icon-512.png", "icon-192.png",
      "apple-touch-icon.png", "icon-maskable-512.png", "favicon.ico"])))
print("source", (w, h), "-> square", square.size)
