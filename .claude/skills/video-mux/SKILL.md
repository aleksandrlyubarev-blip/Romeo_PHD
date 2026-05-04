---
name: video-mux
description: Mux a re-encoded video back together with the original audio bitstream and container metadata, without re-encoding either side. Use when the user has a video-only output (encoded MP4/MKV with no audio), or asks to "put the audio back", "remux with original audio", "preserve metadata", "fix lost rotation". The contract is bit-exact for both video and audio bitstreams; rotation, GPS, creation_time, HDR side-data are all carried over via -map_metadata. Re-encoding audio for "compatibility" is almost never the right answer — copy it.
---

# Lossless audio + metadata mux

## When to reach for this

Right after any pipeline that produces a video-only re-encode (RFV
restore, super-resolution, frame interpolation, watermark removal, ...).
The encoded video is in your hand, the original input is on disk, and
you need to combine them without compromising either.

## The command

```bash
ffmpeg -hide_banner -nostdin -y -loglevel error \
       -i restored_video.mkv \         # input 0: new video
       -i audio_sidecar.mka \          # input 1: audio extracted earlier
       -i original.mp4 \               # input 2: original (metadata source only)
       -map 0:v:0 \
       -map 1:a \
       -c:v copy -c:a copy \
       -map_metadata 2 \
       -map_metadata:s:v:0 2:s:v:0 \
       -movflags +faststart \          # MP4/MOV only
       final.mp4
```

* **Three inputs** by design. The original is included only for tag
  scraping — no streams are mapped from it.
* `-c:v copy -c:a copy` — bit-exact for both bitstreams. Re-encoding
  AAC to AAC at the same bitrate visibly degrades it (generation loss
  on high-frequency content); always copy.
* `-map_metadata 2` — container-level tags (title, creation_time,
  make/model, GPS, encoder) from the original.
* `-map_metadata:s:v:0 2:s:v:0` — stream-level video tags too, which
  carries rotation Display Matrix and any HDR side-data the encoder
  didn't already write.
* `+faststart` — only for MP4/MOV/M4V; moves the `moov` atom to the
  start of the file so streaming clients can begin playback before
  the file is fully buffered.

## Audio sidecar extraction (run once, before re-encoding video)

```bash
ffmpeg -hide_banner -nostdin -y -loglevel error \
       -i original.mp4 \
       -map 0:a \
       -c:a copy \
       audio_sidecar.mka
```

Use `.mka` (Matroska Audio) as the container — it tolerates virtually
any codec. Matching the original container is risky (e.g. MP4 + raw PCM
is illegal even though some tools will write it).

## Python helpers in this repo

```python
from scripts.rfv_pipeline.pipeline import extract_audio, mux_audio
from scripts.rfv_pipeline.probe import probe

info = probe("original.mp4")
audio = extract_audio(info, work_dir=Path("/tmp/work"))   # → /tmp/work/audio.mka
# ... encode video → /tmp/work/restored_video.mkv ...
mux_audio(
    video_only=Path("/tmp/work/restored_video.mkv"),
    audio=audio,
    info=info,
    output=Path("/tmp/final.mp4"),
)
```

## Pitfalls

| Mistake | Real-world impact |
|---|---|
| Re-encoding audio "to be safe" (`-c:a aac -b:a 128k`) | generation loss; high frequencies fizzle |
| Forgetting `-map_metadata 0` | rotation, creation_time, GPS all lost |
| Using `-shortest` to "trim" an off-by-one frame | drops the last 1–2s of audio silently |
| Using MP4 with PCM audio | illegal combination; ffmpeg writes it but most players choke |
| Skipping `+faststart` on web video | viewer waits for full download before play |

## When NOT to use this skill

- The original audio actually needs editing (volume, EQ, normalisation)
  — that's a re-encode, not a remux. Use audio-focused FFmpeg filters.
- The original has multiple audio tracks and the user wants only one
  — same command but use `-map 1:a:0` (or whichever index) instead of
  `-map 1:a`.
