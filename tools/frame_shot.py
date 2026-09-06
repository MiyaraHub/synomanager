#!/usr/bin/env python3
"""Wrap a raw device screenshot in the phone frame synomanager.com uses.

Every screenshot under docs/screenshots/ is a 1324x2644 PNG holding a 1080x2400
screen inside a 32px bezel with a soft drop shadow. The geometry is the same one
avrmaestro.com uses, so the two sites' shots sit at identical proportions:

    canvas   1324 x 2644
    body     x 90..1235, y 90..2555   (1144 x 2464, screen + 32 each side)
    screen   x 122..1202, y 122..2522 (1080 x 2400)

Captures come off a Pixel 10 Pro XL at 1344x2992. That aspect (0.4492) and the
frame's (0.45) differ by under a fifth of a percent, so the resize is invisible.

Usage:
    frame_shot.py RAW.png OUT.png
    frame_shot.py --dir RAW_DIR OUT_DIR

Privacy passes happen BEFORE framing, in blur_regions.py - a shot that needs one
is blurred into a staging file and framed from there, so no unblurred pixel ever
reaches docs/screenshots/.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

CANVAS = (1324, 2644)
SCREEN = (1080, 2400)
BEZEL = 32
SCREEN_XY = (122, 122)
BODY_XY = (SCREEN_XY[0] - BEZEL, SCREEN_XY[1] - BEZEL)
BODY = (SCREEN[0] + BEZEL * 2, SCREEN[1] + BEZEL * 2)

BODY_RADIUS = 112
SCREEN_RADIUS = 84
BODY_COLOR = (0, 0, 0, 255)
EDGE_COLOR = (28, 28, 30, 255)

SHADOW_BLUR = 26
SHADOW_ALPHA = 120
SHADOW_OFFSET = (0, 10)

RAW_W, RAW_H = 1344, 2992

# The notification-icon zone of the status bar: everything between the clock and
# the right-hand system icons.
#
# Android's SystemUI demo mode does not reliably hide notification icons on
# Android 17, so whatever the owner of the phone happens to have received lands
# in a public screenshot. Blanking the zone with the bar's own background colour
# removes the icons and nothing else - the clock, wifi and battery are untouched,
# and the app content below the bar is never modified.
#
# Geometry measured on a Pixel 10 Pro XL capture: the right-hand system group
# starts at the cellular bars (1061) and runs to the battery (1253), so the zone
# stops at 1112 - past the whole cellular group, inside the gap before wifi.
NOTIF_ZONE = (205, 0, 1112, 150)


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255
    )
    return mask


def blank_notifications(raw: Image.Image) -> Image.Image:
    out = raw.convert("RGB")
    # Sample the bar's own background rather than assuming black, so a light
    # theme or a tinted app bar still comes out seamless.
    bg = out.getpixel((out.width // 2, 8))
    ImageDraw.Draw(out).rectangle(NOTIF_ZONE, fill=bg)
    return out


def frame(raw: Image.Image) -> Image.Image:
    screen = blank_notifications(raw).resize(SCREEN, Image.LANCZOS)
    screen.putalpha(rounded_mask(SCREEN, SCREEN_RADIUS))

    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))

    shadow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [
            BODY_XY[0] + SHADOW_OFFSET[0],
            BODY_XY[1] + SHADOW_OFFSET[1],
            BODY_XY[0] + BODY[0] + SHADOW_OFFSET[0],
            BODY_XY[1] + BODY[1] + SHADOW_OFFSET[1],
        ],
        radius=BODY_RADIUS,
        fill=(0, 0, 0, SHADOW_ALPHA),
    )
    canvas = Image.alpha_composite(
        canvas, shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    )

    body = Image.new("RGBA", BODY, EDGE_COLOR)
    inner = Image.new("RGBA", (BODY[0] - 6, BODY[1] - 6), BODY_COLOR)
    inner.putalpha(rounded_mask(inner.size, BODY_RADIUS - 3))
    body.paste(inner, (3, 3), inner)
    body.putalpha(rounded_mask(BODY, BODY_RADIUS))
    canvas.paste(body, BODY_XY, body)

    canvas.paste(screen, SCREEN_XY, screen)
    return canvas


def assert_clean_bar(img: Image.Image, src: Path):
    """Refuse to emit a shot whose status bar still carries app icons.

    The blanking above should make this impossible, so a failure here means the
    zone moved - a different device, a taller status bar - rather than that a
    notification slipped through. Either way the shot does not ship. A check
    that depends on somebody looking is not a check.
    """
    x0 = SCREEN_XY[0] + int(NOTIF_ZONE[0] * SCREEN[0] / RAW_W)
    x1 = SCREEN_XY[0] + int(NOTIF_ZONE[2] * SCREEN[0] / RAW_W)
    y1 = SCREEN_XY[1] + int(NOTIF_ZONE[3] * SCREEN[1] / RAW_H)
    zone = img.convert("RGB").crop((x0, SCREEN_XY[1], x1, y1))
    colours = zone.getcolors(maxcolors=1 << 20) or []
    if not colours:
        raise SystemExit(f"{src}: notification zone sampled nothing")
    dominant = max(colours)[0] / (zone.width * zone.height)
    if dominant < 0.999:
        raise SystemExit(
            f"{src}: the status bar's notification zone is not uniform "
            f"({dominant:.4f} single-colour). Something is rendering there "
            f"and it would ship to a public page."
        )


# WebP at this quality is visually indistinguishable from the PNG on a UI
# screenshot and roughly a tenth of the weight - the whole set went from 21MB
# to about 2.5MB. Page weight is a Core Web Vitals input, so this is an SEO
# change as much as a bandwidth one. Alpha is preserved, which the rounded
# corners and the drop shadow need.
WEBP_QUALITY = 88


def convert(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    out = frame(Image.open(src))
    assert_clean_bar(out, src)
    if dst.suffix.lower() == ".webp":
        out.save(dst, "WEBP", quality=WEBP_QUALITY, method=6)
    else:
        out.save(dst, "PNG", optimize=True)
    print(f"{src.name} -> {dst}  {out.size}  {dst.stat().st_size // 1024}K")


def main():
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "--dir":
        src_dir, dst_dir = Path(args[1]), Path(args[2])
        shots = sorted(src_dir.glob("*.png"))
        if not shots:
            sys.exit(f"no PNGs in {src_dir}")
        for shot in shots:
            convert(shot, dst_dir / shot.name)
        return
    if len(args) != 2:
        sys.exit(__doc__)
    convert(Path(args[0]), Path(args[1]))


if __name__ == "__main__":
    main()
