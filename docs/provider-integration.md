# VL2D Provider Integration Guide

This document describes how VAD, enhancement, and OCR modules integrate into the VL2D pipeline, how to add a new provider, and how the built-in providers are expected to behave.

## 1. Pipeline Boundaries

VL2D processes one video through these stages:

1. Extract mono audio from the source video with `ffmpeg`
2. Run a VAD provider to detect speech segments
3. Cut each segment and pass it through an enhancement provider
4. Sample video frames inside each segment and pass ROIs to an OCR provider
5. Aggregate OCR observations into sample text
6. Persist `Sample` / `FrameObservation` records in SQLite
7. Expose results through CLI export and the Web review UI

Each provider is responsible only for its own stage. The pipeline owns artifact paths, DB writes, retries, and result aggregation.

## 2. Provider Contracts

Provider interfaces live in [`src/vl2d/providers/base.py`](../src/vl2d/providers/base.py).

### VAD

- Interface: `VADProvider.detect(audio_path, sample_rate) -> list[SpeechSegment]`
- Input: mono WAV path and target sample rate
- Output: ordered `SpeechSegment` objects in milliseconds
- Requirements:
  - do not write DB state
  - return empty list instead of raising when there is simply no speech
  - raise only for real execution failures

### Enhancement

- Interface: `EnhancerProvider.enhance(segment_path, output_path) -> AudioArtifact`
- Input: a single segment WAV and the target output path
- Output: `AudioArtifact` with the final file path and metadata
- Requirements:
  - write the enhanced artifact to `output_path`
  - keep sample rate / channels consistent with pipeline expectations unless explicitly documented

### OCR

- Interface: `OCRProvider.recognize(frame_path, roi) -> OCRObservation`
- Input: a cropped frame path and ROI metadata
- Output: `OCRObservation` with recognized text, confidence, and metadata
- Requirements:
  - never invent placeholder text
  - when OCR is unavailable or degraded, return `text=""` and set `metadata.degraded=true`
  - keep diagnostic reasons in `metadata.reason`

## 3. Built-in Providers

### VAD

- `silero_vad`: preferred production VAD when `silero-vad` and `torch` are installed
- `energy_vad`: lightweight fallback for tests and CPU-only local runs

### Enhancement

- `semamba`: integration shell for the external SEMamba stack
- `passthrough_enhancer`: copies audio without enhancement; useful for tests and fallback

### OCR

- `paddle_ocr`: default OCR provider for Chinese subtitles; Python-side PaddleOCR adapter
- `tesseract_ocr`: alternative OCR provider; runs the `tesseract` CLI with language `chi_sim` by default
- `paddleocr_vl`: compatibility alias that resolves to the same PaddleOCR implementation as `paddle_ocr`
- `mock_ocr`: non-recognizing fallback used only for tests or explicit fallback scenarios

## 4. Default OCR Strategy For Chinese Subtitles

VL2D now defaults to `paddle_ocr` because:

- it is the better fit for the current requirement of recognizing Chinese subtitles directly from video frames
- it keeps the default OCR stack inside Python instead of shelling out to an external CLI
- the project still keeps `tesseract_ocr` available as a simpler alternative when that deployment model is preferable

Required runtime pieces:

1. Install the optional package extra: `uv pip install -e ".[dev,ocr-paddle]"`
2. Install a compatible `paddlepaddle` runtime for your CPU or GPU environment
3. Keep `VL2D_DEFAULT_OCR=paddle_ocr` or select `paddle_ocr` in job payloads

Useful runtime settings:

- `VL2D_DEFAULT_OCR=paddle_ocr`
- `VL2D_PADDLE_OCR_LANG=ch`
- `VL2D_PADDLE_OCR_USE_ANGLE_CLS=true`

Validation checklist:

1. Install `paddleocr` and a compatible `paddlepaddle` runtime
2. Start VL2D and process a small video
3. Check the Web sample card: there should be no degraded OCR warning
4. Inspect a `FrameObservation.metadata_json` entry and confirm `provider` is `paddle_ocr`
5. Inspect exported `manifest.jsonl` and verify Chinese subtitle text is present

## 5. Tesseract OCR As An Alternative

Use `tesseract_ocr` when you want a lighter OCR path based on the host `tesseract` binary instead of the Paddle runtime.

Required runtime pieces:

1. `tesseract` binary installed on the host
2. `chi_sim.traineddata` installed in the active `tessdata` directory
3. Optional `VL2D_TESSDATA_PREFIX` if your traineddata directory is not on the default search path
4. Set `VL2D_DEFAULT_OCR=tesseract_ocr` or choose `tesseract_ocr` in job creation payloads

Useful runtime settings:

- `VL2D_DEFAULT_OCR=tesseract_ocr`
- `VL2D_TESSERACT_CMD=tesseract`
- `VL2D_TESSERACT_LANG=chi_sim`
- `VL2D_TESSERACT_PSM=6`
- `VL2D_TESSERACT_OEM=1`
- `VL2D_TESSDATA_PREFIX=/path/to/tessdata`

