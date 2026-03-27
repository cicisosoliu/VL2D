from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from vl2d.config import Settings
from vl2d.providers import get_provider_registry
from vl2d.providers.tesseract_ocr import _parse_tesseract_languages


@dataclass(slots=True)
class DoctorCheck:
    name: str
    status: str
    summary: str
    details: list[str] = field(default_factory=list)
    recommendation: str | None = None
    blocking: bool = False


@dataclass(slots=True)
class DoctorReport:
    settings: Settings
    checks: list[DoctorCheck]

    @property
    def blocking_checks(self) -> list[DoctorCheck]:
        return [check for check in self.checks if check.blocking]

    @property
    def is_ready(self) -> bool:
        return not self.blocking_checks


def _default_uses_tesseract(settings: Settings) -> bool:
    return settings.default_ocr_provider == "tesseract_ocr"


def _default_uses_paddle(settings: Settings) -> bool:
    return settings.default_ocr_provider in {"paddle_ocr", "paddleocr_vl"}


def _command_path(command: str) -> str | None:
    resolved = shutil.which(command)
    if resolved:
        return resolved
    if Path(command).exists():
        return str(Path(command).resolve())
    return None


def _build_tesseract_env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    if settings.tessdata_prefix:
        env["TESSDATA_PREFIX"] = settings.tessdata_prefix
    return env


def _check_provider_registry(settings: Settings) -> DoctorCheck:
    providers = get_provider_registry().describe().ocr
    if settings.default_ocr_provider in providers:
        return DoctorCheck(
            name="OCR provider",
            status="pass",
            summary=f"default OCR provider '{settings.default_ocr_provider}' is registered",
            details=[f"available providers: {', '.join(providers)}"],
        )
    return DoctorCheck(
        name="OCR provider",
        status="fail",
        summary=f"default OCR provider '{settings.default_ocr_provider}' is not registered",
        details=[f"available providers: {', '.join(providers)}"],
        recommendation="Set `VL2D_DEFAULT_OCR` to one of the registered providers listed above.",
        blocking=True,
    )


def _check_ffmpeg() -> DoctorCheck:
    resolved = shutil.which("ffmpeg")
    if resolved:
        return DoctorCheck(name="ffmpeg", status="pass", summary=f"ffmpeg found at {resolved}")
    return DoctorCheck(
        name="ffmpeg",
        status="fail",
        summary="ffmpeg was not found on PATH",
        recommendation="Install `ffmpeg` and confirm `ffmpeg -version` works in this shell.",
        blocking=True,
    )


def _check_tesseract(settings: Settings) -> DoctorCheck:
    resolved = _command_path(settings.tesseract_cmd)
    blocking = _default_uses_tesseract(settings)
    if resolved is None:
        return DoctorCheck(
            name="tesseract_ocr",
            status="fail" if blocking else "warn",
            summary=f"tesseract executable not found: {settings.tesseract_cmd}",
            recommendation=(
                "Install `tesseract` and the configured language pack, or switch "
                "`VL2D_DEFAULT_OCR` to `paddle_ocr`."
            ),
            blocking=blocking,
        )

    try:
        result = subprocess.run(
            [resolved, "--list-langs"],
            check=True,
            capture_output=True,
            text=True,
            env=_build_tesseract_env(settings),
        )
    except Exception as exc:
        return DoctorCheck(
            name="tesseract_ocr",
            status="fail" if blocking else "warn",
            summary=f"failed to list tesseract languages: {exc}",
            details=[f"command: {resolved} --list-langs"],
            recommendation="Fix the tesseract installation so `tesseract --list-langs` succeeds.",
            blocking=blocking,
        )

    languages = sorted(_parse_tesseract_languages(result.stdout))
    details = [f"command: {resolved}", f"available languages: {', '.join(languages) or 'none'}"]
    if settings.tesseract_lang in languages:
        return DoctorCheck(
            name="tesseract_ocr",
            status="pass",
            summary=f"language '{settings.tesseract_lang}' is available for Tesseract OCR",
            details=details,
        )

    return DoctorCheck(
        name="tesseract_ocr",
        status="fail" if blocking else "warn",
        summary=f"traineddata for '{settings.tesseract_lang}' is not installed",
        details=details,
        recommendation=(
            f"Install `{settings.tesseract_lang}.traineddata` or set "
            "`VL2D_TESSERACT_LANG` to one of the installed languages."
        ),
        blocking=blocking,
    )


def _check_paddle_ocr(settings: Settings) -> DoctorCheck:
    has_paddleocr = importlib.util.find_spec("paddleocr") is not None
    has_paddle = importlib.util.find_spec("paddle") is not None
    blocking = _default_uses_paddle(settings)
    details = [
        f"paddleocr installed: {'yes' if has_paddleocr else 'no'}",
        f"paddle runtime installed: {'yes' if has_paddle else 'no'}",
        f"configured language: {settings.paddle_ocr_lang}",
        f"angle classification: {'enabled' if settings.paddle_ocr_use_angle_cls else 'disabled'}",
    ]

    if has_paddleocr and has_paddle:
        return DoctorCheck(
            name="paddle_ocr",
            status="pass",
            summary="PaddleOCR Python package and paddle runtime are installed",
            details=details,
        )

    missing: list[str] = []
    if not has_paddleocr:
        missing.append("paddleocr")
    if not has_paddle:
        missing.append("paddlepaddle runtime")
    missing_text = ", ".join(missing)
    recommendation_parts: list[str] = []
    if not has_paddleocr:
        recommendation_parts.append('run `uv pip install -e ".[dev,ocr-paddle]"`')
    if not has_paddle:
        recommendation_parts.append("install a compatible `paddlepaddle` runtime")
    recommendation = ", then ".join(recommendation_parts)
    if not recommendation:
        recommendation = "verify the PaddleOCR environment"
    recommendation += ", and keep `VL2D_DEFAULT_OCR=paddle_ocr` if you want PaddleOCR as default."
    return DoctorCheck(
        name="paddle_ocr",
        status="fail" if blocking else "warn",
        summary=f"Paddle OCR runtime is incomplete: missing {missing_text}",
        details=details,
        recommendation=recommendation,
        blocking=blocking,
    )


def collect_doctor_report(settings: Settings) -> DoctorReport:
    checks = [
        _check_provider_registry(settings),
        _check_ffmpeg(),
        _check_tesseract(settings),
        _check_paddle_ocr(settings),
    ]
    return DoctorReport(settings=settings, checks=checks)
