"""Thumbnails from a JSON spec of layers drawn in order.

{
  "out": "thumb-A.jpg",
  "size": [1280, 720],                       # YouTube; 1200x630 for a Facebook/OG link
  "background": {"color": "#060c08", "glow": ["#145a2a", "#0e3c1e"]},
  "layers": [
    {"type": "image", "src": "frame.png", "crop": [0, 56, 2432, 1080], "width": 900, "x": 350, "y": 250,
     "frame": "window" | "phone" | null, "angle": 0, "shadow": true, "radius": 14},
    {"type": "text", "text": "MY PHONE", "x": 40, "y": 18, "size": 150, "color": "white",
     "font": null, "kind": "headline", "stroke": 6, "anchor": "la"},
    {"type": "tag", "text": "FREE PLUGIN", "x": 900, "y": 70, "size": 46, "bg": "yellow", "color": "black"},
    {"type": "arrow", "from": [560, 250], "to": [740, 330], "color": "yellow", "width": 14, "head": 40},
    {"type": "wifi", "x": 640, "y": 470, "color": "yellow", "scale": 1.0}
  ]
}
Coordinates are the thumbnail's pixels; "x","y" of an image is its top-left before any rotation.
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFilter

from .text import font, rgb

YOUTUBE = (1280, 720)


def _background(size, bg):
    W, H = size
    base = rgb(bg.get('color', '#060c08'))[:3]
    im = Image.new('RGB', size, base)
    glows = bg.get('glow', [])
    if glows:
        g = Image.new('RGB', size, base)
        d = ImageDraw.Draw(g)
        boxes = [[W * 0.35, -H * 0.3, W * 1.25, H * 1.3], [-W * 0.25, H * 0.4, W * 0.5, H * 1.6]]
        for color, box in zip(glows, boxes):
            d.ellipse(box, fill=rgb(color)[:3])
        im = Image.blend(im, g.filter(ImageFilter.GaussianBlur(min(W, H) // 5)), 1.0)
    return im.convert('RGBA')


def _rounded(img, r):
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], r, fill=255)
    out = img.convert('RGBA')
    out.putalpha(mask)
    return out


def _shadowed(img, blur=24, offset=(0, 14), alpha=200):
    pad = blur * 3
    canvas = Image.new('RGBA', (img.size[0] + pad * 2, img.size[1] + pad * 2), (0, 0, 0, 0))
    sh = Image.new('RGBA', img.size, (0, 0, 0, 255))
    sh.putalpha(img.getchannel('A').point(lambda a: a * alpha // 255))
    canvas.alpha_composite(sh, (pad + offset[0], pad + offset[1]))
    canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(img, (pad, pad))
    return canvas, pad


def _image_layer(base, L, root):
    src = Image.open(os.path.join(root, L['src'])).convert('RGB')
    if L.get('crop'):
        x, y, w, h = L['crop']
        src = src.crop((x, y, x + w, y + h))
    width = int(L.get('width', src.size[0]))
    height = int(width * src.size[1] / src.size[0])
    img = src.resize((width, height), Image.LANCZOS)
    frame = L.get('frame')
    if frame == 'phone':
        img = _rounded(img, int(width * 0.03))
        b = int(width * 0.035)
        body = Image.new('RGBA', (width + 2 * b, height + 2 * b), (0, 0, 0, 0))
        ImageDraw.Draw(body).rounded_rectangle([0, 0, body.size[0] - 1, body.size[1] - 1], int(width * 0.06),
                                               fill=(14, 14, 16, 255), outline=(70, 74, 78, 255), width=3)
        body.alpha_composite(img, (b, b))
        img = body
    else:
        img = _rounded(img, int(L.get('radius', 14 if frame == 'window' else 0)))
        if frame == 'window':
            ImageDraw.Draw(img).rounded_rectangle([0, 0, width - 1, height - 1], int(L.get('radius', 14)),
                                                  outline=(90, 100, 92, 255), width=3)
    if L.get('angle'):
        img = img.rotate(L['angle'], resample=Image.BICUBIC, expand=True)
    if L.get('shadow', True):
        img, pad = _shadowed(img)
    else:
        pad = 0
    base.alpha_composite(img, (int(L.get('x', 0)) - pad, int(L.get('y', 0)) - pad))


def _arrow(d, p0, p1, color, width=14, head=40):
    d.line([tuple(p0), tuple(p1)], fill=color, width=width)
    a = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    d.polygon([tuple(p1), (p1[0] - head * math.cos(a - 0.45), p1[1] - head * math.sin(a - 0.45)),
               (p1[0] - head * math.cos(a + 0.45), p1[1] - head * math.sin(a + 0.45))], fill=color)


def _wifi(d, cx, cy, color, scale=1.0):
    r0, step, w = 26 * scale, 30 * scale, int(12 * scale)
    d.ellipse([cx - 10 * scale, cy - 10 * scale, cx + 10 * scale, cy + 10 * scale], fill=color)
    for i in range(3):
        r = r0 + i * step
        d.arc([cx - r, cy - r, cx + r, cy + r], 225, 315, fill=color, width=w)


def render(spec: dict, root: str = '.') -> Image.Image:
    size = tuple(spec.get('size', YOUTUBE))
    im = _background(size, spec.get('background', {}))
    for L in spec.get('layers', []):
        t = L.get('type')
        if t == 'image':
            _image_layer(im, L, root)
            continue
        d = ImageDraw.Draw(im)
        if t == 'text':
            f = font(int(L.get('size', 80)), L.get('font'), L.get('kind', 'headline'))
            d.text((L['x'], L['y']), L['text'], font=f, fill=rgb(L.get('color', 'white')), anchor=L.get('anchor', 'la'),
                   stroke_width=int(L.get('stroke', 6)), stroke_fill=rgb(L.get('stroke_color', 'black')))
        elif t == 'tag':
            f = font(int(L.get('size', 40)), L.get('font'), 'body')
            x, y = L['x'], L['y']
            l, tp, r, b = d.textbbox((x, y), L['text'], font=f)
            pad = int(L.get('size', 40) * 0.35)
            d.rounded_rectangle([l - pad, tp - pad * 0.6, r + pad, b + pad * 0.6], pad * 0.6, fill=rgb(L.get('bg', 'yellow')))
            d.text((x, y), L['text'], font=f, fill=rgb(L.get('color', 'black')))
        elif t == 'arrow':
            _arrow(d, L['from'], L['to'], rgb(L.get('color', 'yellow')), int(L.get('width', 14)), int(L.get('head', 40)))
        elif t == 'wifi':
            _wifi(d, L['x'], L['y'], rgb(L.get('color', 'yellow')), float(L.get('scale', 1.0)))
        else:
            raise ValueError(f'unknown layer type {t!r}')
    return im.convert('RGB')


def save(spec: dict, root: str = '.') -> dict:
    out = os.path.join(root, spec.get('out', 'thumbnail.jpg'))
    im = render(spec, root)
    im.save(out, quality=int(spec.get('quality', 92)))
    size = os.path.getsize(out)
    return {'out': out, 'size': list(im.size), 'bytes': size, 'youtube_ok': size <= 2 * 1024 * 1024}
