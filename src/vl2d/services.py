from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from vl2d.config import Settings
from vl2d.models import ExportRecord, FrameObservation, Job, Sample, Video
from vl2d.schemas import JobCreateRequest, RejectedFileRead, SamplePatchRequest
from vl2d.storage import copy_input_video, save_uploaded_video
from vl2d.video_formats import VideoFormatError, validate_video_filename


def create_video_from_path(session: Session, settings: Settings, input_path: Path) -> Video:
    if not input_path.exists():
        raise FileNotFoundError(f"video not found: {input_path}")
    validate_video_filename(input_path.name)

    _, stored_path = copy_input_video(settings, input_path)
    video = Video(filename=input_path.name, stored_path=stored_path)
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


async def create_video_from_upload(session: Session, settings: Settings, upload: UploadFile) -> Video:
    try:
        validate_video_filename(upload.filename)
    except VideoFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _, stored_path = await save_uploaded_video(settings, upload)
    video = Video(filename=upload.filename or "upload.bin", stored_path=stored_path)
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


async def create_jobs_from_uploads(
    session: Session,
    settings: Settings,
    uploads: list[UploadFile],
) -> tuple[list[Job], list[RejectedFileRead]]:
    jobs: list[Job] = []
    rejected: list[RejectedFileRead] = []
    for upload in uploads:
        try:
            video = await create_video_from_upload(session, settings, upload)
            jobs.append(create_job(session, settings, JobCreateRequest(video_id=video.id)))
        except HTTPException as exc:
            rejected.append(
                RejectedFileRead(
                    filename=upload.filename or "upload.bin",
                    reason=str(exc.detail),
                )
            )
            await upload.close()
    return jobs, rejected


def create_job(session: Session, settings: Settings, payload: JobCreateRequest) -> Job:
    video = session.get(Video, payload.video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")

    provider_stack = {
        "vad": payload.vad_provider or settings.default_vad_provider,
        "enhancer": payload.enhancer_provider or settings.default_enhancer_provider,
        "ocr": payload.ocr_provider or settings.default_ocr_provider,
    }
    job = Job(video_id=video.id, status="queued", provider_stack=provider_stack, stats={})
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def list_jobs(session: Session) -> list[Job]:
    statement = select(Job).order_by(Job.created_at.desc())
    return list(session.scalars(statement))


def get_job_or_404(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def count_samples(session: Session, job_id: str | None = None, review_status: str | None = None) -> int:
    statement = select(func.count()).select_from(Sample)
    if job_id:
        statement = statement.where(Sample.job_id == job_id)
    if review_status:
        statement = statement.where(Sample.review_status == review_status)
    return int(session.scalar(statement) or 0)


def list_samples(
    session: Session,
    job_id: str | None = None,
    review_status: str | None = None,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[Sample]:
    statement = select(Sample).options(selectinload(Sample.frame_observations)).order_by(Sample.segment_index.asc())
    if job_id:
        statement = statement.where(Sample.job_id == job_id)
    if review_status:
        statement = statement.where(Sample.review_status == review_status)
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement))


def get_sample_or_404(session: Session, sample_id: str) -> Sample:
    statement = (
        select(Sample)
        .where(Sample.id == sample_id)
        .options(selectinload(Sample.frame_observations))
    )
    sample = session.scalar(statement)
    if sample is None:
        raise HTTPException(status_code=404, detail="sample not found")
    return sample


def update_sample(session: Session, sample_id: str, payload: SamplePatchRequest) -> Sample:
    sample = get_sample_or_404(session, sample_id)
    if payload.final_text is not None:
        sample.final_text = payload.final_text
    if payload.review_status is not None:
        sample.review_status = payload.review_status
    session.commit()
    session.refresh(sample)
    return get_sample_or_404(session, sample.id)


def get_export_or_404(session: Session, export_id: str) -> ExportRecord:
    export_record = session.get(ExportRecord, export_id)
    if export_record is None:
        raise HTTPException(status_code=404, detail="export not found")
    return export_record


def sample_counts_for_job(session: Session, job_id: str) -> dict[str, int]:
    statement = select(Sample.review_status, func.count()).where(Sample.job_id == job_id).group_by(Sample.review_status)
    rows = session.execute(statement).all()
    counts = {status: count for status, count in rows}
    counts["total"] = sum(counts.values())
    return counts


def first_frame_for_sample(sample: Sample) -> FrameObservation | None:
    if not sample.frame_observations:
        return None
    return sorted(sample.frame_observations, key=lambda item: item.frame_time_ms)[0]
