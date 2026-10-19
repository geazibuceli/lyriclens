# Architecture and API

Optional text translation runs after ASR in a separate bounded single-thread worker. The M2M100 CPU/int8 model is prepared explicitly and loaded from a separate local cache. Each translation persists a hash and snapshot of the saved source segments, model provenance, generated output and independent edits under the job's `translations` map. Source edits mark translations stale; stale exports are rejected. Job deletion is blocked until active translation finishes or acknowledges cancellation. See [TRANSLATION.md](TRANSLATION.md) for lifecycle, API and limits.

React/TypeScript calls localhost FastAPI (native frontend 5181, backend 8011). One daemon worker consumes a bounded queue of eight waiting jobs and runs one pipeline operation at a time. Recognition loads models on demand and caches up to two configurations. The separator uses a persistent isolated process with an operation deadline. First-call timing includes initialization. ASR and separation devices are configured separately. An OS file lock protects the data directory; use one Uvicorn worker without reload during jobs. SQLite uses short connections and a process-local mutation lock.

Files live under generated UUID directories: `original` is immutable uploaded audio; `decoded.wav` is separately resampled mono 16 kHz PCM, stems and `vocals-16k.wav` are derived; `direct-raw.json` and `vocals-raw.json` preserve the emitted response before segment validation. SQLite stores display filename, hash, bytes, request, settings, selected revision, environment versions, decoding information, timings, results, edits, warnings, failures, and UTC timestamps. Nothing derives a storage path from a user filename. Public responses omit storage paths and stack traces. Detailed exceptions remain in local logs. Deleting a stopped job removes all its artifacts and database metadata. There is no automatic retention cleanup.

Allowed lifecycle: queued → processing → completed/failed/canceled/interrupted. A cancel request marks intent; the worker checks before/after operations. Active CTranslate2 calls cannot be interrupted safely from this thread. There is no enforceable in-process inference timeout; use an isolated process/OS deadline if strict runtime termination is required. FFmpeg and Demucs subprocesses have enforceable timeouts. Restart converts unfinished queued/processing jobs to interrupted; no silent retries. Shutdown waits briefly and marks interrupted if cooperative exit occurs; a later startup also recovers unfinished jobs. Model outputs completed before cancellation may remain preserved but the job is canceled.

One pipeline succeeding makes the job completed; inspect each pipeline's state for partial failure. Results are never merged. Text edits and original segments are stored separately. JSON export contains full provenance, both pipelines, and both original/edited versions. TXT/SRT use saved edits unless `original=true`. Unsuccessful pipelines retain failure messages and, where available, raw response artifacts.

FFmpeg receives an argument array with restricted input protocols, the first audio stream, video disabled, a decode deadline and an output limit of the configured duration plus one second. Duration is measured from decoded samples, with silence retained for identity timestamp mapping. Separated audio must retain duration within 100 ms. Segment starts must be finite, nonnegative and ordered; ends must be later than starts and within the recording. Overlapping segments retain their model-generated times.

Uploads are restricted to four display extensions, then actually decoded for validity. Both streamed multipart body size and file bytes are bounded; multipart overhead allowance is 64 KiB. HTTP uploads are spooled by Starlette before handler processing; decoding and model inference run only in the worker. A corrupt or too-long upload becomes a failed job. Its original is preserved for inspection; partial decode/stem artifacts are removed. Use OS isolation before accepting remote hostile media.

## Endpoints

Interactive request/response JSON schemas for Job, PipelineResult, ModelReadiness, Edit and Segment are at `/docs`. All errors use `{ "detail": "message" }` (framework validation can use a detail array).

| Method | Route | Contract |
|---|---|---|
| GET | `/api/health` | Application and worker liveness; no model initialization |
| GET | `/api/models` | Preparation state, configured model/revision, device, limits, target languages; no download |
| POST | `/api/jobs` | Multipart `file`, `language` (`auto/ko/ja/zh/en/es/pt/fr`), `pipeline` (`direct/vocals/both`); 202 Job |
| GET | `/api/jobs` | Newest-first Job array |
| GET | `/api/jobs/{id}` | Job with current state, stage, provenance and results |
| GET | `/api/jobs/{id}/audio` | Original bytes with byte-range support through FileResponse |
| PUT | `/api/jobs/{id}/edit` | `{pipeline: "direct" or "vocals", segments: [{start: seconds, end: seconds, text: string}]}`; updated Job |
| POST | `/api/jobs/{id}/cancel` | Cooperative cancellation request; Job |
| POST | `/api/jobs/{id}/retranscribe` | JSON `language` (manual target), `pipeline`, `start`, `end`, `context_seconds` (0–10, default 2); 202 separate Job |
| GET | `/api/jobs/{id}/export` | Query `pipeline`, `format=txt/json/srt`, `original=false`; download |
| GET | `/api/jobs/{id}/raw` | Query `pipeline`; raw adapter response artifact |
| DELETE | `/api/jobs/{id}` | 204; 409 while queued/processing |

Job fields: `id`, `filename`, `sha256`, `bytes`, `state`, `stage`, `requested_language`, `pipelines`, `model_id`, `revision`, `inference`, `environment`, `created_at`, `started_at?`, `completed_at?`, `cancel_requested`, `audio?`, `decode_seconds?`, `total_seconds?`, `error?`, `results`. Each result key is `direct` or `vocals`; successful values contain `state`, `original` (segments), `original_text`, `edited` (segments or null), `edited_at?`, `detected_language`, `language_source`, `warnings`, `seconds`, and `provenance`. Failed results contain `state`, `error`, `seconds`. Missing optional fields mean the stage has not completed.

Adapters are protocols in `adapters.py` for decoding, transcription, separation and optional alignment. The explicit Large-v3 profile activates Whisper native word alignment inside the ASR adapter to refine segment boundaries. There is no separate alignment model; raw returned words are retained and the UI still uses approximate segments. Tests inject fake adapters through `create_app`, without a production mock mode or placeholder transcript endpoint.

Region jobs preserve their own full original file and source-job identifier. The selected interval is expanded by bounded context, extracted to a separately named PCM file, then transcribed. Raw model timestamps remain relative to the region; validated display/export segments add the recorded offset into the full clip. Both region-local and original bounds are checked. No inference-based segment language annotation is claimed. A user-selected language is a recorded instruction.

Exact all-zero PCM is a defensible digital-silence signal. That case skips both models and records `model_executed=false`, a null raw model response and the signal-control method. It is not a voice-activity classifier. Pure-tone and instrumental hallucinations remain possible; failed negative controls are preserved for review.
