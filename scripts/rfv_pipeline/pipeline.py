"""RFV pipeline: probe → extract → restore → mux.

Two extraction modes are exposed:

* **stream** (default): ``ffmpeg -f rawvideo`` on stdout pipes straight into
  Python; each frame is handed to the restorer and its result is pushed into
  a second ffmpeg writing the final encode. Zero PNG round-trips, zero disk.

* **disk**: PNG (8-bit ``rgb24``) or PNG-16 (``rgb48be``) per frame; useful
  when the restorer insists on a path on disk, when you want to inspect
  intermediate frames, or when the source is VFR and we need explicit
  per-frame durations to rebuild it via the concat demuxer.

Audio, container metadata, and rotation are *never* re-encoded. They are
extracted to a sidecar file once, then muxed onto the final video as a
last copy-only step (``-c:a copy -map_metadata 0``). This is the single
biggest difference between a "naive" pipeline and one that survives
contact with real-world footage.

For long inputs you can opt into chunked processing
(``PipelineConfig.chunk_seconds``); we then split with the segment muxer at
keyframe boundaries, process each chunk independently, and stitch with the
concat demuxer using ``-c copy`` (no re-encode at the seam).
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .ffmpeg_runner import (
    FFmpegError,
    Progress,
    ffmpeg_bin,
    run,
    spawn,
    wait,
    write_concat_list,
)
from .probe import MediaInfo, VideoInfo, probe

log = logging.getLogger("rfv.pipeline")

# Function the user supplies. Two contracts are accepted:
#   1. (src_path: Path, dst_path: Path) -> None    [disk mode]
#   2. (frame: np.ndarray)              -> np.ndarray  [stream mode]
# Both are wrapped behind a uniform .restore() call below.
RestoreDiskFn = Callable[[Path, Path], None]
RestoreArrayFn = Callable[["np.ndarray"], "np.ndarray"]  # type: ignore[name-defined]


@dataclass
class PipelineConfig:
    input: Path
    output: Path
    crf: int = 20
    encoder: str = "auto"          # auto / libx264 / libx265 / h264_nvenc / ...
    preset: str = "slow"           # libx26x: veryslow..ultrafast; nvenc: p1..p7
    tune: Optional[str] = "film"   # film / animation / grain / fastdecode / None
    hwaccel: Optional[str] = None  # nvidia / intel / amd / videotoolbox
    keep_audio: bool = True
    chunk_seconds: float = 0.0     # 0 disables chunking
    work_dir: Optional[Path] = None
    mode: str = "stream"           # stream | disk
    container: Optional[str] = None  # auto from output suffix
    pix_fmt_out: Optional[str] = None  # auto from input bit depth
    dry_run: bool = False
    extra_x264_params: dict = field(default_factory=dict)
    extra_x265_params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Encoder / pix_fmt selection
# ---------------------------------------------------------------------------

# What the source's pix_fmt should become for processing in numpy and what
# the output container should encode as. Keys are *families* — anything that
# starts with ``yuv420p`` matches "yuv420p", etc.
_PIX_FMT_PROCESSING = {
    8:  "rgb24",       # 3 bytes per pixel
    10: "rgb48le",     # 6 bytes per pixel; valid range is 0..1023 << 6
    12: "rgb48le",
    16: "rgb48le",
}


def pick_encoder(cfg: PipelineConfig, info: VideoInfo) -> str:
    """Resolve ``encoder=auto`` based on source bit depth and hwaccel choice."""
    if cfg.encoder != "auto":
        return cfg.encoder
    if cfg.hwaccel == "nvidia":
        return "hevc_nvenc" if info.bit_depth >= 10 or info.is_hdr else "h264_nvenc"
    if cfg.hwaccel == "intel":
        return "hevc_qsv" if info.bit_depth >= 10 or info.is_hdr else "h264_qsv"
    if cfg.hwaccel == "amd":
        return "hevc_vaapi" if info.bit_depth >= 10 or info.is_hdr else "h264_vaapi"
    if cfg.hwaccel == "videotoolbox":
        return "hevc_videotoolbox" if info.bit_depth >= 10 else "h264_videotoolbox"
    # Software fallback. HDR / 10-bit must use libx265 (libx264 only carries
    # 10-bit if compiled with --bit-depth=10, which most distros don't).
    return "libx265" if info.bit_depth >= 10 or info.is_hdr else "libx264"


def pick_output_pix_fmt(cfg: PipelineConfig, info: VideoInfo, encoder: str) -> str:
    if cfg.pix_fmt_out:
        return cfg.pix_fmt_out
    # Honour source chroma layout where the encoder allows it. We deliberately
    # do NOT silently downsample yuv444 → yuv420.
    if encoder.startswith(("h264_", "hevc_")) and "nvenc" in encoder:
        return "p010le" if info.bit_depth >= 10 else "yuv420p"  # nvenc = 4:2:0
    if encoder.endswith("_qsv"):
        return "p010le" if info.bit_depth >= 10 else "nv12"
    if encoder.endswith("_vaapi"):
        return "p010le" if info.bit_depth >= 10 else "nv12"
    if encoder == "libx265":
        if "yuv444" in info.pix_fmt:
            return "yuv444p10le" if info.bit_depth >= 10 else "yuv444p"
        if "yuv422" in info.pix_fmt:
            return "yuv422p10le" if info.bit_depth >= 10 else "yuv422p"
        return "yuv420p10le" if info.bit_depth >= 10 else "yuv420p"
    # libx264
    if "yuv444" in info.pix_fmt:
        return "yuv444p"
    if "yuv422" in info.pix_fmt:
        return "yuv422p"
    return "yuv420p"


def color_args(info: VideoInfo) -> list[str]:
    """Tag the output stream with the same colour metadata as the source.

    Without these flags ffmpeg writes zeros and players guess (most assume
    BT.709 limited, which silently mangles BT.601 SD content and any HDR
    grade). They also have to match the actual pixel data — we never *change*
    the colour space, only annotate what the encoder is producing.
    """
    out = [
        "-color_range", info.color_range,
        "-colorspace", info.color_space,
        "-color_primaries", info.color_primaries,
        "-color_trc", info.color_transfer,
    ]
    return out


def hdr_x265_params(info: VideoInfo) -> str:
    """Stitch HDR10 metadata into an -x265-params blob.

    Master display + max-cll come from the source side_data when present;
    otherwise we emit only the static colour-volume tags so HDR10 players
    still pick the file up correctly.
    """
    parts = [
        "colorprim=" + info.color_primaries,
        "transfer=" + info.color_transfer,
        "colormatrix=" + info.color_space,
        "range=" + ("full" if info.color_range == "pc" else "limited"),
        "hdr-opt=1",
        "repeat-headers=1",
    ]
    for sd in info.raw.get("side_data_list", []) or []:
        sdt = sd.get("side_data_type", "")
        if sdt == "Mastering display metadata":
            md = (
                f"G({sd.get('green_x',0)},{sd.get('green_y',0)})"
                f"B({sd.get('blue_x',0)},{sd.get('blue_y',0)})"
                f"R({sd.get('red_x',0)},{sd.get('red_y',0)})"
                f"WP({sd.get('white_point_x',0)},{sd.get('white_point_y',0)})"
                f"L({sd.get('max_luminance',10000000)},{sd.get('min_luminance',1)})"
            )
            parts.append("master-display=" + md)
        elif sdt == "Content light level metadata":
            parts.append(f"max-cll={sd.get('max_content',1000)},{sd.get('max_average',400)}")
    return ":".join(parts)


# ---------------------------------------------------------------------------
# Decoder / encoder argv builders
# ---------------------------------------------------------------------------

def decoder_args(info: MediaInfo, cfg: PipelineConfig, *, for_pipe: bool) -> list[str]:
    """ffmpeg argv that *produces* either rawvideo on stdout or PNG on disk.

    HW-accelerated decode is only useful when we're keeping frames on the
    GPU (i.e. encoder is also HW). For the pipe-to-Python case we explicitly
    download to system memory by NOT passing ``-hwaccel_output_format``.
    """
    args: list[str] = []
    if cfg.hwaccel == "nvidia":
        args += ["-hwaccel", "cuda"]
    elif cfg.hwaccel == "intel":
        args += ["-hwaccel", "qsv"]
    elif cfg.hwaccel == "amd":
        args += ["-hwaccel", "vaapi", "-hwaccel_device", "/dev/dri/renderD128"]
    elif cfg.hwaccel == "videotoolbox":
        args += ["-hwaccel", "videotoolbox"]
    args += ["-i", str(info.path)]
    if for_pipe:
        # ``passthrough`` keeps source PTS/duration even for VFR; ``cfr``
        # would silently duplicate or drop frames to hit a constant rate.
        args += ["-map", "0:v:0", "-fps_mode", "passthrough"]
    return args


def stream_decoder_cmd(info: MediaInfo, cfg: PipelineConfig, processing_pix_fmt: str) -> list[str]:
    """Decoder in pipe-mode: emits headerless rawvideo on stdout."""
    return [
        ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error",
        *decoder_args(info, cfg, for_pipe=True),
        "-f", "rawvideo",
        "-pix_fmt", processing_pix_fmt,
        "pipe:1",
    ]


def stream_encoder_cmd(
    info: MediaInfo,
    cfg: PipelineConfig,
    processing_pix_fmt: str,
    output: Path,
    *,
    encoder: str,
    pix_fmt_out: str,
) -> list[str]:
    """Encoder in pipe-mode: consumes rawvideo from stdin, writes container.

    Audio is *not* attached here — that happens in :func:`mux_audio` afterwards
    so we never re-touch the bitstream. Keeps the encoder single-input and
    avoids the ``-shortest`` foot-gun.
    """
    v = info.video
    width, height = v.width, v.height
    fps_arg = str(v.avg_fps) if v.avg_fps else "30"

    cmd: list[str] = [
        ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        # Raw input description — must mirror the decoder's pix_fmt and
        # geometry exactly, otherwise the encoder reads garbage.
        "-f", "rawvideo",
        "-pix_fmt", processing_pix_fmt,
        "-video_size", f"{width}x{height}",
        "-framerate", fps_arg,
        "-i", "pipe:0",
        "-an",                       # explicitly no audio at this stage
        "-pix_fmt", pix_fmt_out,
    ]

    cmd += color_args(v)
    cmd += _encoder_quality_args(cfg, encoder, v)

    # Rotation: re-emit display matrix so players know what to do. The new
    # ``-display_rotation`` was added in FFmpeg 7.0 and is the only future-
    # proof way; older builds fall back to the deprecated metadata tag.
    if v.rotation:
        cmd += ["-display_rotation:v:0", str((-v.rotation) % 360)]

    # ``+faststart`` moves the moov atom to the start of the file so
    # players can begin streaming without seeking. Only meaningful for MP4.
    if output.suffix.lower() in {".mp4", ".m4v", ".mov"}:
        cmd += ["-movflags", "+faststart"]

    cmd.append(str(output))
    return cmd


def _encoder_quality_args(cfg: PipelineConfig, encoder: str, v: VideoInfo) -> list[str]:
    """Quality knobs that differ wildly between encoders."""
    args: list[str] = ["-c:v", encoder]
    if encoder in {"libx264", "libx265"}:
        args += ["-preset", cfg.preset, "-crf", str(cfg.crf)]
        if cfg.tune:
            args += ["-tune", cfg.tune]
        if encoder == "libx265" and (v.is_hdr or v.bit_depth >= 10):
            args += ["-x265-params", hdr_x265_params(v)]
    elif encoder.endswith("_nvenc"):
        # NVENC has no CRF; ``-rc vbr -cq N`` is the closest perceptual
        # equivalent. ``p7`` is the slowest/highest-quality preset on
        # modern drivers; ``hq`` tune optimises for SSIM over speed.
        args += [
            "-preset", cfg.preset if cfg.preset.startswith("p") else "p7",
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", str(cfg.crf),
            "-b:v", "0",          # CQ-only; let the encoder decide bitrate
            "-spatial-aq", "1",
            "-temporal-aq", "1",
        ]
    elif encoder.endswith("_qsv"):
        args += ["-preset", "veryslow", "-global_quality", str(cfg.crf), "-look_ahead", "1"]
    elif encoder.endswith("_vaapi"):
        # VAAPI uses QP, not CRF; map approximately.
        args += ["-qp", str(cfg.crf), "-quality", "1"]
    elif encoder.endswith("_videotoolbox"):
        # VideoToolbox quality is 0..100; map roughly inverse of CRF.
        q = max(0, min(100, int((51 - cfg.crf) * 2)))
        args += ["-q:v", str(q)]
    else:
        args += ["-crf", str(cfg.crf)]
    return args


# ---------------------------------------------------------------------------
# Audio / metadata mux
# ---------------------------------------------------------------------------

def extract_audio(info: MediaInfo, work_dir: Path) -> Optional[Path]:
    """Pull audio bitstream into a sidecar container without re-encoding."""
    if not info.has_audio:
        return None
    # ``.mka`` (Matroska Audio) tolerates virtually any codec; using the
    # container's native one is risky if the input is ``.mp4`` with PCM
    # audio (MP4 + raw PCM is illegal).
    out = work_dir / "audio.mka"
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        "-i", str(info.path),
        "-map", "0:a",
        "-c:a", "copy",
        str(out),
    ]
    run(cmd)
    return out


def mux_audio(
    video_only: Path,
    audio: Optional[Path],
    info: MediaInfo,
    output: Path,
) -> None:
    """Final remux: video stream from our encoded file, audio from sidecar.

    ``-map_metadata 0`` copies container-level tags (title, creation_time,
    GPS, etc.); ``-map_metadata:s:v 0:s:v 0`` copies stream-level video
    tags. Both are no-ops on streams we omitted, and they're cheap.
    """
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        "-i", str(video_only),
    ]
    if audio is not None:
        cmd += ["-i", str(audio)]
    # Carry container metadata from the *original* file, not the video-only
    # intermediate. The original is the third (or second) input.
    cmd += ["-i", str(info.path)]
    src_idx = 2 if audio is not None else 1
    cmd += [
        "-map", "0:v:0",
    ]
    if audio is not None:
        cmd += ["-map", "1:a"]
    cmd += [
        "-c:v", "copy",
        "-c:a", "copy",
        f"-map_metadata", str(src_idx),
        f"-map_metadata:s:v:0", f"{src_idx}:s:v:0",
    ]
    if output.suffix.lower() in {".mp4", ".m4v", ".mov"}:
        cmd += ["-movflags", "+faststart"]
    cmd.append(str(output))
    run(cmd)


# ---------------------------------------------------------------------------
# Stream-mode pipeline
# ---------------------------------------------------------------------------

class RFVPipeline:
    def __init__(
        self,
        config: PipelineConfig,
        restore_array: Optional[RestoreArrayFn] = None,
        restore_disk: Optional[RestoreDiskFn] = None,
        on_progress: Optional[Callable[[Progress], None]] = None,
    ):
        if not (restore_array or restore_disk):
            raise ValueError("supply restore_array= or restore_disk=")
        self.cfg = config
        self.restore_array = restore_array
        self.restore_disk = restore_disk
        self.on_progress = on_progress

    # -- public entrypoint -------------------------------------------------

    def run(self) -> None:
        info = probe(self.cfg.input)
        log.info(
            "input: %dx%d %s %d-bit %s avg_fps=%s vfr=%s hdr=%s rot=%d audio=%d",
            info.video.width, info.video.height, info.video.codec,
            info.video.bit_depth, info.video.pix_fmt, info.video.avg_fps,
            info.video.is_vfr, info.video.is_hdr, info.video.rotation,
            len(info.audio),
        )

        if self.cfg.dry_run:
            self._dry_run(info)
            return

        with self._work_dir() as wd:
            audio = extract_audio(info, wd) if (self.cfg.keep_audio and info.has_audio) else None

            if self.cfg.chunk_seconds > 0 and info.video.duration and \
                    info.video.duration > self.cfg.chunk_seconds * 1.5:
                self._run_chunked(info, wd, audio)
            else:
                video_only = wd / "restored_video.mkv"
                if self.cfg.mode == "stream":
                    self._run_stream(info, video_only)
                else:
                    self._run_disk(info, wd, video_only)
                mux_audio(video_only, audio, info, self.cfg.output)

    # -- mode implementations ---------------------------------------------

    def _run_stream(self, info: MediaInfo, output: Path) -> None:
        try:
            import numpy as np  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("stream mode needs numpy") from exc
        if self.restore_array is None:
            raise RuntimeError("stream mode needs restore_array=; use mode='disk' instead")

        v = info.video
        proc_pix = _PIX_FMT_PROCESSING[v.bit_depth if v.bit_depth in _PIX_FMT_PROCESSING else 8]
        encoder = pick_encoder(self.cfg, v)
        out_pix = pick_output_pix_fmt(self.cfg, v, encoder)
        log.info("stream mode: proc=%s enc=%s out_pix=%s", proc_pix, encoder, out_pix)

        dec_cmd = stream_decoder_cmd(info, self.cfg, proc_pix)
        enc_cmd = stream_encoder_cmd(
            info, self.cfg, proc_pix, output, encoder=encoder, pix_fmt_out=out_pix,
        )

        decoder = spawn(dec_cmd, stdout=subprocess.PIPE)
        encoder_p = spawn(
            enc_cmd, stdin=subprocess.PIPE,
            on_progress=self.on_progress,
        )
        try:
            self._pump_frames(decoder, encoder_p, v, proc_pix)
        finally:
            try: encoder_p.stdin and encoder_p.stdin.close()
            except Exception: pass
            wait(encoder_p)
            wait(decoder)

    def _pump_frames(self, decoder, encoder_p, v: VideoInfo, proc_pix: str) -> None:
        import numpy as np
        bytes_per_pixel = 6 if proc_pix == "rgb48le" else 3
        frame_bytes = v.width * v.height * bytes_per_pixel
        dtype = np.uint16 if proc_pix == "rgb48le" else np.uint8
        idx = 0
        # We deliberately read in single-frame chunks. Reading multi-frame
        # buffers would slightly improve throughput but breaks ordering
        # guarantees once the restorer is parallelised.
        while True:
            buf = decoder.stdout.read(frame_bytes)
            if not buf or len(buf) < frame_bytes:
                break
            frame = np.frombuffer(buf, dtype=dtype).reshape(v.height, v.width, 3)
            restored = self.restore_array(frame)  # type: ignore[misc]
            if restored.dtype != dtype or restored.shape != frame.shape:
                raise RuntimeError(
                    f"restorer must return {frame.shape} {dtype}, got "
                    f"{restored.shape} {restored.dtype}"
                )
            try:
                encoder_p.stdin.write(restored.tobytes())
            except BrokenPipeError as exc:
                raise FFmpegError(
                    encoder_p.poll() or -1,
                    b"".join(getattr(encoder_p, "_rfv_stderr", [])).decode("utf-8", "replace"),
                    getattr(encoder_p, "_rfv_cmd", []),
                ) from exc
            idx += 1
        log.info("stream mode: pumped %d frames", idx)

    def _run_disk(self, info: MediaInfo, wd: Path, output: Path) -> None:
        if self.restore_disk is None:
            raise RuntimeError("disk mode needs restore_disk=")
        v = info.video
        frames_in = wd / "frames_in"
        frames_out = wd / "frames_out"
        frames_in.mkdir(); frames_out.mkdir()

        # PNG-16 only when source actually carries >8-bit data, otherwise
        # PNG-8: 16-bit PNGs are ~2× the size and most restorer models cast
        # back to uint8 anyway.
        png_pix = "rgb48be" if v.bit_depth > 8 else "rgb24"
        # ``-vsync passthrough`` (alias for ``-fps_mode passthrough``) keeps
        # source PTS so we can rebuild VFR timing on the way back.
        cmd = [
            ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            *decoder_args(info, self.cfg, for_pipe=True),
            "-pix_fmt", png_pix,
            # PNG predictor=mixed is small + fast; compression 1 is much
            # faster than 9 with ~10% larger files. Frame extraction is
            # I/O bound so the trade is usually worth it.
            "-pred", "mixed",
            "-compression_level", "1",
            "-start_number", "0",
            str(frames_in / "f_%08d.png"),
        ]
        run(cmd, on_progress=self.on_progress)

        frames = sorted(frames_in.iterdir())
        log.info("disk mode: extracted %d frames as %s", len(frames), png_pix)
        for f in frames:
            out_path = frames_out / f.name
            self.restore_disk(f, out_path)  # type: ignore[misc]

        self._encode_disk_frames(info, frames_out, output, png_pix)

    def _encode_disk_frames(
        self, info: MediaInfo, frames_dir: Path, output: Path, png_pix: str,
    ) -> None:
        v = info.video
        encoder = pick_encoder(self.cfg, v)
        out_pix = pick_output_pix_fmt(self.cfg, v, encoder)

        # For VFR sources we have to mux through the concat demuxer with
        # explicit per-frame durations; for CFR the image2 demuxer + a
        # single ``-framerate`` flag is enough and ~3× faster.
        if v.is_vfr:
            from .probe import dump_pts
            pts = dump_pts(info.path)
            files = sorted(frames_dir.iterdir())
            if len(pts) != len(files):
                log.warning(
                    "VFR PTS count (%d) != frame count (%d); using avg_fps fallback",
                    len(pts), len(files),
                )
                pts = [i / float(v.avg_fps or 30) for i in range(len(files))]
            durations = [pts[i + 1] - pts[i] for i in range(len(pts) - 1)]
            durations.append(durations[-1] if durations else 1 / float(v.avg_fps or 30))
            concat_path = frames_dir.parent / "frames.ffconcat"
            write_concat_list(concat_path, list(zip(files, durations)))
            input_args = ["-f", "concat", "-safe", "0", "-i", str(concat_path)]
        else:
            input_args = [
                "-framerate", str(v.avg_fps),
                "-start_number", "0",
                "-i", str(frames_dir / "f_%08d.png"),
            ]

        cmd = [
            ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            *input_args,
            "-an",
            "-pix_fmt", out_pix,
            *color_args(v),
            *_encoder_quality_args(self.cfg, encoder, v),
        ]
        if v.rotation:
            cmd += ["-display_rotation:v:0", str((-v.rotation) % 360)]
        if output.suffix.lower() in {".mp4", ".m4v", ".mov"}:
            cmd += ["-movflags", "+faststart"]
        cmd.append(str(output))
        run(cmd, on_progress=self.on_progress)

    # -- chunked path ------------------------------------------------------

    def _run_chunked(self, info: MediaInfo, wd: Path, audio: Optional[Path]) -> None:
        """Split → process per-chunk → concat with -c copy.

        We split with the segment muxer at *keyframe* boundaries
        (``-reset_timestamps 1`` + ``-force_key_frames`` is more invasive,
        so we don't force keyframes on the source — we just live with the
        nearest one and accept slightly varied chunk lengths). The concat
        step uses ``-c copy`` so no re-encode happens at the seam.
        """
        chunks_in = wd / "chunks_in"
        chunks_out = wd / "chunks_out"
        chunks_in.mkdir(); chunks_out.mkdir()

        # 1. split
        run([
            ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-i", str(info.path),
            "-map", "0:v:0",
            "-c:v", "copy",
            "-f", "segment",
            "-segment_time", str(self.cfg.chunk_seconds),
            "-reset_timestamps", "1",
            str(chunks_in / "chunk_%05d.mkv"),
        ])

        # 2. process each chunk independently
        chunk_files = sorted(chunks_in.iterdir())
        log.info("chunked mode: %d chunks of ~%ss", len(chunk_files), self.cfg.chunk_seconds)
        sub_cfg = PipelineConfig(**{**self.cfg.__dict__, "chunk_seconds": 0.0,
                                    "keep_audio": False})
        for cf in chunk_files:
            sub_cfg.input = cf
            sub_cfg.output = chunks_out / cf.name
            sub_pipe = RFVPipeline(
                sub_cfg,
                restore_array=self.restore_array,
                restore_disk=self.restore_disk,
                on_progress=self.on_progress,
            )
            sub_pipe.run()

        # 3. concat with copy
        list_path = wd / "concat.txt"
        write_concat_list(list_path, [(p, None) for p in sorted(chunks_out.iterdir())])
        merged = wd / "merged.mkv"
        run([
            ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-c", "copy",
            str(merged),
        ])
        mux_audio(merged, audio, info, self.cfg.output)

    # -- helpers -----------------------------------------------------------

    def _work_dir(self):
        if self.cfg.work_dir:
            self.cfg.work_dir.mkdir(parents=True, exist_ok=True)
            return _NoCleanup(self.cfg.work_dir)
        return tempfile.TemporaryDirectory(prefix="rfv_")

    def _dry_run(self, info: MediaInfo) -> None:
        v = info.video
        proc_pix = _PIX_FMT_PROCESSING.get(v.bit_depth, "rgb24")
        encoder = pick_encoder(self.cfg, v)
        out_pix = pick_output_pix_fmt(self.cfg, v, encoder)
        if self.cfg.mode == "stream":
            print("# decoder")
            print(" \\\n  ".join(stream_decoder_cmd(info, self.cfg, proc_pix)))
            print("\n# encoder")
            print(" \\\n  ".join(stream_encoder_cmd(
                info, self.cfg, proc_pix, self.cfg.output,
                encoder=encoder, pix_fmt_out=out_pix,
            )))
        else:
            print("# disk-mode commands omitted (frame paths depend on extraction)")
        print("\n# audio sidecar")
        print(f"# {extract_audio.__module__}.{extract_audio.__name__}(info, work_dir)")


class _NoCleanup:
    def __init__(self, path: Path):
        self.path = path
    def __enter__(self) -> Path:
        return self.path
    def __exit__(self, *_):
        return False
