# Delivery verification

Verified on 2026-10-15: Windows, Python 3.11.17, Node.js 24.11.0, 16 logical CPUs. Inference packages: faster-whisper 1.2.1, CTranslate2 4.8.3, Demucs 4.0.1, PyTorch/torchaudio 2.5.1, SoundFile 0.13.1. The initial Python 3.14 API-only environment is separate.

## Real pretrained execution

Whisper Small `Systran/faster-whisper-small@2ec96c5472da50d38d40c0cfe0602af2e94b4c8a` and Demucs `htdemucs/955717e8-8726e21a.th` were downloaded and executed locally. CPU uses int8 ASR and deterministic CPU separation (`shifts=0`, overlap 0.25). A persistent isolated process reuses the separator and can be terminated by its deadline. Runtime requests never download weights or send audio externally.

All seven languages completed both pipelines on one licensed FLEURS speech clip each, with automatic detection and separate manual-language runs. All 14 automatic runs identified the labeled whole-clip language on this tiny sample. This is not an estimate of general detection accuracy. The following values are speech diagnostics, not singing results:

| Language | Direct CER | Vocal CER | Direct seconds | Vocal seconds |
|---|---:|---:|---:|---:|
| Korean | 5.66% | 5.66% | 3.07 | 14.00 |
| Japanese | 4.44% | 4.44% | 2.30 | 4.90 |
| Mandarin | 17.39% | 17.39% | 1.99 | 4.76 |
| English | 1.23% | 1.23% | 1.95 | 4.83 |
| Spanish | 0.71% | 0.71% | 2.31 | 6.40 |
| Portuguese (Brazilian sample) | 2.11% | 1.58% | 2.67 | 7.89 |
| French | 5.49% | 5.49% | 2.12 | 5.04 |

See `evaluation/speech-results.json` and `evaluation/manual-speech-results.json` for raw/normalized texts, per-clip CER/WER, failures, detection, real-time factor, environment and sampled process-tree RSS. Japanese/Mandarin WER is undefined because no validated lexical tokenizer is enabled. These are development diagnostics, not a representative benchmark. Initialization and shared-machine load affect timing. Summed RSS can include retained child models; it is not model-exclusive allocation or VRAM.

## Singing and GPU

Later singing work added the explicitly selected Large-v3 profile with native word alignment. It completed **28/28 real runs on 14 natural-singing clips across all seven targets**: 24 runs have independent corpus orthographic references covering six languages; four Japanese runs have execution/timestamp checks without CER/WER. Before alignment the same Large-v3 profile failed two annotated Direct runs and all four Japanese runs on out-of-range timestamps. Full metrics, restrictions and before/after reports are linked from [SINGING.md](SINGING.md). This is development evidence, not representative singing validation or measured word-level timing accuracy.

Chromium subsequently passed the Large-v3 upload, both pipelines, Unicode edits, seeking, SRT export, responsive layout and contextual region retranscription, including inherited model/revision. Artifacts are in ignored `artifacts/browser-large-v3`. The native backend is running CUDA float16; the Small default remains available. Earlier Docker checks below cover Small, not the newly added Large-v3 profile.

Celestianpower's public-domain English solo singing recording completed real browser upload, both pipelines, editable Unicode text, timestamp seeking and SRT download. The clip is 22.756 seconds. The final browser run measured Direct 1.81s and vocal-assisted 7.13s with the final persistent separator; records are in evaluation/singing-smoke-results.json and browser artifacts. No singing WER/CER is assigned without a manually checked reference. This earlier Small smoke is supplemented by the later natural-singing development comparison across six annotated languages and separate unscored Japanese execution; see [SINGING.md](SINGING.md).

Windows CUDA/float16 ASR also completed on the pinned model and same singing clip. `evaluation/gpu-smoke.json` records the response, settings, 3.00s end-to-end smoke runtime and sampled RSS. This is not a CPU speed comparison. The initial CUDA run lacked `cublas64_12.dll`; explicitly installed cuBLAS 12.9.2.10, cuDNN 9.27.0.42 and NVRTC 12.9.86 resolved it. GPU separation has not been exercised.

