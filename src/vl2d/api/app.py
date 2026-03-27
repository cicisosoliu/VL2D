from __future__ import annotations

import math
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from vl2d.config import Settings, get_settings
from vl2d.db import get_db, init_db
from vl2d.exporter import export_job_dataset
from vl2d.providers import get_provider_registry
from vl2d.schemas import (
    ExportCreateRequest,
    ExportRead,
    JobCreateRequest,
    JobRead,
    ProvidersRead,
    SamplePageRead,
    SamplePatchRequest,
    SampleRead,
    VideoRead,
)
from vl2d.services import (
    count_samples,
    create_job,
    create_video_from_upload,
    get_export_or_404,
    get_job_or_404,
    get_sample_or_404,
    list_jobs,
    list_samples,
    update_sample,
)
from vl2d.storage import resolve_artifact


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.ensure_dirs()
        init_db(settings)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/files", StaticFiles(directory=settings.data_dir), name="files")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/providers", response_model=ProvidersRead)
    def read_providers() -> ProvidersRead:
        providers = get_provider_registry().describe()
        return ProvidersRead(vad=providers.vad, enhancer=providers.enhancer, ocr=providers.ocr)

    @app.post("/api/videos", response_model=VideoRead)
    async def upload_video(
        file: UploadFile = File(...),
        session: Session = Depends(get_db),
    ) -> VideoRead:
        video = await create_video_from_upload(session, settings, file)
        return VideoRead.model_validate(video)

    @app.get("/api/jobs", response_model=list[JobRead])
    def read_jobs(session: Session = Depends(get_db)) -> list[JobRead]:
        return [JobRead.model_validate(job) for job in list_jobs(session)]

    @app.post("/api/jobs", response_model=JobRead)
    def enqueue_job(payload: JobCreateRequest, session: Session = Depends(get_db)) -> JobRead:
        job = create_job(session, settings, payload)
        return JobRead.model_validate(job)

    @app.get("/api/jobs/{job_id}", response_model=JobRead)
    def read_job(job_id: str, session: Session = Depends(get_db)) -> JobRead:
        job = get_job_or_404(session, job_id)
        return JobRead.model_validate(job)

    @app.get("/api/samples", response_model=SamplePageRead)
    def read_samples(
        job_id: str | None = Query(default=None),
        review_status: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=12, ge=1, le=100),
        session: Session = Depends(get_db),
    ) -> SamplePageRead:
        total = count_samples(session, job_id=job_id, review_status=review_status)
        offset = (page - 1) * page_size
        samples = list_samples(session, job_id=job_id, review_status=review_status, offset=offset, limit=page_size)
        total_pages = math.ceil(total / page_size) if total else 0
        return SamplePageRead(
            items=[SampleRead.model_validate(sample) for sample in samples],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @app.get("/api/samples/{sample_id}", response_model=SampleRead)
    def read_sample(sample_id: str, session: Session = Depends(get_db)) -> SampleRead:
        sample = get_sample_or_404(session, sample_id)
        return SampleRead.model_validate(sample)

    @app.patch("/api/samples/{sample_id}", response_model=SampleRead)
    def patch_sample(
        sample_id: str,
        payload: SamplePatchRequest,
        session: Session = Depends(get_db),
    ) -> SampleRead:
        sample = update_sample(session, sample_id, payload)
        return SampleRead.model_validate(sample)

    @app.post("/api/exports", response_model=ExportRead)
    def create_export(payload: ExportCreateRequest, session: Session = Depends(get_db)) -> ExportRead:
        job = get_job_or_404(session, payload.job_id)
        export_record = export_job_dataset(
            session,
            settings,
            job,
            include_all_statuses=payload.include_all_statuses or settings.allow_all_export_statuses,
        )
        return ExportRead.model_validate(export_record)

    @app.get("/api/exports/{export_id}", response_model=ExportRead)
    def read_export(export_id: str, session: Session = Depends(get_db)) -> ExportRead:
        export_record = get_export_or_404(session, export_id)
        return ExportRead.model_validate(export_record)

    @app.get("/api/exports/{export_id}/download")
    def download_export(export_id: str, session: Session = Depends(get_db)) -> FileResponse:
        export_record = get_export_or_404(session, export_id)
        archive_path = resolve_artifact(settings, export_record.artifact_path)
        if archive_path is None or not archive_path.exists():
            raise HTTPException(status_code=404, detail="export artifact not found")
        return FileResponse(path=archive_path, filename=Path(archive_path).name, media_type="application/zip")

    return app
