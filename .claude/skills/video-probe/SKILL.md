---
name: video-probe
description: Inspect a video file end-to-end before doing anything to it. Use when the user asks "what is this video", "media info", "is this VFR / HDR", "what codec / colour space / fps", or any time you need to choose encode flags. Returns codec, geometry, FPS (avg vs declared), VFR detection, bit depth, colour space / primaries / transfer (HDR-aware), baked-in rotation, every audio stream, and container tags. Always probe before extracting frames or re-encoding — guessing flags causes washed-out output, audio drift, and lost rotation metadata.
---

# Probing video correctly

## Why this skill exists

Almost every video bug — washed-out colour, audio drift, sideways playback,
HDR banding — traces back to a wrong assumption about the source. Run this
skill before extracting frames, re-encoding, or proposing FFmpeg flags.

## How to run

The repo ships `scripts/rfv_pipeline/probe.py`. Prefer it over hand-rolled
`ffprobe` calls — it normalises edge cases (Display Matrix vs `tags.rotate`,
`bits_per_raw_sample` vs pix_fmt-derived bit depth, BT.2020 SDR misclassified
as HDR, etc.).

### Python

```python
from scripts.rfv_pipeline.probe import probe, detect_vfr_strict

info = probe("input.mp4")
print(info.video.width, info.video.height, info.video.codec)
print("avg_fps:", info.video.avg_fps, "  vfr:", info.video.is_vfr)
print("bit_depth:", info.video.bit_depth, "  hdr:", info.video.is_hdr)
print("rotation (CW):", info.video.rotation)
print("audio streams:", len(info.audio))

# When the cheap VFR heuristic is inconclusive (e.g. screen recordings
# that *declare* a sane r_frame_rate but actually aren't constant)
if not info.video.is_vfr:
    really_vfr = detect_vfr_strict(info.path, max_packets=5000)
```

### CLI (one-shot, JSON to stdout)

```bash
python -m scripts.rfv_pipeline --input input.mp4 --probe-only
```

### Raw `ffprobe` (only if the wrapper isn't available)

```bash
ffprobe -v error -print_format json -show_format -show_streams input.mp4
```

The fields that actually matter:
- `streams[v].avg_frame_rate` vs `r_frame_rate` — VFR detection
- `streams[v].pix_fmt` + `bits_per_raw_sample` — bit depth
- `streams[v].color_range / color_space / color_transfer / color_primaries`
  — colour pipeline; HDR if `color_transfer ∈ {smpte2084, arib-std-b67}`
  or `color_primaries == bt2020`
- `streams[v].side_data_list[].Display Matrix.rotation` — modern rotation
  (FFmpeg ≥ 7.0); falls back to `tags.rotate` on older builds
- `streams[v].side_data_list[]` for `Mastering display metadata` and
  `Content light level metadata` — required to re-emit HDR10 metadata
  on remux
- `format.duration` and `format.tags` (creation_time, make, model, GPS)

## What to report back to the user

A 1-line "punch card" they can act on:

```
1920x1080 h264 8-bit yuv420p, 29.97 CFR, BT.709 limited, audio: aac 2ch 48kHz, rotation: 0, duration: 12m04s
```

If you see anything tricky (`is_vfr`, `is_hdr`, non-zero `rotation`, multi-
audio, exotic pix_fmt like `yuv444p10le`), call it out explicitly — those
are the cases where naive re-encode chains silently corrupt the file.

## When NOT to use this skill

- The user already gave you full ffprobe output — read it instead.
- The task is purely about the audio bitstream and you don't need video
  metadata (use `ffprobe -select_streams a` directly).
