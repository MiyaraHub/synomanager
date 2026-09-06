#!/usr/bin/env python3
"""Blur the parts of a capture that are somebody's actual content.

Syno Manager shows a real NAS, and several of its screens draw the owner's
private material: the Photos library is family photographs, Surveillance Station
is a live view of rooms in a house, File Station and Note Station list file and
note names. Those screens still have to appear in the manual - the layout IS the
documentation - so the frame ships and the content inside it does not.

The blur is deliberately not a black box. A redaction bar tells a reader nothing
about what the screen looks like; a heavy blur keeps the composition, the tile
grid, the aspect ratios and the colour balance while destroying every
recoverable detail. Two passes do that:

  1. downsample to a handful of pixels and back up, which throws the detail
     away rather than smearing it - a Gaussian alone is reversible enough on
     text that it is not a redaction,
  2. a Gaussian over the result, so the seams of step 1 do not read as mosaic.

Regions are given in RAW capture coordinates (1344x2992 on the Pixel 10 Pro XL),
because that is what a measurement off the capture gives you.

Usage:
    blur_regions.py IN.png OUT.png x0,y0,x1,y1 [x0,y0,x1,y1 ...]
    blur_regions.py IN.png OUT.png --grid x0,y0,x1,y1,cols,rows   (blur a tile grid)
"""
import sys
from pathlib import Path

from PIL import Image, ImageFilter

# The region is reduced until its longest side is this many pixels, then blown
# back up. Proportional rather than absolute, so a full-screen camera view and a
# single thumbnail come out equally unreadable instead of the small one surviving.
TARGET_LONG_SIDE = 8
GAUSSIAN_RATIO = 0.06
GAUSSIAN_MIN = 6


def blur_box(img: Image.Image, box) -> None:
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.width, x1), min(img.height, y1)
    if x1 <= x0 or y1 <= y0:
        raise SystemExit(f"empty region {box}")
    region = img.crop((x0, y0, x1, y1))
    w, h = region.size

    scale = TARGET_LONG_SIDE / max(w, h)
    small = region.resize(
        (max(1, round(w * scale)), max(1, round(h * scale))), Image.BILINEAR
    )
    radius = max(GAUSSIAN_MIN, round(min(w, h) * GAUSSIAN_RATIO))
    region = small.resize((w, h), Image.BILINEAR).filter(
        ImageFilter.GaussianBlur(radius)
    )
    img.paste(region, (x0, y0))


def parse(spec: str):
    parts = [int(p) for p in spec.split(",")]
    if len(parts) != 4:
        raise SystemExit(f"region must be x0,y0,x1,y1 - got {spec!r}")
    return parts


def main():
    args = sys.argv[1:]
    if len(args) < 3:
        sys.exit(__doc__)
    src, dst, rest = Path(args[0]), Path(args[1]), args[2:]
    img = Image.open(src).convert("RGB")

    boxes = []
    i = 0
    while i < len(rest):
        if rest[i] == "--grid":
            x0, y0, x1, y1, cols, rows = [int(p) for p in rest[i + 1].split(",")]
            cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
            for r in range(rows):
                for c in range(cols):
                    boxes.append(
                        [
                            int(x0 + c * cw),
                            int(y0 + r * ch),
                            int(x0 + (c + 1) * cw),
                            int(y0 + (r + 1) * ch),
                        ]
                    )
            i += 2
        else:
            boxes.append(parse(rest[i]))
            i += 1

    for box in boxes:
        blur_box(img, box)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "PNG", optimize=True)
    print(f"{src.name} -> {dst}  {len(boxes)} region(s) blurred")


if __name__ == "__main__":
    main()
