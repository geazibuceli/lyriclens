# LyricLens

Local multilingual transcription of music clips up to **10 minutes** and **150 MiB** by default. Upload your own audio, select a language, review approximate segment timestamps, edit the result, and export TXT, JSON, or SRT. Override these limits with `LYRICLENS_MAX_SECONDS` and `LYRICLENS_MAX_BYTES`. LyricLens recognizes audio with pretrained models. It never searches for songs or retrieves, completes, translates, or romanizes lyrics.

## Features

- **Seven language choices:** Korean, Japanese, Mandarin Chinese, English, Spanish, Portuguese and French, plus automatic whole-clip detection.
- **Two recognition routes:** transcribe the original audio directly or isolate vocals with Demucs; compare both outputs side by side.
- **Explicit model selection:** lighter Whisper Small or experimental Large-v3 with native alignment.
- **Review and editing:** play the source audio, seek to approximate segment times, preserve Unicode, edit text and segment boundaries, and export TXT, JSON or SRT.
- **Local job history:** SQLite persistence, bounded processing, cancellation, deletion and recovery of interrupted jobs.
- **Passage retranscription:** select a region and another language instruction while preserving original-clip timestamps and model provenance.
- **Measured diagnostics:** real-model execution records, singing experiments, negative controls and reproducible evaluation scripts.

Runtime processing stays local. Model weights are prepared explicitly; uploaded audio is not sent to an external transcription service. Singing recognition remains imperfect: fluent text and successful execution do not prove accuracy.

## Repository layout

```text
lyriclens-app/
  backend/       FastAPI API, inference adapters, worker, storage and tests
  frontend/      React and TypeScript application
  scripts/       Local launch helpers and reproducible diagnostic scripts
  evaluation/    Evaluation manifests and recorded results
  docs/          Architecture, model review, limitations and verification
  compose.yaml   Docker services
```

## Contents

