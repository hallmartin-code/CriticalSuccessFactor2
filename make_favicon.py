"""Generate the raster favicons from the brand mark in ``web/favicon.svg``.

The mark is three 95-degree arcs around a shared centre with a filled dot inside
each, in the coral/amber/teal palette the one-pager and the upload page share.
Both files are checked in; rerun this only when the mark itself changes:

    python make_favicon.py
"""

from __future__ import annotations

from math import cos, radians, sin
from pathlib import Path

from PIL import Image, ImageDraw

WEB_DIR = Path(__file__).with_name("web")

# --- geometry, in the same 100x100 viewBox as web/favicon.svg ---------------

CENTRE = 50.0
RADIUS = 34.0
STROKE = 13.0
DOT_RADIUS = 8.5

CORAL = "#EE5A4E"
AMBER = "#F3A22A"
TEAL = "#35BEBB"

# (colour, arc start, arc end) in Pillow's convention: degrees from 3 o'clock,
# sweeping clockwise on screen. Each arc spans 95 degrees, leaving 25-degree gaps.
ARCS = (
    (CORAL, 160.0, 255.0),
    (AMBER, 290.0, 25.0),
    (TEAL, 50.0, 145.0),
)

# (colour, x, y) of the dot nested inside each arc.
DOTS = (
    (CORAL, 35.28, 41.50),
    (AMBER, 65.97, 44.19),
    (TEAL, 48.52, 66.94),
)

SUPERSAMPLE = 8  # draw large, downsample once — Pillow has no antialiased arc
ICO_SIZES = ((16, 16), (32, 32), (48, 48), (64, 64))
APPLE_TOUCH_SIZE = 180


def render(size: int, background: str | None = None) -> Image.Image:
    """Render the brand mark at ``size`` px square.

    Args:
        size: Output edge length in pixels.
        background: Fill colour, or None for a transparent ground.
    """
    scale = size * SUPERSAMPLE / 100.0
    canvas = size * SUPERSAMPLE
    image = Image.new("RGBA", (canvas, canvas), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    width = STROKE * scale
    # Pillow strokes an arc inward from the bounding box; SVG centres it on the
    # path. Inflate the box by half the stroke so both land on the same ring.
    outer = RADIUS + STROKE / 2
    box = [
        (CENTRE - outer) * scale,
        (CENTRE - outer) * scale,
        (CENTRE + outer) * scale,
        (CENTRE + outer) * scale,
    ]
    for colour, start, end in ARCS:
        draw.arc(box, start=start, end=end, fill=colour, width=round(width))
        # Pillow has no round line cap; cap each end with a circle of the same radius.
        for angle in (start, end):
            _dot(draw, *_on_circle(angle), STROKE / 2, colour, scale)

    for colour, x, y in DOTS:
        _dot(draw, x, y, DOT_RADIUS, colour, scale)

    return image.resize((size, size), Image.LANCZOS)


def _on_circle(angle_degrees: float) -> tuple[float, float]:
    """Return the viewBox point at ``angle_degrees`` on the stroke's centre line."""
    angle = radians(angle_degrees)
    return CENTRE + RADIUS * cos(angle), CENTRE + RADIUS * sin(angle)


def _dot(
    draw: ImageDraw.ImageDraw, x: float, y: float, radius: float, colour: str, scale: float
) -> None:
    """Fill a circle given in viewBox units, scaled onto the supersampled canvas."""
    scaled_radius = radius * scale
    centre_x, centre_y = x * scale, y * scale
    draw.ellipse(
        [
            centre_x - scaled_radius,
            centre_y - scaled_radius,
            centre_x + scaled_radius,
            centre_y + scaled_radius,
        ],
        fill=colour,
    )


def main() -> None:
    """Write favicon.ico and apple-touch-icon.png into ``web/``."""
    largest = max(size for size, _ in ICO_SIZES)
    render(largest).save(WEB_DIR / "favicon.ico", sizes=ICO_SIZES)

    # iOS composites transparency onto black, so the touch icon gets a white ground.
    render(APPLE_TOUCH_SIZE, background="#FFFFFF").convert("RGB").save(
        WEB_DIR / "apple-touch-icon.png"
    )

    for name in ("favicon.ico", "apple-touch-icon.png"):
        path = WEB_DIR / name
        print(f"Wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
