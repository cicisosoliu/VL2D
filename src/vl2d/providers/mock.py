from __future__ import annotations

import array
import math
import shutil
import wave
from pathlib import Path

from vl2d.config import Settings
from vl2d.domain import AudioArtifact, OCRObservation, SpeechSegment
from vl2d.media import wav_duration_ms
from vl2d.providers.base import EnhancerProvider, OCRProvider, VADProvider


class EnergyVADProvider(VADProvider):
    name = "energy_vad"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def detect(self, audio_path: Path, sample_rate: int) -> list[SpeechSegment]:
        with wave.open(str(audio_path), "rb") as handle:
            frame_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
            channels = handle.getnchannels()
            chunk_ms = 30
            frames_per_chunk = max(1, int(frame_rate * (chunk_ms / 1000)))
            raw = handle.readframes(handle.getnframes())

        frame_bytes = frames_per_chunk * sample_width * channels
        energies: list[int] = []
        for offset in range(0, len(raw), frame_bytes):
            chunk = raw[offset : offset + frame_bytes]
            if not chunk:
                continue
            energies.append(_rms(chunk, sample_width))

        if not energies:
            return []

        baseline = max(200, int(sum(energies) / len(energies) * 1.5))
        segments: list[SpeechSegment] = []
        active_start: int | None = None
        for index, energy in enumerate(energies):
            start_ms = index * chunk_ms
            end_ms = start_ms + chunk_ms
            if energy >= baseline and active_start is None:
                active_start = start_ms
            elif energy < baseline and active_start is not None:
                segments.append(SpeechSegment(start_ms=active_start, end_ms=end_ms))
                active_start = None
        if active_start is not None:
            segments.append(SpeechSegment(start_ms=active_start, end_ms=wav_duration_ms(audio_path)))
        return segments


def _rms(chunk: bytes, sample_width: int) -> int:
    if sample_width != 2:
        return 0
    samples = array.array("h")
    samples.frombytes(chunk)
    if not samples:
        return 0
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    return int(math.sqrt(mean_square))


class PassthroughEnhancerProvider(EnhancerProvider):
    name = "passthrough_enhancer"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enhance(self, segment_path: Path, output_path: Path) -> AudioArtifact:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(segment_path, output_path)
        return AudioArtifact(path=output_path, sample_rate=self.settings.sample_rate, metadata={"degraded": True})


class MockOCRProvider(OCRProvider):
    name = "mock_ocr"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def recognize(self, frame_path: Path, roi: dict[str, float] | None = None) -> OCRObservation:
        return OCRObservation(
            text="",
            confidence=0.0,
            frame_time_ms=0,
            roi=roi,
            metadata={
                "provider": self.name,
                "degraded": True,
                "reason": "mock_ocr does not perform real text recognition",
            },
        )
