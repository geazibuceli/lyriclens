# Troubleshooting

| Symptom | Action |
|---|---|
| Server starts but processing is disabled | Check `/api/models`; install FFmpeg and explicitly prepare the model. Health does not mean model-ready. |
| FFmpeg unavailable | Run `ffmpeg -version` in the same shell; reopen the terminal after install or set `LYRICLENS_FFMPEG` to its executable. |
| Model download fails | Check network/proxy, disk space, repository and pinned revision. Run preparation again; no model is substituted. Runtime remains offline. |
| Python 3.14 cannot install inference/separation | Create the documented Python 3.11 environment. API-only tests on 3.14 do not verify native inference wheels. |
| CUDA/cuDNN library error | Verify upstream CUDA 12/cuDNN 9 requirements and matching CTranslate2/PyTorch builds, or explicitly select CPU/int8. |
| Demucs fails or is missing | Prepare optional dependencies/checkpoint in Python 3.11, or select Original audio. Archived Demucs may require maintenance. |
| Torchaudio cannot load PCM WAV | Install the complete separation dependency group, including SoundFile 0.13.1. The verified Windows profile needs that audio backend. |
| `cublas64_12.dll` missing on Windows | Install the explicit `cuda-windows` extra, restart the backend, and use CUDA/float16. No CPU fallback is performed. GPU drivers are separate prerequisites. |
| Port 8000 is occupied | Native LyricLens uses 8011 (API) and 5181 (UI); Docker uses 8012/5182. Leave unrelated services running. |
| Cancellation takes a long time | Cancellation waits for the active model call. Decode and separation have subprocess deadlines; in-process ASR has no hard deadline. |
| Queue full | Wait for a job to stop. Concurrency is intentionally one inference call. |
| Job becomes interrupted | The server restarted or shut down before completion. Reuse the original audio with Run again; unfinished jobs are not silently resumed. |
| Invalid or corrupt audio | Re-export to WAV/FLAC and try again. Extension alone does not prove format validity. |
| Transcript is empty/wrong | Select language manually, compare vocal separation, try clearer/longer audio within the limit, or edit. Instrumental sections should have no words; model hallucinations remain possible. |
| Wrong writing system | Check manual language and original audio. No translation or romanization is requested; preserve raw output for diagnosis. |
| Invalid model timestamps | That pipeline fails instead of manufacturing/clamping timing. Inspect its raw response, change model/settings only with development evaluation. |
| Edits missing from export | Click Save edits first. JSON includes original and edits; original TXT exports intentionally ignore edits. |
| Second server cannot start | Stop the first server using that data directory. The OS lock is released on process exit; do not delete live data. |
| `npm.ps1` is blocked in PowerShell | Use `npm.cmd ci` and `npm.cmd run dev`. No execution-policy change is needed. |

Logs contain processing stages and job identifiers, with detailed failures only in the local server console. Export JSON for reproducibility, but review its display filename, transcript and environment details before sharing it. Audio and transcripts remain until explicitly deleted. Interrupted and failed originals are deliberately preserved.
