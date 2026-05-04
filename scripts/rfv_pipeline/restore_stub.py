"""Reference restorer implementations.

Two contracts are demonstrated; pick one and point ``--restorer`` at it.

Stream contract (pix in / pix out, used in ``mode=stream``):

    def my_restore(frame: np.ndarray) -> np.ndarray:
        # frame.shape == (H, W, 3); dtype is uint8 (8-bit src) or uint16 (>8-bit)
        ...
        return restored

Disk contract (paths in / paths out, used in ``mode=disk``):

    def my_restore(src: Path, dst: Path) -> None:
        # read PNG at src, restore, write PNG at dst (preserve bit depth)
        ...

The point of this stub: when wiring up a new restorer, run the pipeline
with ``--restorer rfv_pipeline.restore_stub:identity_array`` (or the disk
twin) first to confirm the FFmpeg side is plumbed correctly *before*
adding GPU/model failure modes to the debug surface.
"""
from __future__ import annotations

import shutil
from pathlib import Path


def identity_array(frame):                 # type: ignore[no-untyped-def]
    """Pass-through for the stream contract. Verifies pipe + colours."""
    return frame


def identity_disk(src: Path, dst: Path) -> None:
    """Pass-through for the disk contract. Just copies the PNG."""
    shutil.copyfile(src, dst)


def darken_array(frame, factor: float = 0.7):  # type: ignore[no-untyped-def]
    """Visibly modify the frame so you can confirm the result is your output
    and not the encoder accidentally muxing the source."""
    import numpy as np
    return (frame.astype(np.float32) * factor).clip(0, _max_for(frame)).astype(frame.dtype)


def _max_for(frame):                       # type: ignore[no-untyped-def]
    return 65535 if frame.dtype.itemsize == 2 else 255


# Example wrapper around a hypothetical user-provided ``restore_face(path)``
# function whose return type we don't know in advance.
def adapt_legacy_restore_face(restore_face):    # type: ignore[no-untyped-def]
    """Adapt a legacy ``restore_face(frame_path) -> ndarray | bytes | path``
    function to the disk contract used by the pipeline.

    Examples
    --------
    >>> from rfv_pipeline.restore_stub import adapt_legacy_restore_face
    >>> from gfpgan_app import restore_face
    >>> disk_fn = adapt_legacy_restore_face(restore_face)
    """
    from pathlib import Path as _P
    def _disk(src: _P, dst: _P) -> None:
        result = restore_face(str(src))
        if isinstance(result, (str, _P)):
            shutil.copyfile(result, dst)
            return
        if isinstance(result, (bytes, bytearray)):
            dst.write_bytes(bytes(result))
            return
        # numpy array fallback
        import imageio.v3 as iio
        iio.imwrite(dst, result)
    return _disk
