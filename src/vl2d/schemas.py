from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    stored_path: str
    created_at: datetime


class RejectedFileRead(BaseModel):
    filename: str
    reason: str


class JobCreateRequest(BaseModel):
    video_id: str
    vad_provider: str | None = None
    enhancer_provider: str | None = None
    ocr_provider: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    status: str
    progress_step: str | None
    progress_message: str | None
    progress_percent: int | None
    worker_id: str | None
    error_message: str | None
    provider_stack: dict
    stats: dict
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class FrameObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    frame_path: str
    roi_path: str | None
    frame_time_ms: int
    text: str
    confidence: float
    metadata_json: dict = Field(default_factory=dict)


class SampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    video_id: str
    segment_index: int
    start_ms: int
    end_ms: int
    duration_ms: int
    audio_path: str
    raw_text: str
    final_text: str
    review_status: str
    provider_stack: dict
    confidence_summary: dict
    flags: list
    created_at: datetime
    updated_at: datetime
    frame_observations: list[FrameObservationRead] = Field(default_factory=list)


class SamplePageRead(BaseModel):
    items: list[SampleRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class SamplePatchRequest(BaseModel):
    final_text: str | None = None
    review_status: str | None = None


class ExportCreateRequest(BaseModel):
    job_id: str
    include_all_statuses: bool = False


class ExportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    status: str
    include_all_statuses: bool
    artifact_path: str | None
    item_count: int
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None


class ProvidersRead(BaseModel):
    vad: list[str]
    enhancer: list[str]
    ocr: list[str]


class JobBatchRead(BaseModel):
    jobs: list[JobRead]
    rejected_files: list[RejectedFileRead] = Field(default_factory=list)
