# promo-composer

Turn app recordings into finished promo material from small JSON files:

- **Videos** for YouTube (16:9), Shorts/Reels/TikTok (9:16), square (1:1) and feed (4:5): two (or one, or three) recordings shown together per clip, the sound's name and a caption, a hook on the first clip, an end card with your icon, loudness at -14 LUFS, and **YouTube chapters** written for you.
- **A report** of where every panel landed, and a `layout` command that maps any rectangle of a source recording into the finished video, so you can check sync in the final file with [event-sync](https://github.com/sufystudios/event-sync).
- **Thumbnails** from layers: real frames in phone or window frames (tilted, with shadows), outlined headline text, tags, arrows, a Wi-Fi symbol.
- **copy-check**: titles, descriptions, store "What's new" text and captions against each platform's limits, plus YouTube's chapter rules.

```
promocompose video promo.json                 # -> promo.mp4 + promo.report.json (chapters, panels)
promocompose video promo.json --format 9:16 --out short.mp4
promocompose layout promo.json --panel 0 --roi 760,615,40,40   # where that source rect is in the output
promocompose thumbs thumbs.json
promocompose copy-check texts.json
```

Built for the promo videos of [DroneSynth](https://play.google.com/store/apps/details?id=xyz.sufystudios.synthguide) (an Android phone playing the free DroneSynth desktop plugin) with [promo-capture](https://github.com/sufystudios/promo-capture) and [event-sync](https://github.com/sufystudios/event-sync).

## Install

Python 3.9+, Pillow, and [ffmpeg](https://ffmpeg.org) on PATH.

```
pip install git+https://github.com/sufystudios/promo-composer
python3 -m promocompose --help        # or from a clone
```

## A video spec

```json
{
  "out": "promo.mp4",
  "format": "16:9",
  "hook": "MY PHONE IS PLAYING THE WINDOWS PLUGIN",
  "kicker": "STEREO FILTERS · MOTION",
  "panels": [{"label": "Android phone"}, {"label": "The free Windows plugin", "crop": [0, 56, 2432, 1080]}],
  "clips": [
    {"name": "Orbit", "caption": "The sound swinging from left to right and back",
     "sources": ["takes/s1-phone.mp4", "takes/s1-plugin.mov"], "starts": [6.2, 6.435], "duration": 10.1, "audio": 1}
  ],
  "note": "Headphones on",
  "footer": "MyApp · Android · iPhone",
  "end_card": {"title": "MyApp", "lines": ["One line that sells it", "Where to get it"], "icon": "icon.png", "seconds": 4}
}
```

`starts` are where each recording's clip begins. Measure them with `eventsync offset` (its `trim` values) rather than guessing. Full field list: [AGENTS.md](AGENTS.md) and `examples/`.

## Tests

```
python3 -m unittest discover -s tests -v
```

They build real videos from generated sources, including a variable-frame-rate one like a phone's screen recording, and check size, length, that picture and sound end together, loudness, chapters and panel placement.

## License

MIT. See [LICENSE](LICENSE).
