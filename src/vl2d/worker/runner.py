from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from vl2d.config import Settings, get_settings
from vl2d.db import get_session_factory, init_db
from vl2d.domain import ProgressUpdate
from vl2d.models import Job, utcnow
from vl2d.pipeline import process_job

logger = logging.getLogger(__name__)


def _claim_next_job(session: Session, worker_id: str) -> Job | None:
    statement = select(Job).where(Job.status == "queued").order_by(Job.created_at.asc()).limit(1)
    job = session.scalar(statement)
    if job is None:
        return None
    job.status = "running"
    job.worker_id = worker_id
    job.started_at = utcnow().astimezone(timezone.utc)
    job.progress_step = "claimed"
    job.progress_message = "Job claimed by worker"
    job.progress_percent = 0
    session.commit()
    session.refresh(job)
    return job


def run_worker_once(
    settings: Settings | None = None,
    *,
    worker_id: str | None = None,
    progress_callback: Callable[[ProgressUpdate], None] | None = None,
) -> bool:
    settings = settings or get_settings()
    init_db(settings)
    worker_id = worker_id or f"{socket.gethostname()}-worker"
    session_factory = get_session_factory(settings)
    with session_factory() as session:
        job = _claim_next_job(session, worker_id)
        if job is None:
            return False
        if progress_callback is not None:
            progress_callback(ProgressUpdate(step="claimed", message="Job claimed by worker", progress=0.0))
        try:
            process_job(session, settings, job, progress_callback=progress_callback)
            logger.info("job %s finished", job.id)
        except Exception as exc:
            logger.exception("job %s failed", job.id)
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = utcnow().astimezone(timezone.utc)
            session.commit()
            if progress_callback is not None:
                progress_callback(ProgressUpdate(step="failed", message=f"Job failed: {exc}", progress=1.0))
        return True


def run_worker_loop(settings: Settings | None = None, *, once: bool = False) -> None:
    settings = settings or get_settings()
    while True:
        ran_job = run_worker_once(settings=settings)
        if once:
            return
        if not ran_job:
            time.sleep(settings.poll_interval_seconds)
