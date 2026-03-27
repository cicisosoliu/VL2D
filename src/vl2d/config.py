from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(slots=True)
class Settings:
    app_name: str
    data_dir: Path
    database_url: str
    videos_dir: Path
    audio_dir: Path
    frames_dir: Path
    artifacts_dir: Path
    exports_dir: Path
    frame_interval_ms: int
    roi_bottom_ratio: float
    min_segment_ms: int
    merge_gap_ms: int
    max_segment_ms: int
    sample_rate: int
    poll_interval_seconds: float
    default_vad_provider: str
    default_enhancer_provider: str
    default_ocr_provider: str
    tesseract_cmd: str
    tesseract_lang: str
    tesseract_psm: int
    tesseract_oem: int
    tessdata_prefix: str | None
    paddle_ocr_lang: str
    paddle_ocr_use_angle_cls: bool
    allow_all_export_statuses: bool
    cors_origins: list[str]

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.videos_dir,
            self.audio_dir,
            self.frames_dir,
            self.artifacts_dir,
            self.exports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    root = Path(os.getenv("VL2D_DATA_DIR", Path.cwd() / "data")).resolve()
    database_path = Path(os.getenv("VL2D_DB_PATH", root / "vl2d.db")).resolve()
    settings = Settings(
        app_name="VL2D",
        data_dir=root,
        database_url=f"sqlite:///{database_path}",
        videos_dir=root / "videos",
        audio_dir=root / "audio",
        frames_dir=root / "frames",
        artifacts_dir=root / "artifacts",
        exports_dir=root / "exports",
        frame_interval_ms=int(os.getenv("VL2D_FRAME_INTERVAL_MS", "500")),
        roi_bottom_ratio=float(os.getenv("VL2D_ROI_BOTTOM_RATIO", "0.5")),
        min_segment_ms=int(os.getenv("VL2D_MIN_SEGMENT_MS", "1000")),
        merge_gap_ms=int(os.getenv("VL2D_MERGE_GAP_MS", "300")),
        max_segment_ms=int(os.getenv("VL2D_MAX_SEGMENT_MS", "20000")),
        sample_rate=int(os.getenv("VL2D_SAMPLE_RATE", "16000")),
        poll_interval_seconds=float(os.getenv("VL2D_POLL_INTERVAL_SECONDS", "2")),
        default_vad_provider=os.getenv("VL2D_DEFAULT_VAD", "silero_vad"),
        default_enhancer_provider=os.getenv("VL2D_DEFAULT_ENHANCER", "semamba"),
        default_ocr_provider=os.getenv("VL2D_DEFAULT_OCR", "paddle_ocr"),
        tesseract_cmd=os.getenv("VL2D_TESSERACT_CMD", "tesseract"),
        tesseract_lang=os.getenv("VL2D_TESSERACT_LANG", "chi_sim"),
        tesseract_psm=int(os.getenv("VL2D_TESSERACT_PSM", "6")),
        tesseract_oem=int(os.getenv("VL2D_TESSERACT_OEM", "1")),
        tessdata_prefix=os.getenv("VL2D_TESSDATA_PREFIX"),
        paddle_ocr_lang=os.getenv("VL2D_PADDLE_OCR_LANG", "ch"),
        paddle_ocr_use_angle_cls=_env_bool("VL2D_PADDLE_OCR_USE_ANGLE_CLS", True),
        allow_all_export_statuses=_env_bool("VL2D_ALLOW_ALL_EXPORT_STATUSES", False),
        cors_origins=[
            origin.strip()
            for origin in os.getenv("VL2D_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if origin.strip()
        ],
    )
    settings.ensure_dirs()
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()
