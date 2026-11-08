# Evaluate complete, real recordings

The current short-clip development results do not establish full-song accuracy.
Do not change default models or claim improved recognition from UI changes.

The [open-song pilot](OPEN_SONG_PILOT.md) adds three complete English CC BY songs
with local source/license evidence and a pending review queue. Its six inference
checks establish execution only; reference review and representative coverage
remain incomplete. These files are separate from the unfilled collection template.

`evaluation/real-song-collection.csv` contains 28 unfilled collection slots:
seven languages, two independent groups per language, in development and final.
Slots are a collection plan, not recordings or reviewed evidence. A complete
benchmark must also pass the existing condition-coverage audit.

## Collect and annotate

Copy the CSV into a local working directory. Fill each row after obtaining
permission for both recording and reference text. Use:

- `audio_path`: PCM WAV, relative to the collection CSV, at most ten minutes.
- `reference_path`: a UTF-8 text file containing exactly the words sung,
  including repetitions. An empty file is appropriate only for a genuine
  no-lyrics negative control.
- `reference_source` and `permissions`: specific provenance and permission
  records, not a generic assertion that public access implies permission.
- `group_id`: a unique song/performance/singer-session group. Keep all related
  excerpts and performances in the same split.
- Six condition columns: explicitly `true` or `false`, based on listening.

Include complete songs, prominent accompaniment, duets/backing vocals, repeated
refrains, degraded recordings and language switching. Aim for at least two
independent reviewed groups for each condition in each split. Add rows as
needed; the 28 slots are a starting plan. Do not mark every condition true to
satisfy coverage. Previously inspected or tuned-on recordings stay in development.

From the repository root, prepare a new versioned manifest:

First check the complete sheet without importing recordings:

```powershell
.\.venv311\Scripts\python.exe lyriclens-app/scripts/prepare_real_song_benchmark.py COLLECTION.csv --check --report COLLECTION-CHECK.json
```

The check lists problems for every row, including missing fields, unavailable or
invalid audio/reference files, duplicate IDs, and groups or identical audio shared
between splits. It also counts independent groups by language and condition in
each split and lists coverage gaps (two groups by default; change with
`--minimum-groups`). JSON reports contain no reference lyrics. Existing report
files are never overwritten. Exit code 1 means the sheet cannot yet be imported;
exit code 0 means it is structurally ready for import, not human-reviewed or
ready for a representative accuracy claim. The original 28-slot template remains
unfilled; its current check is recorded in
[`real-song-collection-check.json`](../evaluation/real-song-collection-check.json).

Once the check passes, prepare the pending-review manifest:

```powershell
.\.venv311\Scripts\python.exe lyriclens-app/scripts/prepare_real_song_benchmark.py COLLECTION.csv PENDING.jsonl
```

The importer validates required fields, WAV duration, language, condition flags,
unique IDs and development/final separation by audio hash and group. Existing
output files are never overwritten. All references remain pending human review.

From `lyriclens-app/backend`, using the same Python environment:

```powershell
python -m lyriclens.benchmark prepare PENDING.jsonl REVIEW.json
python -m lyriclens.benchmark status REVIEW.json
```

The existing review preparer intentionally clears group IDs. Reapply the
curated `group_id` from the collection sheet in `REVIEW.json`, then have a human
listen, correct the reference and confirm permissions. Follow
[human review](BENCHMARK.md#human-review) to verify each recording and export
a reviewed manifest. No tool here substitutes for that listening step.

```powershell
python -m lyriclens.quality audit REVIEWED.jsonl --require-ready
python -m lyriclens.benchmark plan REVIEWED.jsonl DEVELOPMENT.json --split development --profiles configured large-v3 --language-modes auto manual --device cpu --compute int8 --representative
python -m lyriclens.benchmark run DEVELOPMENT.json
```

Use prepared CUDA settings if available. Keep model configuration and inputs
identical across comparisons. Select settings on development only, then freeze
them before evaluating final. Report CER/WER, failures and processing time by
language and condition, with the number of independent groups. Keep missing
conditions and recognition failures visible.

## Measure the editing experience separately

On the same recordings, record time from first result to saved export, number of
corrected passages, failed exports and timing corrections. Compare the previous
editor with the studio using different recordings or counterbalanced order, so
remembering the lyrics does not favor the second attempt. Record hardware and
operator familiarity. These measurements describe editing effort, not ASR accuracy.
