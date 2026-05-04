"""CLI entry point for the RFV pipeline.

    python -m scripts.rfv_pipeline \\
        --input  input.mp4 \\
        --output restored.mp4 \\
        --restorer my_pkg.gfpgan:restore \\
        --crf 18 \\
        --hwaccel nvidia

The restorer is given as ``module.path:callable`` — the callable is
imported lazily so the CLI is usable without the heavy AI deps installed
(handy for ``--dry-run``).
"""
from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path
from typing import Callable

from .ffmpeg_runner import Progress
from .pipeline import PipelineConfig, RFVPipeline
from .probe import probe


def _load_restorer(spec: str) -> Callable:
    if ":" not in spec:
        raise SystemExit(f"--restorer must be 'module.path:callable', got {spec!r}")
    mod_name, attr = spec.split(":", 1)
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:
        raise SystemExit(f"can't import restorer module {mod_name!r}: {exc}") from exc
    try:
        return getattr(mod, attr)
    except AttributeError as exc:
        raise SystemExit(f"{mod_name!r} has no attribute {attr!r}") from exc


def _make_progress_printer():
    last_line = ""
    def cb(p: Progress):
        nonlocal last_line
        line = (
            f"\rframe={p.frame:>7}  "
            f"t={p.out_time_s:>8.2f}s  "
            f"fps={p.fps:>5.1f}  "
            f"speed={p.speed:>5.2f}x  "
            f"{p.bitrate}"
        )
        if line != last_line:
            sys.stderr.write(line)
            sys.stderr.flush()
            last_line = line
        if p.progress == "end":
            sys.stderr.write("\n")
    return cb


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rfv",
        description="Real-world Face Video restoration pipeline (ffmpeg + AI).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", "-i", type=Path, required=True, help="input video file")
    p.add_argument("--output", "-o", type=Path, required=True, help="output video file")
    p.add_argument(
        "--restorer", "-r",
        help="module path to the restorer callable, e.g. 'my_pkg.module:fn'. "
             "Receives (frame_ndarray) -> ndarray in stream mode, "
             "(src_path, dst_path) -> None in disk mode.",
    )
    p.add_argument(
        "--mode", choices=("stream", "disk"), default="stream",
        help="stream = pipe rawvideo through Python (no PNGs touch disk); "
             "disk = write PNGs and call disk-restorer on each",
    )
    p.add_argument("--crf", type=int, default=20,
                   help="quality, libx264/x265 scale (lower=better, 0=lossless)")
    p.add_argument(
        "--encoder", default="auto",
        help="auto / libx264 / libx265 / h264_nvenc / hevc_nvenc / h264_qsv / "
             "hevc_qsv / h264_vaapi / hevc_vaapi / h264_videotoolbox / hevc_videotoolbox",
    )
    p.add_argument("--preset", default="slow",
                   help="encoder preset; libx26x: veryslow..ultrafast; nvenc: p1..p7")
    p.add_argument("--tune", default="film",
                   help="libx26x tune (film/animation/grain/...); empty string disables")
    p.add_argument(
        "--hwaccel", choices=("nvidia", "intel", "amd", "videotoolbox"), default=None,
        help="enable hardware acceleration for decode + matching encoder",
    )
    p.add_argument("--no-audio", dest="keep_audio", action="store_false",
                   help="drop audio instead of copying it through")
    p.add_argument("--keep-audio", dest="keep_audio", action="store_true",
                   help="copy audio bitstream into the output (default)")
    p.set_defaults(keep_audio=True)
    p.add_argument("--chunk-seconds", type=float, default=0.0,
                   help="split into chunks of N seconds, process and concat; 0 = off")
    p.add_argument("--work-dir", type=Path, default=None,
                   help="persistent scratch dir (default: temp dir, auto-deleted)")
    p.add_argument("--pix-fmt-out", default=None,
                   help="override output pix_fmt (default: derived from source)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the resolved ffmpeg commands and exit")
    p.add_argument("--probe-only", action="store_true",
                   help="probe the input, print MediaInfo as JSON, and exit")
    p.add_argument("--verbose", "-v", action="count", default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING - 10 * min(args.verbose, 2),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if args.probe_only:
        info = probe(args.input)
        import dataclasses, json
        # Don't dump the full ffprobe payload — it's huge. Round-trip the
        # rest via dataclasses.asdict.
        d = dataclasses.asdict(info)
        d["video"].pop("raw", None)
        d.pop("raw", None)
        # Fraction is not JSON-serialisable; stringify.
        def default(o):
            return str(o)
        print(json.dumps(d, indent=2, default=default))
        return 0

    cfg = PipelineConfig(
        input=args.input,
        output=args.output,
        crf=args.crf,
        encoder=args.encoder,
        preset=args.preset,
        tune=args.tune or None,
        hwaccel=args.hwaccel,
        keep_audio=args.keep_audio,
        chunk_seconds=args.chunk_seconds,
        work_dir=args.work_dir,
        mode=args.mode,
        pix_fmt_out=args.pix_fmt_out,
        dry_run=args.dry_run,
    )

    restore_array = restore_disk = None
    if args.restorer:
        fn = _load_restorer(args.restorer)
        if args.mode == "stream":
            restore_array = fn
        else:
            restore_disk = fn
    elif not args.dry_run:
        raise SystemExit(
            "--restorer is required unless --dry-run is set. "
            "Use 'rfv_pipeline.restore_stub:identity_array' for a no-op test."
        )

    pipeline = RFVPipeline(
        cfg,
        restore_array=restore_array,
        restore_disk=restore_disk,
        on_progress=_make_progress_printer(),
    )
    pipeline.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
