# Openly licensed complete-song pilot

Three complete English songs from Josh Woodward's *The Wake* were downloaded on
2026-11-08 from the artist's own site. Each recording page declares
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and supplies a vocal MP3
and publisher lyrics. The [artist's FAQ](https://www.joshwoodward.com/faq) also
declares that license for his original music. This is attributed licensed music;
it is not a public-domain or CC0 collection.

| Recording and publisher source | Decoded duration |
|---|---:|
| [I Will Not Let You Let Me Down](https://www.joshwoodward.com/song/IWillNotLetYouLetMeDown) | 181.89 s |
| [This Is Everything](https://www.joshwoodward.com/song/ThisIsEverything) | 206.72 s |
| [Hollow Grove](https://www.joshwoodward.com/song/HollowGrove) | 234.96 s |

Credit each recording to Josh Woodward, link its source and CC BY 4.0, and note
changes. The local `ATTRIBUTION.txt` provides credits. Complete MP3s were decoded
to mono PCM16 WAV at 16 kHz without trimming or removing silence. Publisher lyric
line endings and surrounding whitespace were normalized. Original audio, lyrics,
HTML evidence, file hashes and retrieval timestamps are retained under the ignored
`.runtime/open-song-pilot-v1/` directory, separate from the MIT application source.

## Current evidence and limitations

Small and Large-v3 each completed direct-audio inference on all three full songs
using prepared local models, manual English selection and CUDA/float16. All six
responses had valid segment timestamp bounds. See the
[text-free execution report](../evaluation/open-song-pilot-smoke.json) for exact
settings, revisions, timings and segment counts. Timings include cold loading on
the first song and reuse afterward; they are not controlled speed comparisons.

This is an execution check, not a lyric-accuracy result. The published lyrics use
abbreviations such as `Chorus`; they must be expanded and corrected by listening
before CER/WER is meaningful. No accuracy scores or human approvals were generated.
Other condition labels and language switching also need listening confirmation.
The three songs are conservatively grouped together by artist/album session, all
in development. There is one independent group, one language and no final set.
This does not satisfy representative benchmark coverage or authorize training.
Model defaults remain unchanged.

## Reproduce preparation and execution

From the repository root, with application dependencies and FFmpeg installed:

```powershell
.\.venv311\Scripts\python.exe lyriclens-app/scripts/prepare_open_song_pilot.py .runtime/open-song-pilot-v2
.\.venv311\Scripts\python.exe lyriclens-app/scripts/run_full_song_smoke.py .runtime/open-song-pilot-v2/pending-manifest.jsonl .runtime/open-song-pilot-v2/inference --device cuda --compute float16
```

Preparation explicitly accesses the network and fails if the source license,
identity, lyrics or original vocal link is unavailable or changed. Execution uses
prepared local checkpoints and downloads no models. Use `--device cpu --compute
int8` on CPU. Both scripts require a new output directory and preserve prior work.
`run_full_song_smoke.py` writes raw transcriptions locally and a summary without
lyrics; a failed inference is recorded, remaining runs continue, and the command
exits with code 1 if any run failed. No CER/WER is computed.

## Finish reference review

The prepared `review.json` retains the curated group and has every approval set
to pending. A human reviewer should listen to each original MP3, edit that queue's
`reference` to match every performed repetition, check text permission and confirm
the listening-condition labels. Review the queue rather than just its separate
publisher lyric files. Do not derive ground truth from model transcriptions.

After that listening step, use the existing
[human-review commands](BENCHMARK.md#human-review) to verify each recording and
export a new reviewed manifest. Keep all three in development. Only then run the
reviewed evaluation workflow; a representative comparison additionally requires
more independent artists/sessions, languages, conditions and an untouched final
set as described in the [collection guide](REAL_SONG_COLLECTION.md).
