# Reproducible singing evaluation

Use [BENCHMARK.md](BENCHMARK.md) for reference review, split checks, frozen model protocols and paired comparisons. The commands below reproduce the development diagnostics.

Singing results cover a small six-language development sample; Japanese has execution checks but lacks a reviewed orthographic reference. A representative seven-language benchmark is still pending. See [SINGING.md](SINGING.md) for results and sources. Separate checks cover FLEURS speech in automatic/manual modes and a public-domain English singing clip through the browser.

## Reproduce the supplied diagnostics

Install `pip install -e './backend[fixtures,evaluation,inference,separation,tools]'`. From this project directory:

```powershell
python scripts/prepare_speech_smoke.py
python -m lyriclens.evaluate evaluation/speech-smoke.jsonl --split development --output evaluation/speech-results.json
python -m lyriclens.evaluate evaluation/speech-smoke.jsonl --split development --manual-language --output evaluation/manual-speech-results.json
python scripts/prepare_singing_smoke.py
python scripts/prepare_controls.py
python -m lyriclens.evaluate evaluation/controls.jsonl --split development --output evaluation/control-results.json
```

FLEURS audio and references are [CC-BY-4.0](https://huggingface.co/datasets/google/fleurs), attributed to Conneau et al. (2022), Google. The script selects row 0 of each language's test subset, assigned to **application development**, not final evaluation. Parquet row-group access may transfer hundreds of MB per language; only selected audio clips are retained. Manifests retain exact audio hashes and source/permission references. Downloaded audio is ignored by Git. Do not silently change the dataset/model/settings when comparing recorded results.

The singing fixture is [Celestianpower's 2006 recording](https://commons.wikimedia.org/wiki/File:Mary_Had_a_Little_Lamb.ogg), dedicated to the public domain by its creator, with traditional public-domain composition/text. Original Ogg is retained locally and converted to a separately named WAV. `singing-smoke-source.json` records its source revision, hashes and transformations. No reference is constructed from recognized output or song memory. Negative controls are original deterministic silence/sine signals under CC0, with empty references.

Build `clips.jsonl` with one object per line following `evaluation/manifest.schema.json`. Use original recordings or appropriately licensed audio with permission to use the reference text. Never scrape or redistribute commercial lyrics. Store paths relative to the manifest, and compute SHA-256 from the exact original file. Keep language-balanced development and final splits; avoid putting excerpts from the same recording/song/singer session into both. Document singer, genre, vocal overlap, accompaniment, effects, and noise in `conditions`. Empty references explicitly represent silent/instrumental clips, not missing annotation. References and permission sources must be human-verified. Record mixed-language clips as such; whole-clip language accuracy excludes them and empty references.

```powershell
# Prepare both model caches first. No inference API or runtime downloads.
.\.venv\Scripts\python.exe -m lyriclens.evaluate evaluation/clips.jsonl --split development --output development-results.json
.\.venv\Scripts\python.exe -m lyriclens.evaluate evaluation/clips.jsonl --split final --output final-results.json
```

Default evaluates automatic detection; `--manual-language` runs the manifest language as an instruction and does not score detection. Choose settings using development data only, freeze model/revision/settings, and then run final once. Both pipelines process the same hashed original clip independently, including decoding in each timing. Missing separation preparation is a recorded failure, never a Direct substitute. Failed clips remain in per-clip output and failure rate denominators. Reports include raw output and normalized texts, per-clip CER/WER and timing/real-time factor, followed by per-language/pipeline failure rate, micro CER and eligible language-detection accuracy. Inspect per-clip data before comparing aggregates. Do not compare metrics from different clip sets as a pipeline improvement.

Normalization uses Unicode NFC and casefold, replaces punctuation with spaces and collapses whitespace. Accents, script distinctions and repeated lines are retained. Report raw and normalized text together. CER removes whitespace and computes Levenshtein distance over Unicode code points; a grapheme can contain several code points. Japanese and Mandarin use CER, with WER set to null until a lexical tokenizer is configured. Other languages use whitespace-token WER, which is especially sensitive to Korean spacing. Record any tokenizer changes as a separate protocol version.

Empty reference + empty hypothesis: zero error. Empty reference + nonempty hypothesis: CER/WER undefined (`null`), with explicit insertion count. Such cases must be counted and discussed, not discarded. Micro CER includes insertion errors in its numerator when the group also has nonempty references; inspect empty-reference cases separately. A completely empty dataset is “not evaluated.”

Runtime is end-to-end seconds per pipeline, including decoding, separation and initial model loading. Real-time factor is `seconds / reference_duration`. Record hardware, OS, package versions and warm/cold cache conditions alongside results. With `psutil` installed, memory is sampled process-tree RSS every 50 ms, including reused models. Sampling can miss short peaks and double-count shared pages. Use separate processes for cold-start comparisons and NVIDIA tooling to measure VRAM separately.

Report for each language: number of clips, conditions, failures, WER where applicable, CER, detection eligibility/accuracy, timings, memory method and failure reasons. Absent data stays “not evaluated.” The supplied diagnostic values are in the per-clip JSON reports. They use a tiny sample and shared development hardware, not an isolated performance benchmark. The first separator call includes process/model initialization; later calls reuse that process. Summed RSS can include retained child models during the other pipeline, so treat it as process-tree memory, not model-exclusive allocation.

Silence and pure-tone controls exposed hallucinated words and a zero-variance Demucs failure. Exact all-zero decoded PCM now bypasses recognition and separation, returning an empty transcript with a signal-control record. Near-silent singing is processed normally. Pure-tone hallucinations remain in the results. The earlier report is preserved as `control-results.before-silence-guard.json`.