Implementation notes:

- VL2D runs `tesseract` with `--psm`, `--oem`, and the configured language pack
- if the configured language pack is missing, the provider degrades cleanly instead of inventing text
- `VL2D_TESSDATA_PREFIX` is passed through to the child process when set

Validation checklist:

1. Run `tesseract --list-langs`
2. Confirm `chi_sim` is listed
3. Set `VL2D_DEFAULT_OCR=tesseract_ocr`
4. Start VL2D and process a short Chinese-subtitle clip
5. Confirm the sample card shows OCR text instead of a degraded warning

## 6. Adding A New Provider

### Step 1: Create the provider class

Add a new module under `src/vl2d/providers/` and implement one of the provider base classes.

Example OCR skeleton:

```python
from pathlib import Path

from vl2d.config import Settings
from vl2d.domain import OCRObservation
from vl2d.providers.base import OCRProvider


class MyOCRProvider(OCRProvider):
    name = "my_ocr"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def recognize(self, frame_path: Path, roi: dict[str, float] | None = None) -> OCRObservation:
        return OCRObservation(
            text="",
            confidence=0.0,
            frame_time_ms=0,
            roi=roi,
            metadata={"provider": self.name, "degraded": True, "reason": "not implemented"},
        )
```

### Step 2: Register it

Add the provider to [`src/vl2d/providers/__init__.py`](../src/vl2d/providers/__init__.py).

Examples:

- `registry.register_vad("my_vad", MyVADProvider)`
- `registry.register_enhancer("my_enhancer", MyEnhancerProvider)`
- `registry.register_ocr("my_ocr", MyOCRProvider)`

### Step 3: Select it at runtime

You can select providers through:

- environment defaults in [`src/vl2d/config.py`](../src/vl2d/config.py)
- Web/API job creation payloads
- CLI runs by setting environment variables before execution

Example:

```bash
export VL2D_DEFAULT_OCR=paddle_ocr
export VL2D_PADDLE_OCR_LANG=ch
vl2d web
```

### Step 4: Preserve degradation semantics

If the provider cannot run because a binary, model, or language pack is missing:

- return empty text instead of fake content
- set `metadata.degraded=true`
- attach a human-readable `metadata.reason`
- let the pipeline mark the sample with `ocr_provider_degraded`

This rule keeps the UI and exported dataset honest.

## 7. Module-Specific Integration Notes

### VAD modules

- Input must be a WAV file already normalized by the pipeline
- Segment times must be in milliseconds
- Leave merge/split policy to the pipeline when possible

### Enhancement modules

- The pipeline already handles segment cutting
- The provider should focus only on producing the enhanced artifact
- Store model/runtime details in `AudioArtifact.metadata`

### OCR modules

- The pipeline passes already-cropped subtitle ROI images
- Return raw OCR text only; text normalization and de-duplication happen in the pipeline
- Confidence should be numeric and comparable across observations from the same provider
- Put engine-specific diagnostics in `metadata`, for example language, angle-classifier mode, or missing-model notes
- Do not overload `raw_text` with fallback markers; degraded execution must stay empty-text and metadata-driven

## 8. Testing Requirements

When adding or changing a provider:

1. Add at least one unit test for provider-specific parsing / error handling
2. Add or update a registry test so the provider appears in `vl2d providers list`
3. If the provider depends on external binaries or weights, test the degraded path as well as the happy path

## 9. Troubleshooting

### OCR shows degraded warnings

Check:

- `tesseract --version`
- `tesseract --list-langs`
- whether `chi_sim` appears in the language list when using `tesseract_ocr`
- whether `VL2D_TESSDATA_PREFIX` points at the correct tessdata directory
- whether `paddleocr` and a compatible `paddlepaddle` runtime are installed when using `paddle_ocr`

### OCR text is empty

Possible causes:

- the OCR provider is degraded
- the sampled subtitle ROI does not contain readable text
- the selected OCR provider is pointed at the wrong language or missing the right runtime

### Exported samples have empty text

If the OCR provider was degraded, VL2D intentionally leaves text empty instead of exporting fabricated placeholder text.

## 10. Official References

- Tesseract command-line usage: https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html
- Tesseract data files and language codes: https://tesseract-ocr.github.io/tessdoc/Data-Files.html
- Official `tessdata_best` repository: https://github.com/tesseract-ocr/tessdata_best
- PaddleOCR quick start: https://www.paddleocr.ai/v3.0.2/en/version2.x/ppocr/quick_start.html
- PaddleOCR installation guide: https://www.paddleocr.ai/latest/en/version3.x/installation.html
- PaddleOCR installation guide: https://www.paddleocr.ai/latest/en/version3.x/installation.html
