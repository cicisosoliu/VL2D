from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SpeechSegment:
    start_ms: int
    end_ms: int
    confidence: float | None = None
    flags: list[str] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


@dataclass(slots=True)
class AudioArtifact:
    path: Path
    sample_rate: int = 16000
    channels: int = 1
    format: str = "wav"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OCRObservation:
    text: str
    confidence: float
    frame_time_ms: int
    roi: dict[str, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProgressUpdate:
    step: str
    message: str
    progress: float | None = None


ProgressCallback = Callable[[ProgressUpdate], None]
