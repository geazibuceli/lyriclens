# Additional singers and pending pronunciation review

The development pilot now contains five recordings from three credited singers:
the three Josh Woodward tracks, plus two additional performers collected on
2026-11-08. This expands singer diversity; it is not verified accent coverage.
No accent was inferred from a performer's name, country or profile location.

| Recording | Credited singer | Source recording license | Decoded duration |
|---|---|---|---:|
| [On A Silent Night](https://ccmixter.org/files/Javolenus/40172) | Javolenus | CC BY-NC 3.0 | 259.37 s |
| [Where You Are Now](https://ccmixter.org/files/unreal_dm/30304), remix by unreal_dm | Rhiannon Delpero (SizzleFly), credited through Ascension/WolfFly | CC BY-NC 3.0 | 179.93 s |

Javolenus supplies his lyrics in the recording description. The Rhiannon remix
uses the vocal/lyric source published by
[Ascension](https://ccmixter.org/files/ascension/27734), declared CC BY 3.0. The
recording-specific licenses were checked separately from the ccMixter site footer.
The [source inventory](../evaluation/multi-singer-sources.json) records credits,
source URLs, evidence hashes and candidate exclusions.

The new audio and text are for local noncommercial research, separate from the
MIT application code. They are not approved for training or bundled in Git.
Original MP3s, full decoded WAVs, publisher text, raw HTML and credits are stored
under `.runtime/multi-singer-pilot-v2/`. Complete source recordings were decoded to
mono PCM16 at 16 kHz without cuts or silence removal. Publisher lyric markup was
stripped and line whitespace normalized; no model transcription became a reference.
Legacy Windows-1252 punctuation was decoded explicitly where UTF-8 decoding failed.

## Paired execution results

Small and Large-v3 completed all **eight runs** across original audio and isolated
vocals. HTDemucs separation ran on CPU once per recording, with the same hashed
vocal WAV reused across models; recognition used CUDA/float16 and manual English.
The [paired report](../evaluation/multi-singer-direct-vocals-comparison.json)
contains no lyrics or CER/WER scores.

| Song / model | Adjacent duplicate passages, original / vocals | Passages over 20 seconds, original / vocals |
|---|---:|---:|
| On A Silent Night / Small | 0 / 0 | 2 / 4 |
| Where You Are Now / Small | 1 / 0 | 0 / 1 |
| On A Silent Night / Large-v3 | 0 / 0 | 0 / 0 |
| Where You Are Now / Large-v3 | 1 / 0 | 0 / 0 |

These are review prompts. Repetition may be a real refrain, long passages may
contain correct words, and routes can segment the same material differently.
They do not establish which route has better word accuracy. Combined with the
[first pilot](OPEN_SONG_PILOT.md), there are 20 executions on five recordings,
three conservative singer/session groups, one language and no final set.
Model and route defaults remain unchanged.

## Complete the listening review

All references remain pending. The local `review.json` preserves each credited
singer and group; `accent.label` is null and its status is pending. Listen to each
recording, correct the queue's reference to the words actually sung (including
refrains), and confirm the correspondence between remix and source lyric versions.
Check permission and listening-condition labels before using the existing
[benchmark verification/export workflow](BENCHMARK.md#human-review).

`pronunciation-review.csv` starts with one empty row per recording. Add one row
per difficult passage: start/end seconds, publisher wording, performed words,
error type, pronunciation notes and reviewer identity. Useful categories include
word substitution, omission, vowel elongation, joined syllables, backing-vocal
overlap and uncertain wording. Leave uncertain words or accent labels unresolved;
do not fill them using ASR guesses or nationality. Only verified references should
be used to measure word accuracy. No human listening or accent verification has
been certified automatically.

## Reproduce

### Local listening worksheet

The existing recordings and paired responses are assembled in
`.runtime/listening-review-v1/review.html`: five recordings, 73 listening windows,
original/isolated playback, speed controls, publisher reference drafts and four
ASR columns. Open the HTML file in a desktop browser. Select an audio route and
click a window's **Listen** button, then record the words sung or uncertain
pronunciation in that row. Publisher text can be edited separately after listening.

Use **Download review draft** before closing or reloading. Edits are not saved
automatically and are not applied to benchmark references. Downloaded drafts
remain `human_review_verified: false`; actual listening and permission review are
still required before benchmark verification. Rows are 15-second windows, and ASR
passages spanning a boundary appear in adjacent rows rather than being word-aligned.

```powershell
.\.venv311\Scripts\python.exe lyriclens-app/scripts/prepare_listening_review.py .runtime/listening-review-v2 --dataset .runtime/open-song-pilot-v1/pending-manifest.jsonl .runtime/open-song-pilot-v1/direct-vocals-cuda-v1 --dataset .runtime/multi-singer-pilot-v2/pending-manifest.jsonl .runtime/multi-singer-pilot-v2/direct-vocals-v1
```

The generator verifies original-audio hashes, requires all four saved responses
and isolated WAVs, escapes source text in the HTML, and refuses existing output
directories. No network requests, model execution or approval commands are used.

### Source collection and inference

From the repository root, with the existing local models and FFmpeg prepared:

```powershell
.\.venv311\Scripts\python.exe lyriclens-app/scripts/prepare_multi_singer_pilot.py .runtime/multi-singer-pilot-v3
.\.venv311\Scripts\python.exe lyriclens-app/scripts/run_full_song_smoke.py .runtime/multi-singer-pilot-v3/pending-manifest.jsonl .runtime/multi-singer-pilot-v3/direct-vocals --device cuda --compute float16 --pipelines direct vocals --separation-device cpu
.\.venv311\Scripts\python.exe lyriclens-app/scripts/summarize_full_song_routes.py .runtime/multi-singer-pilot-v3/direct-vocals/summary.json .runtime/multi-singer-pilot-v3/direct-vocals/comparison.json
```

Preparation explicitly downloads public files with the source-page referrer
required by the server. License/title/origin checks fail before downloading an
unexpected recording. Outputs must be new paths, preserving previous review work.
The recognizer downloads no models. On CPU, select `--device cpu --compute int8`.
