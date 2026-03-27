from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
from pathlib import Path

from vl2d.config import Settings
from vl2d.domain import OCRObservation
from vl2d.providers.base import OCRProvider


def _parse_tesseract_languages(output: str) -> set[str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if lines and lines[0].startswith("List of available languages"):
        lines = lines[1:]
    return set(lines)


def _parse_tesseract_tsv(output: str) -> tuple[str, float]:
    line_map: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    reader = csv.DictReader(io.StringIO(output), delimiter="\t")
    for row in reader:
        if not row:
            continue
        text = (row.get("text") or "").strip()
        confidence_raw = (row.get("conf") or "").strip()
        level_raw = (row.get("level") or "").strip()
        try:
            level = int(level_raw or "0")
        except ValueError:
            level = 0
        try:
            confidence = float(confidence_raw or "-1")
        except ValueError:
            confidence = -1.0

        if level != 5 or not text or confidence < 0:
            continue

        key = (
            int((row.get("block_num") or "0").strip() or "0"),
            int((row.get("par_num") or "0").strip() or "0"),
            int((row.get("line_num") or "0").strip() or "0"),
        )
        line_map.setdefault(key, []).append(text)
        confidences.append(confidence)

    ordered_lines = [" ".join(line_map[key]) for key in sorted(line_map)]
    text = "\n".join(line for line in ordered_lines if line.strip())
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return text, average_confidence


class TesseractOCRProvider(OCRProvider):
    name = "tesseract_ocr"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.command = settings.tesseract_cmd
        self.language = settings.tesseract_lang
        self.psm = settings.tesseract_psm
        self.oem = settings.tesseract_oem
        self.tessdata_prefix = settings.tessdata_prefix
        self._availability_reason: str | None = None
        self._resolved_command = shutil.which(self.command) or self.command
        self._available_languages = self._discover_languages()

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.tessdata_prefix:
            env["TESSDATA_PREFIX"] = self.tessdata_prefix
        return env

    def _discover_languages(self) -> set[str]:
        if shutil.which(self.command) is None and not Path(self.command).exists():
            self._availability_reason = f"tesseract executable not found: {self.command}"
            return set()

        try:
            result = subprocess.run(
                [self._resolved_command, "--list-langs"],
                check=True,
                capture_output=True,
                text=True,
                env=self._build_env(),
            )
        except Exception as exc:
            self._availability_reason = f"failed to list tesseract languages: {exc}"
            return set()

        languages = _parse_tesseract_languages(result.stdout)
        if self.language not in languages:
            available = ", ".join(sorted(languages)) or "none"
            self._availability_reason = (
                f"traineddata for '{self.language}' is not installed. available languages: {available}"
            )
        return languages

    def recognize(self, frame_path: Path, roi: dict[str, float] | None = None) -> OCRObservation:
        metadata = {
            "provider": self.name,
            "language": self.language,
            "psm": self.psm,
            "oem": self.oem,
        }
        if self._availability_reason is not None:
            metadata["degraded"] = True
            metadata["reason"] = self._availability_reason
            metadata["available_languages"] = sorted(self._available_languages)
            return OCRObservation(text="", confidence=0.0, frame_time_ms=0, roi=roi, metadata=metadata)

        command = [
            self._resolved_command,
            str(frame_path),
            "stdout",
            "-l",
            self.language,
            "--oem",
            str(self.oem),
            "--psm",
            str(self.psm),
            "-c",
            "preserve_interword_spaces=1",
            "tsv",
        ]
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                env=self._build_env(),
            )
        except Exception as exc:
            metadata["degraded"] = True
            metadata["reason"] = f"tesseract OCR failed: {exc}"
            return OCRObservation(text="", confidence=0.0, frame_time_ms=0, roi=roi, metadata=metadata)

        text, average_confidence = _parse_tesseract_tsv(result.stdout)
        if not text:
            metadata["no_text_detected"] = True
            return OCRObservation(text="", confidence=0.0, frame_time_ms=0, roi=roi, metadata=metadata)

        return OCRObservation(
            text=text,
            confidence=average_confidence,
            frame_time_ms=0,
            roi=roi,
            metadata=metadata,
        )
