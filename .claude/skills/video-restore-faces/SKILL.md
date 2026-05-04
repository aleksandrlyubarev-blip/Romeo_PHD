---
name: video-restore-faces
description: Run the Real-world Face Video (RFV) restoration pipeline — probe → extract → AI restore → re-encode → mux original audio + metadata. Use when the user says "restore faces in this video", "GFPGAN / CodeFormer this clip", "fix this old recording's faces", "deblur faces". Owns colour preservation, VFR/HDR handling, rotation metadata, audio passthrough, hardware acceleration, and chunked processing for long inputs. Always probe first (video-probe skill) and report what the pipeline detected before touching the file.
---

# Restoring face video end-to-end

## What this skill orchestrates

`scripts/rfv_pipeline/` already implements the whole flow. This skill picks
the right flags from the source's actual properties and explains the
trade-offs to the user.

## Decision tree

1. **Probe first** (use the `video-probe` skill). Surface anything tricky
   (VFR, HDR, rotation, multi-audio) before proposing a command.
2. **Choose mode**:
   - `--mode stream` (default): pipe rawvideo through Python; restorer
     contract is `restore(np.ndarray) -> np.ndarray`.
   - `--mode disk`: PNG round-trip; restorer contract is
     `restore(src: Path, dst: Path) -> None`.  Use this when the
     restorer (older GFPGAN, BasicSR, etc.) wants file paths.
3. **Choose encoder**:
   - 8-bit SDR + CPU: `libx264` `-preset slow -crf 20 -tune film`
   - 10/12-bit OR HDR: `libx265` (bit depth + HDR side-data preserved
     automatically via `hdr_x265_params(info.video)`)
   - GPU available: pass `--hwaccel nvidia | intel | amd | videotoolbox`
4. **Long input?** (> ~10 min): pass `--chunk-seconds 60` so each chunk
   is processed independently and stitched with `-c copy` (no re-encode
   at the seam, no memory blow-up).

## Canonical command

```bash
python -m scripts.rfv_pipeline \
    --input  ugly.mp4 \
    --output pretty.mp4 \
    --restorer my_models.gfpgan:restore_array \
    --crf 19 --preset slower --tune film \
    --hwaccel nvidia          # if available
```

## Wiring up an existing `restore_face(frame_path)`

The legacy contract (returns ndarray | bytes | path from a path) is
adapted by `restore_stub.adapt_legacy_restore_face`:

```python
# my_pkg/restorer.py
from scripts.rfv_pipeline.restore_stub import adapt_legacy_restore_face
from gfpgan_app import restore_face          # legacy function

restore_disk = adapt_legacy_restore_face(restore_face)
```

Then point the CLI at it:

```bash
python -m scripts.rfv_pipeline -i in.mp4 -o out.mp4 \
    --mode disk --restorer my_pkg.restorer:restore_disk
```

## Smoke-test before a real run

```bash
# Identity restorer = no AI, just verifies the FFmpeg pipe end-to-end
python -m scripts.rfv_pipeline -i sample.mp4 -o sample_passthrough.mp4 \
    --restorer scripts.rfv_pipeline.restore_stub:identity_array \
    --crf 18
```

If this does not produce a bit-perfect-looking copy with the same colour,
duration, audio sync, and rotation as the source, the FFmpeg side is
broken — fix that *before* turning on the AI pass.

## Reporting back

After a run, summarise: input geometry, output codec/encoder, CRF actually
used, runtime, output size, whether audio/metadata/rotation were
preserved (the pipeline always does this; reaffirm so the user trusts it).

## When NOT to use this skill

- Only audio needs work → use FFmpeg's audio filters, not this pipeline.
- The user just wants a single-image face restore → call the restorer
  directly; the pipeline overhead isn't worth it for one frame.
- The source is Dolby Vision Profile 8.1 (BL+EL+RPU) — no AI restoration
  pipeline survives DV 8.1 today; warn the user explicitly and either
  drop to Profile 5 (single-layer) with `dovi_tool` extracted RPU, or
  hand the file back.
