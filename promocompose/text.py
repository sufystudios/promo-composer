"""Fonts and text drawing shared by videos and thumbnails."""
from __future__ import annotations

import os

from PIL import ImageDraw, ImageFont

# Tried in order when a spec doesn't name a font. Bold condensed faces read best on small screens.
HEADLINE_FONTS = [
    '/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf',
    '/System/Library/Fonts/Supplemental/Impact.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf',
    'C:/Windows/Fonts/impact.ttf',
]
BODY_FONTS = [
    '/System/Library/Fonts/Avenir Next.ttc',
    '/System/Library/Fonts/Helvetica.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    'C:/Windows/Fonts/arialbd.ttf',
]


def font(size: int, path: str | None = None, kind: str = 'body', index: int | None = None) -> ImageFont.FreeTypeFont:
    """A font at `size`: `path` if given, else the first installed of the defaults for `kind`
    ('headline' or 'body'), else Pillow's built-in font."""
    candidates = [path] if path else (HEADLINE_FONTS if kind == 'headline' else BODY_FONTS)
    for p in candidates:
        if p and os.path.exists(p):
            if index is None and p.endswith('.ttc') and 'Avenir' in p:
                index = 2  # Avenir Next Demi Bold
            return ImageFont.truetype(p, size, index=index or 0)
    return ImageFont.load_default(size)


def rgb(color, alpha: int = 255) -> tuple[int, int, int, int]:
    """'#34d058', 'white', or [r, g, b] -> RGBA."""
    if isinstance(color, (list, tuple)):
        return tuple(color[:3]) + (color[3] if len(color) > 3 else alpha,)
    named = {'white': (255, 255, 255), 'black': (0, 0, 0), 'green': (52, 208, 88), 'yellow': (255, 214, 10),
             'red': (230, 57, 70), 'blue': (10, 132, 255), 'grey': (150, 160, 150), 'gray': (150, 160, 150)}
    if color in named:
        return named[color] + (alpha,)
    c = color.lstrip('#')
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: float, size: int, **kw) -> ImageFont.FreeTypeFont:
    """The largest font up to `size` whose rendering of `text` fits `max_width`."""
    while size > 10:
        f = font(size, **kw)
        if draw.textlength(text, font=f) <= max_width:
            return f
        size -= 2
    return font(size, **kw)


def draw_text(draw: ImageDraw.ImageDraw, xy, text: str, f, fill, anchor: str = 'ma', stroke: int = 0,
              stroke_fill=(0, 0, 0, 255), shadow: bool = False):
    if shadow:
        draw.text((xy[0] + 3, xy[1] + 3), text, font=f, fill=(0, 0, 0, 170), anchor=anchor)
    draw.text(xy, text, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=stroke_fill)
