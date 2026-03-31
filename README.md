# VL2D

VL2D is a lightweight Python-first pipeline for turning subtitle-bearing videos into reviewable speech datasets. The first release ships with:

- `CLI` processing for single videos or folders
- `FastAPI` backend with `SQLite` storage
- a local `worker` process for queued jobs
- a `React` review UI for sample approval and export
- pluggable `VAD`, enhancement, and `OCR` provider interfaces

## Quick Start

1. Install backend dependencies:

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

For real VAD model execution instead of lightweight fallbacks, install the optional ML extras as well:

```bash
uv pip install -e ".[dev,ml]"
```

The default OCR path targets Simplified Chinese subtitles through `paddle_ocr`. Install the Paddle OCR extra and then install a compatible `paddlepaddle` runtime for your CPU or GPU environment:

```bash
uv pip install -e ".[dev,ocr-paddle]"
```

If you prefer the lighter `tesseract_ocr` path instead, install `tesseract` on the host, make sure `chi_sim.traineddata` is available in your `tessdata` directory, and set `VL2D_DEFAULT_OCR=tesseract_ocr`.

The detailed setup and integration rules for both OCR providers are documented in [`docs/provider-integration.md`](docs/provider-integration.md).

2. Start the web stack:

```bash
vl2d web --host 0.0.0.0 --port 8000
```

3. In a second terminal, start the frontend:

```bash
nvm use
cd web
npm install
npm run dev
```

4. Open the frontend URL shown by Vite and upload a video.

## CLI

Process a local file and export a dataset zip:

```bash
vl2d run /path/to/video.mp4 --export
```

Process all supported videos inside a folder sequentially:

```bash
vl2d run /path/to/video-folder --export
```

VL2D currently accepts `MP4` and `MOV` input files across the CLI, Web upload flow, and backend API. When the CLI input is a directory, VL2D scans it recursively and processes every supported video it finds.

By default, CLI export includes all generated samples because pure CLI mode has no review step. To export only approved samples:

```bash
vl2d run /path/to/video.mp4 --export --approved-only
```

List registered providers:

```bash
vl2d providers list
```

Check local runtime prerequisites for the current OCR setup:

```bash
vl2d doctor
```

## Notes On Providers

The repository includes:

- mock / lightweight providers that work out of the box
- built-in adapters for `silero-vad`, `SEMamba`, `Tesseract OCR`, and `PaddleOCR`

The real heavy model stacks are optional. When those dependencies or language packs are absent, the adapters degrade to non-recognizing fallback behavior with explicit metadata so the pipeline stays runnable without inventing fake OCR text.

The default SEMamba checkpoint path is `model/g_00587000.pth`. Override it with `VL2D_SEMAMBA_CHECKPOINT_PATH` if you need a different checkpoint.

## Layout

- `src/vl2d/`: backend package
- `web/`: React frontend
- `tests/`: backend tests
- `docs/`: project docs
