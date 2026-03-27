from __future__ import annotations

import math
import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from vl2d.config import Settings
from vl2d.domain import OCRObservation, ProgressUpdate, SpeechSegment
from vl2d.media import crop_bottom_region, cut_audio_segment, extract_audio, extract_frame, probe_duration_ms
from vl2d.models import FrameObservation, Job, Sample, Video, utcnow
from vl2d.providers import get_provider_registry
from vl2d.storage import job_artifacts_dir, job_audio_dir, job_frames_dir, relative_to_data, resolve_artifact
from vl2d.text import aggregate_ocr_texts, normalize_text


def _update_job_progress(
    session: Session,
    job: Job,
    update: ProgressUpdate,
    progress_callback: Callable[[ProgressUpdate], None] | None = None,
) -> None:
    job.progress_step = update.step
    job.progress_message = update.message
    job.progress_percent = int(update.progress * 100) if update.progress is not None else None
    session.commit()
    if progress_callback is not None:
        progress_callback(update)


def _normalize_segments(segments: list[SpeechSegment], duration_ms: int, settings: Settings) -> list[SpeechSegment]:
    if not segments and duration_ms > 0:
        return [SpeechSegment(start_ms=0, end_ms=min(duration_ms, settings.max_segment_ms), flags=["fallback_full_audio"])]

    ordered = sorted(
        [
            SpeechSegment(
                start_ms=max(0, min(item.start_ms, duration_ms)),
                end_ms=max(0, min(item.end_ms, duration_ms)),
                confidence=item.confidence,
                flags=list(item.flags),
            )
            for item in segments
            if item.end_ms > item.start_ms
        ],
        key=lambda item: item.start_ms,
    )

    merged: list[SpeechSegment] = []
    for segment in ordered:
        if not merged:
            merged.append(segment)
            continue
        previous = merged[-1]
        if segment.start_ms - previous.end_ms <= settings.merge_gap_ms:
            previous.end_ms = max(previous.end_ms, segment.end_ms)
            previous.flags = sorted(set(previous.flags + segment.flags))
        else:
            merged.append(segment)

    split_segments: list[SpeechSegment] = []
    for segment in merged:
        if segment.duration_ms <= settings.max_segment_ms:
            split_segments.append(segment)
            continue
        total_parts = math.ceil(segment.duration_ms / settings.max_segment_ms)
        for index in range(total_parts):
            part_start = segment.start_ms + index * settings.max_segment_ms
            part_end = min(segment.end_ms, part_start + settings.max_segment_ms)
            split_segments.append(
                SpeechSegment(
                    start_ms=part_start,
                    end_ms=part_end,
                    confidence=segment.confidence,
                    flags=sorted(set(segment.flags + ["hard_split"])),
                )
            )

    filtered = [segment for segment in split_segments if segment.duration_ms >= settings.min_segment_ms]
    if not filtered and duration_ms > 0:
        return [SpeechSegment(start_ms=0, end_ms=min(duration_ms, settings.max_segment_ms), flags=["fallback_full_audio"])]
    return filtered


