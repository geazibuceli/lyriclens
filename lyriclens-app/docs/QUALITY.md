# Recognition quality plan

## Current evidence

The scored development corpus has 12 clips in six languages, mostly solo singing. References are pending human review. The coverage audit therefore reports zero reviewed groups. Japanese has execution checks but no reviewed orthographic reference. Full songs, real accompaniment, duets and an independent final set still need collection.

## Collect a representative set

Use original recordings or material with documented audio/text permission. A fluent reviewer checks the words actually sung. Keep related songs, performances and singer sessions in one `group_id`, and keep development and final groups separate.

The initial collection target is at least **two independent reviewed groups per language and per condition in each split**. This is a coverage threshold; a statistically useful benchmark may need more recordings. Include Korean, Japanese, Mandarin, English, Spanish, Portuguese and French, and these conditions:

| Manifest condition | Recording to collect |
|---|---|
| `full_song` | A complete song within the application's 10-minute limit |
| `accompaniment` | Singing with prominent instruments or backing music |
| `overlapping_vocals` | Duets, backing vocals or overlapping singers |
| `repetition` | Refrains and repeated lines |
| `degraded_recording` | Noise, reverberation, clipping or low-bandwidth capture |
| `language_switching` | Words sung in more than one language; set the top-level field too |

Use structured `conditions`, for example:

```json
{"full_song":true,"accompaniment":true,"overlapping_vocals":false,"repetition":true,"degraded_recording":false}
```

Prepare and review references with [BENCHMARK.md](BENCHMARK.md). Keep provisional lyrics pending; an empty reference represents audio with no sung words. After creating a manifest, inspect coverage:

```powershell
python -m lyriclens.quality audit MANIFEST.jsonl --output .runtime/coverage-v1.json
python -m lyriclens.quality audit MANIFEST.jsonl --require-ready
```

The second command exits with code 1 while coverage or split isolation is incomplete. Coverage counts reviewed original groups, with synthetic fixtures listed separately. The audit validates audio hashes and current review fingerprints.

## Repeat model comparisons

Freeze a reviewed development protocol, evaluate the same clips/settings across models and routes, and inspect failures and CER/WER by language. Pick settings using development data, then evaluate once on the untouched final set. See [the benchmark workflow](BENCHMARK.md).

Pass `--representative` to `lyriclens.benchmark plan` to enforce the coverage threshold before creating a protocol. `--minimum-groups` freezes the required count (default 2). The runner checks that requirement again before inference. Diagnostic protocols can still be created without this flag.

Use `python -m lyriclens.quality report BASELINE.json CANDIDATE.json --output .runtime/condition-comparison.json` for paired results by recording condition. A recording with multiple condition labels contributes to each relevant group; failures remain in attempted counts.

## Synthetic robustness checks

`lyriclens.quality stress` derives reproducible development fixtures from local recordings:

- Target 10 dB additive noise with a fixed seed.
- Telephone-band filtering at 300–3400 Hz.
- A 60 ms echo.
- Three repetitions of the recording and reference.
- Repetitions reaching at least two minutes.

Derived references are inherited and pending review. Repeated audio tests duration and repetition; it does not count as a complete song, a duet or real accompaniment. All variants stay in development with their source group and hashes.

With the existing local research corpus and models prepared:

```powershell
python -m lyriclens.quality stress .runtime/singing-research/manifest.jsonl .runtime/stress-v2 --ids vocadito-6 vocadito-13 vocadito-2
python -m lyriclens.evaluate .runtime/stress-v2/manifest.jsonl --split development --manual-language --model-profile configured --pipelines direct --device cuda --compute float16 --output .runtime/stress-v2/small.json
python -m lyriclens.evaluate .runtime/stress-v2/manifest.jsonl --split development --manual-language --model-profile large-v3 --pipelines direct --device cuda --compute float16 --output .runtime/stress-v2/large.json
python -m lyriclens.quality report .runtime/stress-v2/small.json .runtime/stress-v2/large.json --output .runtime/stress-v2/summary.json
```

Use new output paths for each run. For CPU, pass `--device cpu --compute int8`. Omit `--pipelines direct` to include the prepared vocal-separation route.

## Robustness diagnostic, 2026-10-20

Both profiles completed all **18 direct-route cases**: three vocadito sources (English, French and Spanish), each with an original-input control and five transformations. Reference text came from the existing provisional corpus annotations. These are development diagnostics, not additional independent recordings.

| Condition | Small micro CER | Large-v3 micro CER |
|---|---:|---:|
| Original-input controls | 3.87% | 2.49% |
| Additive noise | 56.08% | 9.94% |
| Telephone filter | 4.14% | 2.76% |
| Echo | 3.04% | 2.76% |
| Three repetitions | 17.50% | 2.76% |
| Repeated audio, at least two minutes | 11.72% | 18.77% |

Each row compares the same three completed cases. Large-v3 was more robust to the added noise, but had higher error on the long repeated audio. These mixed results support keeping model choice available and collecting real long-form examples before changing defaults.

The [aggregate report](../evaluation/robustness-20261020.json) contains settings, paired denominators, failure counts and recognition timings. Audio and full transcripts stay in ignored `.runtime/quality-stress-v1`. Timings include initialization and model reuse and should not be treated as a controlled speed comparison.
