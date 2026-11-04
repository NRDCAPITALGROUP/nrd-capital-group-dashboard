# Rendering the carousel

The helper renders the layout. Codex supplies the copy, timestamps, and crops after visual inspection; it does not generate copy or find faces automatically.

## Runtime

Python needs Pillow. FFmpeg is resolved from `--ffmpeg`, `PATH`, or an installed `imageio_ffmpeg` package. Use the app's workspace dependency tool if default Python lacks Pillow. Helvetica Neue on macOS defaults to `/System/Library/Fonts/HelveticaNeue.ttc`, index 1 (Bold). Override `--font` and `--font-index` when needed. Without Helvetica Neue, the script falls back to Inter Bold if installed and prints a substitution note. `--help` works without Pillow.

Replace `SKILL_DIR` below with this skill's actual directory. Source paths in a manifest are relative to that manifest unless absolute.

## Scout

Inspect duration/orientation with FFprobe or FFmpeg's input metadata. Choose sample times within the duration. Start with widely spaced frames for a long source, then refine around promising sections. Scouting does not transcribe audio.

```bash
python3 SKILL_DIR/scripts/carousel.py scout \
  --source /path/to/video.mov --times 10,45,80,115 \
  --out /path/to/work/scout
```

This saves source-oriented thumbnails and a numbered contact sheet. `--crop X,Y,W,H` supports a second scout of candidate panel crops. Crops use source pixels **after FFmpeg applies display rotation**. Width/height must be in a 3:2 ratio for final rendering.

## Manifest

```json
{
  "title": "Carousel title",
  "source": "/path/to/video.mov",
  "frame_match": "exact",
  "frame_note": "Frames selected from the corresponding spoken passages.",
  "default_crop": [0, 650, 2160, 1440],
  "shade_alpha": 100,
  "slides": [
    {
      "top": {"time": 14.2, "text": "The first thought\ngoes here."},
      "bottom": {
        "time": 17.8,
        "text": "The next thought\ngoes here.",
        "crop": [0, 600, 2160, 1440]
      }
    }
  ]
}
```

These crop values illustrate the schema for a portrait 2160 × 3840 source. **Choose new coordinates for each video.** A 1920 × 1080 landscape source could use a 1620 × 1080 crop positioned around the speaker.

- `frame_match`: `exact` only when speech correspondence is checked; otherwise `illustrative`.
- `frame_note`: an accurate short explanation of selection.
- `default_crop`: `[left, top, width, height]`; each panel's `crop` overrides it. Every rendered panel needs a crop.
- `time`: nonnegative source seconds; decimals allowed.
- `text`: manual `\n` breaks, maximum two nonempty lines. Rebreak or shorten lines over 996 px; do not automatically reduce the type size.
- `source` (per panel, optional): overrides the top-level `source`. It can be a still photo (`.jpg`, `.png`, `.heic`, …) instead of a video; stills ignore `time`, honor EXIF rotation, and need no FFmpeg. Use this for photoshoot carousels. The top-level `source` may be omitted when every panel names its own.
- `shade_alpha`: optional maximum opacity, default 100 out of 255. Around 58 suits dark clothing; 100 suits the grey-shirt reference. Review the subtle gradient visually.

## Render

```bash
python3 SKILL_DIR/scripts/carousel.py render \
  --manifest /path/to/work/carousel.json \
  --out /path/to/outputs/carousel \
  --work /path/to/work/carousel-render
```

Add `--ffmpeg /absolute/path/to/ffmpeg` when needed. The output directory must not already exist; revisions use another directory. The work directory can be reused: frame cache keys include source metadata and timestamp, with crops reapplied each run.

Outputs:

- `slides/01.jpg`, `02.jpg`, etc.: 1080 × 1440 JPEGs, quality 97, no chroma subsampling.
- `carousel.zip`: only numbered JPEGs, at the ZIP root.
- `preview.jpg` and `index.html`: contact sheet and readable local gallery.
- `slide-copy.txt`: copy in reading order.
- `frame-sources.json`: timestamps, crops, source, matching note, and font used.
- `qa.json`: dimensions, line widths, image hashes, and repeat-frame warnings.

Read warnings and inspect the images. Width checks do not establish good framing or emotional fit. Confirm the ZIP and preview represent the same version after every revision.
