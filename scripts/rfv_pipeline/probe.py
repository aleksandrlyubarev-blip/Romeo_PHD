"""ffprobe wrapper.

Probes everything we must know to reconstruct the file losslessly:

* geometry  — width/height/SAR/DAR + baked-in rotation (Display Matrix or
  legacy ``tags.rotate``)
* rate      — avg_frame_rate vs r_frame_rate, declared duration, declared
  nb_frames; cheap VFR heuristic from those, plus an opt-in strict check
* color     — pix_fmt, bit depth, range, primaries/transfer/matrix; HDR
  detection via SMPTE-2084 / HLG transfer or BT.2020 primaries
* audio     — every audio stream, codec, sample rate, channel layout
* tags      — container-level metadata so we can ``-map_metadata 0`` later

We deliberately keep the raw probe payload around so the encoder layer can
emit master-display / max-cll for HDR10 sources and so debugging never has
to re-shell ffprobe.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Optional

log = logging.getLogger("rfv.probe")


class ProbeError(RuntimeError):
    """ffprobe failed or returned something unparseable."""


@dataclass
class VideoInfo:
    width: int
    height: int
    sar: Fraction
    dar: Fraction
    rotation: int                   # degrees clockwise, baked into the file
    avg_fps: Fraction               # actual average fps over the file
    r_fps: Fraction                 # the rate the container declares
    nb_frames: Optional[int]
    duration: Optional[float]
    is_vfr: bool
    codec: str
    pix_fmt: str
    bit_depth: int
    color_range: str                # "tv" / "pc"
    color_space: str                # bt709 / bt2020nc / smpte170m / ...
    color_transfer: str             # bt709 / smpte2084 / arib-std-b67 / ...
    color_primaries: str            # bt709 / bt2020 / smpte170m / ...
    is_hdr: bool
    raw: dict = field(repr=False)


@dataclass
class AudioInfo:
    index: int
    codec: str
    sample_rate: int
    channels: int
    channel_layout: str


@dataclass
class MediaInfo:
    path: Path
    format_name: str
    duration: Optional[float]
    video: VideoInfo
    audio: list[AudioInfo]
    tags: dict
    raw: dict = field(repr=False)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio)


def _ffprobe_bin() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        raise ProbeError("ffprobe not found on PATH")
    return exe


def _frac(value: Optional[str], default: Fraction = Fraction(0)) -> Fraction:
    if not value or value in ("0/0", "N/A"):
        return default
    try:
        return Fraction(value)
    except (ZeroDivisionError, ValueError):
        return default


def _detect_rotation(stream: dict) -> int:
    """Return baked-in rotation in degrees clockwise.

    Two sources, in order of authority:
      1. Modern: side_data_list[].Display Matrix.rotation, in degrees CCW.
      2. Legacy: tags.rotate (MOV/MP4 only, deprecated since FFmpeg 7.0).
    """
    for sd in stream.get("side_data_list", []) or []:
        if sd.get("side_data_type") == "Display Matrix":
            try:
                ccw = float(sd.get("rotation", 0))
                return int(round(-ccw)) % 360
            except (TypeError, ValueError):
                continue
    tags = stream.get("tags") or {}
    if "rotate" in tags:
        try:
            return int(tags["rotate"]) % 360
        except ValueError:
            pass
    return 0


def _detect_bit_depth(stream: dict) -> int:
    bits = stream.get("bits_per_raw_sample") or stream.get("bits_per_coded_sample")
    if bits and str(bits).isdigit() and int(bits) > 0:
        return int(bits)
    pix_fmt = (stream.get("pix_fmt") or "").lower()
    # Order matters: "p16" must win over "p10".
    for token, depth in (("p16", 16), ("p14", 14), ("p12", 12), ("p10", 10),
                         ("64", 16), ("48", 16)):
        if token in pix_fmt:
            return depth
    return 8


def _is_hdr(stream: dict) -> bool:
    transfer = (stream.get("color_transfer") or "").lower()
    primaries = (stream.get("color_primaries") or "").lower()
    # PQ (HDR10/HDR10+/Dolby Vision profile 8) or HLG (broadcast HDR) or
    # plain BT.2020 wide-gamut SDR (still needs careful tagging on remux).
    return transfer in {"smpte2084", "arib-std-b67"} or primaries == "bt2020"


def probe(path: str | Path) -> MediaInfo:
    path = Path(path)
    if not path.exists():
        raise ProbeError(f"input not found: {path}")

    cmd = [
        _ffprobe_bin(),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        # We deliberately do NOT ask for packets here; that walks the whole
        # file and is unacceptable for hour-long inputs. VFR is checked
        # cheaply from avg vs r_frame_rate, with strict mode available below.
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        raise ProbeError(exc.stderr.decode("utf-8", "replace")) from exc
    except FileNotFoundError as exc:
        raise ProbeError(str(exc)) from exc

    data = json.loads(out)
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    v_streams = [s for s in streams if s.get("codec_type") == "video"]
    if not v_streams:
        raise ProbeError(f"no video stream in {path}")
    v = v_streams[0]
    a_streams = [s for s in streams if s.get("codec_type") == "audio"]

    width, height = int(v["width"]), int(v["height"])
    avg_fps = _frac(v.get("avg_frame_rate"))
    r_fps = _frac(v.get("r_frame_rate"))
    duration = float(v.get("duration") or fmt.get("duration") or 0) or None
    nb_frames = int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None

    sar = _frac(v.get("sample_aspect_ratio"), Fraction(1, 1))
    if sar == 0:
        sar = Fraction(1, 1)
    dar = _frac(v.get("display_aspect_ratio"), Fraction(width, height) * sar)

    is_vfr = False
    if avg_fps and r_fps and avg_fps != r_fps:
        # 1% tolerance — 23.976 vs 24 isn't VFR, it's just rounding.
        denom = max(float(r_fps), 1.0)
        if abs(float(avg_fps) - float(r_fps)) / denom > 0.01:
            is_vfr = True

    video = VideoInfo(
        width=width,
        height=height,
        sar=sar,
        dar=dar,
        rotation=_detect_rotation(v),
        avg_fps=avg_fps,
        r_fps=r_fps,
        nb_frames=nb_frames,
        duration=duration,
        is_vfr=is_vfr,
        codec=v.get("codec_name", "unknown"),
        pix_fmt=v.get("pix_fmt", "yuv420p"),
        bit_depth=_detect_bit_depth(v),
        color_range=v.get("color_range") or "tv",
        color_space=v.get("color_space") or "bt709",
        color_transfer=v.get("color_transfer") or "bt709",
        color_primaries=v.get("color_primaries") or "bt709",
        is_hdr=_is_hdr(v),
        raw=v,
    )

    audio = [
        AudioInfo(
            index=int(s.get("index", 0)),
            codec=s.get("codec_name", "unknown"),
            sample_rate=int(s.get("sample_rate") or 0),
            channels=int(s.get("channels") or 0),
            channel_layout=s.get("channel_layout") or "",
        )
        for s in a_streams
    ]

    return MediaInfo(
        path=path,
        format_name=fmt.get("format_name", ""),
        duration=float(fmt["duration"]) if "duration" in fmt else None,
        video=video,
        audio=audio,
        tags=fmt.get("tags", {}) or {},
        raw=data,
    )


def detect_vfr_strict(path: str | Path, max_packets: int = 5000) -> bool:
    """Walk up to ``max_packets`` packets and look at PTS deltas.

    Use this when the cheap heuristic in :func:`probe` is inconclusive — for
    example, screen-recorded MP4s often declare a sane r_frame_rate but
    actually deliver wildly varying frame durations.
    """
    cmd = [
        _ffprobe_bin(), "-v", "error",
        "-select_streams", "v:0",
        "-read_intervals", f"%+#{max_packets}",
        "-show_entries", "packet=pts_time",
        "-of", "csv=p=0",
        str(path),
    ]
    out = subprocess.check_output(cmd).decode().strip().splitlines()
    pts = sorted(float(x) for x in out if x)
    deltas = [round(pts[i + 1] - pts[i], 6) for i in range(len(pts) - 1)
              if pts[i + 1] > pts[i]]
    if len(deltas) < 3:
        return False
    avg = sum(deltas) / len(deltas)
    if avg <= 0:
        return False
    return (max(deltas) - min(deltas)) / avg > 0.05


def dump_pts(path: str | Path) -> list[float]:
    """Full per-frame PTS list. Expensive — only for chunk/concat assembly."""
    cmd = [
        _ffprobe_bin(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "frame=pts_time",
        "-of", "csv=p=0",
        str(path),
    ]
    raw = subprocess.check_output(cmd).decode().splitlines()
    return [float(x) for x in raw if x]
