from __future__ import annotations

from pathlib import Path


SUPPORTED_VIDEO_SUFFIXES = (".mp4", ".mov")


class VideoFormatError(ValueError):
    """Raised when VL2D receives an unsupported input video format."""


def supported_video_extensions_text() -> str:
    return "`.mp4` or `.mov`"


def validate_video_filename(filename: str | None) -> None:
    if not filename:
        raise VideoFormatError(
            f"missing video filename. VL2D supports {supported_video_extensions_text()} input files."
        )

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_VIDEO_SUFFIXES:
        raise VideoFormatError(
            f"unsupported video format '{suffix or '<none>'}'. VL2D supports {supported_video_extensions_text()} input files."
        )
