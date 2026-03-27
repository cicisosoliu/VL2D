from __future__ import annotations

from pathlib import Path

from vl2d.config import Settings
from vl2d.domain import SpeechSegment
from vl2d.providers.base import VADProvider
from vl2d.providers.mock import EnergyVADProvider


class SileroVADProvider(VADProvider):
    name = "silero_vad"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._fallback = EnergyVADProvider(settings)
        try:
            from silero_vad import get_speech_timestamps, load_silero_vad, read_audio  # type: ignore
        except Exception:
            self._read_audio = None
            self._load_silero_vad = None
            self._get_speech_timestamps = None
            self._model = None
        else:
            self._read_audio = read_audio
            self._load_silero_vad = load_silero_vad
            self._get_speech_timestamps = get_speech_timestamps
            self._model = load_silero_vad()

    def detect(self, audio_path: Path, sample_rate: int) -> list[SpeechSegment]:
        if self._model is None or self._read_audio is None or self._get_speech_timestamps is None:
            return self._fallback.detect(audio_path, sample_rate)

        waveform = self._read_audio(str(audio_path), sampling_rate=sample_rate)
        timestamps = self._get_speech_timestamps(waveform, self._model, sampling_rate=sample_rate)
        return [
            SpeechSegment(
                start_ms=int(item["start"] / sample_rate * 1000),
                end_ms=int(item["end"] / sample_rate * 1000),
                confidence=float(item.get("prob", 0.0)),
            )
            for item in timestamps
        ]

