from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="video", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    progress_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_stack: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    stats: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    video: Mapped[Video] = relationship(back_populates="jobs")
    samples: Mapped[list["Sample"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    exports: Mapped[list["ExportRecord"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    final_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False, index=True)
    provider_stack: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confidence_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    job: Mapped[Job] = relationship(back_populates="samples")
    frame_observations: Mapped[list["FrameObservation"]] = relationship(
        back_populates="sample", cascade="all, delete-orphan"
    )


class FrameObservation(Base):
    __tablename__ = "frame_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sample_id: Mapped[str] = mapped_column(ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, index=True)
    frame_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    roi_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    frame_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    sample: Mapped[Sample] = relationship(back_populates="frame_observations")


class ExportRecord(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    include_all_statuses: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[Job] = relationship(back_populates="exports")

