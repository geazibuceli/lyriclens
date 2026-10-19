# Singing development diagnostic

Measured on 2026-10-15 using natural singing. Small and Large-v3 processed identical files with manual language, CUDA float16, beam 5, temperature 0, VAD off and previous-text conditioning off. Large-v3 also used native word alignment, so the comparison measures complete profiles. Demucs htdemucs used CPU, shifts 0 and overlap 0.25. Recognition received audio and language settings only.

## Results

The development set contains 12 corpus-annotated clips in six languages, mostly solo unaccompanied singing. References are pending human review. An independent final set and broader coverage of accompaniment, artists, dialects and recording conditions are still needed. Potential pretrained-model exposure is unknown.

Vocal-assisted micro CER below aggregates reference characters over successful clips. Lower is better. Failure counts are essential: scores with different successful-clip sets cannot establish a paired improvement.

| Language | Clips | Small CER | Large-v3 CER | Small failures | Large-v3 failures |
|---|---:|---:|---:|---:|---:|
| Korean | 2 | 20.95% | 14.19% | 0 | 0 |
| Mandarin | 2 | 40.74%* | 12.99% | 1 | 0 |
| English | 2 | 7.37% | 2.11% | 0 | 0 |
| Spanish | 1 | 3.80% | 3.80% | 0 | 0 |
| Portuguese | 3 | 3.77% | 1.89% | 0 | 0 |
| French | 2 | 3.98% | 0.92% | 0 | 0 |

*Small's Mandarin score includes only one successful clip; Large-v3 includes both. On their shared completed vocal-assisted clip, CER fell from 40.74% to 11.11%. Large-v3 with native alignment completed **all 24 runs** across both pipelines; Small completed 22 (one Mandarin clip failed in both pipelines). Before alignment, Large-v3 also had two Direct failures: its segment ends extended beyond an English and a Korean clip. The earlier metrics-only report is preserved as singing-model-comparison.before-alignment.json. Native alignment removed these failures in this diagnostic without manually clipping segment ends. Raw output is retained privately. Separation does not consistently improve either model on solo voice. No timing-accuracy score is available without manually aligned ground truth.

Japanese has execution checks on two natural-singing clips. The source provides phoneme labels, so CER/WER remains unscored. Large-v3 with alignment completed 4/4 runs, compared with 0/4 before alignment; Small completed 2/4. Across all seven languages, Large-v3 completed 28/28 runs on 14 clips. These counts measure successful execution and valid timing.

See [per-clip results](../evaluation/singing-model-comparison.json) and [Japanese execution results](../evaluation/japanese-singing-smoke.json). Timing includes decoding, recognition and optional separation, with cold loading and model reuse. Memory is sampled process-tree RSS, excluding VRAM. Machine: Windows, RTX 5080 16 GB, Python 3.11.17; package versions are recorded in the report. Small remains the default; Large-v3 is an experimental option.

## Four-way rerun on 2026-10-19

The current evaluator reran all **48 combinations** (12 clips, two profiles, two routes) with manual language and CUDA/float16, using the same local recordings and corpus references. It now matches the application's stable ordering of valid model segments, preserves the emitted raw order and still rejects out-of-bounds timestamps. Small completed 22/24 runs; Large-v3 completed 24/24. Small's two failures were the same Mandarin clip with out-of-bounds timestamps.

The [four-way summary](../evaluation/singing-four-way-20261019.json) compares accuracy on **11 clips completed by every combination**, with 904 reference characters in each cell. The excluded Mandarin clip still contributes to attempted/failure counts. This shared cohort differs from earlier per-profile successful-clip aggregates above.

| Profile and input | Shared clips | Micro CER | Failures / attempted |
|---|---:|---:|---:|
| Small, original audio | 11 | 8.19% | 1 / 12 |
| Small, separated vocals | 11 | 9.62% | 1 / 12 |
| Large-v3, original audio | 11 | 4.20% | 0 / 12 |
| Large-v3, separated vocals | 11 | 4.31% | 0 / 12 |

Large-v3 on original audio had the lowest aggregate CER in this sample. Separation increased aggregate CER slightly for both profiles on these mostly solo recordings. Accompanied music needs a separate comparison.

The evaluator now records decoding, separation (including decoding its output), and recognition times separately. On the shared cohort, separated routes spent approximately 53 seconds each in separation, compared with approximately 4 seconds (Small) and 8 seconds (Large-v3) in recognition. These are diagnostic stage totals, **not a controlled speed benchmark**: initialization and model reuse differ, and backend verification tests ran during part of the Large-v3 pass. Recognition totals include initial model loading; RSS excludes VRAM.

