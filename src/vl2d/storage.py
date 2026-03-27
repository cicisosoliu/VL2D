from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from vl2d.config import Settings


def slugify_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_")
    return slug or "artifact"


def relative_to_data(settings: Settings, path: Path) -> str:
    return path.resolve().relative_to(settings.data_dir.resolve()).as_posix()


def resolve_artifact(settings: Settings, relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    return (settings.data_dir / relative_path).resolve()


def create_video_storage_path(settings: Settings, filename: str) -> Path:
    name = slugify_name(filename)
    return settings.videos_dir / f"{uuid.uuid4().hex}_{name}"


def copy_input_video(settings: Settings, source_path: Path) -> tuple[Path, str]:
    destination = create_video_storage_path(settings, source_path.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    return destination, relative_to_data(settings, destination)


async def save_uploaded_video(settings: Settings, upload: UploadFile) -> tuple[Path, str]:
    destination = create_video_storage_path(settings, upload.filename or "upload.bin")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            handle.write(chunk)
    await upload.close()
    return destination, relative_to_data(settings, destination)


def job_audio_dir(settings: Settings, job_id: str) -> Path:
    path = settings.audio_dir / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_frames_dir(settings: Settings, job_id: str) -> Path:
    path = settings.frames_dir / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_artifacts_dir(settings: Settings, job_id: str) -> Path:
    path = settings.artifacts_dir / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path

