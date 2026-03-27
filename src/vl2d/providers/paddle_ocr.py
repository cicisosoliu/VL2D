from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from vl2d.config import Settings
from vl2d.domain import OCRObservation
from vl2d.providers.base import OCRProvider

logger = logging.getLogger(__name__)


def _extract_legacy_result(page: Any) -> tuple[list[str], list[float]]:
    lines: list[str] = []
    confidences: list[float] = []

    if not isinstance(page, (list, tuple)):
        return lines, confidences

    for item in page:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text_info = item[1]
        if not isinstance(text_info, (list, tuple)) or not text_info:
            continue
        text = str(text_info[0]).strip()
        if not text:
            continue
        try:
            confidence = float(text_info[1]) if len(text_info) > 1 else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        lines.append(text)
        confidences.append(confidence)

    return lines, confidences


def _extract_modern_result(page: dict[str, Any]) -> tuple[list[str], list[float]]:
    lines: list[str] = []
    confidences: list[float] = []
    texts = page.get("rec_texts")
    scores = page.get("rec_scores")
    if not isinstance(texts, (list, tuple)):
        return lines, confidences

    if not isinstance(scores, (list, tuple)):
        scores = [0.0] * len(texts)

    for text_raw, score_raw in zip(texts, scores, strict=False):
        text = str(text_raw).strip()
        if not text:
            continue
        try:
            confidence = float(score_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        lines.append(text)
        confidences.append(confidence)

    return lines, confidences


def _summarize_paddle_ocr_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, (list, tuple)):
        return {"result_container_type": type(result).__name__}

    page_types = [type(page).__name__ for page in result]
    summary: dict[str, Any] = {
        "result_container_type": type(result).__name__,
        "page_count": len(result),
        "page_types": page_types,
    }
    if result and isinstance(result[0], dict):
        summary["first_page_keys"] = sorted(str(key) for key in result[0].keys())
    return summary


def _parse_paddle_ocr_result(result: Any) -> tuple[str, float]:
    lines: list[str] = []
    confidences: list[float] = []

    if not isinstance(result, (list, tuple)):
        return "", 0.0

    for page in result:
        if isinstance(page, dict):
            page_lines, page_confidences = _extract_modern_result(page)
        else:
            page_lines, page_confidences = _extract_legacy_result(page)
        lines.extend(page_lines)
        confidences.extend(page_confidences)

    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return "\n".join(lines), average_confidence


class PaddleOCRProvider(OCRProvider):
    name = "paddle_ocr"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.language = settings.paddle_ocr_lang
        self.request_angle_cls = settings.paddle_ocr_use_angle_cls
        self._cls_enabled = self.request_angle_cls
        self._ocr = None
        self._availability_reason: str | None = None
        self._init_note: str | None = None
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except Exception as exc:
            self._availability_reason = f"paddleocr import failed: {exc}"
            return

        init_kwargs: dict[str, Any] = {"lang": self.language}
        if self.request_angle_cls:
            init_kwargs["use_angle_cls"] = True

        try:
            self._ocr = PaddleOCR(**init_kwargs)
        except TypeError as exc:
            if "use_angle_cls" not in init_kwargs:
                self._availability_reason = f"PaddleOCR initialization failed: {exc}"
                return
            try:
                self._ocr = PaddleOCR(lang=self.language)
                self._cls_enabled = False
                self._init_note = (
                    "installed PaddleOCR does not accept use_angle_cls; "
                    "continuing without angle classification"
                )
            except Exception as fallback_exc:
                self._availability_reason = f"PaddleOCR initialization failed: {fallback_exc}"
        except Exception as exc:
            self._availability_reason = f"PaddleOCR initialization failed: {exc}"

    def recognize(self, frame_path: Path, roi: dict[str, float] | None = None) -> OCRObservation:
        metadata = {
            "provider": self.name,
            "language": self.language,
            "angle_cls_requested": self.request_angle_cls,
            "angle_cls_enabled": self._cls_enabled,
        }
        if self._init_note:
            metadata["note"] = self._init_note

        if self._ocr is None:
            metadata["degraded"] = True
            metadata["reason"] = self._availability_reason or "PaddleOCR is unavailable"
            return OCRObservation(
                text="",
                confidence=0.0,
                frame_time_ms=0,
                roi=roi,
                metadata=metadata,
            )

        try:
            result = self._ocr.ocr(str(frame_path), cls=self._cls_enabled)
        except TypeError:
            result = self._ocr.ocr(str(frame_path))
            metadata["runtime_fallback"] = "ocr() called without cls argument"
        except Exception as exc:
            metadata["degraded"] = True
            metadata["reason"] = f"OCR inference failed: {exc}"
            logger.exception("Paddle OCR inference failed for %s", frame_path)
            return OCRObservation(
                text="",
                confidence=0.0,
                frame_time_ms=0,
                roi=roi,
                metadata=metadata,
            )

        metadata.update(_summarize_paddle_ocr_result(result))
        text, average_confidence = _parse_paddle_ocr_result(result)
        if not text:
            metadata["no_text_detected"] = True
            logger.info("Paddle OCR returned no text for %s with metadata %s", frame_path, metadata)
            return OCRObservation(
                text="",
                confidence=0.0,
                frame_time_ms=0,
                roi=roi,
                metadata=metadata,
            )

        return OCRObservation(
            text=text,
            confidence=average_confidence,
            frame_time_ms=0,
            roi=roi,
            metadata=metadata,
        )
