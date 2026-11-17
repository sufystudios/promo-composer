# AGENTS.md — promo-composer

Instructions for AI agents making promo videos, thumbnails and post text with this repository.

## Contract

- `python3 -m promocompose <video|layout|thumbs|copy-check> ...` (or `promocompose`). One JSON object on stdout.
- Exit codes: `0` ok · `1` failed (`{"error": "failed", "message": ...}`), invalid spec, or copy-check over a limit.
- `video` also writes `<out>.report.json`: `size`, `layout`, `duration`, `panels[].rect` (output pixels), `clips[]` (start/end in output seconds), `chapters` (paste into the YouTube description).

## The whole pipeline (with the sibling tools)

1. **Capture** each take: [promo-capture](https://github.com/sufystudios/promo-capture) (`promocap take spec.json`) records the phone/simulator and the desktop window with its audio.
2. **Measure** each take: [event-sync](https://github.com/sufystudios/event-sync) `eventsync offset --a phone.mp4 --a-roi <key> --b window.mov` gives `trim.a_start` / `trim.b_start`.
3. **Compose**: put those numbers in `clips[].starts` and run `promocompose video spec.json`.
4. **Verify the finished file**, not the pieces: map the key's source rectangle into the output (`promocompose layout spec.json --panel 0 --roi <key>`), then for each clip find when that output rectangle lights (`eventsync event`) and when the sound starts (`eventsync onset`, or the loudness series). Every clip should be within about one frame (33 ms). Report the worst figure to the user.
5. **Thumbnails** (`thumbs`) from frames of the same takes, and **text** checked with `copy-check`.

## Video spec reference

| Field | Meaning |
|---|---|
| `out` | output .mp4 (the report goes next to it) |
| `format` | `16:9` 1920x1080 · `9:16` 1080x1920 · `1:1` 1080x1080 · `4:5` 1080x1350 |
| `layout` | `side-by-side` (default for 16:9) · `stacked` (default otherwise) · `single` (one source) |
| `panels[]` | one per source: `label` (text under it), `crop` [x,y,w,h] in that source's pixels (e.g. drop a window's title bar) |
| `clips[]` | `name`, `caption`, `sources` (one per panel), `starts` (seconds into each source), `duration`, `audio` (index of the source whose sound is used; default the last) |
| `hook` | big line over the first clip only |
| `kicker` | small accent line over every clip's name |
| `note`, `footer` | under the caption / at the bottom |
| `end_card` | `title`, `lines` (first is the accent line), `icon` (png), `seconds` |
| `theme` | `background`, `accent`, `text`, `muted` colours |
| `fonts` | `headline`, `body`: font files (defaults are looked up for macOS, Linux, Windows) |
| `loudness` | integrated LUFS target, default -14 (YouTube, Facebook, Instagram normalise near it) |

Validate first: `promocompose video spec.json --validate`. Override per run: `--format 9:16 --out short.mp4` (the layout follows the format).

## Thumbnails spec

`{"out", "size": [1280, 720], "background": {"color", "glow": [c1, c2]}, "layers": [...]}`; several thumbnails as a list or `{"thumbnails": [...]}`. Layers, drawn in order:

- `image`: `src`, `crop`, `width`, `x`, `y`, `frame` (`phone` adds a bezel, `window` a rounded frame), `angle`, `shadow`
- `text`: `text`, `x`, `y`, `size`, `color`, `kind` (`headline`/`body`), `font`, `stroke`, `anchor` (Pillow anchors: `la` left-top, `ma` centre-top)
- `tag`: a rounded label: `text`, `x`, `y`, `size`, `bg`, `color`
- `arrow`: `from`, `to`, `color`, `width`, `head`
- `wifi`: `x`, `y`, `color`, `scale`

What works: 2–5 words of text, very large; one idea per thumbnail; real UI from the video; high contrast with an outline on text. Make three, each with a different hook, for YouTube's "Test & compare". Draw arrows as shapes: many fonts lack "→" and render a box.

## copy-check fields

`youtube_title` (100; ~60 visible), `youtube_description` (5000; also checks chapters: first 0:00, at least 3, each ≥ 10 s), `youtube_tags` (500), `play_title` (30), `play_short_description` (80), `play_full_description` (4000), `play_whats_new` (500), `appstore_name` (30), `appstore_subtitle` (30), `appstore_promotional_text` (170), `appstore_description` (4000), `appstore_keywords` (100), `appstore_whats_new` (4000), `facebook_post` (~125 visible), `instagram_caption` (2200, ≤ 30 hashtags), `x_post` (280), `tiktok_caption` (2200). Unknown keys fail, so typos don't slip through.

## Lessons from real videos

- **Check sync in the final file, every clip.** A first version cut each clip correctly, but each clip's picture ran 0.13–0.2 s longer than its sound (a phone recording's variable frame rate made the overlay overrun). Once joined, the picture drifted behind the sound clip by clip: +233 ms by the sixth clip of one promo, 0.6 s by the end of another. Clip-level checks all passed. The builder now trims both streams to the clip length and the tests cover a VFR source, but always run step 4 of the pipeline.
- **One latency per take.** The same phone over the same Wi-Fi was heard 0.84–1.14 s late, varying per take: never reuse one take's `starts` for another.
- **Keep the numbers true.** End-card claims ("212 premium sounds") went stale between videos: check them against the app's source or tests before rendering.
- **Fonts:** pass `fonts` for brand fonts; the defaults are system fonts and fall back to Pillow's built-in one, which looks plain.

## Changing the code

`promocompose/video.py` (validate, layout, source_roi_to_output, build, chapters), `thumbs.py`, `copycheck.py`, `text.py` (fonts, colours), `cli.py`. Tests in `tests/test_promocompose.py` build real files with ffmpeg; keep them fast (a few seconds of media).