def _sample_frame_times(segment: SpeechSegment, interval_ms: int) -> list[int]:
    if segment.duration_ms <= interval_ms:
        return [segment.start_ms + max(1, segment.duration_ms // 2)]
    times = list(range(segment.start_ms + interval_ms // 2, segment.end_ms, interval_ms))
    return times or [segment.start_ms + max(1, segment.duration_ms // 2)]


def _ocr_segment(
    *,
    settings: Settings,
    video_path: Path,
    ocr_provider,
    frames_dir: Path,
    segment: SpeechSegment,
    sample_id: str,
) -> tuple[list[FrameObservation], str, dict]:
    observations: list[FrameObservation] = []
    texts: list[str] = []
    confidences: list[float] = []
    roi = {"bottom_ratio": settings.roi_bottom_ratio}

    for frame_index, frame_time_ms in enumerate(_sample_frame_times(segment, settings.frame_interval_ms)):
        frame_path = frames_dir / f"{sample_id}_{frame_index:02d}_{frame_time_ms}.png"
        roi_path = frames_dir / f"{sample_id}_{frame_index:02d}_{frame_time_ms}_roi.png"
        extract_frame(video_path, frame_path, frame_time_ms)
        crop_bottom_region(frame_path, roi_path, settings.roi_bottom_ratio)

        recognized: OCRObservation = ocr_provider.recognize(roi_path, roi=roi)
        recognized = OCRObservation(
            text=normalize_text(recognized.text),
            confidence=float(recognized.confidence),
            frame_time_ms=frame_time_ms,
            roi=roi,
            metadata=recognized.metadata,
        )
        if recognized.text:
            texts.append(recognized.text)
            confidences.append(recognized.confidence)

        observations.append(
            FrameObservation(
                sample_id=sample_id,
                frame_path=relative_to_data(settings, frame_path),
                roi_path=relative_to_data(settings, roi_path),
                frame_time_ms=frame_time_ms,
                text=recognized.text,
                confidence=recognized.confidence,
                metadata_json=recognized.metadata,
            )
        )

    raw_text = aggregate_ocr_texts(texts)
    confidence_summary = {
        "observation_count": len(observations),
        "text_observation_count": len([item for item in texts if item]),
        "degraded_observation_count": len(
            [item for item in observations if bool((item.metadata_json or {}).get("degraded"))]
        ),
        "average_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "max_confidence": round(max(confidences), 4) if confidences else 0.0,
    }
    return observations, raw_text, confidence_summary


def process_job(
    session: Session,
    settings: Settings,
    job: Job,
    *,
    progress_callback: Callable[[ProgressUpdate], None] | None = None,
) -> Job:
    video = session.get(Video, job.video_id)
    if video is None:
        raise RuntimeError("job video not found")

    video_path = resolve_artifact(settings, video.stored_path)
    if video_path is None:
        raise RuntimeError("video path could not be resolved")

    registry = get_provider_registry()
    vad_provider = registry.create_vad(job.provider_stack["vad"], settings)
    enhancer_provider = registry.create_enhancer(job.provider_stack["enhancer"], settings)
    ocr_provider = registry.create_ocr(job.provider_stack["ocr"], settings)

    audio_dir = job_audio_dir(settings, job.id)
    frames_dir = job_frames_dir(settings, job.id)
    artifacts_dir = job_artifacts_dir(settings, job.id)
    source_audio_path = audio_dir / "source.wav"

    _update_job_progress(
        session,
        job,
        ProgressUpdate(step="extract_audio", message="Extracting mono wav", progress=0.05),
        progress_callback,
    )
    extract_audio(video_path, source_audio_path, settings.sample_rate)
    duration_ms = probe_duration_ms(video_path)

    _update_job_progress(
        session,
        job,
        ProgressUpdate(step="vad", message="Detecting speech regions", progress=0.15),
        progress_callback,
    )
    raw_segments = vad_provider.detect(source_audio_path, settings.sample_rate)
    segments = _normalize_segments(raw_segments, duration_ms, settings)

    total = max(1, len(segments))
    processed = 0
    for index, segment in enumerate(segments):
        processed += 1
        segment_stem = f"segment_{index:05d}"
        raw_segment_path = audio_dir / f"{segment_stem}_raw.wav"
        enhanced_segment_path = audio_dir / f"{segment_stem}.wav"
        cut_audio_segment(source_audio_path, raw_segment_path, segment.start_ms, segment.end_ms)

        _update_job_progress(
            session,
            job,
            ProgressUpdate(
                step="enhance",
                message=f"Enhancing segment {processed}/{total}",
                progress=0.15 + (processed / total) * 0.25,
            ),
            progress_callback,
        )
        audio_artifact = enhancer_provider.enhance(raw_segment_path, enhanced_segment_path)
        sample = Sample(
            job_id=job.id,
            video_id=video.id,
            segment_index=index,
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            duration_ms=segment.duration_ms,
            audio_path=relative_to_data(settings, audio_artifact.path),
            provider_stack=job.provider_stack,
            confidence_summary={},
            flags=list(segment.flags),
        )
        session.add(sample)
        session.flush()

        _update_job_progress(
            session,
            job,
            ProgressUpdate(
                step="ocr",
                message=f"Running OCR on segment {processed}/{total}",
                progress=0.4 + (processed / total) * 0.45,
            ),
            progress_callback,
        )
        frame_observations, raw_text, confidence_summary = _ocr_segment(
            settings=settings,
            video_path=video_path,
            ocr_provider=ocr_provider,
            frames_dir=frames_dir,
            segment=segment,
            sample_id=sample.id,
        )
        sample.raw_text = raw_text
        sample.final_text = raw_text
        sample.confidence_summary = confidence_summary
        if not raw_text:
            sample.flags = sorted(set(sample.flags + ["no_text_detected"]))
        if any(bool((observation.metadata_json or {}).get("degraded")) for observation in frame_observations):
            sample.flags = sorted(set(sample.flags + ["ocr_provider_degraded"]))
        for observation in frame_observations:
            observation.sample_id = sample.id
            session.add(observation)
        session.commit()

    summary_path = artifacts_dir / "job_summary.json"
    summary_path.write_text(
        json.dumps({"segment_count": len(segments), "provider_stack": job.provider_stack}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    job.status = "succeeded"
    job.stats = {
        "sample_count": len(segments),
        "artifact_summary_path": relative_to_data(settings, summary_path),
    }
    job.finished_at = utcnow()
    _update_job_progress(
        session,
        job,
        ProgressUpdate(step="completed", message="Finished processing video", progress=1.0),
        progress_callback,
    )
    session.refresh(job)
    return job
