from __future__ import annotations

from pathlib import Path

from vl2d.storage import resolve_artifact
from vl2d.worker.runner import run_worker_once


def test_upload_process_review_and_export(client, app_env, sample_video: Path) -> None:
    with sample_video.open("rb") as handle:
        response = client.post(
            "/api/videos",
            files={"file": ("sample.mp4", handle, "video/mp4")},
        )
    response.raise_for_status()
    video = response.json()

    job_response = client.post("/api/jobs", json={"video_id": video["id"]})
    job_response.raise_for_status()
    job = job_response.json()

    assert run_worker_once(app_env, worker_id="pytest-worker") is True

    job_after = client.get(f"/api/jobs/{job['id']}")
    job_after.raise_for_status()
    assert job_after.json()["status"] == "succeeded"

    samples_response = client.get("/api/samples", params={"job_id": job["id"]})
    samples_response.raise_for_status()
    sample_page = samples_response.json()
    assert sample_page["total"] >= 1
    assert sample_page["page"] == 1
    assert len(sample_page["items"]) >= 1

    sample = sample_page["items"][0]
    patch_response = client.patch(
        f"/api/samples/{sample['id']}",
        json={"review_status": "approved", "final_text": "བོད་ཡིག"},
    )
    patch_response.raise_for_status()
    assert patch_response.json()["review_status"] == "approved"

    export_response = client.post("/api/exports", json={"job_id": job["id"]})
    export_response.raise_for_status()
    export_record = export_response.json()
    assert export_record["status"] == "succeeded"

    archive_path = resolve_artifact(app_env, export_record["artifact_path"])
    assert archive_path is not None
    assert archive_path.exists()


def test_upload_supports_mov_files(client, sample_video_mov: Path) -> None:
    with sample_video_mov.open("rb") as handle:
        response = client.post(
            "/api/videos",
            files={"file": ("sample.mov", handle, "video/quicktime")},
        )

    response.raise_for_status()
    payload = response.json()
    assert payload["filename"] == "sample.mov"
    assert payload["stored_path"].endswith(".mov")


def test_upload_rejects_unsupported_video_extension(client, tmp_path: Path) -> None:
    bad_file = tmp_path / "sample.avi"
    bad_file.write_bytes(b"not-a-real-video")

    with bad_file.open("rb") as handle:
        response = client.post(
            "/api/videos",
            files={"file": ("sample.avi", handle, "video/x-msvideo")},
        )

    assert response.status_code == 400
    assert ".mp4" in response.text
    assert ".mov" in response.text


def test_batch_upload_queues_all_supported_videos(client, sample_video: Path, sample_video_mov: Path) -> None:
    with sample_video.open("rb") as handle_mp4, sample_video_mov.open("rb") as handle_mov:
        response = client.post(
            "/api/jobs/upload-batch",
            files=[
                ("files", ("sample.mp4", handle_mp4, "video/mp4")),
                ("files", ("sample.mov", handle_mov, "video/quicktime")),
            ],
        )

    response.raise_for_status()
    payload = response.json()
    assert len(payload["jobs"]) == 2
    assert payload["rejected_files"] == []
    assert all(job["status"] == "queued" for job in payload["jobs"])


def test_batch_upload_reports_rejected_files(client, sample_video: Path, tmp_path: Path) -> None:
    bad_file = tmp_path / "sample.txt"
    bad_file.write_text("not a video", encoding="utf-8")

    with sample_video.open("rb") as handle_mp4, bad_file.open("rb") as handle_bad:
        response = client.post(
            "/api/jobs/upload-batch",
            files=[
                ("files", ("sample.mp4", handle_mp4, "video/mp4")),
                ("files", ("sample.txt", handle_bad, "text/plain")),
            ],
        )

    response.raise_for_status()
    payload = response.json()
    assert len(payload["jobs"]) == 1
    assert len(payload["rejected_files"]) == 1
    assert payload["rejected_files"][0]["filename"] == "sample.txt"
    assert ".mov" in payload["rejected_files"][0]["reason"]


def test_sample_pagination(client, app_env, sample_video: Path) -> None:
    with sample_video.open("rb") as handle:
        response = client.post("/api/videos", files={"file": ("sample.mp4", handle, "video/mp4")})
    response.raise_for_status()
    video = response.json()

    job_response = client.post("/api/jobs", json={"video_id": video["id"]})
    job_response.raise_for_status()
    job = job_response.json()

    assert run_worker_once(app_env, worker_id="pytest-pagination") is True

    page_response = client.get("/api/samples", params={"job_id": job["id"], "page": 1, "page_size": 1})
    page_response.raise_for_status()
    payload = page_response.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["total"] >= 1
    assert payload["total_pages"] >= 1
    assert len(payload["items"]) == 1
