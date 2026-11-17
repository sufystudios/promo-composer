"""python3 -m unittest discover -s tests -v   (needs ffmpeg; makes its own media)"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from promocompose import copycheck, thumbs, video  # noqa: E402
from promocompose.cli import main  # noqa: E402


def ff(*args):
    subprocess.run(['ffmpeg', '-y', '-v', 'error', *args], check=True)


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height:format=duration',
                          '-of', 'json', path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


class ComposerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        cls.phone = os.path.join(d, 'phone.mp4')
        cls.plugin = os.path.join(d, 'plugin.mov')
        # Variable frame rate, like a phone's screen recording (frames dropped unevenly): this
        # once made each clip's picture run longer than its sound.
        ff('-f', 'lavfi', '-i', 'testsrc=size=1600x720:rate=60:duration=12',
           '-vf', "select='not(mod(n\\,3))+not(mod(n\\,7))',setpts=N/(37*TB)", '-fps_mode', 'vfr',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', cls.phone)
        ff('-f', 'lavfi', '-i', 'testsrc2=size=1216x568:rate=30:duration=12',
           '-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=48000:duration=12',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', cls.plugin)
        Image.new('RGB', (512, 512), (40, 120, 255)).save(os.path.join(d, 'icon.png'))
        cls.spec = {
            'out': os.path.join(d, 'out', 'promo.mp4'),
            'format': '16:9',
            'hook': 'MY PHONE IS PLAYING THE PLUGIN',
            'kicker': 'MOTION',
            'panels': [{'label': 'Phone'}, {'label': 'Plugin', 'crop': [0, 28, 1216, 540]}],
            'clips': [
                {'name': 'One', 'caption': 'First sound', 'sources': [cls.phone, cls.plugin], 'starts': [1.0, 1.5],
                 'duration': 4, 'audio': 1},
                {'name': 'Two', 'caption': 'Second sound', 'sources': [cls.phone, cls.plugin], 'starts': [6.0, 6.5],
                 'duration': 4, 'audio': 1},
            ],
            'note': 'Headphones on',
            'footer': 'Example app · Android · iPhone',
            'end_card': {'title': 'Example', 'lines': ['Line one', 'Line two'], 'icon': os.path.join(d, 'icon.png'),
                         'seconds': 2},
        }

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check_video(self, report, size):
        info = probe(report['out'])
        v = next(s for s in info['streams'] if s['codec_type'] == 'video')
        self.assertEqual([v['width'], v['height']], list(size))
        self.assertTrue(any(s['codec_type'] == 'audio' for s in info['streams']))
        self.assertAlmostEqual(float(info['format']['duration']), 10.0, delta=0.1)
        # Picture and sound end together (no drift across clips).
        durs = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,duration', '-of', 'json',
                               report['out']], capture_output=True, text=True).stdout
        d = {s['codec_type']: float(s['duration']) for s in json.loads(durs)['streams']}
        self.assertAlmostEqual(d['video'], d['audio'], delta=0.05, msg=d)
        self.assertEqual([c['name'] for c in report['clips']], ['One', 'Two', 'end card'])
        self.assertEqual(report['chapters'], '0:00 One\n0:04 Two')
        W, H = size
        rects = [p['rect'] for p in report['panels']]
        for x, y, w, h in rects:
            self.assertTrue(0 <= x and 0 <= y and x + w <= W and y + h <= H, rects)
        a, b = rects
        overlap = not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])
        self.assertFalse(overlap, rects)

    def test_widescreen(self):
        report = video.build(self.spec)
        self.check_video(report, (1920, 1080))
        self.assertEqual(report['layout'], 'side-by-side')
        self.assertTrue(os.path.exists(os.path.splitext(report['out'])[0] + '.report.json'))
        # Loudness lands near the -14 LUFS target.
        r = subprocess.run(['ffmpeg', '-v', 'info', '-i', report['out'], '-af', 'ebur128', '-f', 'null', '-'],
                           capture_output=True, text=True)
        lufs = float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)[-1])
        self.assertAlmostEqual(lufs, -14, delta=2.0)

    def test_portrait(self):
        spec = dict(self.spec, format='9:16', out=os.path.join(self.tmp.name, 'out', 'short.mp4'))
        report = video.build(spec)
        self.check_video(report, (1080, 1920))
        self.assertEqual(report['layout'], 'stacked')

    def test_validate(self):
        self.assertEqual(video.validate(self.spec), [])
        bad = json.loads(json.dumps(self.spec))
        bad['clips'][0]['starts'] = [1.0]
        bad['clips'][1]['sources'][0] = '/nope.mp4'
        bad['format'] = '3:2'
        problems = video.validate(bad)
        self.assertEqual(len(problems), 3, problems)

    def test_roi_mapping(self):
        lay = video.layout(self.spec, [(1600, 720), (1216, 568)])
        # The whole cropped plugin maps onto its panel exactly.
        self.assertEqual(video.source_roi_to_output(lay, 1, [0, 28, 1216, 540], (1216, 568)), lay['panels'][1])
        x, y, w, h = video.source_roi_to_output(lay, 0, [800, 360, 100, 100], (1600, 720))
        px, py, pw, ph = lay['panels'][0]
        self.assertAlmostEqual(x, px + pw / 2, delta=1)
        self.assertAlmostEqual(w, 100 * pw / 1600, delta=1)

    def test_layout_cli(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'spec.json')
            json.dump(self.spec, open(path, 'w'))
            self.assertEqual(main(['layout', path, '--panel', '1', '--roi', '0,28,1216,540']), 0)
            self.assertEqual(main(['video', path, '--validate']), 0)


class ThumbsTest(unittest.TestCase):
    def test_render(self):
        with tempfile.TemporaryDirectory() as d:
            Image.new('RGB', (1600, 720), (30, 160, 70)).save(os.path.join(d, 'frame.png'))
            spec = {'out': 'thumb.jpg', 'background': {'glow': ['#145a2a']}, 'layers': [
                {'type': 'image', 'src': 'frame.png', 'width': 560, 'x': 20, 'y': 330, 'frame': 'phone', 'angle': 6},
                {'type': 'image', 'src': 'frame.png', 'crop': [0, 0, 800, 400], 'width': 600, 'x': 650, 'y': 260,
                 'frame': 'window'},
                {'type': 'text', 'text': 'NO CABLES.', 'x': 640, 'y': 10, 'size': 200, 'anchor': 'ma'},
                {'type': 'tag', 'text': 'FREE', 'x': 900, 'y': 60, 'size': 46},
                {'type': 'arrow', 'from': [560, 250], 'to': [740, 330]},
                {'type': 'wifi', 'x': 640, 'y': 470},
            ]}
            r = thumbs.save(spec, d)
            self.assertEqual(r['size'], [1280, 720])
            self.assertTrue(r['youtube_ok'])
            im = Image.open(r['out'])
            self.assertGreater(im.getpixel((640, 120))[0], 200)  # the white headline is there

    def test_unknown_layer(self):
        with self.assertRaises(ValueError):
            thumbs.render({'layers': [{'type': 'sparkles'}]})


class CopyTest(unittest.TestCase):
    def test_limits(self):
        r = copycheck.check({'youtube_title': 'x' * 101, 'play_whats_new': 'ok', 'appstore_subtitle': 'y' * 31})
        self.assertFalse(r['ok'])
        self.assertFalse(r['fields']['youtube_title']['ok'])
        self.assertTrue(r['fields']['play_whats_new']['ok'])
        self.assertIn('1 characters too long', r['fields']['appstore_subtitle']['problem'])

    def test_unknown_field(self):
        self.assertFalse(copycheck.check({'yt_title': 'x'})['ok'])

    def test_chapters(self):
        good = 'Intro\n0:00 One\n0:10 Two\n0:20 Three\n'
        self.assertEqual(copycheck.chapter_problems(good), [])
        bad = '0:05 One\n0:10 Two\n'
        problems = copycheck.chapter_problems(bad)
        self.assertTrue(any('0:00' in p for p in problems))
        self.assertTrue(any('three' in p for p in problems))
        self.assertTrue(any('shorter than 10 s' in p for p in problems))


if __name__ == '__main__':
    unittest.main()
