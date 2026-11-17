"""Check promo text against each platform's limits before you paste it.

Input JSON: {"youtube_title": "...", "youtube_description": "...", "play_whats_new": "...", ...}
Unknown keys are reported, so typos don't pass silently.
"""
from __future__ import annotations

import re

# hard: the platform rejects or truncates more. soft: where it cuts the visible text in feeds/search.
LIMITS = {
    'youtube_title':            {'hard': 100, 'soft': 60, 'note': 'about 60 characters show in search and on phones'},
    'youtube_description':      {'hard': 5000, 'soft': 150, 'note': 'the first ~150 characters show above "more"'},
    'youtube_tags':             {'hard': 500, 'note': 'all tags together, commas included'},
    'play_title':               {'hard': 30},
    'play_short_description':   {'hard': 80},
    'play_full_description':    {'hard': 4000},
    'play_whats_new':           {'hard': 500},
    'appstore_name':            {'hard': 30},
    'appstore_subtitle':        {'hard': 30},
    'appstore_promotional_text': {'hard': 170},
    'appstore_description':     {'hard': 4000},
    'appstore_keywords':        {'hard': 100, 'note': 'comma-separated, no spaces needed after commas'},
    'appstore_whats_new':       {'hard': 4000},
    'facebook_post':            {'hard': 63206, 'soft': 125, 'note': 'about 125 characters show before "See more"'},
    'instagram_caption':        {'hard': 2200, 'soft': 125, 'note': 'at most 30 hashtags'},
    'x_post':                   {'hard': 280},
    'tiktok_caption':           {'hard': 2200},
}


def check(texts: dict) -> dict:
    results, ok = {}, True
    for key, value in texts.items():
        if key not in LIMITS:
            results[key] = {'ok': False, 'problem': f'unknown field; known: {", ".join(sorted(LIMITS))}'}
            ok = False
            continue
        lim = LIMITS[key]
        n = len(value)
        r = {'length': n, 'limit': lim['hard'], 'ok': n <= lim['hard']}
        if 'soft' in lim:
            r['visible_part'] = value[: lim['soft']]
        if lim.get('note'):
            r['note'] = lim['note']
        if key == 'instagram_caption' and len(re.findall(r'#\w+', value)) > 30:
            r['ok'] = False
            r['problem'] = 'more than 30 hashtags'
        if key == 'youtube_description':
            problems = chapter_problems(value)
            if problems:
                r['chapters'] = problems
        if not r['ok'] and 'problem' not in r:
            r['problem'] = f'{n - lim["hard"]} characters too long'
        ok = ok and r['ok']
        results[key] = r
    return {'ok': ok, 'fields': results}


def chapter_problems(description: str) -> list[str]:
    """YouTube makes chapters from timestamps in the description only if: the first is 0:00,
    there are at least three, and each is at least 10 seconds long."""
    times = []
    for line in description.splitlines():
        m = re.match(r'\s*(?:(\d+):)?(\d{1,2}):(\d{2})\b', line)
        if m:
            h, mnt, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
            times.append(h * 3600 + mnt * 60 + s)
    if not times:
        return []
    p = []
    if times[0] != 0:
        p.append('the first chapter must start at 0:00')
    if len(times) < 3:
        p.append('YouTube needs at least three chapters')
    for a, b in zip(times, times[1:]):
        if b - a < 10:
            p.append(f'chapter at {a // 60}:{a % 60:02d} is shorter than 10 s')
        if b <= a:
            p.append('chapter times must increase')
    return p
