"""promocompose: promo videos, thumbnails and post text from JSON specs. Every command prints JSON."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import copycheck, thumbs, video


def _load(path):
    with open(path) as f:
        return json.load(f)


def cmd_video(o):
    spec = _load(o.spec)
    if o.out:
        spec['out'] = o.out
    if o.format:
        spec['format'] = o.format
        spec.pop('layout', None)
    if o.validate:
        problems = video.validate(spec)
        return {'valid': not problems, 'problems': problems}
    return video.build(spec, work=o.work, keep_work=bool(o.work))


def cmd_layout(o):
    """Where the panels will be, without building anything (and a source ROI's place in the output)."""
    spec = _load(o.spec)
    if o.format:
        spec['format'] = o.format
        spec.pop('layout', None)
    sizes = [video.probe_size(s) for s in spec['clips'][0]['sources']]
    lay = video.layout(spec, sizes)
    result = {'size': lay['size'], 'layout': lay['layout'], 'panels': lay['panels'], 'crops': lay['crops']}
    if o.roi is not None:
        roi = [float(v) for v in o.roi.split(',')]
        result['output_roi'] = video.source_roi_to_output(lay, o.panel, roi, sizes[o.panel])
    return result


def cmd_thumbs(o):
    spec = _load(o.spec)
    root = os.path.dirname(os.path.abspath(o.spec))
    items = spec if isinstance(spec, list) else spec.get('thumbnails', [spec])
    return {'thumbnails': [thumbs.save(t, root) for t in items]}


def cmd_copy(o):
    return copycheck.check(_load(o.texts))


def build_parser():
    p = argparse.ArgumentParser(prog='promocompose', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('video', help='build a video from a spec')
    s.add_argument('spec'); s.add_argument('--out'); s.add_argument('--format', choices=sorted(video.FORMATS))
    s.add_argument('--validate', action='store_true'); s.add_argument('--work', help='keep intermediate files here')
    s.set_defaults(fn=cmd_video)
    s = sub.add_parser('layout', help="show the layout; map a source ROI into the output")
    s.add_argument('spec'); s.add_argument('--format', choices=sorted(video.FORMATS))
    s.add_argument('--panel', type=int, default=0); s.add_argument('--roi', help='x,y,w,h in the source')
    s.set_defaults(fn=cmd_layout)
    s = sub.add_parser('thumbs', help='render thumbnails from a spec (one, a list, or {"thumbnails": [...]})')
    s.add_argument('spec'); s.set_defaults(fn=cmd_thumbs)
    s = sub.add_parser('copy-check', help='check post and store text against platform limits')
    s.add_argument('texts'); s.set_defaults(fn=cmd_copy)
    return p


def main(argv=None):
    o = build_parser().parse_args(argv)
    try:
        result = o.fn(o)
    except (ValueError, RuntimeError, OSError, KeyError) as e:
        print(json.dumps({'error': 'failed', 'message': str(e)}))
        return 1
    print(json.dumps(result, indent=2))
    if result.get('valid') is False or result.get('ok') is False:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