Full transcripts and audio stay under `.runtime/singing-comparison-20261019` and `.runtime/singing-research`. The repository contains the aggregate summary. See the [four-way workflow](BENCHMARK.md#four-way-quality-and-timing-summary) for reproduction and reference review.

## Further error-reduction experiments

A second development search ran **144 successful recognition executions**: six configurations on the same 12 annotated clips, each through Direct and vocal-assisted input. The current Large-v3 baseline was rerun, with identical error counts to the earlier comparison. Five candidates tested wider beam search, previous-text context, a shorter length penalty, and pitch-preserving tempo factors 1.15/1.30. Original clip hashes and reference-character denominators were verified across comparisons. All raw text stays private.

| Diagnostic | Current profile CER | Candidate CER | Outcome |
|---|---:|---:|---|
| Korean, Direct and vocals, tempo 1.15 | 14.19% | 12.84% | Improvement on two development clips |
| Spanish, Direct, beam 10 with context | 2.53% | 1.27% | Improvement on one development clip |
| Mandarin, Direct, tempo 1.15 | 12.99% | 33.77% | Regression |
| French, vocals, tempo 1.15 | 0.92% | 1.53% | Regression |
| Korean, Direct, beam 10/patience 2 | 14.19% | 20.27% | Regression |

Every candidate that reduced errors also regressed in another language/route group. English and Portuguese showed no improvement. Keep the current defaults and validate promising settings on separate recordings before adopting a preset.

The [decoding report](../evaluation/singing-decoding-experiments.json), [tempo report](../evaluation/singing-tempo-experiments.json) and [candidate decision](../evaluation/singing-tuning-decision.json) record improvements and regressions. Screening rejects candidates with higher CER in any evaluated language/route group.

## Additional experiments on 2026-10-19

A new search ran **144 recognition attempts** on the same 12 local clips and both cached input routes: 48 Small runs (baseline and native alignment) and 96 Large-v3 runs (baseline, beam 3, length penalty 1.2 and blank suppression disabled). Inputs were checked against the original/derived hashes from the prior experiment. Parameters were fixed before execution. No lyrics or references were supplied to the recognizer. The tested controls are documented in the [upstream transcribe implementation](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py).

| Candidate | Observed result | Application decision |
|---|---|---|
| Small with native alignment | 24/24 completed versus 22/24; one fewer character error on Spanish Direct; no increased CER in any shared successful language/route group | Available as an explicit experimental `aligned` profile; reuses Small weights |
| Large-v3, beam 3 | Korean vocals CER increased from 14.19% to 16.89%; no accuracy improvement elsewhere | Keep the existing beam setting |
| Large-v3, length penalty 1.2 | No character-error change | Keep the existing setting |
| Large-v3, blank suppression disabled | No character-error change | Keep the existing setting |

Small's native alignment recovered the two Mandarin timestamp failures. Recovered runs are reported separately and are **not** counted as an accuracy gain. On the shared Spanish Direct clip, CER changed from 3.80% to 2.53% (three to two errors over 79 reference characters). English, French, Korean, Portuguese and the shared Mandarin clip retained their error counts. Alignment success does not establish timestamp accuracy without manually aligned ground truth. Japanese was not scored in this search, and custom configured models were not tested.

Reports: [Small alignment](../evaluation/singing-small-alignment-20261019.json) and [additional Large-v3 decoding](../evaluation/singing-decoding-extra-20261019.json). Each includes paired screening by language/route, shared reference counts and recovered/lost executions. The gate blocks any language/route regression; an eligible candidate still requires independent reviewed validation before changing defaults. Full research responses stay private. The Small baseline has two failed attempts; the remaining 142 attempts completed. ASR-only timings include cold model initialization and exclude shared preprocessing; they are not an end-to-end speed comparison.

Choose **Whisper Small + alignment (experimental)** in the upload form to use native alignment with the prepared Small weights. The profile keeps raw output and passage settings, and may add processing time. Small without alignment remains the initial setting.

Reproduce with new report names (existing experiment outputs are preserved):

```powershell
.\.venv311\Scripts\python.exe lyriclens-app/scripts/tune_singing.py --variants baseline native-alignment --model-profile configured --reuse-derived --report-name small-alignment-new
.\.venv311\Scripts\python.exe lyriclens-app/scripts/tune_singing.py --variants baseline beam-3 longer keep-blank --reuse-derived --report-name large-decoding-new
```

The cached inputs and prior baseline must already exist; see the preparation commands below. For a named baseline rerun, pass `--cache-baseline` with its private `REPORT_NAME-raw.json` path; otherwise verification reads the original `decoding-experiments/raw-results.json`. Select the new profile in **Recognition model** after restarting the backend and refreshing the interface. It may add processing time; choose Large-v3 separately when comparing lyric quality.

## Automatic timing recovery rerun

Recognition with invalid model timing retries once using native alignment on the same checkpoint and hardware. The raw report retains both responses and effective settings. Valid output returns immediately; invalid aligned output fails validation.

On 2026-10-19, the application adapter reran the original 12 development clips through both routes, plus the two Japanese execution clips through both routes, using Small on CUDA/float16:

| Sample | Previous completed | Current completed | Successful recoveries |
|---|---:|---:|---:|
| Six-language scored development set | 22 / 24 | 24 / 24 | 2 Mandarin runs |
| Japanese execution diagnostic | 2 / 4 | 4 / 4 | 2 Japanese runs |
| Total | 24 / 28 | 28 / 28 | 4 |

All 22 previously successful scored runs retained their CER. Recovered runs have null CER deltas because the earlier run failed. Japanese CER/WER remains unscored pending a reviewed orthographic reference.

The text-free [paired comparison](../evaluation/singing-timing-recovery-20261019.json) records each scored run's before/after state, CER delta and recovery flags. The [Japanese rerun](../evaluation/japanese-timing-recovery-20261019.json) records execution and recovery metadata without lyrics. Both first and final raw responses stay privately under `.runtime/timing-recovery-20261019`. The four recovered runs retain valid model-generated times without manual clipping. Reported timing includes the extra recognition call, so recovery is not a speed optimization.

Reproduce into new filenames/directories:

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.evaluate .runtime/singing-research/manifest.jsonl --split development --manual-language --model-profile configured --device cuda --compute float16 --output .runtime/small-recovery-new.json
.\.venv311\Scripts\python.exe lyriclens-app/scripts/benchmark_japanese_singing.py --profiles configured --output .runtime/japanese-recovery-new.json --raw-directory .runtime/japanese-recovery-new
```

The Japanese runner now uses the application's stable segment ordering, accepts explicit profiles, and refuses existing output/raw-report paths to preserve prior evidence. The official HTS archive must already exist locally; this run downloads nothing.

## Sources and permissions

- [vocadito v3](https://zenodo.org/records/5578807), Bittner, Pasalo, Bosch, Meseguer Brocal and Rubinstein (2021), CC-BY-4.0. Trained-musician lyric annotations; English clips 6/10, French 13/23, Spanish 2, Mandarin 35/36. Mandarin uses the supplied character section, not the pinyin section. Original references remain preserved locally.
- [CSD v1.0](https://zenodo.org/records/4785016), Choi et al., KAIST, CC-BY-NC-SA-4.0. Supplied Hangul references. Deterministic selection: first two key-a Korean clips numbered 002–015 within the 60-second application limit, resulting in kr007a/kr011a. Selection preceded inference. One singer and plain delivery cannot represent Korean singing generally.
- [CoVox](https://osf.io/cgexn/), Bruder and Larrouy-Maestri (2025), [study and supplemental reference](https://doi.org/10.3758/s13428-025-02664-9). Exact phrases from Supporting Text S1, matched to the NR/AL stimulus codes, not from model output. Clips S07_NR_pop_L, S09_NR_pop_L and S05_AL_cl_L; Brazilian Portuguese, pop and operatic delivery. OSF metadata declares CC-BY-NC-ND-4.0 while the recordings README states CC-BY-NC-SA: this discrepancy is retained, and media, references and derived transcripts are not redistributed. Local noncommercial diagnostic only; no training.
- [Official HTS NIT-SONG070 F001 archive](https://hts.sp.nitech.ac.jp/archives/2.3/HTS-demo_NIT-SONG070-F001.tar.bz2), data/COPYING, CC-BY-3.0, Nagoya Institute of Technology Department of Computer Science (2004–2015). Natural Japanese singing, files 003/004. Original 48kHz little-endian PCM16 is wrapped in WAV without changing samples, then decoded by the application. Source phoneme labels are not an orthographic quality reference.

Research audio, reference text and full reports stay under ignored `.runtime/singing-research`. Public reports contain numeric results and source information. Dataset licenses are listed above; the project MIT license covers application code.

## Reproduce

Further decoding experiments can be run separately without changing runtime defaults:

```powershell
.\.venv311\Scripts\python.exe lyriclens-app/scripts/tune_singing.py --report-name singing-decoding-rerun
.\.venv311\Scripts\python.exe lyriclens-app/scripts/tune_singing.py --variants tempo-115 tempo-130 --reuse-derived --cache-baseline .runtime/singing-research/decoding-experiments/singing-decoding-rerun-raw.json --report-name singing-tempo-rerun
```

The first run compares the current Large-v3 profile against beam 10/patience 2, beam 10 with previous-text context, and beam 10 with length penalty 0.8. The second checks tempo 1.15/1.30 with pitch preserved. Cached derived audio is verified against baseline hashes before reuse. Tempo timestamps are mapped back by multiplying by the tempo factor and strictly validated against original duration; raw returned timing is retained. References are never passed to recognition. All variants are development experiments, with no runtime changes selected automatically. ASR-only timing excludes shared audio preparation and is not comparable to the end-to-end timings above.

From the repository root, in the prepared Python 3.11 environment (network only for explicit preparation):

```powershell
.\.venv311\Scripts\python.exe -m lyriclens.models download --profile large-v3
.\.venv311\Scripts\python.exe lyriclens-app/scripts/prepare_singing_research.py
.\.venv311\Scripts\python.exe lyriclens-app/scripts/benchmark_singing.py
# Separately download the official HTS archive above to .runtime/hts-japanese.tar.bz2.
.\.venv311\Scripts\python.exe lyriclens-app/scripts/benchmark_japanese_singing.py
```

Research preparation additionally needs fsspec and aiohttp; inference/evaluation/separation extras and prepared checkpoints are required. GPU inference needs the documented CUDA setup. Research scripts do not run during application requests. Do not redistribute the ignored research directory.
