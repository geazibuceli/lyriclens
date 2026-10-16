# Singing development diagnostic

Measured locally on 2026-10-15, using natural human singing, not speech or synthesized songs. Small and Large-v3 processed identical files with manual language, CUDA float16, beam 5, temperature 0, VAD off and previous-text conditioning off. The experimental Large-v3 profile additionally enables native word alignment; Small keeps its original segment decoding. This compares complete profiles, not model size in isolation. Demucs htdemucs used CPU, shifts 0 and overlap 0.25. Neither references nor recognized text are used as prompts. The application never looks up lyrics.

## Results

Twelve independently annotated clips cover six languages. These are tiny **development** samples of primarily solo unaccompanied singing, not a representative benchmark of commercial music, accompaniment, artists, dialects or recording conditions. There is no held-out final singing score. Published corpus references were not manually re-audited by a native-speaking panel. Potential pretrained-model exposure is unknown.

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

Japanese has a separate natural-singing execution diagnostic, **without CER/WER**: the accessible official source supplies phoneme labels rather than an independently checked orthographic transcript. Large-v3 with native alignment completed both clips in both pipelines (4/4), versus 0/4 before alignment. Small completed 2/4. These are execution and timestamp-validity results, not word-accuracy scores. Across all seven languages, the experimental profile completed 28/28 runs on 14 clips. Do not compare kana/kanji ASR to a fabricated transcript or claim seven-language singing accuracy. The PJS official downloads returned a quota-exceeded HTML page and were not used as audio.

See [text-free per-clip results](../evaluation/singing-model-comparison.json) and [Japanese execution results](../evaluation/japanese-singing-smoke.json). Timing includes decoding, inference and, for vocals, separation; cold initialization and model reuse affect it. Sampled process-tree RSS excludes VRAM and is not a hardware minimum. Machine: Windows, RTX 5080 16 GB, Python 3.11.17; all package versions are recorded in the comparison. Default recognition remains Small. Large-v3 is an explicit experimental option, not an automatic replacement or a guarantee.

## Further error-reduction experiments

A second development search ran **144 successful recognition executions**: six configurations on the same 12 annotated clips, each through Direct and vocal-assisted input. The current Large-v3 baseline was rerun, with identical error counts to the earlier comparison. Five candidates tested wider beam search, previous-text context, a shorter length penalty, and pitch-preserving tempo factors 1.15/1.30. Original clip hashes and reference-character denominators were verified across comparisons. All raw text stays private.

| Diagnostic | Current profile CER | Candidate CER | Outcome |
|---|---:|---:|---|
| Korean, Direct and vocals, tempo 1.15 | 14.19% | 12.84% | Improvement on two development clips |
| Spanish, Direct, beam 10 with context | 2.53% | 1.27% | Improvement on one development clip |
| Mandarin, Direct, tempo 1.15 | 12.99% | 33.77% | Regression |
| French, vocals, tempo 1.15 | 0.92% | 1.53% | Regression |
| Korean, Direct, beam 10/patience 2 | 14.19% | 20.27% | Regression |

No tested candidate reduced errors without regressions in other language/pipeline groups. English and Portuguese did not improve in this search. Japanese remains unscored; execution success cannot establish lower CER. **Runtime defaults are unchanged.** Do not turn the best result from each tiny group into an automatic per-language rule: this would select settings on the same examples used to report the improvement. A separate recording/song/singer validation set is needed before adopting such presets. There is no evidence here that one adjustment lowers error in all seven languages, or on ten-minute recordings.

The metrics-only [decoding report](../evaluation/singing-decoding-experiments.json), [tempo report](../evaluation/singing-tempo-experiments.json), and [candidate decision](../evaluation/singing-tuning-decision.json) retain improvements and regressions. The decision checks for any higher CER in an evaluated language/pipeline group; it is a conservative development screening rule, not statistical validation.

## Sources and permissions

- [vocadito v3](https://zenodo.org/records/5578807), Bittner, Pasalo, Bosch, Meseguer Brocal and Rubinstein (2021), CC-BY-4.0. Trained-musician lyric annotations; English clips 6/10, French 13/23, Spanish 2, Mandarin 35/36. Mandarin uses the supplied character section, not the pinyin section. Original references remain preserved locally.
- [CSD v1.0](https://zenodo.org/records/4785016), Choi et al., KAIST, CC-BY-NC-SA-4.0. Supplied Hangul references. Deterministic selection: first two key-a Korean clips numbered 002–015 within the 60-second application limit, resulting in kr007a/kr011a. Selection preceded inference. One singer and plain delivery cannot represent Korean singing generally.
- [CoVox](https://osf.io/cgexn/), Bruder and Larrouy-Maestri (2025), [study and supplemental reference](https://doi.org/10.3758/s13428-025-02664-9). Exact phrases from Supporting Text S1, matched to the NR/AL stimulus codes, not from model output. Clips S07_NR_pop_L, S09_NR_pop_L and S05_AL_cl_L; Brazilian Portuguese, pop and operatic delivery. OSF metadata declares CC-BY-NC-ND-4.0 while the recordings README states CC-BY-NC-SA: this discrepancy is retained, and media, references and derived transcripts are not redistributed. Local noncommercial diagnostic only; no training.
- [Official HTS NIT-SONG070 F001 archive](https://hts.sp.nitech.ac.jp/archives/2.3/HTS-demo_NIT-SONG070-F001.tar.bz2), data/COPYING, CC-BY-3.0, Nagoya Institute of Technology Department of Computer Science (2004–2015). Natural Japanese singing, files 003/004. Original 48kHz little-endian PCM16 is wrapped in WAV without changing samples, then decoded by the application. Source phoneme labels are not an orthographic quality reference.

All downloaded research audio, full references, raw model text and full reports stay under ignored repository `.runtime/singing-research`. The source-code MIT license does not relicense datasets. Only numeric results and provenance are included in the public comparison. GTSinger was not used because its separate access terms require additional legal representations.

## Reproduce

Further decoding experiments can be run separately without changing runtime defaults:

```powershell
.\.venv311\Scripts\python.exe lyriclens-app/scripts/tune_singing.py
.\.venv311\Scripts\python.exe lyriclens-app/scripts/tune_singing.py --variants tempo-115 tempo-130 --reuse-derived --report-name singing-tempo-experiments
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