- [Native setup](#native-setup)
- [Models and explicit preparation](#models-and-explicit-preparation)
- [Explicit larger model for singing](#explicit-larger-model-for-singing)
- [What works and what is unverified](#what-works-and-what-is-unverified)
- [Verification](#verification)
- [Experimental mixed-language workflow](#experimental-mixed-language-workflow)
- [Docker](#docker)
- [License](#license)

## Native setup

Uploads support WAV, MP3, FLAC, M4A and **MP4**. For MP4 videos, FFmpeg extracts the first audio track; video frames are ignored. The original file is retained and playback uses its audio. Videos without an audio track fail with an explanatory message. Extracted audio is limited to 10 minutes; the 150 MiB upload limit applies to the entire video file. Uncommon audio codecs may not play in every browser.

Use Python **3.11** for the full stack, particularly optional Demucs with PyTorch 2.5.1. Native Windows inference was exercised with Python 3.11.17 and Node.js 24.11.0. The lightweight API/tests also run on Python 3.14; native inference on 3.14 is not verified. Linux CPU packaging is supplied through Docker. macOS execution remains unverified.

If Python 3.11 is missing on Windows, install it with `winget install --id Python.Python.3.11 -e` and reopen the terminal. Node.js can be installed with `winget install --id OpenJS.NodeJS.LTS -e`.

Install FFmpeg and verify `ffmpeg -version`. On Windows: `winget install --id Gyan.FFmpeg -e`, then open a new terminal. On Debian/Ubuntu: `sudo apt-get update && sudo apt-get install ffmpeg`. On macOS: `brew install ffmpeg`. Set `LYRICLENS_FFMPEG` to an absolute executable path if necessary. Follow [FFmpeg's official download links](https://ffmpeg.org/download.html) for other distributions.

Start at the repository root, in PowerShell. The first command enters the application directory; subsequent backend commands use that directory unless stated otherwise:

```powershell
cd lyriclens-app
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './backend[inference,test,tools,evaluation]'
# Explicit network download of the pinned multilingual model; reuses local files.
.\.venv\Scripts\python.exe -m lyriclens.models download
.\.venv\Scripts\python.exe -m uvicorn lyriclens.api:app --host 127.0.0.1 --port 8011
```

In another terminal, starting at the repository root:

```powershell
cd lyriclens-app/frontend
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5181. The frontend proxies `/api` to localhost:8011; API schemas are at http://127.0.0.1:8011/docs. These ports avoid the unrelated application already using port 8000 in the development workspace. In Bash, use `python3.11 -m venv .venv`, `.venv/bin/python`, and `npm` instead. The default data directory is always `lyriclens-app/data`, independent of the working directory. An explicit relative `LYRICLENS_DATA` is resolved from the current directory. `.env.example` is **not automatically loaded**; set environment variables in the shell, for example `$env:LYRICLENS_MAX_SECONDS='45'`. The `tools` extra supplies a bundled FFmpeg executable when none is on PATH; no runtime binary download is performed.

In the prepared IDE workspace, the local runtime is at the repository root in `.venv311`. From that root, run `.\.venv311\Scripts\python.exe -m uvicorn lyriclens.api:app --host 127.0.0.1 --port 8011`; run `npm.cmd run dev` inside `lyriclens-app/frontend`. Weights are already prepared in `lyriclens-app/data`. PowerShell helpers are in [run-backend.ps1](lyriclens-app/scripts/run-backend.ps1) and [run-frontend.ps1](lyriclens-app/scripts/run-frontend.ps1).

## Models and explicit preparation

The default is `Systran/faster-whisper-small`, revision `2ec96c5472da50d38d40c0cfe0602af2e94b4c8a`. The download command retrieves its CTranslate2 weights and tokenizer/configuration from Hugging Face into a revision-specific local directory. Verified weight-file size: **483,546,902 bytes**, plus about 2.7 MB of configuration/tokenizer files. Optional Demucs checkpoint size: **84,141,911 bytes**. No audio is sent, and no weights are committed to this repository.

Change `LYRICLENS_MODEL` and `LYRICLENS_REVISION` together to select another compatible multilingual CTranslate2 repository. Prepare it explicitly. Custom models are not verified options; the server exposes its selection through `/api/models`. There is no automatic fallback, and runtime loading is local-only. A `READY.json` marker means preparation finished, not that hardware inference was validated. `/api/models` distinguishes preparation and FFmpeg availability from `/api/health`, which never loads or downloads a model.

For optional vocal separation, in the **Python 3.11** environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e './backend[separation]'
.\.venv\Scripts\python.exe -m lyriclens.models separation-download
```

This explicitly downloads Meta's `htdemucs` checkpoint `955717e8-8726e21a.th` and checks its published SHA-256 prefix. Demucs 4.0.1 uses that local repository only. Upstream is archived/unmaintained, so separation is isolated and optional. A missing or failed separator does not prevent Direct from completing. Comparing both runs preserves separate outputs and timing; outputs are never merged.

Verified CPU profile: `LYRICLENS_DEVICE=cpu`, `LYRICLENS_COMPUTE=int8`, `LYRICLENS_SEPARATION_DEVICE=cpu`. Verified Windows ASR GPU profile: install `pip install -e './backend[cuda-windows]'`, then set `LYRICLENS_DEVICE=cuda` and `LYRICLENS_COMPUTE=float16`. These explicitly installed CUDA 12 cuBLAS/cuDNN 9 DLLs are discovered locally; no fallback occurs. Demucs has a separate device setting and stays on CPU unless explicitly changed; GPU separation requires a compatible PyTorch CUDA build and has not been tested. Diagnostic process-tree memory peaks and timings are in the evaluation reports, not hardware minimum guarantees. Apple Metal acceleration is not implemented. Run `python -m lyriclens.doctor` for a no-download prerequisite check.

## Explicit larger model for singing

The upload form offers **Whisper Large-v3 (experimental)** as a per-job choice. Prepare it with `python -m lyriclens.models download --profile large-v3`; verified weight-file size is 3,087,284,237 bytes plus tokenizer/configuration. Its pinned revision is `edaa852ec7e145841d8ffdb056a99866b5f0a478`. Small remains the default. Region retranscription inherits the parent's model, revision and device. Missing weights never trigger a request-time download. The worker retains at most two recognition model instances; memory depends on their combination.

Large-v3 with native alignment completed both routes on all 12 annotated development singing clips (24 runs), with lower error on several languages than Small. It corrected the out-of-range segment ends observed before alignment. This does **not** solve singing generally: Japanese quality is unscored, and the samples mostly lack accompaniment. Read the [singing results and limitations](lyriclens-app/docs/SINGING.md) before interpreting these measurements. Both models have now executed on natural singing across all seven languages.

## What works and what is unverified

Implemented: bounded single-process worker, persistent SQLite jobs and recovery, configurable byte/duration limits, original-file retention, FFmpeg decoding, local model adapters, seven manual language codes and automatic detection, both pipelines, Unicode editing, playback, seek controls, side-by-side results, exports, raw-response access, cancellation, guarded deletion, and a manifest evaluation runner.

Ordinary job integration tests use deterministic adapters; format tests additionally invoke real FFmpeg. Real Whisper Small and Demucs executions completed for **all seven languages on licensed FLEURS speech samples**, including both automatic detection and manual overrides. A public-domain English singing recording also completed both pipelines through the browser. CPU and Windows CUDA ASR were exercised. These small diagnostic samples do not validate singing accuracy across seven languages. See the [capability table](lyriclens-app/docs/MODELS.md), [measured results](lyriclens-app/docs/VERIFICATION.md), and [evaluation protocol](lyriclens-app/docs/EVALUATION.md).

The [verification record](lyriclens-app/docs/VERIFICATION.md) distinguishes mocked tests, actual decoding, real inference, browser interaction, accessibility checks, Docker checks, and remaining dataset limitations. No reference transcript was inferred from model output.

Automatic detection is an estimate for the whole clip. It may return a language outside the seven targets, which is preserved without relabeling. Manual language is a user instruction, not a verified fact. Portuguese output is not regional dialect detection. Mandarin support does not imply every Chinese variety. Source writing systems and diacritics are preserved; no Chinese script conversion is applied.

Singing, heavy accompaniment, rap, overlapping voices, live audio, effects, and language switching may produce wrong words or hallucinations. Empty output is allowed. Fluent output is not evidence of accuracy. Whisper thresholds are not a reliable vocal detector: real negative controls produced hallucinations, preserved in `evaluation/control-results.before-silence-guard.json`. Exact all-zero PCM now bypasses ASR/separation with an explicit recorded signal-control reason; this does not classify quiet singing as silence. A pure-tone control can still produce hallucinated words, preserved in the current report. VAD remains disabled because speech VAD may remove singing. Raw scores are uncalibrated. Invalid timestamps fail that pipeline and preserve raw output; no word timing is invented.

## Verification

Run these commands from the application directory (`lyriclens-app`):

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm.cmd ci
npm.cmd run build
```

`backend/requirements-test-lock.txt` records the resolved lightweight API/test dependency set verified on Windows Python 3.14. For that exact test environment, install it with `python -m pip install -r backend/requirements-test-lock.txt`, then `python -m pip install --no-deps -e backend`. Inference dependencies are pinned at the top level in `pyproject.toml`; their native transitive wheels remain platform-specific and are not claimed as a cross-platform locked environment.

`backend/requirements-windows-py311-lock.txt` additionally records the complete verified Windows Python 3.11 inference/separation/evaluation environment, including the explicitly installed CUDA wheels. Use it only for that platform/profile; it is not a cross-platform lock or a GPU-driver installer.

To reproduce browser checks after starting both native servers, from the application directory (lyriclens-app):

```powershell
python -m pip install -e './backend[browser,fixtures]'
python -m playwright install chromium
python scripts/prepare_singing_smoke.py
python scripts/browser_smoke.py
python scripts/accessibility_smoke.py
```

The browser script uses real local models, checks desktop/mobile layouts and exports, and retranscribes a passage with original-clip timestamp mapping. Accessibility uses the locally installed axe-core from `npm ci`. Reports/screenshots go to ignored `artifacts/browser`. See [evaluation instructions](lyriclens-app/docs/EVALUATION.md) for the seven-language licensed speech diagnostics and negative controls.

Optional real-model test, after preparation and FFmpeg setup:

```powershell
$env:LYRICLENS_SMOKE_AUDIO='C:\authorized-audio\clip.wav'
$env:LYRICLENS_SMOKE_LANGUAGE='pt'
.\.venv\Scripts\python.exe -m pytest backend/tests -k real_model_smoke -v
```

This verifies execution and timestamp validity, not transcript accuracy. CI does not download weights or require GPU access. See [architecture/API](lyriclens-app/docs/ARCHITECTURE.md), [troubleshooting](lyriclens-app/docs/TROUBLESHOOTING.md), and [third-party attribution](lyriclens-app/docs/MODELS.md).

## Experimental mixed-language workflow

Whisper's native multilingual options do not establish reliable segment-level language annotation on singing. The normal workflow uses one whole-clip instruction or estimate. In a completed transcript, open **Experimental: retranscribe a passage in another language**, choose a passage and language, then run it. A separate job processes that region with two seconds of surrounding context. Timestamps map back to the original full clip; the original job and full audio are retained. Region language is explicitly a user instruction, never inferred annotation. JSON retains the selected/context boundaries and offset. Whole-clip “Run again” remains available. The Large-v3 experimental profile enables native Whisper word alignment to refine segment boundaries. Small retains its original decoding settings. No separate alignment model is downloaded; times remain approximate.

## Docker

Native real inference and the Docker builds were exercised. CPU Direct is included by default:

The default Linux image completed real Direct inference and exports; the optional CPU-separation image also completed both pipelines. Recorded results are linked in the verification report.

```sh
# Start at the repository root.
cd lyriclens-app
docker compose build
docker compose run --rm backend python -m lyriclens.models download
docker compose up
```

Open http://127.0.0.1:5182 (Docker backend host port 8012). Persistent data is in `lyriclens-data`. For optional CPU separation, build with `docker compose build --build-arg WITH_SEPARATION=true backend`, then explicitly run `docker compose run --rm backend python -m lyriclens.models separation-download`. This optional image adds CPU-only PyTorch wheels. Do not expose the local MVP publicly without authentication, authorization, origin/CSRF protection, TLS, process/network isolation, quotas, proxy body limits and OS resource limits.

## License

Project source is provided under the [MIT license](lyriclens-app/LICENSE). Models, dependencies and evaluation datasets have independent licenses and attribution requirements documented in the [model review](lyriclens-app/docs/MODELS.md) and [singing evaluation](lyriclens-app/docs/SINGING.md). Model weights, local environments and downloaded research audio are excluded from the repository.
