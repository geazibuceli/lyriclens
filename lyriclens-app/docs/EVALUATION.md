# Reproducible singing evaluation

For the review queue, human attestations, split-leakage checks, frozen model protocols and automated paired comparisons, use [BENCHMARK.md](BENCHMARK.md). The new runner requires reviewed references; legacy diagnostics below remain available separately.

A representative seven-language singing benchmark remains **not evaluated**. A tiny natural-singing development comparison now covers six independently annotated languages; Japanese has execution diagnostics without a checked orthographic reference. See [SINGING.md](SINGING.md) for measured results, sources and restrictions. Separately, one licensed FLEURS speech clip per target language was run with both real pipelines, in automatic and manual modes. A public-domain English singing clip was exercised through the complete browser workflow without assigning WER/CER because no human-verified reference was supplied. Mocked Unicode tests are software tests, not model quality tests. Speech diagnostics must never be reported as singing accuracy.

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

Normalization: Unicode NFC, Unicode casefold, punctuation replaced by spaces, whitespace collapsed. Keep accents, diacritics, script distinctions and repeated chorus lines. No Chinese script conversion, transliteration, translation, deduplication or linguistic “cleanup.” Report raw and normalized texts together. CER removes whitespace and computes Unicode-codepoint Levenshtein distance. It does not claim grapheme-cluster equivalence. Japanese and Mandarin receive CER; WER is null because no validated lexical tokenizer is configured. For the other languages WER uses Unicode whitespace tokens; Korean WER is particularly spacing-sensitive. Punctuation replacement can affect segmentation and is part of the published protocol. If needed, add a versioned tokenizer and report its exact configuration separately.

Empty reference + empty hypothesis: zero error. Empty reference + nonempty hypothesis: CER/WER undefined (`null`), with explicit insertion count. Such cases must be counted and discussed, not discarded. Micro CER includes insertion errors in its numerator when the group also has nonempty references; inspect empty-reference cases separately. A completely empty dataset is “not evaluated.”

Runtime is wall-clock end-to-end seconds per pipeline, including decode/separation and first lazy model load. `seconds / reference_duration` is real-time factor. First-run load cost and filesystem/cache state must be disclosed. The runner preserves model and environment provenance. Peak memory is sampled process-tree RSS at 50 ms when `psutil` is installed (`pip install -e './backend[evaluation]'`); this can miss short-lived peaks and double-count shared pages, and is **not GPU VRAM**. It includes the reused ASR model retained from earlier runs. For independent cold-start comparisons use separate invocations/processes. Record hardware/OS, installed packages, warm/cold conditions, and sample interval alongside published results. VRAM requires separate NVIDIA tooling; no VRAM value is invented.

Report for each language: number of clips, conditions, failures, WER where applicable, CER, detection eligibility/accuracy, timings, memory method and failure reasons. Absent data stays “not evaluated.” The supplied diagnostic values are in the per-clip JSON reports. They use a tiny sample and shared development hardware, not an isolated performance benchmark. The first separator call includes process/model initialization; later calls reuse that process. Summed RSS can include retained child models during the other pipeline, so treat it as process-tree memory, not model-exclusive allocation.

Real negative controls exposed hallucinated output on digital silence and pure tone, and a zero-variance Demucs failure. The pre-fix report is preserved in `control-results.before-silence-guard.json`. The app now detects only exact all-zero decoded PCM, skips both models with an explicit signal-control record, and returns no words without estimating a language. This does not remove near-silent singing or pretend to detect all instrumental audio. Pure-tone hallucinations remain visible in current results. Do not hide them, score them as success, or interpret fluent text as accuracy.
