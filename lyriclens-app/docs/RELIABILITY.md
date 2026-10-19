# Review tools, recovery and workspace maintenance

## Undo, redo and keyboard review

Each transcript editor has **Undo transcript edit** and **Redo transcript edit** controls. They cover text, language labels, timings, segment removal and additions. Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y redoes, and Ctrl/Cmd+Enter saves. Saving preserves the open editor history; undoing a saved edit changes the draft until you save again. Exports continue to use saved text.

History is local to the currently open transcript editor, capped at 50 changes and two million serialized characters in each direction; large transcripts keep fewer steps. It is not a persistent revision archive. Reloading or switching jobs discards undo history; browser drafts can recover unsaved editor content with an explicit restore action. See [EDITING.md](EDITING.md) for draft limits, split/merge, search, bilingual exports and backups. Translation editing retains its separate save flow; transcript shortcuts do not intercept translation fields.

Choose **Load audio waveform** below the original audio player. The server decodes the full original into temporary mono PCM16, returns at most 1200 amplitude peaks, and removes the temporary file. It does not recognize words, remove silence or alter timestamps. Use **Waveform position seconds** or its arrow keys to seek. Seeking stops segment repeat. Amplitude is not a word-boundary or confidence estimate. Waveform loading requires FFmpeg and a readable original recording.

Review suggestions flag passages longer than 20 seconds, identical adjacent text and some repeated text patterns. They do not change text or estimate a calibrated probability of error. Choruses can legitimately repeat. The existing direct/vocal comparison exposes disagreements separately. These tools help listening and correction; they do not establish lower CER/WER.

## Resume stopped work

The server marks queued/processing jobs and translations **interrupted** on startup. It does not silently restart expensive work. Open the job and choose **Resume unfinished transcription**. Completed routes, raw output, saved edits and translations are retained. Only unfinished/failed recognition routes run again, with the same original, model revision and job configuration. An unfinished recognition route starts from the beginning; there is no partial decoder or in-model checkpoint. A completed job with a failed second route can also retry that route.

Resume requires the original recording to exist and match its stored SHA-256. Active work and full queues are rejected; a rejected submission restores the previous saved state. Model/dependency failures remain visible. Region and multilingual instructions remain part of the saved job.

Translation persists each completed segment with its progress count. **Resume translation from saved segments** continues a stopped translation from that checkpoint using the saved source snapshot and language instructions. Changed source text or language labels require a new translation. Checkpoints created before segment persistence was introduced may have no saved segments and therefore restart from the beginning. A crash during one model call repeats only that unfinished segment; it does not claim a checkpoint inside inference. Model downloads remain explicit.

## Progress

Active recognition shows the actual stage, elapsed time in the current attempt and recorded stage transitions. Decoding, region extraction, vocal separation, recognition and multilingual passage stages have distinct labels. Earlier completed routes remain visible after resume. Translation shows completed segments, a segment-count progress bar and elapsed time for the current attempt. There is no invented ASR percentage or reliable remaining-time estimate. Cancellation waits for the current operation to return.

## Environment and storage

**Environment checks** runs on workspace load and can be refreshed. The Windows launcher also prints setup notices. Checks cover FFmpeg, recognition and optional separation dependencies, prepared ASR profiles, the separation checkpoint and the configured CTranslate2 device/compute support. No inference, installation or download is triggered. A successful device check does not guarantee enough GPU memory or that every inference library call will succeed. Optional features can require setup while direct recognition works.

Open **Local storage and cache** and select **Measure local storage** to inspect managed job sizes, generated cache, model directories and free drive space. Measurement is on demand. Python/Node environments, external evaluation files and launcher logs are outside these totals. Model entries are read-only; no model-removal action is provided.

**Clear generated cache for [recording]** removes only that job's decoded audio, cropped temporary audio and vocal stems. It preserves original recordings, raw model responses, SQLite records, saved transcripts and translations. Active jobs/translations cannot be cleaned. Linked paths/junctions are excluded. Locked files can leave a partially cleaned cache; the API reports the failure and allows retry. Future processing rebuilds generated audio. Complete job deletion remains a separate existing action.

## API and verification

| Endpoint | Purpose |
|---|---|
| `POST /api/jobs/{id}/resume` | Queue unfinished recognition routes, preserving completed results |
| `POST /api/jobs/{id}/translation/resume` | Resume the saved translation checkpoint with pipeline/source/target |
| `GET /api/jobs/{id}/waveform` | Temporary decode and amplitude bins; no recognition |
| `GET /api/diagnostics` | Read-only environment checks |
| `GET /api/storage` | On-demand managed storage measurement |
| `POST /api/jobs/{id}/cleanup-cache` | Remove only known generated cache paths for one stopped job |

Backend tests cover route preservation, edited-result preservation, queue rollback, changed originals, translation checkpoints, service restart, cache scope/active guards, external-link rejection where symlink creation is permitted, diagnostics without ASR and real FFmpeg waveform decoding. `scripts/reliability_browser_smoke.py` creates its own silence fixture, checks history and saved-state behavior, waveform seeking, environment UI, selective cleanup, original/text preservation, desktop/mobile overflow and axe WCAG A/AA. It deletes only its own job. Screenshots/reports remain ignored in `artifacts/browser-reliability`.
