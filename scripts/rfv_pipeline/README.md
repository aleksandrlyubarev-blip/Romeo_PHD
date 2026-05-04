# RFV — Real-world Face Video restoration pipeline

A production-grade FFmpeg + Python harness for AI face-restoration on
arbitrary input video.  The point of this README is not "what the code
does" — that's in the docstrings — but **why every FFmpeg flag is the way
it is**, what a "naive" pipeline gets wrong, and how to handle the awkward
edge cases (VFR, HDR, ProRes, rotated phone clips) without losing audio
sync, colour, or metadata.

---

## TL;DR

```bash
# Smoke test (no AI, just verifies ffmpeg pipe + colour passthrough)
python -m rfv_pipeline \
    --input  in.mp4 \
    --output out.mp4 \
    --restorer rfv_pipeline.restore_stub:identity_array \
    --crf 18 --preset slow

# Real run, GPU
python -m rfv_pipeline \
    --input  ugly.mp4 \
    --output pretty.mp4 \
    --restorer my_models.gfpgan:restore_array \
    --hwaccel nvidia --crf 19

# Long video, chunked
python -m rfv_pipeline -i talk.mkv -o talk.restored.mkv \
    --restorer my_models.codeformer:restore_array \
    --chunk-seconds 60
```

---

## Architecture

```
              ┌────────────────────────┐
              │ ffprobe (probe.py)     │  → MediaInfo
              └────────────────────────┘
                          │
                ┌─────────┴──────────┐
                ▼                    ▼
   stream mode (default)        disk mode
                │                    │
   ffmpeg-decode → stdout      ffmpeg-decode → PNG/PNG-16
   (rawvideo, no                files (with passthrough
   colour conversion)           PTS for VFR)
                │                    │
   Python: numpy frames         Python: per-file restore_face(src, dst)
   → restore_array(arr) → ...        │
                │                    │
   ffmpeg-encode ← stdin       ffmpeg-encode ← image2 / concat demuxer
   (libx264/x265/_nvenc/...)   (per-frame durations for VFR)
                │                    │
                └─────────┬──────────┘
                          ▼
                 audio (sidecar -c:a copy)
                          │
                          ▼
                 final mux (-c copy, -map_metadata 0)
```

The audio track and container metadata never touch a re-encoder.  They
are extracted once with `-c:a copy`, then muxed back at the end with
`-c copy` + `-map_metadata 0`.  This is the single most important
invariant for a real-world pipeline.

---

## Frame extraction — what & why

### Naive version (DO NOT SHIP)

```bash
ffmpeg -i input.mp4 -vf fps=30 -q:v 1 frames/%08d.png
```

What this gets wrong:
| Problem | Effect |
|---|---|
| `-vf fps=30` | drops/duplicates frames whenever the source is VFR |
| no `-pix_fmt` | falls back to `rgb24`, throwing away ≥10-bit precision |
| no `-vsync passthrough` | resamples timestamps, losing PTS for the rebuild |
| no `-an` | extracts audio into the PNGs' (nonexistent) audio track and prints scary warnings |
| no `-loglevel error` | spams stderr; impossible to parse failures |

### What we use (stream mode)

```bash
ffmpeg -hide_banner -nostdin -loglevel error \
       -i input.mp4 \
       -map 0:v:0 \
       -fps_mode passthrough \
       -f rawvideo \
       -pix_fmt rgb48le \
       pipe:1
```

* `-map 0:v:0` — only the first video stream; audio + subtitle streams
  are handled by a separate `-c:a copy` extraction.  Saves two orders
  of magnitude of stderr noise on multi-track inputs.
* `-fps_mode passthrough` — keep source PTS exactly.  The legacy alias
  `-vsync passthrough` still works but is deprecated since FFmpeg 5.1.
* `-f rawvideo -pix_fmt rgb48le` — 16-bit container for any source ≥
  9-bit.  Dropping to `rgb24` here would silently throw away 2 bits of
  HDR precision.
