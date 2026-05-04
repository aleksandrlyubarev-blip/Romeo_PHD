"""Real-world Face Video restoration pipeline (FFmpeg + AI restorer)."""
from .ffmpeg_runner import FFmpegError, Progress, ffmpeg_bin, run, spawn, wait
from .pipeline import (
    PipelineConfig,
    RFVPipeline,
    color_args,
    extract_audio,
    hdr_x265_params,
    mux_audio,
    pick_encoder,
    pick_output_pix_fmt,
    stream_decoder_cmd,
    stream_encoder_cmd,
)
from .probe import (
    AudioInfo,
    MediaInfo,
    ProbeError,
    VideoInfo,
    detect_vfr_strict,
    dump_pts,
    probe,
)

__all__ = [
    "AudioInfo", "MediaInfo", "ProbeError", "VideoInfo",
    "detect_vfr_strict", "dump_pts", "probe",
    "FFmpegError", "Progress", "ffmpeg_bin", "run", "spawn", "wait",
    "PipelineConfig", "RFVPipeline",
    "color_args", "extract_audio", "hdr_x265_params", "mux_audio",
    "pick_encoder", "pick_output_pix_fmt",
    "stream_decoder_cmd", "stream_encoder_cmd",
]
