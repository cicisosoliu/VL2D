from __future__ import annotations

import threading
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn

from vl2d.api import create_app
from vl2d.config import get_settings
from vl2d.db import get_session_factory, init_db
from vl2d.doctor import DoctorCheck, collect_doctor_report
from vl2d.domain import ProgressUpdate
from vl2d.exporter import export_job_dataset
from vl2d.providers import get_provider_registry
from vl2d.schemas import JobCreateRequest
from vl2d.services import create_job, create_video_from_path, get_job_or_404
from vl2d.storage import resolve_artifact
from vl2d.video_formats import VideoFormatError
from vl2d.worker.runner import run_worker_loop, run_worker_once

app = typer.Typer(help="VL2D command line interface")
providers_app = typer.Typer(help="Inspect available providers")
app.add_typer(providers_app, name="providers")
console = Console()


def _doctor_status_label(check: DoctorCheck) -> str:
    if check.status == "pass":
        return "[green]PASS[/green]"
    if check.status == "warn":
        return "[yellow]WARN[/yellow]"
    return "[red]FAIL[/red]"


@providers_app.command("list")
def list_registered_providers() -> None:
    providers = get_provider_registry().describe()
    console.print({"vad": providers.vad, "enhancer": providers.enhancer, "ocr": providers.ocr})


@app.command()
def run(
    input_path: Path = typer.Argument(..., exists=True, resolve_path=True),
    export: bool = typer.Option(False, "--export", help="Export a dataset bundle after processing"),
    include_all_statuses: bool = typer.Option(
        True,
        "--include-all-statuses/--approved-only",
        help="CLI export defaults to all samples because there is no review step in pure CLI mode.",
    ),
) -> None:
    settings = get_settings()
    init_db(settings)
    session_factory = get_session_factory(settings)
    with session_factory() as session:
        try:
            video = create_video_from_path(session, settings, input_path)
        except VideoFormatError as exc:
            raise typer.BadParameter(str(exc), param_hint="input_path") from exc
        job = create_job(session, settings, JobCreateRequest(video_id=video.id))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        process_task = progress.add_task("[cyan]Queued job", total=100)

        def on_process(update: ProgressUpdate) -> None:
            completed = 0.0 if update.progress is None else max(0.0, min(update.progress * 100, 100.0))
            progress.update(process_task, description=f"[cyan]{update.message}", completed=completed)

        ran = run_worker_once(settings=settings, worker_id="cli-runner", progress_callback=on_process)
        if not ran:
            progress.update(process_task, description="[red]No queued job was found", completed=100)
            raise typer.Exit(code=1)

        with session_factory() as session:
            job = get_job_or_404(session, job.id)
            summary_path = resolve_artifact(settings, job.stats.get("artifact_summary_path"))
            console.print(
                {
                    "job_id": job.id,
                    "status": job.status,
                    "sample_count": job.stats.get("sample_count", 0),
                    "summary_path": str(summary_path) if summary_path else None,
                }
            )
            if job.status != "succeeded":
                raise typer.Exit(code=1)

            if export:
                export_task = progress.add_task("[magenta]Preparing export", total=100)

                def on_export(update: ProgressUpdate) -> None:
                    completed = 0.0 if update.progress is None else max(0.0, min(update.progress * 100, 100.0))
                    progress.update(export_task, description=f"[magenta]{update.message}", completed=completed)

                export_record = export_job_dataset(
                    session,
                    settings,
                    job,
                    include_all_statuses=include_all_statuses,
                    progress_callback=on_export,
                )
                archive_path = resolve_artifact(settings, export_record.artifact_path)
                dataset_dir = archive_path.parent / "dataset" if archive_path is not None else None
                console.print(
                    {
                        "export_id": export_record.id,
                        "exported_sample_count": export_record.item_count,
                        "artifact_path": str(archive_path) if archive_path else export_record.artifact_path,
                        "dataset_dir": str(dataset_dir) if dataset_dir else None,
                        "include_all_statuses": include_all_statuses,
                    }
                )
                if export_record.item_count == 0:
                    console.print(
                        "[yellow]Export completed with 0 samples. "
                        "This usually means no samples matched the export filter. "
                        "Use `--include-all-statuses` or approve samples in the Web UI first.[/yellow]"
                    )


@app.command()
def doctor() -> None:
    settings = get_settings()
    report = collect_doctor_report(settings)

    console.print("[bold]VL2D Doctor[/bold]")
    console.print(
        {
            "data_dir": str(settings.data_dir),
            "default_ocr_provider": settings.default_ocr_provider,
            "tesseract_lang": settings.tesseract_lang,
            "paddle_ocr_lang": settings.paddle_ocr_lang,
        }
    )

    for check in report.checks:
        console.print(f"{_doctor_status_label(check)} {escape(check.name)}: {escape(check.summary)}")
        for detail in check.details:
            console.print(f"  - {escape(detail)}")
        if check.recommendation:
            console.print(f"  - fix: {escape(check.recommendation)}")

    if report.is_ready:
        console.print("[green]Doctor summary: current default runtime prerequisites look ready.[/green]")
        return

    console.print(
        f"[red]Doctor summary: {len(report.blocking_checks)} blocking issue(s) detected for the current default runtime.[/red]"
    )
    raise typer.Exit(code=1)


@app.command("serve-api")
def serve_api(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    settings = get_settings()
    init_db(settings)
    uvicorn.run(create_app(settings), host=host, port=port)


@app.command()
def worker(
    once: bool = typer.Option(False, "--once", help="Run at most one queued job"),
) -> None:
    settings = get_settings()
    init_db(settings)
    run_worker_loop(settings, once=once)


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    settings = get_settings()
    init_db(settings)
    worker_thread = threading.Thread(target=run_worker_loop, kwargs={"settings": settings}, daemon=True)
    worker_thread.start()
    uvicorn.run(create_app(settings), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
