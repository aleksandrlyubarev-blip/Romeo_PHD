---
name: video-encode
description: Re-encode a video while preserving everything the source carries — colour space, bit depth, chroma layout, HDR static metadata, rotation, container tags, and audio (via copy). Use when the user says "transcode", "convert this to MP4/MKV", "compress this video", "re-encode at higher quality". Picks the right encoder (libx264 / libx265 / NVENC / QSV / VAAPI / VideoToolbox) for the source bit depth + hwaccel availability and emits the colour-tag stanza so players don't guess. Does NOT include the AI restoration step — for that, use video-restore-faces.
---

# Re-encoding without losing anything

## What "lossless of metadata" means here

The pixel content is re-compressed (so it's not bit-exact at the pixel
level, except `--crf 0`), but **everything else** survives the round-trip:

- colour space / primaries / transfer / range
- bit depth and chroma layout (yuv420p stays 4:2:0; yuv444p10le stays 4:4:4 10-bit)
- HDR10 static metadata (master-display + max-cll)
- baked-in rotation
- audio bitstream (no re-encode at all)
- container tags (creation_time, GPS, make/model)

Doing any of these wrong makes the output look or sound different from
the source for reasons unrelated to the encode quality you actually
asked for.

## Encoder selection cheat sheet

| Source | Encoder | Notes |
|---|---|---|
| 8-bit SDR, CPU | `libx264 -preset slow -crf 20` | tune=film for live action |
| 10-bit SDR or HDR | `libx265 -preset slow -crf 22` + `-x265-params` HDR string | libx264 lacks 10-bit support on most distros |
| Have NVIDIA GPU | `h264_nvenc` / `hevc_nvenc -preset p7 -tune hq -rc vbr -cq <crf>` | no CRF; CQ is closest analogue |
| Have Intel iGPU | `h264_qsv` / `hevc_qsv -global_quality <crf> -look_ahead 1` | |
| Have AMD GPU | `h264_vaapi` / `hevc_vaapi -qp <crf>` | QP is coarser than CRF |
| macOS (M-series / Intel) | `h264_videotoolbox` / `hevc_videotoolbox -q:v <0..100>` | quality is inverted CRF, roughly `(51 - crf) * 2` |

The repo's `pipeline.pick_encoder(cfg, info)` makes this choice for you.

## Canonical command (libx265, HDR-aware)

```bash
ffmpeg -hide_banner -nostdin -y -loglevel error \
       -i input.mkv \
       -map 0:v:0 -map 0:a \
       -c:v libx265 -preset slow -crf 19 -tune film \
       -pix_fmt yuv420p10le \
       -color_range tv -colorspace bt2020nc \
       -color_primaries bt2020 -color_trc smpte2084 \
       -x265-params "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:range=limited:hdr-opt=1:repeat-headers=1:master-display=G(...)B(...)R(...)WP(...)L(10000000,1):max-cll=1000,400" \
       -c:a copy \
       -map_metadata 0 \
       -map_metadata:s:v:0 0:s:v:0 \
       -display_rotation:v:0 0 \         # only if source had rotation
       -movflags +faststart \            # MP4/MOV only
       output.mp4
```

## NVENC variant

NVENC has no CRF; use `-rc vbr -cq N` (treat as if CRF):

```bash
ffmpeg -hwaccel cuda -i input.mkv \
       -c:v hevc_nvenc -preset p7 -tune hq \
       -rc vbr -cq 20 -b:v 0 \
       -spatial-aq 1 -temporal-aq 1 \
       -pix_fmt p010le \                # 4:2:0 10-bit
       -color_range tv -colorspace bt2020nc \
       -color_primaries bt2020 -color_trc smpte2084 \
       -c:a copy -map_metadata 0 \
       output.mp4
```

## Python helper

```python
from scripts.rfv_pipeline.pipeline import (
    pick_encoder, pick_output_pix_fmt, color_args, hdr_x265_params
)
from scripts.rfv_pipeline.probe import probe

info = probe("input.mkv")
encoder = pick_encoder(cfg, info.video)        # 'libx265' / 'hevc_nvenc' / ...
out_pix = pick_output_pix_fmt(cfg, info.video, encoder)
color_flags = color_args(info.video)            # ['-color_range', 'tv', ...]
x265 = hdr_x265_params(info.video) if encoder == "libx265" and info.video.is_hdr else None
```

## Pitfalls

| Mistake | Effect |
|---|---|
| `-pix_fmt yuv420p` on 10-bit source | bit depth crushed; banding in dark areas |
| Skipping `-color_*` flags | players assume BT.709 limited; BT.601 / BT.2020 / full-range source looks washed out |
| `-c:a aac -b:a 128k` instead of `-c:a copy` | generation loss; subtle but audible |
| Hard-coded `-r 30` | breaks every non-30 fps source |
| `-vsync cfr` on VFR | lipsync drift over long takes |
| Forgetting `+faststart` | MP4 won't stream until fully buffered |
| Letting NVENC pick `cbr` | encoder hits target bitrate by hurting quality |

## When NOT to use this skill

- The user wants per-frame AI work → use `video-restore-faces`.
- The user just wants to remux without re-encoding → `-c copy` and skip
  the encoder section entirely.
- The user wants extreme compression for an archive copy and quality
  doesn't matter → `libx265 -preset veryslow -crf 28` (or `-crf 32` for
  HDR10) is fine; otherwise stay in the 18–22 range.