## Negative controls and integrity

Original silence and sine-tone controls exposed hallucinated output and a zero-variance separator failure. `control-results.before-silence-guard.json` preserves these failures. Exact all-zero PCM now skips both models, returns no words, makes no automatic language estimate, and records the signal method and `model_executed=false`. Pure-tone hallucinations remain visible in current results. Quiet singing is not discarded by a guessed silence threshold. No reference or corrected lyrics are inferred from model output.

## Software checks

MP4 support: 41 ordinary tests passed, with two opt-in model tests skipped. Real FFmpeg tests cover an MP4 audio container, an H.264/AAC video uploaded with an uppercase extension, original-file preservation and a video without audio. Frontend production build passed. `scripts/mp4_smoke.py` passed Chromium upload, mono 16kHz audio extraction, original hash verification, original-container audio playback and deletion on its own generated H.264/AAC silent video. This checks the format workflow without claiming a new recognition-quality result.

Windows deletion regression: the browser player now pauses, unloads its source and stays detached during DELETE. The API retries transient file locks, reports a recoverable 409 if audio remains in use, preserves the database record until file cleanup succeeds, and can finish deleting a record whose folder was already removed. Regression suite: 38 passed, two opt-in model tests skipped; frontend production build passed. `scripts/delete_smoke.py` verified HTTP 204 and history removal while its own 120-second silence fixture was playing in Chromium. No user recordings were deleted by this diagnostic.

Linux Docker execution was verified with actual singing audio: Direct completed in 3.86s (`evaluation/docker-smoke.json`); the optional CPU-separation image completed both pipelines in 11.24s (`evaluation/docker-separation-smoke.json`). Both images built, services started, model caches were explicitly prepared, and SRT export succeeded. These separate runtime diagnostics are not cross-platform performance comparisons.

The final backend suite completed with **38 passed**, including both opt-in real-model tests. Without `LYRICLENS_SMOKE_AUDIO`, 36 ordinary tests run and two model tests are skipped. The real separation test verifies that successive calls reuse the same process.

The final backend suite includes mocked job integration tests, real FFmpeg format decoding, and opt-in real ASR/separation tests. Coverage includes upload/body/duration limits, corrupt media, FFmpeg failures/deadlines, queue cleanup, restart recovery, cooperative cancellation, active deletion guards, Unicode, original/edit preservation, exports, raw responses, timestamp bounds, exact digital silence, region context/offset mapping, schemas/readiness, normalization and manifest integrity. The real separation test verifies reuse of the same process.

The production TypeScript/Vite build passed. npm audit reported zero vulnerabilities. Chromium exercised real singing, both results, edits, playback seek, SRT export, desktop/mobile layouts and region retranscription. Browser screenshots and responses are in ignored `artifacts/browser`. Automated axe WCAG 2 A/AA and 2.1 A/AA checks found zero violations on upload/results at 1440px and 390px widths after contrast fixes. Automated checks do not replace assistive-technology review.

Docker frontend/backend builds were executed after native real inference. Default packaging uses CPU Direct; optional CPU separation has a dedicated build argument. Native ports are 8011/5181; Docker host ports are 8012/5182, avoiding the unrelated app on port 8000. Exact commands are in the [setup guide](SETUP.md). Models, downloaded audio, environments and browser binaries are ignored by Git.

## Remaining limits

A seven-language singing benchmark still needs appropriately licensed clips and independently verified references, with development/final separation. No singing quality claim comes from speech samples. Region language is user-instructed, not inferred; automatic segment-language detection remains disabled. Large-v3 explicitly enables native word alignment for approximate segment timing; no separate aligner model is used. ASR cancellation waits for the in-process model call; it has no hard deadline. macOS and GPU separation remain unverified. Public deployment needs the controls documented in architecture.