* `pipe:1` — straight to Python via `Popen.stdout`.  No PNGs touch
  disk; on a 4K HDR source this saves ~600 GB/h.

### What we use (disk mode, when restorer wants paths)

```bash
ffmpeg -hide_banner -nostdin -loglevel error \
       -i input.mp4 \
       -map 0:v:0 \
       -fps_mode passthrough \
       -pix_fmt rgb48be \              # PNG demands big-endian
       -pred mixed -compression_level 1 \
       -start_number 0 \
       frames/f_%08d.png
```

* `-pred mixed` — dynamic predictor selection per row.  ~5 % smaller
  files than the default `none`, no quality cost.
* `-compression_level 1` — extraction is I/O-bound, not CPU-bound.
  Going from 1→9 roughly doubles wall-time and only saves ~10 %.
  (Reverse the trade for archival: `-compression_level 9` if you keep
  the frames around.)
* `-start_number 0` — keep frame indexing zero-based so chunked /
  multi-pass workflows align trivially.

For VFR sources we additionally write a sidecar PTS list via
`ffprobe -show_entries frame=pts_time` and feed it to the encoder
through the **concat demuxer with explicit per-frame durations** — see
"VFR" below.

---

## Reassembly — what & why

### Naive version (DO NOT SHIP)

```bash
ffmpeg -framerate 30 -i frames/%08d.png \
       -c:v libx264 -pix_fmt yuv420p output.mp4
```

What this gets wrong:
| Problem | Effect |
|---|---|
| hard-coded `30` | breaks every non-30-fps source |
| no `-crf` | falls back to bitrate guess (~200 kbps for HD), looks awful |
| no `-preset` | uses `medium`, leaves ~20 % efficiency on the table |
| no colour-tag flags | output decoded as BT.709 limited even when source was BT.601 / BT.2020 / full-range |
| `yuv420p` always | downsamples 4:4:4 chroma; mangles HDR (libx264 has no 10-bit container path on most builds) |
| no audio mux | result has no sound |
| no `+faststart` | MP4 needs a full read before play starts |
| no `-map_metadata 0` | rotation, GPS, creation_time, all gone |

### What we use (stream mode encoder)

```bash
ffmpeg -hide_banner -nostdin -y -loglevel error \
       -f rawvideo -pix_fmt rgb48le \
       -video_size 3840x2160 -framerate 24000/1001 \
       -i pipe:0 \
       -an \
       -pix_fmt yuv420p10le \
       -color_range tv -colorspace bt2020nc \
       -color_primaries bt2020 -color_trc smpte2084 \
       -c:v libx265 -preset slow -crf 19 -tune film \
       -x265-params "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:range=limited:hdr-opt=1:repeat-headers=1:master-display=...:max-cll=1000,400" \
       -display_rotation:v:0 0 \
       -movflags +faststart \
       restored_video.mkv
```

* The raw input stanza (`-f rawvideo … -framerate … -i pipe:0`) **must
  mirror the decoder's pix_fmt and geometry exactly** — otherwise the
  encoder reads garbage and silently produces 5 minutes of green noise.
* `-an` — explicit no-audio.  Audio is muxed in a separate pass so
  this encoder has only one input and we don't trip the `-shortest`
  / `-async` foot-guns.
* Colour stanza tags the bitstream with the source's metadata so
  players don't guess.  We **do not change colour spaces**; if the
  source was BT.2020 PQ, we re-encode to BT.2020 PQ.
* `-x265-params` carries HDR10 static metadata (master-display,
  max-cll) sourced from the input's `side_data_list`.  Without it,
  Apple TV / Chromecast / YouTube ingest treat the file as SDR.
* `-display_rotation` (FFmpeg ≥ 7.0) writes a real Display Matrix
  side-data atom; the legacy `-metadata:s:v:0 rotate=...` only works
  in MP4 and is deprecated.  We emit `-rotation` (CW → CCW sign flip,
  modulo 360).
