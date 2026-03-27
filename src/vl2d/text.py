from __future__ import annotations

import re
import unicodedata

PLACEHOLDER_OCR_PREFIX = "UNVERIFIED "

_whitespace_re = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value or "")
    normalized = _whitespace_re.sub(" ", normalized).strip()
    return normalized


def dedupe_adjacent(values: list[str]) -> list[str]:
    collapsed: list[str] = []
    for value in values:
        if not value:
            continue
        if not collapsed or collapsed[-1] != value:
            collapsed.append(value)
    return collapsed


def aggregate_ocr_texts(values: list[str]) -> str:
    normalized = [normalize_text(value) for value in values]
    normalized = [value for value in normalized if value]
    normalized = dedupe_adjacent(normalized)
    return "\n".join(normalized)


def is_placeholder_ocr_text(value: str) -> bool:
    return normalize_text(value).startswith(PLACEHOLDER_OCR_PREFIX)
