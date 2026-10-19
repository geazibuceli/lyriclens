# Review tools, recovery and workspace maintenance

## Undo, redo and keyboard review

Each transcript editor has **Undo transcript edit** and **Redo transcript edit** controls. They cover text, language labels, timings, segment removal and additions. Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y redoes, and Ctrl/Cmd+Enter saves. Saving preserves the open editor history; undoing a saved edit changes the draft until you save again. Exports continue to use saved text.

Undo history belongs to the open editor and resets when you reload or switch jobs. It stores up to 50 changes and two million serialized characters in each direction, with fewer steps for large transcripts. Use browser drafts to restore unsaved content after reloading. See [EDITING.md](EDITING.md) for drafts, search, exports and backups. Translation fields have their own save controls.

Choose **Load audio waveform** below the player to display up to 1200 amplitude peaks from the recording. Use **Waveform position seconds** or the arrow keys to seek. Seeking stops segment repeat. Loading the waveform requires FFmpeg and the original audio; word boundaries are reviewed in the transcript.

Review suggestions highlight passages longer than 20 seconds and repeated text patterns. Listen before editing: choruses often repeat. Use the direct/vocal comparison to check disagreements between the two results.

## Resume stopped work

The server marks queued/processing jobs and translations **interrupted** on startup. It does not silently restart expensive work. Open the job and choose **Resume unfinished transcription**. Completed routes, raw output, saved edits and translations are retained. Only unfinished/failed recognition routes run again, with the same original, model revision and job configuration. An unfinished recognition route starts from the beginning; there is no partial decoder or in-model checkpoint. A completed job with a failed second route can also retry that route.

Resume requires the original recording to exist and match its stored SHA-256. Active work and full queues are rejected; a rejected submission restores the previous saved state. Model/dependency failures remain visible. Region and multilingual instructions remain part of the saved job.

Translation saves progress after each segment. **Resume translation from saved segments** continues from that point using the saved source and languages. Changed source text or labels require a new translation. Older checkpoints without saved segments restart from the beginning; a crash during a segment repeats that segment.

## Progress

Active recognition shows the processing stage, elapsed time and stage history. Translation also shows completed segments and a progress bar. Cancellation takes effect when the current operation returns.

## Environment and storage

**Environment checks** runs on workspace load and can be refreshed. It checks FFmpeg, dependencies, prepared models and device/compute support. The launcher prints setup notices too. GPU memory and runtime inference should be checked with an actual recording; optional features may need separate setup.

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
