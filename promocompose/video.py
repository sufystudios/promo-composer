"""Build a promo video from a JSON spec: clips of two (or one, or three) recordings shown together,
captions, an end card, loudness for streaming, YouTube chapters, and a report of where everything is.

Spec:
{
  "out": "promo.mp4",
  "format": "16:9",                 # 16:9 (1920x1080) | 9:16 (1080x1920) | 1:1 (1080x1080) | 4:5 (1080x1350)
  "layout": "side-by-side",         # side-by-side | stacked | single   (default: side-by-side for 16:9, stacked otherwise)
  "theme": {"background": "#080c08", "accent": "#34d058", "text": "#ffffff", "muted": "#96a596"},
  "fonts": {"headline": null, "body": null},   # font files; defaults are looked up per OS
  "hook": "MY PHONE IS PLAYING THE WINDOWS PLUGIN",   # first clip only
  "kicker": "STEREO FILTERS · MOTION",               # small line over each clip's name
  "panels": [ {"label": "Android phone", "crop": null},
              {"label": "The free Windows plugin", "crop": [0, 56, 2432, 1080]} ],
  "clips": [
    {"name": "Orbit", "caption": "The sound swinging from left to right",
     "sources": ["takes/s1-phone.mp4", "takes/s1-plugin.mov"], "starts": [6.0, 6.935],
     "duration": 10.1, "audio": 1}
  ],
  "note": "Headphones on",          # under each caption
  "footer": "DroneSynth · Android · iPhone · iPad · Mac",
  "end_card": {"title": "DroneSynth", "lines": ["...", "..."], "icon": "icon.png", "seconds": 4},
  "loudness": -14                   # integrated LUFS (YouTube/Facebook normalise to about -14)
}
"starts" are where each source's clip begins (seconds). Get them from event-sync's
`offset` (trim.a_start / trim.b_start) so the sources line up.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter

from .text import draw_text, fit_font, font, rgb

FORMATS = {'16:9': (1920, 1080), '9:16': (1080, 1920), '1:1': (1080, 1080), '4:5': (1080, 1350)}
DEFAULT_THEME = {'background': '#080c08', 'accent': '#34d058', 'text': '#ffffff', 'muted': '#96a596'}


def probe_size(path: str) -> tuple[int, int]:
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                          '-of', 'json', path], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)['streams'][0]
    return int(s['width']), int(s['height'])


def probe_duration(path: str) -> float:
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', path],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)['format']['duration'])


def validate(spec: dict) -> list[str]:
    p = []
    if spec.get('format', '16:9') not in FORMATS:
        p.append(f'format must be one of {sorted(FORMATS)}')
    if spec.get('layout') not in (None, 'side-by-side', 'stacked', 'single'):
        p.append('layout must be side-by-side, stacked or single')
    clips = spec.get('clips')
    if not clips:
        return p + ['"clips" must be a non-empty list']
    n = len(spec.get('panels') or clips[0].get('sources', []))
    for i, c in enumerate(clips):
        src = c.get('sources', [])
        if len(src) != n:
            p.append(f'clip {i}: {len(src)} sources, but {n} panels')
        if len(c.get('starts', [])) != len(src):
            p.append(f'clip {i}: "starts" needs one time per source')
        if not c.get('duration') or c['duration'] <= 0:
            p.append(f'clip {i}: "duration" (seconds) is required')
        if not (0 <= c.get('audio', len(src) - 1) < max(1, len(src))):
            p.append(f'clip {i}: "audio" must index a source')
        for s in src:
            if not os.path.exists(s):
                p.append(f'clip {i}: no such file {s}')
    if (spec.get('layout') == 'single') and n != 1:
        p.append('layout "single" takes one source per clip')
    return p


# MARK: - Layout


def layout(spec: dict, source_sizes: list[tuple[int, int]]) -> dict:
    """Where everything goes, in output pixels: header band, each panel's rectangle, its label,
    the caption area. Panel sizes keep each (cropped) source's aspect ratio."""
    W, H = FORMATS[spec.get('format', '16:9')]
    lay = spec.get('layout') or ('side-by-side' if W > H else 'stacked')
    if len(source_sizes) == 1:
        lay = 'single'
    crops = [((spec.get('panels') or [{}] * len(source_sizes))[i] or {}).get('crop') for i in range(len(source_sizes))]
    sizes = [(c[2], c[3]) if c else s for c, s in zip(crops, source_sizes)]
    portrait = H > W
    header = int(H * (0.13 if portrait else 0.19))
    footer = int(H * (0.15 if portrait else 0.25))
    label_h = int(H * (0.04 if portrait else 0.05))
    margin, gap = int(W * 0.02), int(W * 0.015)
    area = (margin, header, W - 2 * margin, H - header - footer)
    rects = []
    if lay == 'side-by-side':
        n = len(sizes)
        cell_w = (area[2] - gap * (n - 1)) / n
        cell_h = area[3] - label_h
        scales = [min(cell_w / w, cell_h / h) for w, h in sizes]
        x = area[0]
        for (w, h), s in zip(sizes, scales):
            pw, ph = int(w * s) // 2 * 2, int(h * s) // 2 * 2
            rects.append([int(x + (cell_w - pw) / 2), int(area[1] + (cell_h - ph) / 2), pw, ph])
            x += cell_w + gap
    else:  # stacked or single: full width each, heights by aspect, scaled down together to fit
        n = len(sizes)
        heights = [area[2] * h / w for w, h in sizes]
        total = sum(heights) + n * label_h + gap * (n - 1)
        s = min(1.0, area[3] / total)
        y = area[1] + (area[3] - total * s) / 2
        for (w, h) in sizes:
            pw = int(area[2] * s) // 2 * 2
            ph = int(pw * h / w) // 2 * 2
            rects.append([int((W - pw) / 2), int(y), pw, ph])
            y += ph + label_h * s + gap * s
    labels = [[r[0] + r[2] // 2, r[1] + r[3] + int(label_h * 0.2)] for r in rects]
    return {'size': [W, H], 'layout': lay, 'header': header, 'footer_top': H - footer, 'panels': rects,
            'crops': crops, 'labels': labels, 'label_h': label_h}


def source_roi_to_output(lay: dict, panel: int, roi: list[float], source_size: tuple[int, int]) -> list[int]:
    """Where a rectangle of a source recording (its own pixels) ends up in the output video.
    Use it to point event-sync's `verify` at the same element in the finished video."""
    crop = lay['crops'][panel] or [0, 0, source_size[0], source_size[1]]
    px, py, pw, ph = lay['panels'][panel]
    sx, sy = pw / crop[2], ph / crop[3]
    x, y, w, h = roi
    return [round(px + (x - crop[0]) * sx), round(py + (y - crop[1]) * sy), round(w * sx), round(h * sy)]


# MARK: - Pictures


def overlay_png(path: str, spec: dict, lay: dict, clip: dict, first: bool):
    W, H = lay['size']
    theme = {**DEFAULT_THEME, **spec.get('theme', {})}
    fonts = spec.get('fonts', {})
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    u = H / 1080 if W > H else W / 1080  # type scale
    y = int(18 * u)
    if first and spec.get('hook'):
        f = fit_font(d, spec['hook'], W * 0.92, int(36 * u), path=fonts.get('body'))
        draw_text(d, (W / 2, y), spec['hook'], f, rgb(theme['text']), shadow=True)
        y += int(48 * u)
    if spec.get('kicker'):
        draw_text(d, (W / 2, y), spec['kicker'], font(int(28 * u), fonts.get('body')), rgb(theme['accent']), shadow=True)
        y += int(36 * u)
    name = clip.get('name', '').upper()
    if name:
        f = fit_font(d, name, W * 0.9, int(min(96 * u, lay['header'] - y)), path=fonts.get('headline'), kind='headline')
        draw_text(d, (W / 2, y), name, f, rgb(theme['text']), shadow=True)
    for i, (x, ly) in enumerate(lay['labels']):
        label = ((spec.get('panels') or [{}] * len(lay['labels']))[i] or {}).get('label')
        if label:
            f = fit_font(d, label, lay['panels'][i][2] * 0.98, int(lay['label_h'] * 0.62), path=fonts.get('body'))
            draw_text(d, (x, ly), label, f, rgb(theme['muted']))
    cy = lay['footer_top'] + int(26 * u)
    if clip.get('caption'):
        f = fit_font(d, clip['caption'], W * 0.92, int(44 * u), path=fonts.get('body'))
        draw_text(d, (W / 2, cy), clip['caption'], f, rgb(theme['text']), shadow=True)
        cy += int(64 * u)
    if spec.get('note'):
        draw_text(d, (W / 2, cy), spec['note'], font(int(30 * u), fonts.get('body')), rgb(theme['accent']))
    if spec.get('footer'):
        f = fit_font(d, spec['footer'], W * 0.92, int(26 * u), path=fonts.get('body'))
        draw_text(d, (W / 2, H - int(56 * u)), spec['footer'], f, rgb(theme['muted']))
    im.save(path)


def end_card_png(path: str, spec: dict, size: tuple[int, int]):
    W, H = size
    card = spec['end_card']
    theme = {**DEFAULT_THEME, **spec.get('theme', {})}
    fonts = spec.get('fonts', {})
    bg = rgb(theme['background'])[:3]
    acc = rgb(theme['accent'])[:3]
    im = Image.new('RGB', (W, H), bg)
    glow = Image.new('RGB', (W, H), bg)
    ImageDraw.Draw(glow).ellipse([W * 0.15, H * 0.1, W * 0.85, H * 0.9],
                                 fill=tuple(int(b + (a - b) * 0.35) for a, b in zip(acc, bg)))
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(min(W, H) // 6)), 1.0)
    u = min(W, H) / 1080
    y = int(H * 0.16)
    if card.get('icon') and os.path.exists(card['icon']):
        s = int(240 * u)
        icon = Image.open(card['icon']).convert('RGBA').resize((s, s), Image.LANCZOS)
        mask = Image.new('L', (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], int(s * 0.22), fill=255)
        im.paste(icon, ((W - s) // 2, y), mask)
        y += s + int(40 * u)
    d = ImageDraw.Draw(im)
    f = fit_font(d, card.get('title', ''), W * 0.9, int(110 * u), path=fonts.get('body'))
    draw_text(d, (W / 2, y), card.get('title', ''), f, rgb(theme['text']))
    y += int(150 * u)
    for i, line in enumerate(card.get('lines', [])):
        f = fit_font(d, line, W * 0.9, int((52 if i == 0 else 42) * u), path=fonts.get('body'))
        draw_text(d, (W / 2, y), line, f, rgb(theme['accent'] if i == 0 else theme['muted']))
        y += int(80 * u)
    im.save(path)


# MARK: - Building


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])


def build(spec: dict, work: str | None = None, keep_work: bool = False) -> dict:
    problems = validate(spec)
    if problems:
        raise ValueError('; '.join(problems))
    if not shutil.which('ffmpeg'):
        raise RuntimeError('ffmpeg is not on PATH')
    out = spec.get('out', 'promo.mp4')
    tmp = work or tempfile.mkdtemp(prefix='promocompose-')
    os.makedirs(tmp, exist_ok=True)
    theme = {**DEFAULT_THEME, **spec.get('theme', {})}
    bg = theme['background'].lstrip('#')
    clips, report_clips, lay0, t = [], [], None, 0.0
    sizes0 = None
    for i, c in enumerate(spec['clips']):
        sizes = [probe_size(s) for s in c['sources']]
        lay = layout(spec, sizes)
        lay0, sizes0 = lay0 or lay, sizes0 or sizes
        W, H = lay['size']
        dur = float(c['duration'])
        ov = os.path.join(tmp, f'overlay{i}.png')
        overlay_png(ov, spec, lay, c, i == 0)
        inputs, chains = [], []
        for k, (src, start) in enumerate(zip(c['sources'], c['starts'])):
            inputs += ['-ss', f'{float(start):.3f}', '-t', f'{dur:.3f}', '-i', src]
            crop = lay['crops'][k]
            pre = f'crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},' if crop else ''
            pw, ph = lay['panels'][k][2], lay['panels'][k][3]
            chains.append(f'[{k}:v]fps=30,{pre}scale={pw}:{ph}:flags=lanczos,setsar=1[p{k}]')
        n = len(c['sources'])
        g = ';'.join(chains) + f';color=c=0x{bg}:s={W}x{H}:r=30:d={dur:.3f}[bg]'
        last = 'bg'
        for k in range(n):
            x, y = lay['panels'][k][:2]
            g += f';[{last}][p{k}]overlay={x}:{y}[v{k}]'
            last = f'v{k}'
        # Trim both to exactly `dur`: a variable-frame-rate source (phone screen recordings) can
        # make the overlay run past the clip's end, and over several clips the picture then
        # drifts behind the sound (seen: +0.13-0.2 s per clip).
        g += f';[{last}][{n}:v]overlay=0:0,trim=duration={dur:.3f},setpts=PTS-STARTPTS,format=yuv420p[out]'
        a = c.get('audio', n - 1)
        g += (f';[{a}:a]aresample=48000,apad,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS,'
              f'afade=t=in:d=0.05,afade=t=out:st={max(0.0, dur - 0.4):.3f}:d=0.4[a]')
        clip = os.path.join(tmp, f'clip{i}.mov')
        _run(['ffmpeg', '-y', '-v', 'error', *inputs, '-i', ov, '-filter_complex', g, '-map', '[out]', '-map', '[a]',
              '-t', f'{dur:.3f}', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-c:a', 'pcm_s16le',
              '-ar', '48000', clip])
        clips.append(clip)
        report_clips.append({'name': c.get('name', f'clip {i + 1}'), 'start': round(t, 3), 'end': round(t + dur, 3)})
        t += dur
    if spec.get('end_card'):
        W, H = lay0['size']
        secs = float(spec['end_card'].get('seconds', 4))
        png = os.path.join(tmp, 'end.png')
        end_card_png(png, spec, (W, H))
        clip = os.path.join(tmp, 'clipend.mov')
        _run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-t', str(secs), '-i', png,
              '-f', 'lavfi', '-t', str(secs), '-i', 'anullsrc=r=48000:cl=stereo',
              '-filter_complex', '[0:v]fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p,fade=t=in:d=0.4[v]',
              '-map', '[v]', '-map', '1:a', '-c:v', 'libx264', '-crf', '18', '-c:a', 'pcm_s16le', clip])
        clips.append(clip)
        report_clips.append({'name': 'end card', 'start': round(t, 3), 'end': round(t + secs, 3)})
        t += secs
    lst = os.path.join(tmp, 'list.txt')
    with open(lst, 'w') as f:
        f.write(''.join(f"file '{os.path.abspath(c)}'\n" for c in clips))
    joined = os.path.join(tmp, 'joined.mov')
    _run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', joined])
    lufs = spec.get('loudness', -14)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    _run(['ffmpeg', '-y', '-v', 'error', '-i', joined, '-c:v', 'copy',
          # loudnorm and AAC pad the end; trim so the sound ends with the picture.
          '-af', f'loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=48000,atrim=duration={t:.3f}', '-shortest',
          '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', out])
    report = {
        'out': out, 'size': lay0['size'], 'layout': lay0['layout'], 'duration': round(t, 3),
        'panels': [{'rect': r, 'crop': lay0['crops'][k], 'source_size': sizes0[k]}
                   for k, r in enumerate(lay0['panels'])],
        'clips': report_clips,
        'chapters': chapters(report_clips),
    }
    with open(os.path.splitext(out)[0] + '.report.json', 'w') as f:
        json.dump(report, f, indent=2)
    if not keep_work and not work:
        shutil.rmtree(tmp, ignore_errors=True)
    return report


def chapters(clips: list[dict]) -> str:
    """YouTube chapter lines ("0:00 Orbit"). The end card joins the clip before it."""
    lines = []
    for c in clips:
        if c['name'] == 'end card':
            continue
        s = int(round(c['start']))
        lines.append(f'{s // 60}:{s % 60:02d} {c["name"]}')
    return '\n'.join(lines)
