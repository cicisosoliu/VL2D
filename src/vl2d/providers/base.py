from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vl2d.config import Settings
from vl2d.domain import AudioArtifact, OCRObservation, SpeechSegment


class ProviderError(RuntimeError):
    """Raised when a provider cannot complete its work."""


class VADProvider(ABC):
    name: str

    @abstractmethod
    def detect(self, audio_path: Path, sample_rate: int) -> list[SpeechSegment]:
        raise NotImplementedError


class EnhancerProvider(ABC):
    name: str

    @abstractmethod
    def enhance(self, segment_path: Path, output_path: Path) -> AudioArtifact:
        raise NotImplementedError


class OCRProvider(ABC):
    name: str

    @abstractmethod
    def recognize(self, frame_path: Path, roi: dict[str, float] | None = None) -> OCRObservation:
        raise NotImplementedError


ProviderFactory = Callable[[Settings], Any]


@dataclass(slots=True)
class RegisteredProviders:
    vad: list[str]
    enhancer: list[str]
    ocr: list[str]


class ProviderRegistry:
    def __init__(self) -> None:
        self._vad_factories: dict[str, ProviderFactory] = {}
        self._enhancer_factories: dict[str, ProviderFactory] = {}
        self._ocr_factories: dict[str, ProviderFactory] = {}

    def register_vad(self, name: str, factory: ProviderFactory) -> None:
        self._vad_factories[name] = factory

    def register_enhancer(self, name: str, factory: ProviderFactory) -> None:
        self._enhancer_factories[name] = factory

    def register_ocr(self, name: str, factory: ProviderFactory) -> None:
        self._ocr_factories[name] = factory

    def create_vad(self, name: str, settings: Settings) -> VADProvider:
        try:
            return self._vad_factories[name](settings)
        except KeyError as exc:
            raise ProviderError(f"unknown VAD provider: {name}") from exc

    def create_enhancer(self, name: str, settings: Settings) -> EnhancerProvider:
        try:
            return self._enhancer_factories[name](settings)
        except KeyError as exc:
            raise ProviderError(f"unknown enhancer provider: {name}") from exc

    def create_ocr(self, name: str, settings: Settings) -> OCRProvider:
        try:
            return self._ocr_factories[name](settings)
        except KeyError as exc:
            raise ProviderError(f"unknown OCR provider: {name}") from exc

    def describe(self) -> RegisteredProviders:
        return RegisteredProviders(
            vad=sorted(self._vad_factories),
            enhancer=sorted(self._enhancer_factories),
            ocr=sorted(self._ocr_factories),
        )

