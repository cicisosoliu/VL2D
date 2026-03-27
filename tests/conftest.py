from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vl2d.api import create_app
from vl2d.config import get_settings, reset_settings_cache
from vl2d.db import init_db, reset_db_caches


@pytest.fixture()
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VL2D_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VL2D_DEFAULT_VAD", "energy_vad")
    monkeypatch.setenv("VL2D_DEFAULT_ENHANCER", "passthrough_enhancer")
    monkeypatch.setenv("VL2D_DEFAULT_OCR", "mock_ocr")
    reset_settings_cache()
    reset_db_caches()
    settings = get_settings()
    init_db(settings)
    yield settings
    reset_settings_cache()
    reset_db_caches()


@pytest.fixture()
def client(app_env):
    app = create_app(app_env)
    return TestClient(app)


@pytest.fixture()
def sample_video(tmp_path: Path) -> Path:
    output_path = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=640x360:d=2.4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=16000:duration=2.4",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path


@pytest.fixture()
def sample_video_mov(tmp_path: Path) -> Path:
    output_path = tmp_path / "sample.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=640x360:d=2.4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=16000:duration=2.4",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path
