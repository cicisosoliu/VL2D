from __future__ import annotations

import zipfile
from pathlib import Path

from sqlalchemy import select
from typer.testing import CliRunner

from vl2d.cli import app
from vl2d.db import get_session_factory
from vl2d.doctor import DoctorCheck, DoctorReport
from vl2d.models import ExportRecord, Job
from vl2d.providers.semamba import SEMambaEnhancerProvider
from vl2d.schemas import JobCreateRequest
from vl2d.services import create_job, create_video_from_path
from vl2d.storage import resolve_artifact
from vl2d.worker.runner import run_worker_once


def test_cli_run_exports_all_statuses_by_default(app_env, sample_video: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(sample_video), "--export"])
    assert result.exit_code == 0, result.output

    session_factory = get_session_factory(app_env)
    with session_factory() as session:
        export_record = session.scalar(select(ExportRecord).order_by(ExportRecord.created_at.desc()))
        assert export_record is not None
        assert export_record.item_count >= 1
        archive_path = resolve_artifact(app_env, export_record.artifact_path)
        assert archive_path is not None
        assert archive_path.exists()

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert any(name.startswith("dataset/wav/") for name in names)
        assert "dataset/manifest.jsonl" in names


def test_cli_run_supports_mov_input(app_env, sample_video_mov: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(sample_video_mov), "--export"])
    assert result.exit_code == 0, result.output
    assert "sample_count" in result.output


def test_cli_run_rejects_unsupported_video_extension(tmp_path: Path) -> None:
    invalid_video = tmp_path / "sample.avi"
    invalid_video.write_bytes(b"not-a-real-video")

    runner = CliRunner()
    result = runner.invoke(app, ["run", str(invalid_video)])

    assert result.exit_code == 2
    assert ".mp4" in result.output
    assert ".mov" in result.output


def test_cli_run_supports_directory_input(app_env, sample_video: Path, sample_video_mov: Path, tmp_path: Path) -> None:
    input_dir = tmp_path / "batch"
    input_dir.mkdir()
    mp4_copy = input_dir / "batch-a.mp4"
    mov_copy = input_dir / "batch-b.mov"
    mp4_copy.write_bytes(sample_video.read_bytes())
    mov_copy.write_bytes(sample_video_mov.read_bytes())

    runner = CliRunner()
    result = runner.invoke(app, ["run", str(input_dir), "--export"])
    assert result.exit_code == 0, result.output
    assert "processed_video_count" in result.output
    assert "2" in result.output

    session_factory = get_session_factory(app_env)
    with session_factory() as session:
        jobs = session.query(Job).all()
        exports = session.query(ExportRecord).all()
        assert len(jobs) == 2
        assert len(exports) == 2


def test_semamba_provider_uses_new_default_checkpoint(app_env) -> None:
    provider = SEMambaEnhancerProvider(app_env)
    assert provider.checkpoint_path.name == "g_00587000.pth"
    assert provider.checkpoint_path.as_posix().endswith("model/g_00587000.pth")


def test_worker_reports_progress_updates(app_env, sample_video: Path) -> None:
    session_factory = get_session_factory(app_env)
    with session_factory() as session:
        video = create_video_from_path(session, app_env, sample_video)
        create_job(session, app_env, JobCreateRequest(video_id=video.id))

    updates: list[str] = []

    def on_progress(update) -> None:
        updates.append(update.step)

    assert run_worker_once(app_env, worker_id="pytest-progress", progress_callback=on_progress) is True
    assert "claimed" in updates
    assert "extract_audio" in updates
    assert "vad" in updates
    assert "ocr" in updates
    assert "completed" in updates


def test_doctor_command_exits_nonzero_when_default_ocr_is_not_ready(app_env) -> None:
    report = DoctorReport(
        settings=app_env,
        checks=[
            DoctorCheck(
                name="tesseract_ocr",
                status="fail",
                summary="traineddata for 'chi_sim' is not installed",
                recommendation="Install `chi_sim.traineddata`.",
                blocking=True,
            )
        ],
    )
    app_env.default_ocr_provider = "tesseract_ocr"

    from vl2d import cli as cli_module

    original_get_settings = cli_module.get_settings
    original_collect_doctor_report = cli_module.collect_doctor_report
    cli_module.get_settings = lambda: app_env
    cli_module.collect_doctor_report = lambda settings: report

    runner = CliRunner()
    try:
        result = runner.invoke(app, ["doctor"])
    finally:
        cli_module.get_settings = original_get_settings
        cli_module.collect_doctor_report = original_collect_doctor_report

    assert result.exit_code == 1
    assert "VL2D Doctor" in result.output
    assert "default_ocr_provider" in result.output
    assert "tesseract_ocr" in result.output
    assert "chi_sim" in result.output
