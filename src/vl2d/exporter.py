from __future__ import annotations

import csv
import json
import shutil
import zipfile
from collections.abc import Callable
from datetime import timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from vl2d.config import Settings
from vl2d.domain import ProgressUpdate
from vl2d.models import ExportRecord, Job, Sample, utcnow
from vl2d.storage import resolve_artifact, relative_to_data
from vl2d.text import is_placeholder_ocr_text


def export_job_dataset(
    session: Session,
    settings: Settings,
    job: Job,
    *,
    include_all_statuses: bool = False,
    progress_callback: Callable[[ProgressUpdate], None] | None = None,
) -> ExportRecord:
    def report(step: str, message: str, progress: float) -> None:
        if progress_callback is not None:
            progress_callback(ProgressUpdate(step=step, message=message, progress=progress))

    export_record = ExportRecord(job_id=job.id, status="running", include_all_statuses=include_all_statuses)
    session.add(export_record)
    session.commit()
    session.refresh(export_record)
    report("export_prepare", "Preparing export bundle", 0.05)

    export_root = settings.exports_dir / export_record.id
    bundle_root = export_root / "dataset"
    wav_root = bundle_root / "wav"
    frames_root = bundle_root / "frames"
    wav_root.mkdir(parents=True, exist_ok=True)
    frames_root.mkdir(parents=True, exist_ok=True)

    statement = (
        select(Sample)
        .where(Sample.job_id == job.id)
        .options(selectinload(Sample.frame_observations))
        .order_by(Sample.segment_index.asc())
    )
    if not include_all_statuses:
        statement = statement.where(Sample.review_status == "approved")
    samples = list(session.scalars(statement))
    report("export_collect", f"Collected {len(samples)} samples for export", 0.15)

    manifest_path = bundle_root / "manifest.jsonl"
    metadata_path = bundle_root / "metadata.csv"
    report_path = bundle_root / "review_report.csv"

    with manifest_path.open("w", encoding="utf-8") as manifest_handle, metadata_path.open(
        "w", encoding="utf-8", newline=""
    ) as metadata_handle, report_path.open("w", encoding="utf-8", newline="") as report_handle:
        metadata_writer = csv.DictWriter(
            metadata_handle,
            fieldnames=[
                "sample_id",
                "audio_relpath",
                "text",
                "start_ms",
                "end_ms",
                "duration_ms",
                "job_id",
                "video_id",
                "review_status",
            ],
        )
        metadata_writer.writeheader()

        report_writer = csv.DictWriter(
            report_handle,
            fieldnames=["sample_id", "review_status", "raw_text", "final_text", "flag_count"],
        )
        report_writer.writeheader()

        total = max(1, len(samples))
        for index, sample in enumerate(samples, start=1):
            source_audio = resolve_artifact(settings, sample.audio_path)
            if source_audio is None:
                continue
            target_audio = wav_root / f"{sample.segment_index:05d}_{Path(sample.audio_path).name}"
            shutil.copy2(source_audio, target_audio)
            audio_relpath = target_audio.relative_to(bundle_root).as_posix()

            frame_relpaths: list[str] = []
            for observation in sample.frame_observations:
                source_frame = resolve_artifact(settings, observation.roi_path or observation.frame_path)
                if source_frame is None:
                    continue
                target_frame_dir = frames_root / sample.id
                target_frame_dir.mkdir(parents=True, exist_ok=True)
                target_frame = target_frame_dir / Path(source_frame).name
                shutil.copy2(source_frame, target_frame)
                frame_relpaths.append(target_frame.relative_to(bundle_root).as_posix())

            text_value = sample.final_text or sample.raw_text
            if (
                any(bool((observation.metadata_json or {}).get("degraded")) for observation in sample.frame_observations)
                and is_placeholder_ocr_text(text_value)
            ):
                text_value = ""
            record = {
                "sample_id": sample.id,
                "audio_relpath": audio_relpath,
                "text": text_value,
                "start_ms": sample.start_ms,
                "end_ms": sample.end_ms,
                "duration_ms": sample.duration_ms,
                "job_id": sample.job_id,
                "video_id": sample.video_id,
                "review_status": sample.review_status,
                "frame_relpaths": frame_relpaths,
                "provider_stack": sample.provider_stack,
            }
            manifest_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            metadata_writer.writerow(
                {
                    "sample_id": sample.id,
                    "audio_relpath": audio_relpath,
                    "text": text_value,
                    "start_ms": sample.start_ms,
                    "end_ms": sample.end_ms,
                    "duration_ms": sample.duration_ms,
                    "job_id": sample.job_id,
                    "video_id": sample.video_id,
                    "review_status": sample.review_status,
                }
            )
            report_writer.writerow(
                {
                    "sample_id": sample.id,
                    "review_status": sample.review_status,
                    "raw_text": "" if is_placeholder_ocr_text(sample.raw_text) else sample.raw_text,
                    "final_text": "" if is_placeholder_ocr_text(sample.final_text) else sample.final_text,
                    "flag_count": len(sample.flags or []),
                }
            )
            report("export_write", f"Exporting sample {index}/{len(samples)}", 0.15 + (index / total) * 0.7)

    archive_path = export_root / f"{export_record.id}.zip"
    report("export_archive", "Creating zip archive", 0.9)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in bundle_root.rglob("*"):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(bundle_root.parent).as_posix())

    export_record.status = "succeeded"
    export_record.item_count = len(samples)
    export_record.artifact_path = relative_to_data(settings, archive_path)
    export_record.finished_at = utcnow().astimezone(timezone.utc)
    session.commit()
    session.refresh(export_record)
    report("export_completed", f"Export finished with {len(samples)} samples", 1.0)
    return export_record