* `-movflags +faststart` runs a second pass on MP4 output to move the
  `moov` atom to the front.  Streaming clients refuse to start
  otherwise.

### Final mux (audio + container metadata)

```bash
ffmpeg -hide_banner -nostdin -y -loglevel error \
       -i restored_video.mkv \
       -i audio.mka \
       -i input.mp4 \
       -map 0:v:0 -map 1:a \
       -c:v copy -c:a copy \
       -map_metadata 2 \
       -map_metadata:s:v:0 2:s:v:0 \
       -movflags +faststart \
       output.mp4
```

* Three inputs: the new video, the original audio sidecar, and the
  *original input* (only for tag scraping, no streams mapped from it
  except metadata).
* `-c:v copy -c:a copy` — no re-encode at all.  This step is bit-exact
  for both video bitstream and audio bitstream.
* `-map_metadata 2` — copy container-level tags (title,
  `creation_time`, `make`, `model`, GPS) from the original.
* `-map_metadata:s:v:0 2:s:v:0` — copy stream-level video tags too,
  including any HDR side-data the encoder didn't already write.

---

## VFR (variable frame rate)

Phone screen recordings, OBS captures, and most "smart" cameras emit
VFR.  If you flatten that to CFR you either drop frames (judder) or
duplicate them (lipsync drift over long takes).

Detection lives in `probe.py`:

* **Cheap**: compare `avg_frame_rate` to `r_frame_rate` with a 1 %
  tolerance.  Catches obvious VFR, ignores 23.976 vs 24 quantisation.
* **Strict**: `detect_vfr_strict()` walks up to N packets via
  `ffprobe -read_intervals %+#N` and looks at PTS deltas.  Use this
  when the cheap check is inconclusive.

Reconstruction uses the **concat demuxer with per-frame durations**:

```
ffconcat version 1.0
file 'frames/f_00000000.png'
duration 0.041708
file 'frames/f_00000001.png'
duration 0.016791
file 'frames/f_00000002.png'
duration 0.066458
…
file 'frames/f_00012345.png'   # last file repeated to commit duration
```

Then:

```bash
ffmpeg -f concat -safe 0 -i frames.ffconcat \
       -fps_mode vfr \
       -c:v libx264 -crf 18 -preset slow -tune film \
       …
```

`-fps_mode vfr` keeps the per-frame durations through the encoder;
without it the timestamps are CFR-resampled at the demuxer's nominal
rate and the trick is wasted.

---

## HDR (HDR10 / HDR10+ / HLG / Dolby Vision profile 5/8.x)

Detection: `color_transfer ∈ {smpte2084, arib-std-b67}` or
`color_primaries == bt2020`.

Output requirements:

