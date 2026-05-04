"""Thin Popen wrapper for ffmpeg.

Two patterns are supported:

* :func:`run`           — fire and forget, used for quick ops (audio extract,
                          mux, concat). Streams stderr through a pump thread
                          so the parent doesn't block when ffmpeg writes its
                          chatty status output, and consumes the dedicated
                          ``-progress pipe:N`` channel separately so binary
                          stdout (rawvideo) stays uncorrupted.
* :func:`spawn`         — returns a live ``subprocess.Popen`` for chaining
                          decoder ↔ Python ↔ encoder via OS pipes. Stderr
                          and progress are still drained by background
                          threads so the producer never blocks on a full
                          stderr buffer (this is the classic deadlock that
                          bites every ffmpeg-pipe pipeline).

Why a custom progress FD instead of parsing stderr?
ffmpeg's stderr format is not stable across versions and contains both
warnings ("Past duration ... too large") and the live status line on the
same stream. ``-progress pipe:N`` is machine-readable, stable, and emits
``progress=end`` exactly once at clean shutdown — perfect for tqdm.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

log = logging.getLogger("rfv.ffmpeg")


def ffmpeg_bin() -> str:
    exe = os.environ.get("RFV_FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError(
            "ffmpeg not found; install it or set the RFV_FFMPEG env var"
        )
    return exe


@dataclass
class Progress:
    frame: int = 0
    fps: float = 0.0
    out_time_us: int = 0
    bitrate: str = ""
    speed: float = 0.0
    total_size: int = 0
    progress: str = "continue"   # "continue" | "end"

    @property
    def out_time_s(self) -> float:
        return self.out_time_us / 1_000_000


_PROGRESS_RE = re.compile(r"^([a-z_]+)=(.*)$")


def _pump_progress(fp, on_progress: Callable[[Progress], None]) -> None:
    p = Progress()
    try:
        for raw in fp:
            line = raw.decode("utf-8", "replace").strip()
            m = _PROGRESS_RE.match(line)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            if key == "frame" and val.isdigit():
                p.frame = int(val)
            elif key == "fps":
                try: p.fps = float(val)
                except ValueError: pass
            elif key == "out_time_us" and val.lstrip("-").isdigit():
                p.out_time_us = int(val)
            elif key == "bitrate":
                p.bitrate = val
            elif key == "speed":
                try: p.speed = float(val.rstrip("x"))
                except ValueError: pass
            elif key == "total_size" and val.isdigit():
                p.total_size = int(val)
            elif key == "progress":
                p.progress = val
                try:
                    on_progress(p)
                except Exception:                # never let callbacks kill us
                    log.exception("progress callback raised")
                if val == "end":
                    break
    finally:
        try: fp.close()
        except Exception: pass


def _pump_stderr(fp, sink: list[bytes], echo: bool) -> None:
    try:
        for chunk in iter(lambda: fp.read(8192), b""):
            sink.append(chunk)
            if echo:
                try: os.write(2, chunk)
                except OSError: pass
    finally:
        try: fp.close()
        except Exception: pass


class FFmpegError(RuntimeError):
    def __init__(self, returncode: int, stderr: str, cmd: list[str]):
        self.returncode = returncode
        self.stderr = stderr
        self.cmd = cmd
        tail = stderr.strip().splitlines()[-1] if stderr.strip() else "<no stderr>"
        super().__init__(f"ffmpeg failed ({returncode}): {tail}")


def _inject_progress(cmd: list[str], fd: int) -> list[str]:
    """Insert -progress and -nostats right after the binary, before -i."""
    head, tail = cmd[:1], cmd[1:]
    # -hide_banner / -nostdin / -y are global and stay where they are; we just
    # add the progress flags before the first input/output spec.
    return head + ["-progress", f"pipe:{fd}", "-nostats"] + tail


def run(
    cmd: list[str],
    *,
    on_progress: Optional[Callable[[Progress], None]] = None,
    echo_stderr: bool = False,
) -> None:
    """Run ffmpeg to completion, raising :class:`FFmpegError` on non-zero exit."""
    progress_r = progress_w = None
    if on_progress is not None:
        progress_r, progress_w = os.pipe()
        cmd = _inject_progress(cmd, progress_w)

    log.debug("ffmpeg run: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        pass_fds=(progress_w,) if progress_w is not None else (),
        close_fds=True,
    )
    if progress_w is not None:
        os.close(progress_w)

    err_buf: list[bytes] = []
    t_err = threading.Thread(
        target=_pump_stderr, args=(proc.stderr, err_buf, echo_stderr), daemon=True
    )
    t_err.start()
    t_prog = None
    if progress_r is not None:
        t_prog = threading.Thread(
            target=_pump_progress,
            args=(os.fdopen(progress_r, "rb", buffering=0), on_progress),
            daemon=True,
        )
        t_prog.start()

    rc = proc.wait()
    t_err.join(timeout=5)
    if t_prog is not None:
        t_prog.join(timeout=5)
    if rc != 0:
        raise FFmpegError(rc, b"".join(err_buf).decode("utf-8", "replace"), cmd)


def spawn(
    cmd: list[str],
    *,
    stdin: int | None = None,
    stdout: int | None = None,
    on_progress: Optional[Callable[[Progress], None]] = None,
    echo_stderr: bool = False,
) -> subprocess.Popen:
    """Start ffmpeg without waiting; caller manages the pipe.

    ``stdin``/``stdout`` follow Popen semantics (None → DEVNULL, ``PIPE``,
    or an int fd). Stderr is always captured by a pump thread and stored
    on ``proc._rfv_stderr`` for post-mortem inspection.
    """
    progress_r = progress_w = None
    if on_progress is not None:
        progress_r, progress_w = os.pipe()
        cmd = _inject_progress(cmd, progress_w)

    pass_fds: tuple[int, ...] = ()
    if progress_w is not None:
        pass_fds = (progress_w,)

    log.debug("ffmpeg spawn: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdin=stdin if stdin is not None else subprocess.DEVNULL,
        stdout=stdout if stdout is not None else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        pass_fds=pass_fds,
        close_fds=True,
    )
    if progress_w is not None:
        os.close(progress_w)

    err_buf: list[bytes] = []
    proc._rfv_stderr = err_buf  # type: ignore[attr-defined]
    proc._rfv_cmd = cmd          # type: ignore[attr-defined]
    threading.Thread(
        target=_pump_stderr, args=(proc.stderr, err_buf, echo_stderr), daemon=True
    ).start()
    if progress_r is not None:
        threading.Thread(
            target=_pump_progress,
            args=(os.fdopen(progress_r, "rb", buffering=0), on_progress),
            daemon=True,
        ).start()
    return proc


def wait(proc: subprocess.Popen) -> None:
    """Block until ``proc`` exits; raise :class:`FFmpegError` on failure."""
    rc = proc.wait()
    if rc != 0:
        stderr_bytes = b"".join(getattr(proc, "_rfv_stderr", []))
        raise FFmpegError(
            rc,
            stderr_bytes.decode("utf-8", "replace"),
            getattr(proc, "_rfv_cmd", []),
        )


def write_concat_list(path: Path, entries: Iterable[tuple[Path, Optional[float]]]) -> None:
    """Build a concat-demuxer list file.

    Each entry is ``(file_path, duration_seconds_or_None)``. Per the concat
    demuxer spec, ``duration`` lines are required when concatenating still
    images at varying intervals (i.e. our VFR-preserving frame mux), and
    the last entry must be repeated — otherwise its duration is dropped.
    """
    items = list(entries)
    lines = ["ffconcat version 1.0"]
    for fp, dur in items:
        # The path is single-quoted; the demuxer treats a leading backslash
        # as an escape, so an embedded apostrophe must be closed → escaped
        # → reopened.
        safe = str(fp).replace("'", r"'\''")
        lines.append(f"file '{safe}'")
        if dur is not None:
            lines.append(f"duration {dur:.9f}")
    if items:
        last_fp, _ = items[-1]
        safe_last = str(last_fp).replace("'", r"'\''")
        lines.append(f"file '{safe_last}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
