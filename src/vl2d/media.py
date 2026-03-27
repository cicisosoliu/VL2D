from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

from PIL import Image


class MediaError(RuntimeError):
    """Raised when ffmpeg or ffprobe fails."""


def _run_command(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore")
        raise MediaError(stderr or "media command failed") from exc


def extract_audio(video_path: Path, output_path: Path, sample_rate: int) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            str(output_path),
        ]
    )
    return output_path


def cut_audio_segment(audio_path: Path, output_path: Path, start_ms: int, end_ms: int) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_ms / 1000:.3f}",
            "-to",
            f"{end_ms / 1000:.3f}",
            "-i",
            str(audio_path),
            "-acodec",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path


def extract_frame(video_path: Path, output_path: Path, time_ms: int) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{time_ms / 1000:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(output_path),
        ]
    )
    return output_path


def crop_bottom_region(image_path: Path, output_path: Path, bottom_ratio: float) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        width, height = image.size
        top = int(height * max(0.0, min(1.0, 1.0 - bottom_ratio)))
        cropped = image.crop((0, top, width, height))
        cropped.save(output_path)
    return output_path


def probe_duration_ms(media_path: Path) -> int:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(media_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise MediaError("ffprobe failed") from exc

    payload = json.loads(result.stdout)
    duration = float(payload["format"]["duration"])
    return int(duration * 1000)


def wav_duration_ms(wav_path: Path) -> int:
    with wave.open(str(wav_path), "rb") as handle:
        frames = handle.getnframes()
        sample_rate = handle.getframerate()
    return int((frames / sample_rate) * 1000)