1. **Encoder**: must be 10-bit capable.  `libx265` is the safe choice
   (`libx264` only carries 10-bit if compiled `--bit-depth=10`, which
   most distros don't).  HW: `hevc_nvenc` / `hevc_qsv` / `hevc_vaapi`
   with `-pix_fmt p010le`.
2. **Pix fmt**: `yuv420p10le` (BT.2020 4:2:0 10-bit) for libx265,
   `p010le` for HW.  Never `yuv420p`.
3. **Static metadata**: emit `-x265-params master-display=...:max-cll=...`
   sourced from the input's `side_data_list` (`Mastering display
   metadata` + `Content light level metadata`).  We auto-build this
   string in `pipeline.hdr_x265_params()`.
4. **Container**: MKV is safest.  MP4 is fine but some players (Quick
   Look on macOS pre-Sonoma) refuse HDR MP4 with HEVC SEI metadata.
5. **Dolby Vision**: profile 5 (single-layer, IPT-PQ-C2) survives a
   re-encode only if you carry the RPU sidecar via
   `-strict unofficial -dolbyvision true` on libx265 ≥ 3.6 *and* the
   source RPU was extracted with `dovi_tool`.  Profile 8.1 (BL+EL+RPU)
   does not survive any pipeline that touches pixels — restoration on
   DV 8.1 is, today, a research problem.  We leave the file to the
   user.

---

## Hardware acceleration — when it actually helps

Pure HW pipeline (`-hwaccel cuda -hwaccel_output_format cuda → frame
on GPU → h264_nvenc`) is the only hardware path that's genuinely
faster than CPU.  Once we drag the frame across the PCIe bus into
numpy for the AI pass, the NVENC encoder is downstream of a CPU
buffer anyway and the speed-up shrinks to the difference between
NVENC and `libx264 -preset veryfast`.

What we do support:

* `--hwaccel nvidia`: `-hwaccel cuda` for decode (frees CPU for the
  restorer thread), `h264_nvenc` / `hevc_nvenc` for encode with
  `-rc vbr -cq <crf> -preset p7 -tune hq -spatial-aq 1 -temporal-aq
  1`.  NVENC has no CRF; CQ is the closest perceptual analogue.
* `--hwaccel intel`: `-hwaccel qsv`, `h264_qsv` / `hevc_qsv` with
  `-global_quality <crf> -look_ahead 1`.
* `--hwaccel amd`: `-hwaccel vaapi -hwaccel_device /dev/dri/renderD128`,
  `h264_vaapi` / `hevc_vaapi` with `-qp <crf>`.  VAAPI doesn't expose
  per-frame quality the way x264/x265 does; QP is a coarse proxy.
* `--hwaccel videotoolbox`: macOS only; quality scale is 0..100 and
  we map roughly inverse to the CRF the user asked for.

What we **do not** do: silently swap in `-hwaccel cuda` just because
NVIDIA hardware is present.  That breaks colour pipelines (CUDA
filtergraph has limited pix_fmt support) and is why so many "auto-
GPU" video tools produce washed-out output.

---

## Chunked processing for long inputs

```bash
python -m rfv_pipeline -i 4hour_lecture.mkv -o restored.mkv \
       --restorer my_models.codeformer:restore_array \
       --chunk-seconds 90
```

Implemented as:

```bash
# 1. split at keyframes — segment muxer, no re-encode
ffmpeg -i input.mkv -map 0:v:0 -c:v copy \
       -f segment -segment_time 90 -reset_timestamps 1 \
       chunks_in/chunk_%05d.mkv

# 2. process each chunk independently (recursive RFVPipeline.run with
#    chunk_seconds=0)

# 3. concat with -c copy — no re-encode at the seam
ffmpeg -f concat -safe 0 -i concat.txt -c copy merged.mkv
```

* The segment muxer cuts at the **next** keyframe, so chunks are
  slightly variable length.  We tolerate that — the alternative
  (`-force_key_frames` on input) requires a full re-encode of the
  source.
* `-reset_timestamps 1` so each chunk starts at PTS 0; otherwise the
  concat step has to rebuild PTS, which it can do but slowly.
* `-c copy` at concat means seam quality == source quality.  No
  generation loss.

---

## Common pitfalls and their fixes

| Symptom | Real cause | Fix |
|---|---|---|
| Audio drifts ahead of video by ~50 ms in a 1 h file | encoder's `-r 30` resampled VFR to CFR | extract with `-fps_mode passthrough`, mux with concat demuxer + per-frame durations |
| Output is washed out / too contrasty | source was BT.601 limited or BT.2020 full, output tagged BT.709 limited | emit explicit `-color_range / -colorspace / -color_primaries / -color_trc` matching the source |
| Vertical phone video plays sideways | `tags.rotate` was lost on re-encode | use `-display_rotation:v:0 <ccw>` (FFmpeg 7+) or `-metadata:s:v:0 rotate=N` (legacy MP4 only); never bake rotation into pixels unless you also clear the metadata |
| Players show banding on dark areas of HDR output | encoded as 8-bit (`yuv420p`) | `--encoder libx265` with `-pix_fmt yuv420p10le`; we do this automatically when source is ≥ 10-bit |
| First few frames are duplicated | encoder's input GOP started before the decoder caught up | `-fps_mode passthrough` on both ends; never rely on `-vsync 1` (CFR + drop) |
| Output MP4 won't play in browser until fully buffered | `moov` atom at the end | `-movflags +faststart` (MP4 only; MKV doesn't need this) |
| `Broken pipe` from the decoder mid-run | encoder crashed, stderr hidden | the runner's pump thread captures stderr and re-raises as `FFmpegError(stderr=...)` — read it |
| Memory blows up on hour-long input | naive `imageio.mimread` loaded the whole video | use stream mode (default) — frames flow through Python in 1-frame chunks |

---

## Scenario commands

### ProRes 422 HQ source (10-bit 4:2:2, common for editorial)

```bash
python -m rfv_pipeline -i master.mov -o restored.mov \
    --encoder libx265 --crf 16 --preset slower \
    --restorer my_models.gfpgan:restore_array
```

Pipeline picks `yuv422p10le` automatically (preserves chroma layout).

### 8-bit phone video

```bash
python -m rfv_pipeline -i phone.mp4 -o phone.fixed.mp4 \
    --crf 20 --preset slow --restorer my_models.gfpgan:restore_array
```

Default path: `libx264`, `yuv420p`, BT.709 colour.

### HDR10 HEVC source

```bash
python -m rfv_pipeline -i hdr.mkv -o hdr.restored.mkv \
    --encoder libx265 --crf 18 --preset slower \
    --restorer my_models.codeformer:restore_array
```

Auto-detected as HDR; pipeline emits `-pix_fmt yuv420p10le`,
`-x265-params "...:hdr-opt=1:master-display=...:max-cll=..."`.

### VFR screen capture

```bash
python -m rfv_pipeline -i screen.mkv -o screen.fixed.mkv \
    --mode disk --restorer my_models.basicsr:restore_disk
```

Disk mode forces the concat-demuxer rebuild path which preserves
per-frame timing.  Stream mode also works for VFR (we always pass
`-fps_mode passthrough`), but the disk path lets you eyeball
frame_id ↔ PTS alignment in the sidecar `frames.ffconcat`.

### Lossless intermediate (for handing off to a colourist)

```bash
python -m rfv_pipeline -i in.mov -o out.mkv \
    --encoder libx264 --crf 0 --preset veryslow \
    --pix-fmt-out yuv444p \
    --restorer my_models.gfpgan:restore_array
```

`--crf 0 --pix-fmt-out yuv444p` gives mathematically lossless
H.264 4:4:4.  File sizes are about 4× the equivalent CRF 18 — only
use as an intermediate.

---

## Restorer contracts

```python
# Stream contract  (mode=stream, default)
def restore(frame: np.ndarray) -> np.ndarray:
    # frame.shape == (H, W, 3); dtype uint8 (8-bit src) or uint16 (>8-bit)
    return restored

# Disk contract  (mode=disk)
def restore(src: pathlib.Path, dst: pathlib.Path) -> None:
    # read PNG at src, write PNG at dst, preserve bit depth
    ...
```

Stream is faster and avoids touching disk; pick disk only when the
restorer's API insists on file paths (older releases of GFPGAN /
CodeFormer / Real-ESRGAN do this).  For the existing
`restore_face(frame_path)` style function the TZ mentions, wrap it
with `restore_stub.adapt_legacy_restore_face`.

---

## Files

```
rfv_pipeline/
├── __init__.py          # public API re-exports
├── __main__.py          # `python -m rfv_pipeline`
├── cli.py               # argparse, restorer loader, progress printer
├── ffmpeg_runner.py     # subprocess + -progress pipe + concat lists
├── pipeline.py          # extract → restore → encode → mux orchestration
├── probe.py             # ffprobe wrapper, MediaInfo, VFR/HDR detection
├── restore_stub.py      # identity & legacy adapters
├── requirements.txt
└── README.md            # this file
```
