---
name: video-extract-frames
description: Losslessly extract frames from a video for AI processing or per-frame inspection. Use when the user says "extract frames", "save frames as PNG", "dump frames", "split video into images", or any per-frame analysis pipeline. Picks the right pix_fmt for the source bit depth (rgb24 / rgb48), preserves PTS for variable-frame-rate sources, never silently downsamples chroma, and supports both pipe-mode (rawvideo on stdout, no disk I/O) and disk-mode (PNG/PNG-16). Always probe the source first (via the video-probe skill) so the bit depth and FPS are right.
---

# Extracting frames without losing anything

## Decision tree

1. **Does the consumer want a numpy array per frame?** → pipe-mode
   (zero disk, fastest).
2. **Does the consumer need a file path per frame** (older AI models,
   debugging)? → disk-mode (PNG-8 if 8-bit source, PNG-16 if ≥9-bit).
3. **Is the source VFR?** Check via the `video-probe` skill — if yes,
   you must use `-fps_mode passthrough` AND keep the per-frame PTS in a
   sidecar, otherwise re-mux drops/duplicates frames and audio drifts.

## Pipe-mode (recommended)

```bash
ffmpeg -hide_banner -nostdin -loglevel error \
       -i input.mp4 \
       -map 0:v:0 \
       -fps_mode passthrough \
       -f rawvideo \
       -pix_fmt rgb48le        # rgb24 if source is 8-bit
       pipe:1
```

In Python:

```python
from scripts.rfv_pipeline.ffmpeg_runner import spawn
from scripts.rfv_pipeline.probe import probe
import subprocess, numpy as np

info = probe("input.mp4")
v = info.video
proc_pix = "rgb48le" if v.bit_depth > 8 else "rgb24"
bpp = 6 if proc_pix == "rgb48le" else 3
dtype = np.uint16 if proc_pix == "rgb48le" else np.uint8

dec = spawn([
    "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
    "-i", str(info.path),
    "-map", "0:v:0",
    "-fps_mode", "passthrough",
    "-f", "rawvideo", "-pix_fmt", proc_pix,
    "pipe:1",
], stdout=subprocess.PIPE)

frame_bytes = v.width * v.height * bpp
while True:
    buf = dec.stdout.read(frame_bytes)
    if len(buf) < frame_bytes:
        break
    frame = np.frombuffer(buf, dtype=dtype).reshape(v.height, v.width, 3)
    # ... process frame ...
```

## Disk-mode (when consumer wants paths)

```bash
ffmpeg -hide_banner -nostdin -loglevel error \
       -i input.mp4 \
       -map 0:v:0 \
       -fps_mode passthrough \
       -pix_fmt rgb48be          # PNG demands big-endian; rgb24 for 8-bit
       -pred mixed -compression_level 1 \
       -start_number 0 \
       frames/f_%08d.png
```

* `-pred mixed` — saves ~5% with no quality loss
* `-compression_level 1` — extraction is I/O-bound; level 9 doubles time
  for 10% smaller files
* `-start_number 0` — keeps frame indexing zero-based

For VFR sources, also dump per-frame PTS:

```bash
ffprobe -v error -select_streams v:0 \
        -show_entries frame=pts_time \
        -of csv=p=0 input.mp4 > frames/pts.csv
```

The `dump_pts()` helper in `probe.py` returns the same data as a Python list.

## Pitfalls to call out

| Mistake | Real-world impact |
|---|---|
| `-vf fps=30` on VFR source | drops/duplicates frames, audio drifts |
| `-pix_fmt rgb24` on 10-bit source | silent loss of 2 bits HDR precision |
| Forgetting `-an` when writing PNGs | scary (harmless) audio-stream warnings |
| Forgetting `-map 0:v:0` on multi-video files | extracts wrong stream |
| `-vsync 1` (CFR) | silently changes frame timing |

## When NOT to use this skill

- The user wants only a thumbnail / single frame at time T → use
  `ffmpeg -ss T -i in.mp4 -frames:v 1 out.png` (with `-ss` *before* `-i`
  for fast seek by keyframe).
- The user wants a contact-sheet / mosaic → that's a `-vf tile=...`
  filtergraph, not per-frame extraction.
